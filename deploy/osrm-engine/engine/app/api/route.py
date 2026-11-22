from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.schemas import (
    BorderFeesOut,
    BreakdownOutput,
    LegOutput,
    QuoteRequest,
    QuoteResponse,
    RouteOutput,
    TimingOutput,
)
from app.services.border_fees import apply_border_fees_override, calc_border_fees
from app.services.geocoder import bbox_country, country_of   # 🆕 v008：运输范围判定
from app.services.cost_engine import (
    CostResult,
    NoFittingVehicleModel,
    UnknownCargoType,
    UnknownVehicleModel,
    compute_cost_consolidated,
    compute_cost_full_truck,
    compute_vehicle_count,
    vehicle_count_breakdown,
)
from app.services.osrm_client import OSRMClient, OSRMError, RouteResult
from app.services import line_pricing      # 🆕 v020 T-D：逐行车型计价（逐行闸门 + 逐行计费 + 整票求和）
from app.services import price_factor
from app.services.price_factor import current_price_factor
# 🆕 v023：口岸费 scope 的**唯一派生出口**（响应侧与导出侧同源；本文件不许再手写同一条规则）。
from app.services.quote_format import border_fee_scope_of
from app.services.vehicle_registry import get_model, models_by_category, profile_for_model

router = APIRouter()

# ── 🆕 v024 T1/T3：普货口径（`estimate_mode="general_cargo"`）的冻结文案 ──────────────
# 口径必须**印在响应里自证**：普货按「车型全包公里费率 × 里程 × N 车」估算，重量不进钱
# （整车链路 `compute_cost_full_truck` 的基价/装卸都按车型固定费，不按吨）。
# 🆕 v024 T3：文案的**定义搬到了 `services/quote_format.py`**（唯一定义处）——
#   因为报价单渲染器也要印同一句，两处各写一份必然漂移（v023 口岸费规则先例）。
#   本模块与 `quote_docx_builder` 都从这里取，名字保持不变（外部 import 不受影响）。
from app.services.quote_format import (  # noqa: E402  （与其它 services import 同段）
    ESTIMATE_BASIS_GENERAL_CARGO, HEAVY_LIFT_SKIPPED_NOTE, estimate_basis_of,
)
GENERAL_CARGO_NEEDS_COUNT = (
    "普货模式（general_cargo）必须给出车辆数 cost_params.force_vehicle_count（≥1）"
    " —— 本模式不按货物信息推算车数，也不许缺省按 1 辆算"
)


def is_general_cargo(request: QuoteRequest) -> bool:
    """普货口径判定（唯一判据，两个入口共用）。"""
    return getattr(request, "estimate_mode", "normal") == "general_cargo"


def _estimate_meta(request: QuoteRequest) -> dict:
    """普货口径的自证元数据（响应侧单点组装；`normal` ⇒ 全空，老响应逐字节不变）。

    ⚠️ 不设「载荷档位」这类「只标注不改钱」的字段（F1 裁定，门禁 MODE-4 直接判红）：
    进钱的旋钮是 `cargo.type` 的载荷系数，库里没有折扣档，自造一个不动钱的档位比不设更糟。
    """
    if not is_general_cargo(request):
        return {"estimate_mode": "normal", "estimate_basis": None, "estimate_notes": []}
    return {
        "estimate_mode": "general_cargo",
        "estimate_basis": estimate_basis_of(request.estimate_mode),
        # 缺项明示必须**与金额一致**（v026 复核实发：无条件注 ⇒ 给 20 t 时响应里同时出现
        # `vietnam_side.items.heavy_lift = 16000.0`（已计）与「未提供货物重量 ⇒ 吊装费未计」）。
        # 判据是「本票到底有没有重量」而不是「是不是普货模式」：
        #   · 没给重量 ⇒ 吊装费真未计 ⇒ 注（缺项必须写明，不许静默少一项）；
        #   · 给了重量 ⇒ 吊装费按吨真计 ⇒ **不许注**（口径句与金额自相矛盾比少一句更糟）。
        "estimate_notes": [HEAVY_LIFT_SKIPPED_NOTE] if request.cargo.weight_kg is None else [],
    }


def _resolve_osrm_profile(request: QuoteRequest) -> str | None:
    """🆕 v015.4：按所选车型决定 OSRM profile。

    优先级：请求体显式 `vehicle.osrm_profile` → 车辆型号库 `osrm_profile` 列（按 vehicle_model_id 查）
            → None（= 未按车型选路，用全局默认 profile，与 v015.4 之前行为一致）。

    为什么放在这里而不是 OSRMClient 里：车型→profile 的映射属于**业务主数据**
    （车辆型号库.csv，31 款声明 truck / 3 个小厢货声明 driving），客户端只负责请求与降级。
    """
    explicit = (request.vehicle.osrm_profile or "").strip().lower()
    if explicit:
        return explicit
    return profile_for_model(request.vehicle.vehicle_model_id)


