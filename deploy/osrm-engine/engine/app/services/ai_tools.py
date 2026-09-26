"""
OSRM++ AI 聊天工具定义与执行器
==============================

为 DeepSeek Function Calling 提供工具 schema 定义和对应的 Python 执行函数。

工具列表:
- calculate_freight_cost: 计算运费（核心工具）
- calculate_border_fees: 计算口岸费用（🆕 替换 cargo_estimate）
- query_vehicle_models: 查询可用车型
- compare_routes: 多方案费用对比
- geocode_address: 地址→坐标
- query_exchange_rate: 查询实时汇率（CNY→VND）
"""

import asyncio
import json
import math
import re
from typing import Any

from app.ai import registry as _registry
from app.services.cost_engine import (
    CostResult,
    compute_cost_consolidated,
    compute_cost_full_truck,
)
from app.services.exchange_rate import get_exchange_rate
from app.services.geocoder import search_address
from app.services.osrm_client import OSRMClient
from app.services.vehicle_registry import VEHICLE_MODELS, get_model, profile_for_model


# ══════════════════════════════════════════════════════════════
# 工具 Schema 定义（OpenAI Function Calling 格式）
# ══════════════════════════════════════════════════════════════

# ⚠️ v006：工具 schema 不再手写 —— 声明在 `app/ai/spec.py`（唯一真源），
# 由 `app/ai/registry.tool_schemas()` 生成，见本文件末尾的 `TOOLS = ...`。


# ══════════════════════════════════════════════════════════════
# 工具执行器
# ══════════════════════════════════════════════════════════════

_osrm = OSRMClient()


def _parse_coords(raw: str) -> list[tuple[float, float]] | None:
    """尝试把 '21.98,106.71' 解析为 (lng, lat)。"""
    parts = raw.replace(" ", "").split(",")
    if len(parts) == 2:
        try:
            return [(float(parts[1]), float(parts[0]))]
        except ValueError:
            pass
    return None


async def _resolve_coords(address: str) -> tuple[float, float]:
    """将地址解析为 (lng, lat)。"""
    coords = _parse_coords(address)
    if coords:
        return coords[0]
    results = await search_address(address, limit=1)
    if not results:
        raise ValueError(f"找不到地址: {address}，请尝试更具体的地址（如加上省份名）")
    return (results[0].lng, results[0].lat)


def _fmt_vnd(amount: float) -> str:
    return f"{int(round(amount)):,}"


def _format_cost_result(r: CostResult, vehicle_name: str = "", distance_km: float = 0,
                         duration_h: float = 0, cargo_weight_ton: float = 0,
                         origin_coords: tuple | None = None,
                         dest_coords: tuple | None = None,
                         vehicle_count: int = 1,
                         profile_used: str | None = None,
                         profile_honored: bool = True,
                         profile_note: str | None = None) -> dict:
    """把 CostResult 格式化为 AI 友好的 dict。"""
    b = r.breakdown
    result = {
        "vehicle": vehicle_name or b.matched_vehicle_model_name,
        "vehicle_model_id": b.matched_vehicle_model_id,
        "distance_km": round(distance_km, 1) if distance_km else 0,
        "duration_h": round(duration_h, 1) if duration_h else 0,
        "cargo_weight_ton": cargo_weight_ton,
        "capacity_ratio": round(b.capacity_ratio, 2),
        "vehicle_count": vehicle_count,
        "breakdown": {
            "distance_cost_vnd": _fmt_vnd(b.cost_distance),
            "time_cost_vnd": _fmt_vnd(b.cost_time),
            "fuel_cost_vnd": _fmt_vnd(b.cost_fuel),
            "loading_cost_vnd": _fmt_vnd(b.cost_loading),
            "insurance_cost_vnd": _fmt_vnd(b.cost_insurance),
            "toll_cost_vnd": _fmt_vnd(b.cost_toll),
            "misc_cost_vnd": _fmt_vnd(b.cost_misc),
            "body_surcharge_vnd": _fmt_vnd(b.cost_body_surcharge),
            "restricted_zone_surcharge_vnd": _fmt_vnd(b.cost_restricted_zone),
            "construction_zone_surcharge_vnd": _fmt_vnd(b.cost_construction_zone),
            "mountain_road_surcharge_vnd": _fmt_vnd(b.cost_mountain_road),
            "port_surcharge_vnd": _fmt_vnd(b.cost_port),
            "fixed_surcharge_vnd": _fmt_vnd(b.cost_fixed),
        },
        "total_cost_vnd": _fmt_vnd(b.cost_total * vehicle_count),
    }
    if vehicle_count > 1:
        result["cost_per_vehicle_vnd"] = _fmt_vnd(b.cost_total)
    result["cost_per_km_vnd"] = _fmt_vnd(b.cost_per_km)
    # 🆕 v015.4：把「是否按车型限高限重校验」如实带给模型。否则 AI 对话（最用户可见的报价入口）
    # 对降级完全失明 —— 用户会以为是按所选车型的限高限重算的。仅在实际未兑现时才带 note。
    if profile_used:
        result["profile_used"] = profile_used
    if not profile_honored:
        result["profile_honored"] = False
        result["profile_note"] = profile_note
    if origin_coords:
        result["_origin"] = {"lng": origin_coords[0], "lat": origin_coords[1]}
    if dest_coords:
        result["_destination"] = {"lng": dest_coords[0], "lat": dest_coords[1]}
    return result


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    role: str = "internal",
    confirmed: bool = False,
) -> str:
    """（v006）AI 工具执行入口 —— 转发给能力注册表。

    注册表里是唯一收口点：未知工具 → 权限 → 确认 → 审计 → 执行，
    错误语义与重构前一致（都返回 JSON 字符串，不抛异常）。
    调用契约不变：`await execute_tool(name, args)` 仍可用。
    """
    return await _registry.invoke(name, arguments, role=role, confirmed=confirmed)


