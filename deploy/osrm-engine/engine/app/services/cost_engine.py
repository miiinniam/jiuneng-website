"""费用计算引擎 —— 工程性的组装逻辑（车型库查找、货物类型校验、异常处理、结果组装）。

真正的计算公式（阈值、系数、公式结构）都在同目录下的
`费用计算公式.py` 里，以后调整报价规则只改那一个文件；
这个文件不涉及具体数字，改动车型查找方式/拼货整车编排逻辑才需要动这里。

拼货（consolidated）/整车（full_truck）两种模式共用同一套核心公式：先按"整车口径"
算出各项费用（就是假设这一趟车全部归这批货物专用），拼货模式再对其中"整趟车"性质的
费用（距离/时间/油耗/路桥/三项路况附加费/车型固定附加费）统一乘 capacity_ratio 做分摊，
"本单专属"费用（装卸费/保险费/misc）不打折——整车模式 capacity_ratio 恒为 1.0，
是拼货公式的特例，两种模式因此可以共用同一个 _compute_for_model 核心函数。

已知的模型简化：拼货模式下的速度惩罚/运力占比只按"这一批货物自己的重量体积"计算，
不建模"同一辆车上可能还装着其他货主的货物"——系统拿不到其他货主的数据，这是当前版本
的天然局限。

版本: 与 费用计算公式.py 同步（见该文件版本历史），编排层本身无独立公式版本。
      2026-07-03: 整车模式新增超载校验、变量重命名 cargo_rate_multiplier、油耗叠加注释
"""

from dataclasses import dataclass, field

from app.services import 费用计算公式 as 公式
from app.services.presets import CARGO_TYPE_RATES
from app.services.vehicle_registry import VEHICLE_MODELS, VehicleModel, get_model


class UnknownVehicleModel(ValueError):
    pass


class UnknownCargoType(ValueError):
    pass


class NoFittingVehicleModel(ValueError):
    """拼货模式下，没有任何车型库中的型号能装下这批货物。"""


@dataclass
class RouteTiming:
    speed_factor: float
    adjusted_duration_h: float
    rest_hours: float
    loading_hours: float
    total_duration_h: float


@dataclass
class CostBreakdown:
    cost_distance: float
    cost_time: float
    cost_fuel: float
    cost_loading: float
    cost_insurance: float
    cost_toll: float
    cost_misc: float
    cost_body_surcharge: float
    cost_restricted_zone: float
    cost_construction_zone: float
    cost_mountain_road: float
    cost_port: float
    cost_fixed: float
    cost_total: float
    cost_per_km: float
    cost_per_ton_km: float | None
    capacity_ratio: float  # 整车恒为1.0；拼货是实际占比
    matched_vehicle_model_id: str
    matched_vehicle_model_name: str


@dataclass
class CostResult:
    distance_km: float
    timing: RouteTiming
    breakdown: CostBreakdown
    suggestions: list[str] = field(default_factory=list)


def _build_suggestions(
    *,
    load_ratio: float,
    empty_return: bool,
    rest_hours: float,
    cargo_type: str,
    model: VehicleModel,
    avoid_restricted_zones: bool,
    avoid_construction_zones: bool,
    via_mountain_road: bool,
    via_port: bool = False,
) -> list[dict]:
    """返回结构化建议码列表，前端根据 locale 渲染本地化文案。

    每个元素: {"code": str, "params": dict}
    - code: 前端 i18n 查找键
    - params: 动态参数（如 cargo_type 标签），无参数时为空 dict
    """
    suggestions: list[dict] = []
    if load_ratio > 0.8:
        suggestions.append({"code": "heavy_load", "params": {}})
    if empty_return:
        suggestions.append({"code": "empty_return_charged", "params": {}})
    if rest_hours >= 8:
        suggestions.append({"code": "overnight_rest", "params": {}})
    if cargo_type not in ("normal", "other") and cargo_type not in model.suitable_cargo_types:
        suggestions.append({"code": "mismatched_cargo", "params": {"cargoType": cargo_type}})
    if avoid_restricted_zones:
        suggestions.append({"code": "restricted_zone", "params": {}})
    if avoid_construction_zones:
        suggestions.append({"code": "construction_zone", "params": {}})
    if via_mountain_road:
        suggestions.append({"code": "mountain_road", "params": {}})
    if via_port:
        suggestions.append({"code": "port_destination", "params": {}})
    return suggestions


