"""v020 T-D：按配车计划的**逐行车型**计价（逐行闸门 → 逐行计费 → 整票求和）。

为什么（2026-09-29 用户实报「一批重件算不出价」）
--------------------------------------------------
配车侧 `POST /reference/fit-vehicles` 已给出逐行车型（转轮→低平板 13米 40吨、主轴/1-2顶盖→
抽拉式低平板 60吨、定子机座/底环→低平板 17.5米、桥机大梁→抽拉伸缩板 80吨 30米、
球阀→模块车 150吨、主变压器→模块车 250吨），车数 60（OFF 计划）；
但计价侧只拿**一款车**（`vehicle.vehicle_model_id` = 任务卡车型「大件加宽低平板 60吨 13米」）
去核整票 ⇒ 225 t 主变压器撞「超载不可放行」422 ⇒ **整票算不出价**（v018 已改文案、未改口径）。
用户拍板口径：**每行用它自己的计划车型算，整票 = 各行之和**（与装车/配车同源）。

铁律（INV-2）
-------------
本文件**不实现任何公式、也不自己数车**：
- 车数一律来自 `cost_engine.vehicle_count_breakdown()`（内部 `费用计算公式.车辆数分解()`）；
- 金额一律来自 `cost_engine.compute_cost_full_truck()`（内部 `费用计算公式`）；
- 本文件只做「逐行编排 + 逐项相加 + 口径换算（整票 ↔ 单车）」三件纯编排的事。

口径说明（两条都影响上层响应，改前先读）
----------------------------------------
1. **单车口径**：现路径的 `_compute_from_request()` 返回的就是「单车费用」，上层
   `build_quote_response()` 会把它的每个金额项 × 车辆数。逐行模式沿用这条约定：
   本模块给出**整票**（`LinePricePlan.total` = Σ(该行费用 × 该行台数)），调用方用
   `scale_cost_result(total, 1/计划车数)` 换成单车口径；响应金额（金额 × 车数）因此
   **恒等于整票之和**（数值级），不因多一层换算而失真。
2. **无计划车型的行**：配车计划可能给出 `model: null` 的行（实测：1/2座环「库内无车可载：
   超宽 4.98m 超可运上限 4.5m ⇒ 需 T5 特批/专询 ⇒ 需拆运或专线询价」）。
   这些行**不参与逐行计价**（没有车型就没有"这台车装不下"可判、也没有费率可计），
   由调用方在结果里点名（本模块的 `LinePricePlan.excluded` + `unpriced_lines` 提示码），
   现实处置＝专线趟价（`manual_oversize_fee_vnd`，实报实销）或拆件后重配。
3. 🆕 T-D2（**整票 = 配车计划**，2026-09-29 用户拍板）：逐行模式的两处口径可被**计划值**覆盖，
   与配车侧 `groups[].items[]` 同源：
   - `items[].vehicle_count`（>0）⇒ 该行台数**直接用计划值**（不再跑车数分解）。
     与 INV-2 **不冲突**：INV-2 管的是「不许自创车数算法」——此处是**采纳配车计划已经算出的台数**
     （计划侧同样出自 `车辆数分解()` + 件守恒下限），不是本文件新立算法；
   - `items[].piece_weight_kg`（>0）⇒ 逐行闸门用**它**当「单件重量」（分瓣行的真实单片，
     如底环 55t 分 2 瓣 ⇒ 单片 27.5t）。闸门判的是「这一件装不装得下这台车」——
     计划按分瓣后单片配车，计价就该按**同一件**判（否则分瓣行被按整件重假 422 拦死）。
   两者**全部缺省** ⇒ 行为与 T-D2 之前**逐字节不变**（台数 = 车数分解，单件重 = 行内 `weight_kg`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.cost_engine import (
    CostBreakdown,
    CostResult,
    RouteTiming,
    UnknownVehicleModel,
    compute_cost_full_truck,
    vehicle_count_breakdown,
)
from app.services.vehicle_registry import VehicleModel, get_model

#: CostBreakdown 里全部**金额**字段（逐项相加用；`cost_engine.CostBreakdown` 加字段时必须同步）
_SUM_FIELDS: tuple[str, ...] = (
    "cost_distance",
    "cost_time",
    "cost_fuel",
    "cost_loading",
    "cost_insurance",
    "cost_toll",
    "cost_misc",
    "cost_body_surcharge",
    "cost_restricted_zone",
    "cost_construction_zone",
    "cost_mountain_road",
    "cost_port",
    "cost_fixed",
    "cost_total",
)


# ── 判定入口 ────────────────────────────────────────────────────────────

def has_line_models(cargo_items: list[dict] | None) -> bool:
    """逐行模式的判定入口：**任一项**带 `vehicle_model_id` ⇒ True（缺省全空 ⇒ False）。"""
    for item in cargo_items or []:
        if str((item or {}).get("vehicle_model_id") or "").strip():
            return True
    return False


# ── 逐行口径（与 fleet_planner 的逐行口径一致，保证与配车同源） ─────────

def line_weight_ton(item: dict) -> float:
    """该行吨位 = 单件重(kg) × 件数 ÷ 1000。"""
    return float((item or {}).get("weight_kg") or 0) * int((item or {}).get("count") or 1) / 1000.0


def line_volume_m3(item: dict) -> float:
    """该行体积 = 长 × 宽 × 高 × 件数（缺高按 0，与 `fleet_planner` 逐行口径一致）。"""
    it = item or {}
    return (float(it.get("length_m") or 0) * float(it.get("width_m") or 0)
            * float(it.get("height_m") or 0) * int(it.get("count") or 1))


def line_breakdown(item: dict, model: VehicleModel) -> dict:
    """该行 × 该行车型的四约束分解（INV-2：车数只出自 `车辆数分解()`）。"""
    return vehicle_count_breakdown(
        model=model,
        cargo_weight_ton=line_weight_ton(item),
        cargo_volume_m3=line_volume_m3(item),
        cargo_items=[item],
    )


# ── 🆕 T-D2：计划值取用点（`vehicle_count` / `piece_weight_kg`；缺省 ⇒ 旧口径逐字节不变）──

def line_piece_weight_kg(item: dict) -> float | None:
    """该行「单件重量」的**计划覆盖值**（kg）：`piece_weight_kg` 存在且 >0 ⇒ 返回它；否则 None。

    分瓣行的真实单片（底环 55t 分 2 瓣 ⇒ 27500）；配车侧同名量 = `items[].piece_w_t` × 1000。
    """
    pw = (item or {}).get("piece_weight_kg")
    if pw is None:
        return None
    try:
        pw = float(pw)
    except (TypeError, ValueError):
        return None
    return pw if pw > 0 else None


def line_gate_breakdown(item: dict, model: VehicleModel) -> dict:
    """逐行**闸门**用的四约束分解：单件重量口径 = `piece_weight_kg`（>0 时；分瓣行真实单片）。

    - 只换「最大单件重量吨」这一项：闸门判的是「单件 > 该行车型核定载重」——计划按分瓣后
      单片配车（`items[].piece_w_t`），计价必须按同一件判，否则分瓣行被假 422 拦死（T-D2）；
    - 该行**总吨位/体积/尺寸原样**（分瓣不改变该行总货重与占地）⇒ 重量/体积/长度/面积四约束不变；
    - `piece_weight_kg` 缺省（或 ≤0）⇒ 直接复用 `line_breakdown()`（旧口径，逐字节不变）。
    """
    pw = line_piece_weight_kg(item)
    if pw is None:
        return line_breakdown(item, model)
    return vehicle_count_breakdown(
        model=model,
        cargo_weight_ton=line_weight_ton(item),
        cargo_volume_m3=line_volume_m3(item),
        cargo_items=[{**(item or {}), "weight_kg": pw}],
    )


def line_planned_trucks(item: dict, model: VehicleModel) -> int:
    """该行**台数**：`vehicle_count` 存在且 >0 ⇒ 采用计划值（用户拍板「整票 = 配车计划」，
    与配车侧 `items[].vehicle_count` 同源；不是本文件自创算法 ⇒ 与 INV-2 不冲突）；

    缺省（或 ≤0）⇒ `车辆数分解()`（INV-2 旧口径，逐字节不变）。
    """
    vc = (item or {}).get("vehicle_count")
    if vc is not None:
        try:
            vc = int(vc)
        except (TypeError, ValueError):
            vc = 0
        if vc > 0:
            return vc
    return int(line_breakdown(item, model)["车数"])


def _line_model_id(item: dict) -> str:
    return str((item or {}).get("vehicle_model_id") or "").strip()


def _line_name(item: dict, idx: int) -> str:
    return str((item or {}).get("name") or f"第 {idx + 1} 行") or f"第 {idx + 1} 行"


# ── 逐行闸门 ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BlockedLine:
    """某行「超载不可分」（单件 > 该行车型核定载重）⇒ 调用方按 v018 骨架报 422 并点名这一行。"""
    name: str
    model: VehicleModel
    piece_ton: float
    breakdown: dict


def check_lines(cargo_items: list[dict] | None, *, allow_oversized_split: bool) -> BlockedLine | None:
    """逐行闸门：对每一行用**它自己的车型**跑 `车辆数分解()`，返回**第一行**「不可分」。

    - 只有该行「不可分」（单件重量 > 该行车型核定载重）且用户未放行（`allow_oversized_split`
      ＝「确认按拆分计算」）时才拦 —— 与单车型路径同一判据、同一放行开关；
    - 🆕 T-D2：单件重量口径 = `items[].piece_weight_kg`（>0 时；分瓣行的真实单片重），
      缺省 = 行内 `weight_kg`（旧口径逐字节不变）；
    - 没有计划车型的行不参与闸门（没有车型就没有"这台车装不下"可判，见模块 docstring 口径 2）；
    - 车型不在库中 ⇒ `UnknownVehicleModel`（调用方译 400，与单车型路径同一错误口径）。
    """
    for idx, item in enumerate(cargo_items or []):
        model_id = _line_model_id(item)
        if not model_id:
            continue
        model = get_model(model_id)
        if model is None:
            raise UnknownVehicleModel(f"{model_id}（本行：{_line_name(item, idx)}）")
        breakdown = line_gate_breakdown(item, model)
        if breakdown.get("不可分") and not allow_oversized_split:
            return BlockedLine(
                name=_line_name(item, idx),
                model=model,
                piece_ton=float(breakdown.get("最大单件重量吨") or 0),
                breakdown=breakdown,
            )
    return None


# ── 逐行计费 + 整票求和 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class LinePrice:
    """一行的计价结果：`result` 是该行**单车**费用，`scaled` = 该行费用 × 该行台数。"""
    line_id: str
    name: str
    model_id: str
    trucks: int
    weight_ton: float
    result: CostResult
    scaled: CostResult


@dataclass
class LinePricePlan:
    lines: list[LinePrice] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)   # 无计划车型的行（本票未计价，须点名）
    total_trucks: int = 0
    total: CostResult | None = None                      # 整票口径 = Σ 各行 scaled

    @property
    def excluded_names(self) -> list[str]:
        return [str((it or {}).get("name") or "（未命名行）") for it in self.excluded]

    @property
    def model_ids(self) -> list[str]:
        seen: list[str] = []
        for ln in self.lines:
            if ln.model_id not in seen:
                seen.append(ln.model_id)
        return seen


def price_lines(cargo_items: list[dict] | None, *, common_kwargs: dict) -> LinePricePlan:
    """逐行计费：每行用**它自己的计划车型**调 `compute_cost_full_truck()`，再 × 该行台数。

    台数口径：`items[].vehicle_count`（>0 时）＝**配车计划该行台数**（用户拍板「整票 = 配车计划」）；
    缺省 ⇒ `车辆数分解()`（INV-2）。两种口径给的都是「这一行要几台车」，本文件不新立车数算法。

    `common_kwargs` = 与单车型路径共用的计费入参（距离/时长/货物类型/各项开关/油价/工资…），
    **不含** `cargo_weight_ton`：单车吨位按「该行吨位」逐行给（整车模式金额与吨位无关，
    吨位只影响载重比 → 时长口径，与现路径恒等）。
    """
    plan = LinePricePlan()
    for idx, item in enumerate(cargo_items or []):
        model_id = _line_model_id(item)
        if not model_id:
            plan.excluded.append(item or {})
            continue
        model = get_model(model_id)
        if model is None:
            raise UnknownVehicleModel(model_id)
        trucks = line_planned_trucks(item, model)
        weight_ton = line_weight_ton(item)
        # 逐行口径：单车吨位 = 该行吨位，单件明细 = 该行（覆盖 common_kwargs 里的整票值）
        line_kwargs = dict(common_kwargs)
        line_kwargs["vehicle_model_id"] = model_id
        line_kwargs["cargo_weight_ton"] = weight_ton
        line_kwargs["cargo_items"] = [item]
        result = compute_cost_full_truck(**line_kwargs)
        plan.lines.append(LinePrice(
            line_id=str(idx), name=_line_name(item, idx), model_id=model_id,
            trucks=trucks, weight_ton=weight_ton, result=result,
            scaled=scale_cost_result(result, trucks),
        ))
    if not plan.lines:
        raise ValueError("逐行车型计价：没有任何带计划车型的行（判定入口 has_line_models() 应先返回 False）")
    plan.total_trucks = sum(ln.trucks for ln in plan.lines)
    plan.total = sum_cost_results(
        [ln.scaled for ln in plan.lines],
        total_weight_ton=sum(ln.weight_ton for ln in plan.lines),
    )
    # 未计价的行：不静默 —— 挂在提示码上（响应 `suggestions[]` 现字段，形状不变）
    if plan.excluded:
        plan.total.suggestions = list(plan.total.suggestions) + [{
            "code": "unpriced_lines",
            "params": {
                "names": plan.excluded_names,
                "note": "以下货行没有计划车型，未计入本票费用（配车计划未给出车型 ⇒ 通常需拆运或专线询价后手工计价）",
            },
        }]
    return plan


# ── 纯函数：逐项相加 / 口径换算 ──────────────────────────────────────────

def _merge_suggestions(groups: list[list]) -> list[dict]:
    """合并多行的建议码：按 (code, params) 去重，保持首次出现顺序。"""
    merged: list[dict] = []
    seen: set[str] = set()
    for group in groups:
        for s in group or []:
            if not isinstance(s, dict):
                continue
            key = f"{s.get('code')}|{sorted((s.get('params') or {}).items())!r}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(s)
    return merged


def _scaled_per_km(b: CostBreakdown, factor: float, distance_km: float) -> float:
    return (float(b.cost_total or 0.0) * factor / distance_km) if distance_km > 0 else 0.0


def scale_cost_result(result: CostResult, factor: float) -> CostResult:
    """按比例缩放一个 CostResult（「整票 ↔ 单车」口径换算；factor=台数 或 1/台数）。

    - 缩放**金额项**（CostBreakdown 的 cost_*）与 `cost_per_km`；
    - `cost_per_ton_km` 是**比率**（元/吨公里，整票口径下 = 整票总额 ÷（里程 × 总吨）），
      不随台数缩放 —— 单车口径与整票口径的值本来就相同（台数与吨位同步换算），
      这里显式保留，避免上层 `breakdown.cost_per_ton_km` 被多除一次；
    - `capacity_ratio` / 车型标识 / `timing` / `distance_km` 原样保留。
    """
    b = result.breakdown
    scaled = {f: float(getattr(b, f) or 0.0) * factor for f in _SUM_FIELDS}
    breakdown = CostBreakdown(
        **scaled,
        cost_per_km=_scaled_per_km(b, factor, result.distance_km),
        cost_per_ton_km=b.cost_per_ton_km,
        capacity_ratio=b.capacity_ratio,
        matched_vehicle_model_id=b.matched_vehicle_model_id,
        matched_vehicle_model_name=b.matched_vehicle_model_name,
    )
    return CostResult(
        distance_km=result.distance_km,
        timing=result.timing,
        breakdown=breakdown,
        suggestions=list(result.suggestions or []),
    )


def sum_cost_results(parts: list[CostResult], *,
                     distance_km: float | None = None,
                     total_weight_ton: float | None = None) -> CostResult:
    """把若干 CostResult **逐项相加**成一个（整票口径）—— 纯函数，无 IO、无公式。

    - 金额项：Σ（`_SUM_FIELDS`）；
    - `distance_km`：本票同一条路线 ⇒ 取共用值（不参与相加）；
    - `timing`：取**最慢的一行**（时长/休息/装卸不可相加；编队按最慢车计，保守）；
    - `capacity_ratio`：恒 1.0（整车口径的比率，不是金额，不许相加）；
    - `cost_per_km` / `cost_per_ton_km`：由整票合计**重算**（不是相加）；
    - `matched_vehicle_model_*`：单一车型 ⇒ 该车型；多车型混编 ⇒ 点名「配车计划逐行车型」；
    - `suggestions`：各分项去重合并（首次出现顺序）。
    """
    items = [p for p in (parts or []) if p is not None]
    if not items:
        raise ValueError("sum_cost_results：没有任何分项（逐行计价至少要有一行带计划车型）")

    d_km = float(distance_km if distance_km is not None else items[0].distance_km)
    sums = {f: 0.0 for f in _SUM_FIELDS}
    for p in items:
        for f in _SUM_FIELDS:
            sums[f] += float(getattr(p.breakdown, f) or 0.0)

    slowest = max(items, key=lambda p: float(p.timing.total_duration_h or 0.0)).timing
    timing = RouteTiming(
        speed_factor=slowest.speed_factor,
        adjusted_duration_h=slowest.adjusted_duration_h,
        rest_hours=slowest.rest_hours,
        loading_hours=slowest.loading_hours,
        total_duration_h=slowest.total_duration_h,
    )

    model_ids = sorted({p.breakdown.matched_vehicle_model_id for p in items})
    if len(model_ids) == 1:
        matched_id, matched_name = model_ids[0], items[0].breakdown.matched_vehicle_model_name
    else:
        names = []
        for p in items:
            nm = p.breakdown.matched_vehicle_model_name
            if nm not in names:
                names.append(nm)
        matched_id = "line_plan"
        matched_name = f"配车计划逐行车型（{len(items)} 行 · {len(names)} 款）"

    breakdown = CostBreakdown(
        **sums,
        cost_per_km=(sums["cost_total"] / d_km) if d_km > 0 else 0.0,
        cost_per_ton_km=(sums["cost_total"] / (d_km * total_weight_ton))
        if (d_km > 0 and total_weight_ton) else None,
        capacity_ratio=1.0,
        matched_vehicle_model_id=matched_id,
        matched_vehicle_model_name=matched_name,
    )
    return CostResult(
        distance_km=d_km,
        timing=timing,
        breakdown=breakdown,
        suggestions=_merge_suggestions([list(p.suggestions or []) for p in items]),
    )