async def _calc_cost(args: dict) -> str:
    """执行运费计算。"""
    origin_str = args["origin"]
    dest_str = args["destination"]
    if "cargo_weight_ton" in args:
        weight_ton = float(args["cargo_weight_ton"])
    elif "cargo_weight_kg" in args:
        weight_ton = float(args["cargo_weight_kg"]) / 1000.0
    else:
        return json.dumps({"error": "缺少货物重量参数 (cargo_weight_ton)"}, ensure_ascii=False)
    weight_kg = weight_ton * 1000.0
    cargo_type = args.get("cargo_type", "normal")
    vehicle_id = args.get("vehicle_model_id", "")
    loading_mode = args.get("loading_mode", "full_truck")
    empty_return = bool(args.get("empty_return", False))
    need_loading = bool(args.get("need_loading", False))

    origin_lng, origin_lat = await _resolve_coords(origin_str)
    dest_lng, dest_lat = await _resolve_coords(dest_str)

    # 🆕 v015.4：按车型取路线 profile（与 /route/cost、/batch/quote 同口径）。模块级 `_osrm` 是
    # 全局默认 profile 的共享 client，车型声明了 osrm_profile 时必须另起一个，否则 AI 报价
    # 永远不按车型限高限重校验（且无从告知用户）。
    _profile = profile_for_model(vehicle_id) or (args.get("osrm_profile") or "").strip().lower() or None
    _route_client = OSRMClient(profile=_profile) if _profile else _osrm
    route = await _route_client.get_route([(origin_lng, origin_lat), (dest_lng, dest_lat)])
    distance_m = route.distance_m
    duration_s = route.duration_s
    distance_km = distance_m / 1000.0

    from app.config import settings

    vehicle_count = 1
    if loading_mode == "full_truck":
        if not vehicle_id:
            return json.dumps({
                "error": "整车模式需要指定车型。请先调用 query_vehicle_models 查看可用车型，或告诉我货物的大致吨位我帮你推荐。",
                "hint": "让用户选择车型，或直接指定 vehicle_model_id",
            }, ensure_ascii=False)

        model = get_model(vehicle_id)
        if model:
            # 🆕 四约束车辆数（重量/体积/长件/面积）
            from app.services.cost_engine import compute_vehicle_count
            vehicle_count = compute_vehicle_count(
                model=model,
                cargo_weight_ton=weight_ton,
                cargo_volume_m3=args.get("volume_m3"),
                cargo_items=args.get("items"),
            )

        per_vehicle_weight_ton = weight_ton / vehicle_count

        result = compute_cost_full_truck(
            distance_m=distance_m, duration_s=duration_s,
            cargo_weight_ton=per_vehicle_weight_ton,
            vehicle_model_id=vehicle_id, cargo_type=cargo_type,
            empty_return=empty_return, need_loading=need_loading,
            fuel_price_vnd=settings.default_fuel_price_vnd,
            wage_hourly_vnd=settings.default_wage_hourly_vnd,
            loading_rate_vnd_per_ton=settings.loading_rate_vnd_per_ton,
            insurance_rate=settings.insurance_rate,
        )
        return json.dumps(
            _format_cost_result(result, distance_km=distance_km, duration_h=duration_s / 3600,
                                cargo_weight_ton=weight_ton,
                                profile_used=getattr(route, "profile_used", None),
                                profile_honored=bool(getattr(route, "profile_honored", True)),
                                profile_note=getattr(route, "profile_note", None),
                                origin_coords=(origin_lng, origin_lat),
                                dest_coords=(dest_lng, dest_lat),
                                vehicle_count=vehicle_count),
            ensure_ascii=False,
        )
    else:
        volume_m3 = args.get("volume_m3", 0) or 0
        result = compute_cost_consolidated(
            distance_m=distance_m, duration_s=duration_s,
            cargo_weight_ton=weight_ton, cargo_volume_m3=volume_m3,
            cargo_type=cargo_type, empty_return=empty_return,
            need_loading=need_loading,
            cargo_items=args.get("items"),
            fuel_price_vnd=settings.default_fuel_price_vnd,
            wage_hourly_vnd=settings.default_wage_hourly_vnd,
            loading_rate_vnd_per_ton=settings.loading_rate_vnd_per_ton,
            insurance_rate=settings.insurance_rate,
        )
        return json.dumps(
            _format_cost_result(result, distance_km=distance_km, duration_h=duration_s / 3600,
                                cargo_weight_ton=weight_ton,
                                profile_used=getattr(route, "profile_used", None),
                                profile_honored=bool(getattr(route, "profile_honored", True)),
                                profile_note=getattr(route, "profile_note", None),
                                origin_coords=(origin_lng, origin_lat),
                                dest_coords=(dest_lng, dest_lat)),
            ensure_ascii=False,
        )