def _compute_for_model(
    *,
    model: VehicleModel,
    capacity_ratio: float,
    distance_m: float,
    duration_s: float,
    cargo_weight_ton: float,
    cargo_type: str,
    empty_return: bool,
    need_loading: bool,
    avoid_restricted_zones: bool,
    avoid_construction_zones: bool,
    via_mountain_road: bool,
    via_port: bool = False,
    fuel_price_vnd: float,
    wage_hourly_vnd: float,
    cargo_value_vnd: float | None,
    toll_rate_vnd_per_km: float | None,
    misc_cost_vnd: float,
    loading_rate_vnd_per_ton: float,
    insurance_rate: float,
) -> tuple[RouteTiming, CostBreakdown]:
    """给定一个已经匹配好的车型 + capacity_ratio，算出完整的费用明细。

    整车模式调用时 capacity_ratio 恒为 1.0；拼货模式由调用方（自动匹配循环）传入实际占比。
    """
    cargo = CARGO_TYPE_RATES.get(cargo_type)
    if cargo is None:
        raise UnknownCargoType(cargo_type)

    d_km = distance_m / 1000
    t_raw_h = duration_s / 3600
    load_ratio = cargo_weight_ton / model.max_load_ton if model.max_load_ton else 0.0

    speed_factor, adjusted_duration_h, rest_hours, loading_hours, total_duration_h = 公式.计算总用时(
        载重比例=load_ratio,
        原始行驶小时=t_raw_h,
        货物重量吨=cargo_weight_ton,
        需要装卸=need_loading,
    )

    timing = RouteTiming(
        speed_factor=speed_factor,
        adjusted_duration_h=adjusted_duration_h,
        rest_hours=rest_hours,
        loading_hours=loading_hours,
        total_duration_h=total_duration_h,
    )

    # cargo_rate_multiplier 只来自货物类型——车型的差异化已经直接体现在
    # base_rate_vnd_per_km 这个具体数字里，不再需要"吨位档位 x 车身系数"的二维乘积
    cargo_rate_multiplier = cargo.rate_multiplier
    # 油耗附加是货物类型和车辆两者叠加（不是取最大值）：
    #   - 货物类型 fuel_penalty：冷链/危险品货物本身需要的额外油耗（温控、安全措施）
    #   - 车辆 fuel_penalty：冷链车制冷机组、特种车身设备的额外油耗
    #   例：冷链货物(0.20) + 油冷冷链车(0.25) = 0.45 总燃油附加
    combined_fuel_penalty = cargo.fuel_penalty + model.fuel_penalty

    # 先按整车口径算出 _full 版本
    cost_distance_full = 公式.距离成本(d_km, model.base_rate_vnd_per_km, cargo_rate_multiplier, empty_return)
    cost_time_full = 公式.时间成本(total_duration_h, wage_hourly_vnd)
    cost_fuel_full = 公式.油耗成本(d_km, model.fuel_l_per_100km, fuel_price_vnd, load_ratio, combined_fuel_penalty)
    toll_rate = toll_rate_vnd_per_km if toll_rate_vnd_per_km is not None else model.toll_rate_vnd_per_km
    cost_toll_full = 公式.路桥费(d_km, toll_rate)
    cost_body_surcharge_full = 公式.车身附加费(model.fixed_surcharge_vnd)
    cost_port_full = 公式.港口附加费(model.fixed_surcharge_vnd, via_port)
    cost_restricted_zone_full = 公式.禁限行绕行费(
        公式.禁限行绕行基础费_vnd, cargo_rate_multiplier, avoid_restricted_zones
    )
    cost_construction_zone_full = 公式.施工封闭绕行费(
        公式.施工封闭绕行基础费_vnd, cargo_rate_multiplier, avoid_construction_zones
    )
    cost_mountain_road_full = 公式.上坡山区附加费(
        公式.上坡山区附加基础费_vnd, cargo_rate_multiplier, via_mountain_road
    )

    # 再对"整趟车"性质的费用打 capacity_ratio（整车模式 ratio=1.0，等价于不打折）
    cost_distance = cost_distance_full * capacity_ratio
    cost_time = cost_time_full * capacity_ratio
    cost_fuel = cost_fuel_full * capacity_ratio
    cost_toll = cost_toll_full * capacity_ratio
    cost_body_surcharge = cost_body_surcharge_full * capacity_ratio
    cost_restricted_zone = cost_restricted_zone_full * capacity_ratio
    cost_construction_zone = cost_construction_zone_full * capacity_ratio
    cost_mountain_road = cost_mountain_road_full * capacity_ratio
    cost_port = cost_port_full * capacity_ratio

    # "本单专属"费用，不打折：
    cost_loading = 公式.装卸费(cargo_weight_ton, loading_rate_vnd_per_ton, need_loading)
    cost_insurance = 公式.保险费(cargo_value_vnd, insurance_rate)

    cost_fixed = (
        cost_loading
        + cost_insurance
        + cost_toll
        + cost_body_surcharge
        + cost_restricted_zone
        + cost_construction_zone
        + cost_mountain_road
        + cost_port
        + misc_cost_vnd
    )
    cost_total = cost_distance + cost_time + cost_fuel + cost_fixed

    breakdown = CostBreakdown(
        cost_distance=cost_distance,
        cost_time=cost_time,
        cost_fuel=cost_fuel,
        cost_loading=cost_loading,
        cost_insurance=cost_insurance,
        cost_toll=cost_toll,
        cost_misc=misc_cost_vnd,
        cost_body_surcharge=cost_body_surcharge,
        cost_restricted_zone=cost_restricted_zone,
        cost_construction_zone=cost_construction_zone,
        cost_mountain_road=cost_mountain_road,
        cost_port=cost_port,
        cost_fixed=cost_fixed,
        cost_total=cost_total,
        cost_per_km=cost_total / d_km if d_km > 0 else 0.0,
        cost_per_ton_km=(cost_total / (d_km * cargo_weight_ton)) if d_km > 0 and cargo_weight_ton > 0 else None,
        capacity_ratio=capacity_ratio,
        matched_vehicle_model_id=model.model_id,
        matched_vehicle_model_name=model.display_name,
    )
    return timing, breakdown