def _coords_from_route_input(route, scope: str | None = None) -> list[tuple[float, float]]:
    points = [route.origin]
    # 🆕 v008：只有**跨境**（或判不准 → 保守按跨境）时才把口岸当途经点。
    #   境内路线（如河内→胡志明）若仍带上口岸，OSRM 会强行绕到口岸再折回
    #   —— 实测表现为地图上出现「凭祥 → 河内 → 胡志明」，且距离/时长/分段全错。
    if route.border and (scope is None or scope in ("cross_border", "unknown")):
        points.append(route.border)  # 口岸作为途经点 → OSRM 拆成 中国段/越南段
    points.extend(route.waypoints)
    points.append(route.destination)
    return [(p.lng, p.lat) for p in points]


def _country_of_point(p) -> str:
    """判定某个点属于哪国/是不是口岸：① 地址名走本地地名表 ② 坐标包围盒兜底。"""
    if p is None:
        return ""
    name = getattr(p, "address", None) or ""
    c = country_of(str(name)) if str(name).strip() else ""
    if c:
        return c
    return bbox_country(getattr(p, "lat", None), getattr(p, "lng", None))


def _scope_from_countries(origin_c: str, dest_c: str) -> str:
    if origin_c == "BORDER" or dest_c == "BORDER":
        return "cross_border"          # 起点/终点就在口岸 → 跨境语义
    if origin_c and dest_c:
        if origin_c == dest_c == "CN":
            return "domestic_cn"
        if origin_c == dest_c == "VN":
            return "domestic_vn"
        if {origin_c, dest_c} == {"CN", "VN"}:
            return "cross_border"
    return "unknown"


def _route_scope(route) -> str:
    """🆕 v008：判定运输范围 —— `domestic_cn` / `domestic_vn` / `cross_border` / `unknown`。

    为什么必须判：起终点同在越南时，若仍把「友谊关」当途经点塞给 OSRM，
    路线会被绕到凭祥再折回（用户实测：河内→胡志明 画成 凭祥→河内→胡志明），
    且口岸费、中国段/越南段分段、导出件文案会全错。

    依据：① 地址名 → 本地地名表（67 条，带 CN/VN/BORDER）
          ② 坐标 → 中越包围盒兜底（边境带重合时返回空）
          ③ 判不准 → `unknown`，**按跨境保守处理**（与旧行为一致，不会漏收口岸费）。
    """
    return _scope_from_countries(_country_of_point(route.origin), _country_of_point(route.destination))


def _legs_from_route(route_result: RouteResult, scope: str | None = None) -> tuple[LegOutput | None, LegOutput | None]:
    """从 route result 的 legs 提取 中国段/越南段（发车地→口岸、口岸→目的地）。

    🆕 v008：**只有跨境才有「中国段/越南段」语义** —— 境内路线返回 (None, None)，
    前端据此只显示「全程」，不再谎报中国段/越南段。
    """
    if scope in ("domestic_cn", "domestic_vn"):
        return None, None
    legs = route_result.legs
    if len(legs) >= 2:
        china = LegOutput(distance_km=legs[0].distance_m / 1000, duration_h=legs[0].duration_s / 3600)
        vietnam = LegOutput(distance_km=legs[1].distance_m / 1000, duration_h=legs[1].duration_s / 3600)
        return china, vietnam
    return None, None