def _calc_border_fees(args: dict) -> str:
    """🆕 计算口岸费用（两端分开，不含税）"""
    from app.services.border_costs import calc_ddp_fees_only

    vehicle_count = int(args.get("vehicle_count", 1))
    result = calc_ddp_fees_only(vehicle_count=vehicle_count)

    return json.dumps({
        "vehicle_count": vehicle_count,
        "china_side": {
            "items": result.china_side.items,
            "subtotal_rmb": result.china_total,
        },
        "vietnam_side": {
            "items": result.vietnam_side.items,
            "subtotal_rmb": result.vietnam_total,
        },
        "total_border_fees_rmb": result.ddp_total,
        "note": "仅口岸操作费用，不含关税/增值税。费用基于玖能国际实际报价数据。",
    }, ensure_ascii=False)


def _query_vehicles(args: dict) -> str:
    """查询车型列表。"""
    category = args.get("category", "")
    min_load = float(args.get("min_load_ton", 0) or 0)

    filtered = VEHICLE_MODELS
    if category:
        filtered = [m for m in filtered if m.category == category]
    if min_load > 0:
        filtered = [m for m in filtered if m.max_load_ton >= min_load]

    vehicles = [
        {
            "model_id": m.model_id,
            "name": m.display_name,
            "category": m.category,
            "max_load_ton": m.max_load_ton,
            "volume_m3": m.volume_capacity_m3,
            "length_m": m.length_m,
            "base_rate_vnd_per_km": m.base_rate_vnd_per_km,
            "fuel_l_per_100km": m.fuel_l_per_100km,
            "suitable_cargo": list(m.suitable_cargo_types),
        }
        for m in filtered
    ]
    return json.dumps({"count": len(vehicles), "vehicles": vehicles}, ensure_ascii=False)


async def _query_vehicle_count(args: dict) -> str:
    """🆕 按四约束核算车辆数，返回真实分解（供 AI 用数据回答，不猜）。"""
    import json
    from app.services import 费用计算公式 as 公式
    from app.services.vehicle_registry import VEHICLE_MODELS, get_model

    items = args.get("items") or []
    wt = float(args.get("cargo_weight_ton") or 0)
    if not wt and args.get("cargo_weight_kg"):
        wt = float(args["cargo_weight_kg"]) / 1000.0
    vol = float(args.get("volume_m3") or 0)
    feat = 公式.货物载荷特征完整(
        货物总重量吨=wt, 货物总体积立方米=(vol if vol else None), 单件货物=items,
    )
    max_len, footprint = feat["最大单件长度米"], feat["总占地面积平方米"]

    def _fits(m):
        for it in items:
            iw = float(it.get("weight_kg") or 0) / 1000.0
            il = float(it.get("length_m") or 0)
            ia = (float(it.get("length_m") or 0) * float(it.get("width_m") or 0)) if not it.get("stackable", True) else 0
            if m.max_load_ton and iw > m.max_load_ton:
                return False
            if m.length_m and il > m.length_m:
                return False
            if m.floor_area_m2 and ia > m.floor_area_m2 * m.loading_efficiency:
                return False
        return True

    model = get_model(args.get("vehicle_model_id") or "") if args.get("vehicle_model_id") else None
    if not model:
        cand = [m for m in VEHICLE_MODELS if _fits(m) and m.max_load_ton]
        one_shot = [m for m in cand if m.max_load_ton >= wt]   # 单车能装下总重
        if one_shot:
            model = min(one_shot, key=lambda m: m.max_load_ton)   # 选最小够用
        else:
            model = max(cand, key=lambda m: m.max_load_ton) if cand else None   # 超重 → 最大车，多车
        model = model or get_model("flatbed_13m") or (VEHICLE_MODELS[0] if VEHICLE_MODELS else None)
    if not model:
        return json.dumps({"error": "无可用车型"}, ensure_ascii=False)

    bd = 公式.车辆数分解(
        货物总重量吨=wt, 货物总体积立方米=(vol if vol else None), 最大单件长度米=max_len,
        货物总占地面积平方米=footprint, 车型最大载重吨=model.max_load_ton,
        车型容积立方米=model.effective_volume_m3, 车型地板长米=model.length_m,
        车型地板面积平方米=model.floor_area_m2, 装载效率=model.loading_efficiency,
        最大单件重量吨=feat["最大单件重量吨"],
    )
    _oversize = bool(bd.get("不可分"))
    return json.dumps({
        "vehicle_model": model.display_name,
        "vehicle_model_id": model.model_id,
        "cargo_weight_ton": wt,
        "vehicle_count": bd["车数"],
        "breaking_down": {"重量": bd["重量"], "体积": bd["体积"], "长度": bd["长度"], "面积": bd["面积"]},
        "driving_constraint": bd["主因"],
        "oversize": _oversize,          # 🆕 单件超载 → 该车型装不下，属超限运输
        "explanation": (
            (
                f"⚠️ 该批货存在单件 {bd['最大单件重量吨']:.1f} 吨 > 车型「{model.display_name}」载重 "
                f"{model.max_load_ton:.0f} 吨，属超限运输（越南公路需特种车 + 超限许可），"
                "不能用该车型拆分报价，请改选【大件/超限】车型或按专线趟价处理。"
            ) if _oversize else (
                f"该批货约 {round(wt, 1)} 吨，经四约束核算需 {bd['车数']} 辆车；"
                f"主因是【{bd['主因']}】约束（重量{bd['重量']}辆/体积{bd['体积']}辆/长度{bd['长度']}辆/面积{bd['面积']}辆），"
                f"车数取四者最大。建议车型：{model.display_name}（载重 {model.max_load_ton} 吨）。"
            )
        ),
    }, ensure_ascii=False)