def compute_cost_full_truck(
    *,
    distance_m: float,
    duration_s: float,
    cargo_weight_ton: float,
    vehicle_model_id: str,
    cargo_type: str = "normal",
    empty_return: bool = False,
    need_loading: bool = False,
    avoid_restricted_zones: bool = False,
    avoid_construction_zones: bool = False,
    via_mountain_road: bool = False,
    via_port: bool = False,
    fuel_price_vnd: float,
    wage_hourly_vnd: float,
    cargo_value_vnd: float | None = None,
    toll_rate_vnd_per_km: float | None = None,
    misc_cost_vnd: float = 0.0,
    loading_rate_vnd_per_ton: float,
    insurance_rate: float,
    cargo_items: list[dict] | None = None,  # 🆕 单件货物明细（长件/面积约束）
) -> CostResult:
    """整车一口价模式：距离 × 全包基价 + 各项附加费。

    与拼货模式不同，整车不再把成本拆成"距离/时间/油耗"三项——
    基价每公里（base_rate_vnd_per_km）本身就是通过供应商真实报价
    反算出来的全包费率，已经隐含了油耗、司机工资等全部成本。
    """
    model = get_model(vehicle_model_id)
    if model is None:
        raise UnknownVehicleModel(vehicle_model_id)
    # 多车拆分由上层 API / AI 工具负责，这里不抛异常
    # 上层会在调用前将重量除以车辆数，保证 per-vehicle weight ≤ max_load_ton
    cargo = CARGO_TYPE_RATES.get(cargo_type)
    if cargo is None:
        raise UnknownCargoType(cargo_type)

    d_km = distance_m / 1000
    load_ratio = cargo_weight_ton / model.max_load_ton if model.max_load_ton else 0.0

    # 时间仅做建议用（休息提醒等），不参与成本计算
    _sf, _adj, rest_h, loading_h, total_duration_h = 公式.计算总用时(
        载重比例=load_ratio,
        原始行驶小时=duration_s / 3600,
        货物重量吨=cargo_weight_ton,
        需要装卸=need_loading,
    )
    timing = RouteTiming(
        speed_factor=_sf,
        adjusted_duration_h=_adj,
        rest_hours=rest_h,
        loading_hours=loading_h,
        total_duration_h=total_duration_h,
    )

    toll_rate = toll_rate_vnd_per_km if toll_rate_vnd_per_km is not None else model.toll_rate_vnd_per_km

    # 各项附加费（按整车全额）
    # fixed_surcharge_vnd 在整车模式下有两种角色：
    #   1. 需要装卸(need_loading=True)：整个 fixed_surcharge 视为装卸费（小卡车/高栏车的
    #      调度费本质就是装卸+出车费，不应再重复计车身附加费）
    #   2. 不需要装卸(need_loading=False)：fixed_surcharge 作为车身附加费（冷链机组维护等）
    路桥 = 公式.路桥费(d_km, toll_rate)
    车身 = 0.0 if need_loading else 公式.车身附加费(model.fixed_surcharge_vnd)
    禁限行 = 公式.禁限行绕行费(公式.禁限行绕行基础费_vnd, cargo.rate_multiplier, avoid_restricted_zones)
    施工 = 公式.施工封闭绕行费(公式.施工封闭绕行基础费_vnd, cargo.rate_multiplier, avoid_construction_zones)
    山区 = 公式.上坡山区附加费(公式.上坡山区附加基础费_vnd, cargo.rate_multiplier, via_mountain_road)
    港口 = 公式.港口附加费(model.fixed_surcharge_vnd, via_port)
    装卸 = model.fixed_surcharge_vnd if need_loading else 0.0  # 整车不按吨计费（重量仅做超载校验）
    保险 = 公式.保险费(cargo_value_vnd, insurance_rate)

    # 整车总成本 = 距离 × 全包基价 + 所有附加费
    # 注：整车基价已包含装卸成本，装卸费仅在用户主动勾选 need_loading 时
    # 按车型固定附加费收取（不按货物重量），避免重复计费
    cost_total = 公式.整车总成本(
        距离公里=d_km,
        基价每公里=model.base_rate_vnd_per_km,
        货物类型系数=cargo.rate_multiplier,
        空车返回=empty_return,
        路桥费_vnd=路桥,
        车身附加费_vnd=车身,
        禁限行附加=禁限行,
        施工封闭附加=施工,
        上坡山区附加=山区,
        港口附加=港口,
        装卸费_vnd=装卸,
        保险费_vnd=保险,
        杂费_vnd=misc_cost_vnd,
    )

    # 距离成本 = 总成本扣除各项附加费后的剩余（即纯"距离×基价"部分）
    cost_distance = 公式.距离成本(d_km, model.base_rate_vnd_per_km, cargo.rate_multiplier, empty_return)

    cost_fixed = 路桥 + 车身 + 禁限行 + 施工 + 山区 + 港口 + 装卸 + 保险 + misc_cost_vnd

    breakdown = CostBreakdown(
        cost_distance=cost_distance,
        cost_time=0.0,   # 整车模式不拆分时间/油耗，这两个填0
        cost_fuel=0.0,
        cost_loading=装卸,
        cost_insurance=保险,
        cost_toll=路桥,
        cost_misc=misc_cost_vnd,
        cost_body_surcharge=车身,
        cost_restricted_zone=禁限行,
        cost_construction_zone=施工,
        cost_mountain_road=山区,
        cost_port=港口,
        cost_fixed=cost_fixed,
        cost_total=cost_total,
        cost_per_km=cost_total / d_km if d_km > 0 else 0.0,
        cost_per_ton_km=(cost_total / (d_km * cargo_weight_ton)) if d_km > 0 and cargo_weight_ton > 0 else None,
        capacity_ratio=1.0,
        matched_vehicle_model_id=model.model_id,
        matched_vehicle_model_name=model.display_name,
    )

    suggestions = _build_suggestions(
        load_ratio=load_ratio,
        empty_return=empty_return,
        rest_hours=rest_h,
        cargo_type=cargo_type,
        model=model,
        avoid_restricted_zones=avoid_restricted_zones,
        avoid_construction_zones=avoid_construction_zones,
        via_mountain_road=via_mountain_road,
        via_port=via_port,
    )
    return CostResult(distance_km=d_km, timing=timing, breakdown=breakdown, suggestions=suggestions)