def build_quote_response(route_result: RouteResult, result: CostResult, vehicle_count: int = 1,
                         border_fees: BorderFeesOut | None = None,
                         margin_rate: float | None = None,
                         scope: str | None = None,
                         price_factor_snapshot: dict | None = None,
                         estimate_meta: dict | None = None) -> QuoteResponse:
    """把 OSRM 路线结果 + 费用计算结果组装成统一的响应格式，单条报价和批量报价共用。
    
    vehicle_count > 1 时，各项费用 × vehicle_count 得到总价，cost_per_vehicle 存单车价格。
    margin_rate 传入则用传入值定价，否则用 settings.margin_rate 默认。
    🆕 v008：scope = 运输范围（domestic_cn/domestic_vn/cross_border/unknown）→ 决定是否给分段。
    🆕 v009：当期价格系数只乘**运输费**（距离成本+固定调度费+路桥+附加），
        不乘装卸费/保险费/杂费：
            总价 = transport_subtotal_vnd × factor + (装卸费 + 保险费 + 杂费) × 车辆数
        系数在这里单点生效 —— `route.py` 与 `batch.py` 共用本函数，口径天然一致。
    """
    b = result.breakdown
    mult = vehicle_count if vehicle_count > 1 else 1
    d_km = result.distance_km
    margin = margin_rate if margin_rate is not None else settings.margin_rate
    china_leg, vietnam_leg = _legs_from_route(route_result, scope)

    # 🆕 v015.4：路线 profile 兑现情况（诚实降级标注）。用 getattr 兜底 —— 测试/外部调用方
    # 可能传轻量打桩对象（只要 distance/duration/geometry 齐全），不能因此炸掉报价。
    prof_requested = getattr(route_result, "profile_requested", None)
    prof_used = getattr(route_result, "profile_used", None) or settings.osrm_profile
    prof_honored = bool(getattr(route_result, "profile_honored", True))
    prof_note = getattr(route_result, "profile_note", None)

    snapshot = price_factor_snapshot if price_factor_snapshot is not None else current_price_factor()
    factor = float(snapshot.get("factor") or 1.0)
    factor_note = snapshot.get("note") if snapshot.get("active") else None

    # 不参与价格系数的费用项（装卸费/保险费/杂费）；整车模式下 cost_time=cost_fuel=0，
    # 所以 transport 正好等于「距离成本 + 固定调度费 + 路桥费 + 三项路况附加 + 港口附加」。
    non_transport_per_vehicle = price_factor.non_transport_cost(
        cost_loading=b.cost_loading,
        cost_insurance=b.cost_insurance,
        cost_misc=b.cost_misc,
    )
    transport_per_vehicle = b.cost_total - non_transport_per_vehicle
    transport_subtotal_vnd = transport_per_vehicle * mult
    total_cost = transport_subtotal_vnd * factor + non_transport_per_vehicle * mult
    price_vnd = total_cost * (1 + margin)
    profit_vnd = total_cost * margin

    return QuoteResponse(
        route=RouteOutput(
            distance_km=d_km,
            duration_h=route_result.duration_s / 3600,
            adjusted_duration_h=result.timing.adjusted_duration_h,
            geometry=route_result.geometry,
            china_leg=china_leg,
            vietnam_leg=vietnam_leg,
            scope=scope,
            price_factor=factor,
            price_factor_note=factor_note,
            transport_subtotal_vnd=transport_subtotal_vnd,
            profile_requested=prof_requested,
            profile_used=prof_used,
            profile_honored=prof_honored,
            profile_note=prof_note,
        ),
        # 🆕 v015.4：顶层镜像字段与 route.* **同值** —— 前端地图面板/导出件任取一处即可，
        # 避免漏读导致「以为做过限高限重校验」。此前只喂了嵌套 RouteOutput，顶层停在默认
        # profile_honored=True ⇒ 读顶层会得到**相反**结论（比没有这个字段更危险）。
        profile_requested=prof_requested,
        profile_used=prof_used,
        profile_honored=prof_honored,
        profile_note=prof_note,
        timing=TimingOutput(**result.timing.__dict__),
        breakdown=BreakdownOutput(
            cost_distance=b.cost_distance * mult,
            cost_time=b.cost_time * mult,
            cost_fuel=b.cost_fuel * mult,
            cost_loading=b.cost_loading * mult,
            cost_insurance=b.cost_insurance * mult,
            cost_toll=b.cost_toll * mult,
            cost_misc=b.cost_misc * mult,
            cost_body_surcharge=b.cost_body_surcharge * mult,
            cost_restricted_zone=b.cost_restricted_zone * mult,
            cost_construction_zone=b.cost_construction_zone * mult,
            cost_mountain_road=b.cost_mountain_road * mult,
            cost_port=b.cost_port * mult,
            cost_fixed=b.cost_fixed * mult,
            cost_total=total_cost,
            cost_per_km=total_cost / d_km if d_km > 0 else 0.0,
            cost_per_ton_km=b.cost_per_ton_km,
            capacity_ratio=b.capacity_ratio,
            matched_vehicle_model_id=b.matched_vehicle_model_id,
            matched_vehicle_model_name=b.matched_vehicle_model_name,
            vehicle_count=vehicle_count,
            cost_per_vehicle=b.cost_total if vehicle_count > 1 else None,
        ),
        suggestions=result.suggestions,
        route_fallback=route_result.fallback,
        vehicle_count=vehicle_count,
        price_vnd=price_vnd,
        profit_vnd=profit_vnd,
        margin_rate=margin,
        border_fees=border_fees,
        # 🆕 v023：响应侧 scope 与导出侧**同源** —— 唯一实现 = `quote_format.border_fee_scope_of()`。
        #   此前这里是手写的「border_fees 非空 ⇒ included」判定，与
        #   `quote_format.border_fees_included_of()` 是两处各自实现的同一条规则
        #   （必漏：只在前端修 scope ⇒ 响应体照旧判三行）。
        border_fee_scope=border_fee_scope_of(border_fees),
        # 兼容字段（老消费方）：任一端计入 ⇒ True。分支一律改用上面的 border_fee_scope。
        border_fees_included=border_fee_scope_of(border_fees) != "none",
        # 🆕 v024 T1：普货口径自证字段（缺省全空 ⇒ 老响应逐字节不变）
        **{k: v for k, v in (estimate_meta or {}).items()},
    )