async def _compare_routes(args: dict) -> str:
    """多方案对比。"""
    scenarios = args.get("scenarios", [])
    if len(scenarios) < 2:
        return json.dumps({"error": "至少需要 2 个方案进行对比"}, ensure_ascii=False)

    results = []
    for sc in scenarios:
        label = sc["label"]
        try:
            cost_args = {
                "origin": sc["origin"],
                "destination": sc["destination"],
                "cargo_weight_ton": sc.get("cargo_weight_ton", 0),
                "cargo_type": sc.get("cargo_type", "normal"),
                "vehicle_model_id": sc.get("vehicle_model_id", ""),
                "loading_mode": sc.get("loading_mode", "full_truck"),
                "empty_return": bool(sc.get("empty_return", False)),
            }
            cost_json = await _calc_cost(cost_args)
            cost_data = json.loads(cost_json)
            cost_data["label"] = label
            results.append(cost_data)
        except Exception as e:
            results.append({"label": label, "error": str(e)})

    valid = [r for r in results if "total_cost_vnd" in r]
    cheapest = min(valid, key=lambda r: r["total_cost_vnd"]) if valid else None

    return json.dumps({
        "scenarios": results,
        "cheapest_label": cheapest["label"] if cheapest else None,
        "cheapest_total_vnd": cheapest["total_cost_vnd"] if cheapest else None,
    }, ensure_ascii=False)


async def _geocode(args: dict) -> str:
    """地址→坐标。"""
    address = args["address"]
    results = await search_address(address, limit=3)
    return json.dumps({
        "query": address,
        "results": [
            {"lat": r.lat, "lng": r.lng, "display_name": r.display_name}
            for r in results
        ],
    }, ensure_ascii=False)