def compute_vehicle_count(
    *,
    model: VehicleModel,
    cargo_weight_ton: float,
    cargo_volume_m3: float | None = None,
    cargo_items: list[dict] | None = None,
) -> int:
    """🆕 计算运输这批货物需要几辆车（四约束取最大值）。

    权重/体积/长件/面积 四约束见 费用计算公式.所需车辆数()。
    使用车型的：
    - max_load_ton（载重）
    - effective_volume_m3（有效容积：厢式=volume_capacity；平板=面积×堆高）
    - floor_area_m2（地板面积）
    - length_m（地板长）
    - loading_efficiency（装载效率）
    """
    return vehicle_count_breakdown(
        model=model,
        cargo_weight_ton=cargo_weight_ton,
        cargo_volume_m3=cargo_volume_m3,
        cargo_items=cargo_items,
    )["车数"]


def vehicle_count_breakdown(
    *,
    model: VehicleModel,
    cargo_weight_ton: float,
    cargo_volume_m3: float | None = None,
    cargo_items: list[dict] | None = None,
) -> dict:
    """🆕 四约束车辆数「分解」（与 compute_vehicle_count 同一套公式，多了中间量）。

    返回值 = 费用计算公式.车辆数分解() 的 dict：
      {车数, 重量, 体积, 长度, 面积, 主因, 不可分, 最大单件重量吨, 车型最大载重吨}
    - 前端用「重量/体积/长度/面积/主因」做「为什么 N 辆」透明展示；
    - `不可分=True`（单件重量 > 车型载重）→ API 层做**超限处置**：
      越南公路 >38t 属超限运输，不静默拆成多辆普通车出假价。
    """
    feat = 公式.货物载荷特征完整(
        货物总重量吨=cargo_weight_ton,
        货物总体积立方米=cargo_volume_m3,
        单件货物=cargo_items,
    )
    return 公式.车辆数分解(
        货物总重量吨=cargo_weight_ton,
        货物总体积立方米=cargo_volume_m3,
        最大单件长度米=feat["最大单件长度米"],
        货物总占地面积平方米=feat["总占地面积平方米"],
        车型最大载重吨=model.max_load_ton,
        车型容积立方米=model.effective_volume_m3,
        车型地板长米=model.length_m,
        车型地板面积平方米=model.floor_area_m2,
        装载效率=model.loading_efficiency,
        最大单件重量吨=feat["最大单件重量吨"],
    )