def _volume_plausibility_error(weight_kg: float, volume_m3: float | None) -> str | None:
    """体积合理性判据：**平均密度**（t/m³），不按绝对体积 —— v015.5。

    为什么改（2026-09-28 用户报障）：
      旧闸「volume_m3 > 2000 ⇒ 422 异常偏大」把**整批货的总方数**当成"一辆车"来比，
      水电机组/变压器这类超大件工程物流（实测：44 件 / 3,800 t / 4,937 m³ / 密度 0.77）
      被直接 422 拦死 —— 判据错、量级也错。
    现在：密度落在 **0.02–10 t/m³** ⇒ 放行（无论方数多大）；填错单位时体积会差 10³ 量级，
      密度必然落到不可能区间，仍能兜住。阈值与前端 v015.2 密度护栏**同口径**。
    """
    if volume_m3 is None or volume_m3 <= 0:
        return None
    density = (weight_kg / 1000.0) / volume_m3
    if 0.02 <= density <= 10:
        return None
    if density < 0.02:
        return (f"货物总体积 {volume_m3:.0f} m³ / 总重 {weight_kg / 1000:.0f} t ⇒ 平均密度仅 {density:.4f} t/m³"
                "（设备类正常 0.1–8）。请检查尺寸单位：机械/设备尺寸一般按【毫米】输入"
                "（mm 当 cm 会放大 1000 倍）。如确认数据无误，可在界面上点「仍按当前值计算」后重试。")
    return (f"货物总体积 {volume_m3:.0f} m³ / 总重 {weight_kg / 1000:.0f} t ⇒ 平均密度 {density:.1f} t/m³，"
            "已高于钢（7.85）。请检查尺寸单位（是否把米填成了厘米？）。"
            "如确认数据无误，可在界面上点「仍按当前值计算」后重试。")


def _capable_models_for(piece_ton: float) -> list:
    """库内能承载该单件的车型（载重升序 ⇒ 最经济在前）。查库失败**不许**影响闸门本身。"""
    found: list = []
    try:
        for _arr in (models_by_category() or {}).values():
            for _m in _arr:
                if float(getattr(_m, "max_load_ton", 0) or 0) >= piece_ton:
                    found.append(_m)
    except Exception:  # noqa: BLE001
        return []
    found.sort(key=lambda m: float(getattr(m, "max_load_ton", 0) or 0))
    return found


def _overload_detail(model, piece: float, line_name: str | None = None) -> str:
    """「超载不可放行」422 文案（v018 骨架 + 库内可承载车型名单）。

    - `line_name=None` ⇒ **v018 逐字不变**（单车型路径）；
    - `line_name` 非空 ⇒ 点名这一行（v020 T-D 逐行闸门：用户要知道是**哪一行**撞了哪台车）。

    🆕 v018：**报错可行动化**（用户实报：225t 件只被告知「请改选更大载重车型」，
      但没人告诉他库里有哪台能拉）—— 直接点名库内能承载该件的车型。
    🆕 v016：区分「超限」（可许可）与「超载」（无许可路径）—— 本闸拦的是**超载**
      （单件 > 核定载质量），中越两侧都无许可路径（中国《道路交通安全法》第 48 条；
      越南 TT12/2025/TT-BXD Điều 8 khoản 2 điểm d + Điều 22 khoản 3 điểm a：
      超核定载质量一律不发许可证）。「允许超限运输配车」开关（cost_params.allow_oversized）
      **只放宽超限**，对本闸没有任何作用 —— 只有 `allow_oversized_split`
      （确认按拆分多辆普通车计算）才放行，语义与超限开关不同，不许混用。
    """
    _capable = _capable_models_for(piece)
    _sugg = (
        "库内可承载本件的车型："
        + "、".join(f"{m.display_name}（{float(m.max_load_ton):.0f} 吨）" for m in _capable[:3])
        + "。"
    ) if _capable else "库内没有能承载本件的车型 ⇒ 只能拆件或录专线趟价。"
    _line = f"（本行：{line_name}）" if line_name else ""
    return (
        f"超载不可放行：单件货物 {piece:.1f} 吨超过车型「{model.display_name}」"
        f"核定载重 {model.max_load_ton:.0f} 吨{_line}。超载在中/越两侧均无许可路径"
        "（中国《道路交通安全法》第 48 条严禁超载；越南 TT12/2025/TT-BXD "
        "Điều 8 khoản 2 điểm d / Điều 22 khoản 3 điểm a 规定超核定载质量不发许可证），"
        "「允许超限运输配车」开关只放宽**超限**（长/宽/高/车货总重）、不放松本闸。"
        + _sugg
        + "确需按多辆普通车拆分计算时，请显式勾选「确认按拆分计算」。"
    )