async def _query_exchange_rate(args: dict | None = None) -> str:
    """查询实时汇率 CNY→VND。

    ⚠️ `args` 必须保留（哪怕不用）：`registry.invoke()` 统一按 `fn(args)` 调用所有执行器，
    签名少一个参数就会报 `takes 0 positional arguments but 1 was given`（v007 实测踩到，
    AI 面板里问「1 CNY = ? VND」直接报“汇率查询工具目前报错了”）。
    """
    rate_data = await get_exchange_rate()
    vnd = rate_data["vnd_per_rmb"]
    return json.dumps({
        "vnd_per_rmb": vnd,
        "source": rate_data["source"],
        "updated": rate_data["updated"],
        "message": f"今日汇率 1 CNY = {vnd:,.0f} VND",
    }, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
# extract_shipping_request：自然语言 → 结构化 JobDraft（吨单位）
# ══════════════════════════════════════════════════════════════

_BORDER_KEYWORDS = ["友谊关", "凭祥", "东兴", "河口", "磨憨", "老街", "谅山", "同登", "芒街"]


def _map_cargo_type(text: str) -> str:
    """货型映射：危险→dangerous，冷链/冷→cold_chain，大件/超限/设备/机器→heavy_equipment，其它→normal。"""
    if any(k in text for k in ("危险", "危化", "危品", "易燃", "毒")):
        return "dangerous"
    if any(k in text for k in ("冷链", "冷藏", "冷库")):
        return "cold_chain"
    if any(k in text for k in (
        "大件", "超限", "设备", "变压器", "机械", "重型", "重货", "压机", "抛光机",
        "机床", "车床", "冲床", "机床", "注塑机", "辊压", "辗压", "特种设备", "工程机械",
    )):
        return "heavy_equipment"
    return "normal"


_VALID_CARGO_TYPES = {"dangerous", "cold_chain", "heavy_equipment", "normal", "oversized", "other"}


def _find_dim(label: str, text: str) -> float:
    """按 '长/宽/高' 标签找尺寸，返回 cm。无单位时按量级推断（≥1000 → 毫米）。"""
    m = re.search(label + r"(?:度)?[：:]?\s*(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?", text)
    if not m:
        return 0.0
    v = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("米", "m"):
        return v * 100
    if unit in ("毫米", "mm"):
        return v / 10
    # 无单位：机械/设备尺寸按毫米为惯例，数值≥1000 视为毫米，防止 mm 被当 cm 导致 ×10/×1000
    if v >= 1000:
        return v / 10
    return v


def _infer_dim_unit(text: str) -> str:
    """推断用户输入的尺寸单位：显式 mm/毫米 → mm；无单位但尺寸数值≥1000（机械/设备惯例）→ mm；否则 cm。"""
    if re.search(r"毫米|[^a-zA-Z]mm[^a-zA-Z]", text, re.I):
        return "mm"
    for m in re.findall(r"\d{1,5}\s*[xX×*]\s*\d{1,5}\s*[xX×*]\s*\d{1,5}", text):
        if any(float(n) >= 1000 for n in re.findall(r"\d+", m)):
            return "mm"
    m2 = re.search(r"长[：:]?\s*(\d+(?:\.\d+)?)", text)
    if m2 and float(m2.group(1)) >= 1000:
        return "mm"
    return "cm"


def _merge_vehicles(vehicles: list, veh: str) -> None:
    """去重追加车型标识。"""
    if veh:
        v = veh.strip().rstrip("，,。 ")
        if v and v not in vehicles:
            vehicles.append(v)


def _parse_cargo_items(text: str, vehicles: list) -> list[dict]:
    """全局按编号标记切块（兼容单行/多行、跳号），逐块解析货物。

    旧实现按行 `^N、` 拆分：若编号货物被压成一行会只匹配第一条。此实现用
    finditer 找到所有 `N、`/`N.` 起点，块边界取到下一个起点，无论换行还是空格分隔都能逐条切出。
    """
    out: list[dict] = []
    item_re = re.compile(r"(?:^|\n|\s)(\d{1,2})[、.．)]\s*")
    starts = list(item_re.finditer(text))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[m.end():end].strip()
        if not body:
            continue
        item = _parse_cargo_line(body, vehicles)
        if item:
            out.append(item)
    return out


def _parse_cargo_line(body: str, vehicles: list) -> dict | None:
    """解析单个编号货物行（如 'PHC5200压机（长×宽×高）：5940X3092X2220,重88T/台，1台（特种设备车）'），
    返回 cargo dict；无尺寸/重量的行（如'备用一台17.5米...'）返回 None。"""
    # ── 车型：优先括号里（…车），否则行内 米车/特种设备车/平板/高栏 ──
    veh = None
    vm = re.search(r"[（(]\s*([^)）]*车)\s*[)）]", body)
    if vm:
        veh = vm.group(1).strip()
    if not veh:
        vm2 = re.search(r"(\d+(?:\.\d+)?\s*米\s*车|特种设备车|特种车|高栏|平板|厢式|冷藏车)", body)
        if vm2:
            veh = vm2.group(1).strip()
    _merge_vehicles(vehicles, veh)

    # ── 尺寸（cm）：长/宽/高 标签 或 a×b×c 连写 ──
    l_cm, w_cm, h_cm = _find_dim("长", body), _find_dim("宽", body), _find_dim("高", body)
    if not (l_cm or w_cm or h_cm):
        dm = re.search(
            r"(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?\s*[xX×*/-]\s*(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?\s*[xX×*/-]\s*(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?",
            body,
        )
        if dm:
            a, b, c = float(dm.group(1)), float(dm.group(3)), float(dm.group(5))
            unit = dm.group(2) or dm.group(4) or dm.group(6) or ""
            if unit in ("米", "m"):
                a, b, c = a * 100, b * 100, c * 100
            elif unit in ("毫米", "mm"):
                a, b, c = a / 10, b / 10, c / 10
            elif max(a, b, c) >= 1000:   # 无单位：按量级推断 mm
                a, b, c = a / 10, b / 10, c / 10
            l_cm, w_cm, h_cm = a, b, c

    # ── 单件重量（吨）：重XXT / XXT每(台|件) / XXT/台 / 每件XXkg ──
    per_weight_ton = None
    pw = re.search(r"重\s*(\d+(?:\.\d+)?)\s*(?:吨|t|T)", body)
    if pw:
        per_weight_ton = float(pw.group(1))
    else:
        pw2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:吨|t|T)\s*(?:/|每)", body)
        if pw2:
            per_weight_ton = float(pw2.group(1))
    if per_weight_ton is None:   # 每台/件 X吨（数字在单位前）
        pw3 = re.search(r"每(?:台|件|个|套|箱|托)\s*(\d+(?:\.\d+)?)\s*(?:吨|t|T)", body)
        if pw3:
            per_weight_ton = float(pw3.group(1))
    # kg 支持：重XXkg / 每(台|件|箱)XXkg / XXkg每件 → 转吨
    if per_weight_ton is None:
        pkg = re.search(r"(?:重\s*|每(?:台|件|个|套|箱|托)\s*)(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤|千克)", body) \
            or re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤|千克)\s*(?:/|每)", body)
        if pkg:
            per_weight_ton = float(pkg.group(1)) / 1000

    # ── 数量 ──
    qty = 1
    qm = re.search(r"(\d+)\s*(?:台|件|个|套|箱|托)", body)
    if qm:
        qty = int(qm.group(1))

    # ── 名称：取括号/尺寸/重量前的主体，再去数量前缀（1件冲床→冲床）──
    name = re.split(r"[（(]|×|X|x|长|宽|高|重|尺寸|cm|CM|吨|T", body)[0].strip()
    name = re.sub(r"^\d+[、.．\)]\s*", "", name).strip()
    name = re.sub(r"^(重)?\s*\d+(?:\.\d+)?\s*(?:吨|t|T|kg)\s*", "", name).strip()
    name = re.sub(r"^\d+\s*(?:台|件|个|套|箱|只|部|辆|托)\s*", "", name).strip()   # 去数量前缀
    name = re.sub(r"\s+\d+(?:\.\d+)?$", "", name).strip()   # 去尾部残留数字/尺寸
    name = name.strip("，,。 、")
    if not name:
        name = body[:20]

    if not (l_cm or w_cm or h_cm or per_weight_ton):
        return None  # 无尺寸/重量说明的行不算货物

    value_vnd = 0
    vm3 = re.search(r"(?:货值|价值|货价)[：:]?\s*([\d,]+)", body)
    if vm3:
        value_vnd = int(vm3.group(1).replace(",", ""))

    return {
        "name": name,
        "l_cm": round(l_cm, 2) if l_cm else 0,
        "w_cm": round(w_cm, 2) if w_cm else 0,
        "h_cm": round(h_cm, 2) if h_cm else 0,
        "weight_ton": round(per_weight_ton or 0, 3),
        "qty": qty,
        "type": _map_cargo_type(body),
        "value_vnd": value_vnd,
    }