def match_consolidated_model(
    *,
    cargo_weight_ton: float,
    cargo_volume_m3: float,
    distance_m: float,
    duration_s: float,
    cargo_type: str = "normal",
    empty_return: bool = False,
    need_loading: bool = False,
    avoid_restricted_zones: bool = False,
    avoid_construction_zones: bool = False,
    via_mountain_road: bool = False,
    via_port: bool = False,
    cargo_items: list[dict] | None = None,  # 🆕 单件货物明细（长件/面积约束）
    fuel_price_vnd: float,
    wage_hourly_vnd: float,
    cargo_value_vnd: float | None = None,
    toll_rate_vnd_per_km: float | None = None,
    misc_cost_vnd: float = 0.0,
    loading_rate_vnd_per_ton: float,
    insurance_rate: float,
) -> tuple[VehicleModel, RouteTiming, CostBreakdown]:
    """拼货自动匹配的核心循环——独立导出，calibration.py 复用同一个函数，
    避免正算和反算各写一份匹配算法后来跑偏。

    在所有能装下这批货物的车型里，选总价最低的一个。
    复杂度 O(N)，N=车型库行数，纯内存计算，distance/duration 是外部一次性传入的路由结果，
    不会在循环里重复调用 OSRM。
    """
    cargo = CARGO_TYPE_RATES.get(cargo_type)
    if cargo is None:
        raise UnknownCargoType(cargo_type)

    # 🆕 单件载荷特征：最大单件长 + 不可堆叠件占地面积
    最大单件长, 占地面积 = 公式.货物载荷特征(
        货物总重量吨=cargo_weight_ton,
        货物总体积立方米=cargo_volume_m3,
        单件货物=cargo_items,
    )

    candidates = [
        m
        for m in VEHICLE_MODELS
        if cargo_weight_ton <= m.max_load_ton
        and (m.effective_volume_m3 is None or cargo_volume_m3 <= m.effective_volume_m3 * m.loading_efficiency)
        # 🆕 长件约束：单件最长 > 地板长 → 排除
        and (最大单件长 is None or m.length_m is None or 最大单件长 <= m.length_m)
        # 🆕 面积约束：不可堆叠件占地 > 地板面积×效率 → 排除
        and (占地面积 is None or m.floor_area_m2 is None
             or 占地面积 <= m.floor_area_m2 * m.loading_efficiency)
    ]
    if not candidates:
        raise NoFittingVehicleModel(
            f"没有能装下这批货物的车型（重量{cargo_weight_ton}吨/体积{cargo_volume_m3}立方米），"
            "可能需要拆分或联系整车专线"
        )

    best_timing: RouteTiming | None = None
    best_breakdown: CostBreakdown | None = None
    best_model: VehicleModel | None = None
    for model in candidates:
        ratio = 公式.容量占比(cargo_weight_ton, cargo_volume_m3, model.max_load_ton, model.volume_capacity_m3)
        timing, breakdown = _compute_for_model(
            model=model,
            capacity_ratio=ratio,
            distance_m=distance_m,
            duration_s=duration_s,
            cargo_weight_ton=cargo_weight_ton,
            cargo_type=cargo_type,
            empty_return=empty_return,
            need_loading=need_loading,
            avoid_restricted_zones=avoid_restricted_zones,
            avoid_construction_zones=avoid_construction_zones,
            via_mountain_road=via_mountain_road,
            via_port=via_port,
            fuel_price_vnd=fuel_price_vnd,
            wage_hourly_vnd=wage_hourly_vnd,
            cargo_value_vnd=cargo_value_vnd,
            toll_rate_vnd_per_km=toll_rate_vnd_per_km,
            misc_cost_vnd=misc_cost_vnd,
            loading_rate_vnd_per_ton=loading_rate_vnd_per_ton,
            insurance_rate=insurance_rate,
        )
        if best_breakdown is None or breakdown.cost_total < best_breakdown.cost_total:
            best_timing, best_breakdown, best_model = timing, breakdown, model

    assert best_timing is not None and best_breakdown is not None and best_model is not None
    return best_model, best_timing, best_breakdown