def _shared_cost_kwargs(request: QuoteRequest, route_result: RouteResult, cargo_items: list[dict]) -> dict:
    """单车型路径与逐行路径**共用**的计费入参（🆕 v020 T-D 抽取；值与原内联 dict 逐字一致）。

    刻意**不含** `cargo_weight_ton`：单车型路径给「整票吨位 ÷ 车数」，逐行路径给「该行吨位」。
    """
    cost_params = request.cost_params
    return dict(
        distance_m=route_result.distance_m,
        duration_s=route_result.duration_s,
        cargo_type=request.cargo.type,
        empty_return=request.vehicle.empty_return,
        need_loading=request.vehicle.need_loading,
        avoid_restricted_zones=request.vehicle.avoid_restricted_zones,
        avoid_construction_zones=request.vehicle.avoid_construction_zones,
        via_mountain_road=request.vehicle.via_mountain_road,
        via_port=request.vehicle.via_port,
        cargo_items=cargo_items,
        fuel_price_vnd=cost_params.fuel_price_vnd or settings.default_fuel_price_vnd,
        wage_hourly_vnd=cost_params.wage_hourly_vnd or settings.default_wage_hourly_vnd,
        cargo_value_vnd=request.cargo.value_vnd,
        toll_rate_vnd_per_km=cost_params.toll_rate_vnd_per_km,
        misc_cost_vnd=cost_params.misc_cost_vnd,
        loading_rate_vnd_per_ton=settings.loading_rate_vnd_per_ton,
        insurance_rate=settings.insurance_rate,
    )


def _compute_line_priced(request: QuoteRequest, cargo_items: list[dict],
                         route_result: RouteResult) -> tuple[CostResult, int]:
    """🆕 v020 T-D：逐行车型计价（逐行闸门 → 逐行计费 → 整票求和）→ (单车口径结果, 总车数)。

    上游 `build_quote_response()` 会把单车口径的每个金额项 × 车辆数 ⇒
    响应金额 = **整票** = Σ 各行（该行费用 × 该行台数），与配车计划同源。
    """
    blocked = line_pricing.check_lines(
        cargo_items, allow_oversized_split=request.cost_params.allow_oversized_split)
    if blocked is not None:
        raise HTTPException(
            status_code=422,
            detail=_overload_detail(blocked.model, blocked.piece_ton, line_name=blocked.name),
        )

    plan = line_pricing.price_lines(
        cargo_items, common_kwargs=_shared_cost_kwargs(request, route_result, cargo_items))
    # 车数 = Σ 各行台数（INV-2：只出自 车辆数分解()）
    vehicle_count = plan.total_trucks
    # 装车实际值覆盖：现逻辑不变（用户「按实际 N 辆重新计价」时传 force_vehicle_count）
    if request.cost_params.force_vehicle_count and request.cost_params.force_vehicle_count > 0:
        vehicle_count = request.cost_params.force_vehicle_count
    # 单车口径 = 整票 ÷ **计划车数**（响应侧再 × 最终车数 ⇒ 金额随实际车数等比换算；
    # 无覆盖时两者相等 ⇒ 响应金额 == 整票之和，数值级）
    return line_pricing.scale_cost_result(plan.total, 1.0 / plan.total_trucks), vehicle_count