def _parse_single_cargo(text: str, vehicles: list) -> dict | None:
    """无编号行时的单货回退解析（'从X发Y，Z吨'）。"""
    gm = re.match(r"(.+?)从", text)
    goods_phrase = ""
    if gm:
        goods_phrase = gm.group(1).strip()
        goods_phrase = re.sub(r"^\d+(?:\.\d+)?\s*(万吨|吨|t|T|kg)?\s*", "", goods_phrase).strip()
        goods_phrase = re.sub(r"^\d+\s*(台|件|个|套|箱|只|部|辆|托)\s*", "", goods_phrase).strip()  # 去数量前缀
        goods_phrase = re.split(r"\s+\d+\s*[xX×*]", goods_phrase)[0].strip()  # 去尾部尺寸/重量/备注
        goods_phrase = re.sub(r"\s*\d+(?:\.\d+)?\s*(毫米|mm|厘米|cm|米|m|吨|t|T|kg).*$", "", goods_phrase).strip()
        goods_phrase = goods_phrase.strip("，,。 、")

    l_cm, w_cm, h_cm = _find_dim("长", text), _find_dim("宽", text), _find_dim("高", text)
    if not (l_cm or w_cm or h_cm):
        dm = re.search(
            r"(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?\s*[xX×*/-]\s*(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?\s*[xX×*/-]\s*(\d+(?:\.\d+)?)\s*(毫米|mm|厘米|cm|公分|米|m)?",
            text,
        )
        if dm:
            a, b, c = float(dm.group(1)), float(dm.group(3)), float(dm.group(5))
            unit = dm.group(2) or dm.group(4) or dm.group(6) or ""
            if unit in ("米", "m"):
                a, b, c = a * 100, b * 100, c * 100
            elif unit in ("毫米", "mm"):
                a, b, c = a / 10, b / 10, c / 10
            elif max(a, b, c) >= 1000:   # 无单位：按量级推断 mm
                a, b, c = a / 10, b / 10, c / 10
            l_cm, w_cm, h_cm = a, b, c

    per_weight_ton = None
    pw = re.search(r"(?:重\s*|每(?:台|件|个|套|箱|托)\s*)?(\d+(?:\.\d+)?)\s*(?:吨|t|T)", text)
    if pw:
        per_weight_ton = float(pw.group(1))
    if per_weight_ton is None:   # kg 支持
        pkg = re.search(r"(?:重\s*|每\s*(?:台|件|个|套|箱|托)\s*)(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤|千克)", text) \
            or re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤|千克)\s*(?:/|每)", text)
        if pkg:
            per_weight_ton = float(pkg.group(1)) / 1000
    qty = 1
    qm = re.search(r"(\d+)\s*(?:台|件|个|套|箱|托)", text)
    if qm:
        qty = int(qm.group(1))
    vp = re.search(r"(\d+(?:\.\d+)?)\s*米\s*(?:车|平板|高栏)|特种设备车", text)
    if vp:
        _merge_vehicles(vehicles, vp.group(0))

    if not (l_cm or w_cm or h_cm or per_weight_ton):
        return None
    return {
        "name": goods_phrase or "货物",
        "l_cm": round(l_cm, 2) if l_cm else 0,
        "w_cm": round(w_cm, 2) if w_cm else 0,
        "h_cm": round(h_cm, 2) if h_cm else 0,
        "weight_ton": round(per_weight_ton or 0, 3),
        "qty": qty,
        "type": _map_cargo_type(text),
        "value_vnd": 0,
    }


