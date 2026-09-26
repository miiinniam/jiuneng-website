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
from app.services import price_factor
from app.services.price_factor import current_price_factor
from app.services.vehicle_registry import get_model, profile_for_model

router = APIRouter()


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
                         price_factor_snapshot: dict | None = None) -> QuoteResponse:
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
    )


def _compute_from_request(request: QuoteRequest, route_result: RouteResult) -> tuple[CostResult, int]:
    """计算单车费用，返回 (单车CostResult, 需要车辆数)。"""
    cost_params = request.cost_params
    weight_ton = request.cargo.weight_kg / 1000
    cargo_items = [i.model_dump() for i in request.cargo.items]

    # 🔒 体积合理性护栏（P1，后端兜底）：mm 被当 cm 会 ×1000，绝不允许算出上千 m³ 的车数
    if request.cargo.volume_m3 is not None and request.cargo.volume_m3 > 2000:
        raise HTTPException(
            status_code=422,
            detail=f"货物总体积 {request.cargo.volume_m3:.0f} m³ 异常偏大（一辆整车通常不超过上千 m³）。"
                   "请检查尺寸单位：机械/设备尺寸一般按【毫米】输入。",
        )

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
            if breakdown.get("不可分") and not cost_params.allow_oversized_split:
                piece = float(breakdown.get("最大单件重量吨") or 0)
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"单件货物 {piece:.1f} 吨超过车型「{model.display_name}」载重 "
                        f"{model.max_load_ton:.0f} 吨。越南公路 >38t 属超限运输（需特种车 + 超限许可），"
                        "请改选【大件/超限】车型，或由操作员录入专线趟价；"
                        "确需按多辆普通车拆分计算时，请显式勾选「确认按拆分计算」。"
                    ),
                )
            vehicle_count = breakdown["车数"]

    # 装车实际值覆盖：当 carbox 实际车数 > 四约束估算时，按实际值重算（避免报价漏算）
    if cost_params.force_vehicle_count and cost_params.force_vehicle_count > 0:
        vehicle_count = cost_params.force_vehicle_count

    # 用单车重量计算
    per_vehicle_weight_ton = weight_ton / vehicle_count

    common_kwargs = dict(
        distance_m=route_result.distance_m,
        duration_s=route_result.duration_s,
        cargo_weight_ton=per_vehicle_weight_ton,
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
    if request.vehicle.loading_mode == "full_truck":
        result = compute_cost_full_truck(vehicle_model_id=request.vehicle.vehicle_model_id, **common_kwargs)
    else:
        result = compute_cost_consolidated(cargo_volume_m3=request.cargo.volume_m3, **common_kwargs)
    return result, vehicle_count


async def _resolve_border_fees(request: QuoteRequest, vehicle_count: int, scope: str | None = None) -> BorderFeesOut | None:
    """按 pricing 逐项覆盖或固定费率自动算，返回 BorderFeesOut（单条/多方案共用）。

    🆕 v008：**境内运输（起终点同国）不涉及进出口口岸费** → 返回 None（前端据此显示「境内运输，不涉及口岸」）。
    """
    if scope in ("domestic_cn", "domestic_vn"):
        return None
    base = await calc_border_fees(
        vehicle_count=vehicle_count,
        heavy_lift_tons=request.cargo.weight_kg / 1000,
    )
    if request.pricing.border_fees_override is not None:
        base = apply_border_fees_override(base, request.pricing.border_fees_override)
    return BorderFeesOut(**base)


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
                                price_factor_snapshot=current_price_factor())


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
                                            price_factor_snapshot=factor_snapshot))

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