def _compute_from_request(request: QuoteRequest, route_result: RouteResult) -> tuple[CostResult, int]:
    """计算单车费用，返回 (单车CostResult, 需要车辆数)。

    🆕 v020 T-D：`cargo.items[].vehicle_model_id` **任一非空** ⇒ 「逐行车型计价」
    （每行用该行自己的计划车型过闸 + 计费，整票 = 各行之和，车数 = Σ 各行台数）；
    **全部缺省** ⇒ 完全走现路径（单车型 `vehicle.vehicle_model_id` + 现闸门），逐字节不变。
    逐行模式下 `vehicle.vehicle_model_id`（任务卡车型）**不参与**闸门与计费，也不做库内校验
    —— 它已被逐行车型取代；没有计划车型的行不在本票计价范围内（见 line_pricing 模块头）。
    """
    cost_params = request.cost_params
    # 🆕 v024 T1：普货口径没有货物信息 ⇒ 重量按 0 处理（**不进钱**，也不许伪造一个数）。
    cargo_weight_kg = request.cargo.weight_kg
    general = is_general_cargo(request)
    weight_ton = (cargo_weight_kg or 0.0) / 1000
    cargo_items = [i.model_dump() for i in request.cargo.items]

    # 🔒 体积合理性护栏（v015.5：按**密度**判，不按绝对体积；见 _volume_plausibility_error）
    #    ——「仍按当前值计算」= cost_params.allow_implausible_volume ⇒ 明知可疑也放行
    # 🆕 v024 T1（守卫 2）：普货无重量时**跳过** —— 否则重量 0 会算出密度 0，
    #    触发「平均密度仅 0.0000 t/m³」的假 422（尺寸/单位问题，与本票无关）。
    if not cost_params.allow_implausible_volume and cargo_weight_kg is not None:
        _vol_err = _volume_plausibility_error(cargo_weight_kg, request.cargo.volume_m3)
        if _vol_err:
            raise HTTPException(status_code=422, detail=_vol_err)

    # 🆕 v024 T1：普货口径 —— 车数**唯一来源**是 cost_params.force_vehicle_count：
    #   ① 不进四约束分解（`vehicle_count_breakdown` 需要重量/体积，无货信息只会印出
    #      「主因 = 重量 / 1 辆」这种假口径）；
    #   ② 不产生超载/轴荷结论（不给 heavy_load 提示）；
    #   ③ 缺省/0 ⇒ 422，**不许静默按 1 辆算**（闸门写在被两个入口共用的本函数内部）。
    if general:
        forced = int(cost_params.force_vehicle_count or 0)
        if forced < 1:
            raise HTTPException(status_code=422, detail=GENERAL_CARGO_NEEDS_COUNT)
        vehicle_count = forced
        common_kwargs = _shared_cost_kwargs(request, route_result, cargo_items)
        common_kwargs["cargo_weight_ton"] = weight_ton / vehicle_count
        result = compute_cost_full_truck(
            vehicle_model_id=request.vehicle.vehicle_model_id, **common_kwargs)
        return result, vehicle_count

    # 🆕 v020 T-D：逐行车型计价（只针对整车；拼货模式不看逐行车型 ⇒ 旧行为不变）
    if request.vehicle.loading_mode == "full_truck" and line_pricing.has_line_models(cargo_items):
        return _compute_line_priced(request, cargo_items, route_result)

    # 整车模式：计算需要几辆车（🆕 四约束：重量/体积/长件/面积）
    vehicle_count = 1
    if request.vehicle.loading_mode == "full_truck" and request.vehicle.vehicle_model_id:
        model = get_model(request.vehicle.vehicle_model_id)
        if model:
            breakdown = vehicle_count_breakdown(
                model=model,
                cargo_weight_ton=weight_ton,
                cargo_volume_m3=request.cargo.volume_m3,
                cargo_items=cargo_items,
            )
            # 🆕 大件/超限拦截：单件重量 > 车型载重 → 该车型装不下这一件，
            # 不再静默按四约束拆成多辆普通车出假价（越南 >38t 属超限运输）。
            # 🆕 v016（**只改文案，闸门逻辑一字不变**）：区分「超限」（可许可）与「超载」（无许可路径）——
            #   本闸拦的是**超载**（单件 > 核定载质量），中越两侧都无许可路径
            #   （中国《道路交通安全法》第 48 条；越南 TT12/2025/TT-BXD Điều 8 khoản 2 điểm d +
            #     Điều 22 khoản 3 điểm a：超核定载质量一律不发许可证）。
            #   「允许超限运输配车」开关（cost_params.allow_oversized）**只放宽超限**，
            #   对本闸没有任何作用 —— 此处只有 `allow_oversized_split`（确认按拆分多辆普通车计算）
            #   才放行，语义与超限开关不同，不许混用。
            if breakdown.get("不可分") and not cost_params.allow_oversized_split:
                piece = float(breakdown.get("最大单件重量吨") or 0)
                # 🆕 v020 T-D：文案抽为 `_overload_detail()`（本路径 line_name=None ⇒ **逐字不变**）
                raise HTTPException(status_code=422, detail=_overload_detail(model, piece))
            vehicle_count = breakdown["车数"]

    # 装车实际值覆盖：当 carbox 实际车数 > 四约束估算时，按实际值重算（避免报价漏算）
    if cost_params.force_vehicle_count and cost_params.force_vehicle_count > 0:
        vehicle_count = cost_params.force_vehicle_count

    # 用单车重量计算
    per_vehicle_weight_ton = weight_ton / vehicle_count

    common_kwargs = _shared_cost_kwargs(request, route_result, cargo_items)
    common_kwargs["cargo_weight_ton"] = per_vehicle_weight_ton
    if request.vehicle.loading_mode == "full_truck":
        result = compute_cost_full_truck(vehicle_model_id=request.vehicle.vehicle_model_id, **common_kwargs)
    else:
        result = compute_cost_consolidated(cargo_volume_m3=request.cargo.volume_m3, **common_kwargs)
    return result, vehicle_count