def _extract_shipping_request(args: dict) -> str:
    """LLM 结构化提取（首选）→ 归一化；未提供结构化 cargo 时回退正则解析。

    LLM 版：把用户自然语言运输需求直接填成结构化 JobDraft（工具 schema 即此结构），
    本函数只做单位归一化（mm/cm/m → l_cm；kg/吨 → weight_ton）并补默认值。
    """
    cargo = args.get("cargo") if isinstance(args, dict) else None
    if isinstance(cargo, list) and cargo:
        return _normalize_llm_draft(args)
    return _extract_shipping_request_regex(args)


def _normalize_llm_draft(args: dict) -> str:
    """LLM 结构化 JobDraft → 归一化为前端任务卡字段（l_cm/w_cm/h_cm/weight_ton/qty/type/value_vnd）。"""
    dim_unit = (args.get("dim_unit") or "cm").lower()
    if dim_unit not in ("mm", "cm", "m"):
        dim_unit = "cm"

    # 单件：长度→厘米换算因子（mm→cm=0.1；cm→cm=1；m→cm=100）；重量→吨
    def to_cm(v):
        if v is None:
            return 0
        if dim_unit == "mm":
            return v * 0.1
        if dim_unit == "m":
            return v * 100
        return v

    def pick(item, *keys):
        for k in keys:
            if item.get(k) is not None:
                return item[k]
        return None

    cargo = []
    for it in args["cargo"]:
        # 长度/宽/高：优先明确后缀字段，否则按 dim_unit 解释
        l = pick(it, "length_cm") if it.get("length_cm") is not None else to_cm(pick(it, "length", "length_m", "l", "l_cm"))
        w = pick(it, "width_cm") if it.get("width_cm") is not None else to_cm(pick(it, "width", "width_m", "w", "w_cm"))
        h = pick(it, "height_cm") if it.get("height_cm") is not None else to_cm(pick(it, "height", "height_m", "h", "h_cm"))
        # 重量→吨
        wt = pick(it, "weight_ton", "weight_t")
        if wt is None and it.get("weight_kg") is not None:
            wt = it["weight_kg"] / 1000.0
        if wt is None and it.get("weight") is not None:
            wt = it["weight"]
        raw_type = (it.get("type") or "").strip().lower()
        type_val = raw_type if raw_type in _VALID_CARGO_TYPES else _map_cargo_type(it.get("name") or "")
        cargo.append({
            "name": (it.get("name") or "货物"),
            "l_cm": round(l, 2) if l else 0,
            "w_cm": round(w, 2) if w else 0,
            "h_cm": round(h, 2) if h else 0,
            "weight_ton": round(float(wt or 0), 3),
            "qty": int(it.get("count") or it.get("qty") or 1),
            "type": type_val,
            "value_vnd": float(it.get("value_vnd") or 0),
        })

    result = {
        "origin": (args.get("origin") or "").strip(),
        "destination": (args.get("destination") or "").strip(),
        "borderCrossing": (args.get("borderCrossing") or "友谊关").strip(),
        "cargo": cargo,
        "vehicle_preference": (args.get("vehicle_preference") or "").strip(),
        "loading_mode": args.get("loading_mode") or "full_truck",
        "requirement": (args.get("requirement") or "").strip(),
        "dim_unit": dim_unit,
    }
    missing = []
    if not result["origin"]:
        missing.append("出发点")
    if not result["destination"]:
        missing.append("目的地")
    if not result["cargo"]:
        missing.append("货物")
    result["maybe_missing"] = missing
    return json.dumps(result, ensure_ascii=False)