def compute_cost_consolidated(
    *,
    distance_m: float,
    duration_s: float,
    cargo_weight_ton: float,
    cargo_volume_m3: float,
    cargo_type: str = "normal",
    empty_return: bool = False,
    need_loading: bool = False,
    avoid_restricted_zones: bool = False,
    avoid_construction_zones: bool = False,
    via_mountain_road: bool = False,
    via_port: bool = False,
    cargo_items: list[dict] | None = None,  # 🆕 单件货物明细（长件/面积约束）
    fuel_price_vnd: float,
    wage_hourly_vnd: float,
    cargo_value_vnd: float | None = None,
    toll_rate_vnd_per_km: float | None = None,
    misc_cost_vnd: float = 0.0,
    loading_rate_vnd_per_ton: float,
    insurance_rate: float,
) -> CostResult:
    best_model, best_timing, best_breakdown = match_consolidated_model(
        cargo_weight_ton=cargo_weight_ton,
        cargo_volume_m3=cargo_volume_m3,
        distance_m=distance_m,
        duration_s=duration_s,
        cargo_type=cargo_type,
        empty_return=empty_return,
        need_loading=need_loading,
        avoid_restricted_zones=avoid_restricted_zones,
        avoid_construction_zones=avoid_construction_zones,
        via_mountain_road=via_mountain_road,
        via_port=via_port,
        cargo_items=cargo_items,
        fuel_price_vnd=fuel_price_vnd,
        wage_hourly_vnd=wage_hourly_vnd,
        cargo_value_vnd=cargo_value_vnd,
        toll_rate_vnd_per_km=toll_rate_vnd_per_km,
        misc_cost_vnd=misc_cost_vnd,
        loading_rate_vnd_per_ton=loading_rate_vnd_per_ton,
        insurance_rate=insurance_rate,
    )

    load_ratio = cargo_weight_ton / best_model.max_load_ton if best_model.max_load_ton else 0.0
    suggestions = _build_suggestions(
        load_ratio=load_ratio,
        empty_return=empty_return,
        rest_hours=best_timing.rest_hours,
        cargo_type=cargo_type,
        model=best_model,
        avoid_restricted_zones=avoid_restricted_zones,
        avoid_construction_zones=avoid_construction_zones,
        via_mountain_road=via_mountain_road,
    )
    suggestions.append({
        "code": "consolidated_match",
        "params": {
            "modelName": best_model.display_name,
            "capacityPct": f"{best_breakdown.capacity_ratio:.0%}",
        },
    })
    return CostResult(
        distance_km=distance_m / 1000, timing=best_timing, breakdown=best_breakdown, suggestions=suggestions
    )