def _trim_border_fees(border_fees: BorderFeesOut, *, include_export: bool, include_import: bool) -> BorderFeesOut:
    """🆕 v023：按端裁剪口岸费 —— **② 两端开关的唯一裁剪点**（在算完之后的单个位置收口）。

    - 被关一端 ⇒ `china_side` / `vietnam_side = None` + 对应 `*_excluded=True`。
      **不许**写成「该端小计 = 0」：本项目既有「0 元」与「不算」分不清的坑，契约上必须分家。
    - `china_total` / `vietnam_total` 保留**真实值**（两端都算出来的值）供审计；`total_*` 只累加未关的一端。
    - ⚠️ 无论关哪一端，**不碰运输服务费**（那是 `margin_rate` / `force_vehicle_count` 的职责）。
    """
    china_total = float(getattr(getattr(border_fees, "china_side", None), "subtotal_rmb", 0) or 0)
    vietnam_total = float(getattr(getattr(border_fees, "vietnam_side", None), "subtotal_rmb", 0) or 0)
    rate = border_fees.exchange_rate
    data = border_fees.model_dump()
    data["china_side"] = border_fees.china_side if include_export else None
    data["vietnam_side"] = border_fees.vietnam_side if include_import else None
    data["china_excluded"] = not include_export
    data["vietnam_excluded"] = not include_import
    data["china_total"] = round(china_total, 2)
    data["vietnam_total"] = round(vietnam_total, 2)
    kept_rmb = (china_total if include_export else 0.0) + (vietnam_total if include_import else 0.0)
    data["total_rmb"] = round(kept_rmb, 2)
    data["total_vnd"] = round(kept_rmb * float(rate)) if rate else 0
    return BorderFeesOut(**data)


async def _resolve_border_fees(request: QuoteRequest, vehicle_count: int, scope: str | None = None) -> BorderFeesOut | None:
    """按 pricing 逐项覆盖或固定费率自动算，返回 BorderFeesOut（单条/多方案共用）。

    🆕 v008：**境内运输（起终点同国）不涉及进出口口岸费** → 返回 None（前端据此显示「境内运输，不涉及口岸」）。
    🆕 v022 T4（步骤⑥）：**用户关掉「进出口费用」开关 ⇒ 同样返回 None**（本报价不含口岸费）。
    🆕 v023（② 两端开关）：`include_export_fees` / `include_import_fees` **按端裁剪** ——
      有效两端 = `include_border_fees ∧ 该端布尔`（主开关关 ⇒ 两端都关，旧 payload 语义逐字节不变）；
      被关一端 ⇒ `None`，两端各自真实合计仍回传供审计（`_trim_border_fees`）。
    ⚠️ 闸门写在本函数内（不是调用点）：`/route/cost`(:452) 与 `/route/alternatives`(:481) 共用，
    否则「方案候选」会照旧带上口岸费、与主报价单不同源。
    ⚠️ 两个 None 由响应体的 `border_fees_included=False` + `route.scope` 区分：
    境内 = 本来就没有口岸；跨境 = 用户主动不含。
    """
    if scope in ("domestic_cn", "domestic_vn"):
        return None
    # 🆕 v022 T4：开关关闭 ⇒ 不算、不传、不计入（总计 = 运输服务费）。
    if not request.pricing.include_border_fees:
        return None
    # 🆕 v023：按端闸门（两个布尔只作**入参**，展示/分支一律走 `border_fee_scope_of()`）。
    include_export = bool(getattr(request.pricing, "include_export_fees", True))
    include_import = bool(getattr(request.pricing, "include_import_fees", True))
    if not include_export and not include_import:
        return None                       # 两端都关 ⇒ 与 v022 主开关关同一形态（border_fees=None）
    override = request.pricing.border_fees_override
    # 🆕 v021：「口岸费车次」只替换**算口岸费**用的车数；运输费车数（vehicle_count）不动。
    #   例外项（吊装费按吨、检验费按柜、滞箱费按天）在 calc_border_fees 内按各自口径算，不受此影响。
    border_vc = vehicle_count
    if override is not None and override.vehicle_count:
        border_vc = int(override.vehicle_count)
    base = await calc_border_fees(
        vehicle_count=border_vc,
        # 🆕 v024 T1（守卫 3）：普货无货物重量 ⇒ 吊装费按 0 吨计（响应另附
        #   `estimate_notes` 明说「未提供货物重量 ⇒ 吊装费未计」，不许静默少一项）。
        heavy_lift_tons=(request.cargo.weight_kg or 0.0) / 1000,
    )
    base["vehicle_count"] = border_vc
    base["fleet_vehicle_count"] = vehicle_count
    if override is not None:
        base = apply_border_fees_override(base, override)
    # 🆕 v023：在**唯一裁剪点**按端收口（两端都开着 ⇒ 逐字节等于 v022 的 `BorderFeesOut(**base)`）。
    return _trim_border_fees(BorderFeesOut(**base),
                             include_export=include_export, include_import=include_import)