def _extract_shipping_request_regex(args: dict) -> str:
    """把用户自然语言运输需求解析为结构化 JobDraft JSON（吨单位）。

    支持多行多货物（'N、货物名（长×宽×高）：A×B×C,重WT/台，QTY台（车型）' 逐行多条），
    并从「越南收货地址/收货地址」行提取目的地。发车地/目的地等缺失时返回 maybe_missing。
    """
    text = args.get("text", "")
    result = {
        "origin": "",
        "destination": "",
        "borderCrossing": "友谊关",
        "cargo": [],
        "vehicle_preference": "",
        "loading_mode": "full_truck",
        "requirement": "",
        "dim_unit": "cm",
        "maybe_missing": [],
    }
    if not text:
        result["maybe_missing"] = ["出发点", "目的地", "货物"]
        return json.dumps(result, ensure_ascii=False)

    # ── 口岸（默认友谊关）──
    for bw in _BORDER_KEYWORDS:
        if bw in text:
            result["borderCrossing"] = bw
            break

    # ── 路线：从...经...到... / 从...到... ──
    route_m = re.search(r"从(.+?)(?:经(.+?))?到(.+?)(?:[，,。；;?？\n]|$)", text)
    if route_m:
        result["origin"] = route_m.group(1).strip()
        if route_m.group(2):
            result["borderCrossing"] = route_m.group(2).strip()
        result["destination"] = route_m.group(3).strip()
    else:
        m2 = re.search(r"([^，,。；;\n]+?)到([^，,。；;\n]+?)(?:[，,。；;?？\n]|$)", text)
        if m2:
            result["origin"] = m2.group(1).strip()
            result["destination"] = m2.group(2).strip()

    # 清洗发车地尾缀/动词
    origin_raw = re.sub(r"(发货|发往|运往|运至|发车)$", "", result["origin"]).strip()
    result["origin"] = re.split(r"[运发载送]", origin_raw)[0].strip()

    # ── 目的地：优先从「越南收货地址/收货地址/地址」行提取 ──
    addr_m = re.search(r"(?:越南收货地址|收货地址|收货地|地址)[：:]?\s*([^\n，。]+)", text)
    if addr_m and addr_m.group(1).strip():
        result["destination"] = addr_m.group(1).strip()
    else:
        result["destination"] = re.sub(
            r"(?:危险品|冷链|冷藏|设备|货物|机器|配件)?\s*\d+(?:\.\d+)?\s*(?:吨|t|T|kg|件|台|个)$",
            "", result["destination"],
        ).strip()

    # ── 货物清单：全局按编号切块（兼容单行/多行、跳号）──
    vehicles: list = []
    result["cargo"] = _parse_cargo_items(text, vehicles)

    # 无编号行 → 单货回退
    if not result["cargo"]:
        old = _parse_single_cargo(text, vehicles)
        if old:
            result["cargo"].append(old)

    # ── 车型偏好：去重合并 ──
    result["vehicle_preference"] = " + ".join(dict.fromkeys(vehicles)) if vehicles else ""

    # ── 运输模式 ──
    if any(k in text for k in ("拼货", "散货", "零担", "拼柜")):
        result["loading_mode"] = "consolidated"

    # ── 用户诉求 ──
    reqs = []
    if any(k in text for k in ("报价", "询价", "多少钱", "价格", "费用", "运费")):
        reqs.append("报价")
    if any(k in text for k in ("时效", "多久", "几天", "多长时间", "时间")):
        reqs.append("时效")
    if any(k in text for k in ("装得下", "装不下", "能不能装", "可不可装", "装不装得下", "可否装")):
        reqs.append("是否装得下")
    if any(k in text for k in ("全程", "中国段", "越南段", "口岸", "报关", "吊车", "杂费", "海关")):
        reqs.append("全程费用")
    if not reqs:
        reqs.append("报价")
    result["requirement"] = "+".join(reqs)

    # ── 缺失字段 ──
    missing = []
    if not result["origin"]:
        missing.append("出发点")
    if not result["destination"]:
        missing.append("目的地")
    if not result["cargo"]:
        missing.append("货物")
    result["maybe_missing"] = missing
    result["dim_unit"] = _infer_dim_unit(text)   # 🆕 AI 自动检测尺寸单位（mm/cm/m）

    return json.dumps(result, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
# v006 能力注册（声明在 app/ai/spec.py —— 唯一真源）
#   加新工具：① spec.py 加一条 CapabilitySpec ② 这里注册执行器；schema/提示/审计自动跟上。
# ══════════════════════════════════════════════════════════════
_registry.register_executor("calculate_freight_cost", _calc_cost)
_registry.register_executor("calculate_border_fees", _calc_border_fees)
_registry.register_executor("query_vehicle_models", _query_vehicles)
_registry.register_executor("query_vehicle_count", _query_vehicle_count)
_registry.register_executor("compare_routes", _compare_routes)
_registry.register_executor("geocode_address", _geocode)
_registry.register_executor("query_exchange_rate", _query_exchange_rate)
_registry.register_executor("extract_shipping_request", _extract_shipping_request)

# LLM 的 tools（与 v005 手写版逐字节等价，见 tests/test_capabilities.py）
TOOLS = _registry.tool_schemas(locality="backend")