@router.post("/route/cost", response_model=QuoteResponse)
async def quote_cost(request: QuoteRequest) -> QuoteResponse:
    scope = _route_scope(request.route)
    coordinates = _coords_from_route_input(request.route, scope)

    # 🆕 v015.4：按所选车型的 OSRM profile 请求路线（兑现不了由 OSRMClient 回退并标注降级）
    client = OSRMClient(profile=_resolve_osrm_profile(request))
    try:
        route_result = await client.get_route(coordinates)
    except OSRMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        result, vehicle_count = _compute_from_request(request, route_result)
    except NoFittingVehicleModel as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (UnknownVehicleModel, UnknownCargoType) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    border_fees = await _resolve_border_fees(request, vehicle_count, scope)
    return build_quote_response(route_result, result, vehicle_count,
                                border_fees=border_fees,
                                margin_rate=request.pricing.margin_rate,
                                scope=scope,
                                price_factor_snapshot=current_price_factor(),
                                estimate_meta=_estimate_meta(request))


@router.post("/route/alternatives")
async def quote_alternatives(request: QuoteRequest) -> dict:
    """§9 多路线对比 —— 返回 OSRM 找到的每条候选路线各自的完整报价，按总费用从低到高排序。"""
    scope = _route_scope(request.route)
    coordinates = _coords_from_route_input(request.route, scope)

    client = OSRMClient(profile=_resolve_osrm_profile(request))
    try:
        route_results = await client.get_routes(coordinates)
    except OSRMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    options: list[QuoteResponse] = []
    factor_snapshot = current_price_factor()   # 一次读取，多个路线方案口径一致
    for route_result in route_results:
        try:
            result, vehicle_count = _compute_from_request(request, route_result)
        except NoFittingVehicleModel as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (UnknownVehicleModel, UnknownCargoType) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        border_fees = await _resolve_border_fees(request, vehicle_count, scope)
        options.append(build_quote_response(route_result, result, vehicle_count,
                                            border_fees=border_fees,
                                            margin_rate=request.pricing.margin_rate,
                                            scope=scope,
                                            price_factor_snapshot=factor_snapshot,
                                            estimate_meta=_estimate_meta(request)))

    options.sort(key=lambda o: o.breakdown.cost_total)
    return {"options": options}


@router.get("/route")
async def get_route(
    origin_lat: float = Query(...),
    origin_lng: float = Query(...),
    dest_lat: float = Query(...),
    dest_lng: float = Query(...),
    profile: str | None = Query(None, description="🆕 v015.4 车型 profile（如 truck）；不传=全局默认"),
) -> dict:
    """只取路线（距离/时间/GeoJSON），不计算费用 — 用于地图预览。

    🆕 v015.4：可传 profile（前端把所选车型的 osrm_profile 带上来）→ 地图预览与报价同一口径；
    兑现不了时返回 profile_honored=false + profile_note（中文），调用方必须显示。
    """
    client = OSRMClient(profile=profile)
    try:
        route_result = await client.get_route([(origin_lng, origin_lat), (dest_lng, dest_lat)])
    except OSRMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "distance_km": round(route_result.distance_m / 1000, 2),
        "duration_h": round(route_result.duration_s / 3600, 2),
        "geometry": route_result.geometry,
        "fallback": route_result.fallback,
        "profile_requested": route_result.profile_requested,
        "profile_used": route_result.profile_used,
        "profile_honored": route_result.profile_honored,
        "profile_note": route_result.profile_note,
    }
