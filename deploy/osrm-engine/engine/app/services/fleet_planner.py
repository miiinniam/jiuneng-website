"""v011 整票试算选车器（纯函数、无 IO）。

铁律（设计 §3.2 INV-2）：本模块**不实现任何**"装得下"判断，
车数一律由 费用计算公式.车辆数分解() 得出 —— 与计价同源。

口径修正记录（T1 实现期，以源码为准）：
  `车辆数分解()` 的真实返回键是 **「车数」**（另有 重量/体积/长度/面积/主因/不可分/
  最大单件重量吨/车型最大载重吨）；实施计划草稿里写的「总车数」在源码中不存在。

v015.8 T3/T4/T5（依据《运输专家意见-v015.8》§2/§4；阈值唯一真源 = 本模块的常量表）：
  · **阈值 v2**：宽拆五档（2.5/3.0/3.5/3.75/4.5/5.5）—— >4.5 判「T5 特批/专询」而**不是**"不可运"
    （座环 4.98m 金标准）；高改**总高口径**（台面高 + 货高 + 垫木 0.12；阈值 4.0/4.2/4.5/4.75/5.5），
    台面高缺失时退化旧口径并**打警告标记**（不许静默）；长保留「车厢+3.0m 装得下」判据并叠加
    **组合长**（货长 + 前后悬 3.0 + 主车 6.5；越 20/25/30、中 18.1/20/28）；重量分档（32/100/200/>200），
    **禁止**拿"库内最大载重"当"运不了"的理由（那是库缺，只可用于"需更高等级装备"，§4.2d）。
  · **车数口径**（T4）：单件 >32t（不可解体）⇒ **工程默认一件一车**
    （旧 TT-46/2015 series 条号已整体失效 ⇒ 现行口径见 `legal_refs`：越侧「超重货」= 整车总质量
    >48t、只准 1 个单原，`legal_refs.vn.d10k2` + `vn.d12k2d`；映射表 `MIGRATION_FROM_TT46`）；
    行内**≥2 个单原同车**仅在"非超重且三向不超限（宽≤2.5 / 长≤20 / 总高≤4.2）"时成立（`vn.d8k3`）；
    拼轴按 **8t/轴线**（三联轴组 24t，`legal_refs.vn.d14`）折算 ⇒ `运输单元数`（车数）与 `轴线条数` 两个量分离输出；
    车数下限 = max(车辆数分解().车数, ceil(件数 / 单件可同车上限))（**ceil 规则写死**；守恒断言用它）。
  · **结论契约**（T5）：`dim_flags`（车辆匹配层）与 `permit_flags`（法规层：许可/勘路/护送/桥涵）**分列**；
    点名行给 `unassigned[].{blocked_axis, over_by, actions[]}`；越许可两个坑（"无其他运输方式"前置、
    勘验/加固/护送费用归属）随附在 permit_flags 里。

热修 v015.8 批次 2 审核（P1-1 / P2-1 / P2-2，报告见 docs/plans/_dispatch/review-batch2-dim-policy.md）：
  · **P1-1**：折叠策略键改用独立键 `fold_shape`（行级与顶层均支持；python 形参名 `shape=` 保留）；
    旧式 `shape` 回退只在**折叠词表**（auto|integral|整体|nK|分N瓣/段）内被转发 —— v013 几何值
    （box/cylinder/coil/pallet/bare）一律不当作折叠值、不报错、原样透传不管（此前真实 ≥2 行请求 500）。
  · **P2-1**：整票路径（`plan_fleet`）同步 T3/T5 尺寸闸 + `oversize["unassigned"]` 恒有键（含三件套）。
  · **P2-2**：缺台面高时高度警告同时进 `permit_flags`（不许只在 dim_flags）。

═══ v016 T-A（依据《配车系统重设计-设计.md》§1–§8；`0.0.1-v015.8` → v016）═══
  · **货行分档 + 排序**（§2）：`line_tier/line_class/line_priority` —— 档0 超重件（单件 >32t
    工程默认；法定「超重货」= 整车总质量 >48t，见 `legal_refs.vn.d10k2`）→ 档1 超限件 →
    档2 常规件；同档内 单件重 → 最大边 → 体积 → line_id（确定性）。**只改谁先挑车，不改单行语义**。
  · **车型排序键加 GVM 档**（§4）：`gvm_tier()` + `_rank_key()`；`cost_caliber` 把「无距离 ⇒
    只比费率」这件事**显式化**（不再静默退化）；`fewer_trips_exemption` 记趟数豁免。
  · **共车层**（§3）：`COLOAD_POLICY` 集中阈值；`pieces_per_truck_cap()` 保留函数名、内部改三段
    （档0 ⇒ 1 / 档1 ⇒ 开关 ON 走串联 cap / 档2 ⇒ 载重商 × 沿车长 × 并排 × 层数）；
    `co_load_allowed()` 判 CO-1…CO-6；档2 **整池共车**（行界是人为的，不该因此多出车）。
  · **车数三重口径**（§5）：`floor`（件守恒下限）/`four_const`（`车辆数分解()`，INV-2 不破）/
    `packer`（前端装车器实测，后端只留占位）；差 >30% 的 `gap_warn` 由前端比对后回填。
  · **「允许超限运输配车」开关**（§6）：`allow_oversized=True` ⇒ `_dim_verdict` 的 **no 档**在硬红线内
    降级为 `over`（宽 4.5–5.5m / 总高 4.75–5.5m ⇒ 可配车 + 许可标 + 超限件可串联共车）；
    **>5.5m、单件超核定载重、轴荷/桥涵一字不放**（超限可许可、超载无许可路径）。
  · **法规条号迁移**（§8.1）：条号唯一真源 = `services/legal_refs.py`；本模块不再硬写条号，
    旧版 TT-46/2015 系列条号一律弃用（映射表见 `legal_refs.MIGRATION_FROM_TT46`）。

═══ v016 T-D（依据《配车系统重设计-设计.md》§7；`0.0.1-v015.8` → v016）═══
  · **配不出的真因 4 → 7**：集中枚举 = `UNFIT_REASONS`（E1–E7：键 → 中文名 + 「最低成本第一步」）——
    `_line_block()` 与 `unfit_reason` 组装**只引用它**（不许散写原因串）。
    判定顺序 = `E1 重 → E5 轴荷 → E6 组合长 → E2 长 → E7 车型外形 → 宽(T5) → 高`。
  · **新增三类**：`gvm_axle_shortfall`（轴荷缺口；选中车型轴线不足 ⇒ 进 `permit_flags`，
    `count_doctrine.axle_shortfall` / 行级 `axle_lines.shortfall` 同源）｜`combo_length_over`
    （组合长 > `COLOAD_POLICY["max_pair_len_m"]` ⇒ 进 `length_flags`）｜`deck_unfit_closed`
    （候选只剩闭箱/高栏/集装箱/冷链类、悬伸=0 ⇒ 「换开放车板」；`_dim_verdict` 对闭箱类同口径硬闸）。
  · 既有 4 类（`piece_overload` / `piece_overlong` / `candidate_narrowed` / `piece_overlong_exceeds_all`）
    的字符串值与 `unassigned[].{blocked_axis, over_by, actions[]}` 契约一字不改。
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

from app.services import legal_refs
from app.services import 费用计算公式 as 公式
from app.services import line_folder
from app.services.vehicle_registry import VehicleModel

ENGINE = "fleet_planner@v016"   # v016：分档排序 + GVM 档 + 共车层 + 超限放行开关（口径串随版本走，便于追溯）

# 判定用的常量（不参与调价，只决定"能不能同车"）
_SPECIAL_CATEGORY = "special"

#: 浮点比较容差（档位边界判定统一 ±1e-9 —— 判据 3「=4.5/=2.5/=4.2 判可运最高档而非不可运」）
_EPS = 1e-9


@dataclass(frozen=True)
class FleetGroup:
    partition: str          # "main" | "oversized"
    model_id: str
    vehicle_count: int
    binding: str            # 决定车数的约束名（重量/体积/长度/面积/单件超载不可分）
    payload: dict           # 载荷特征
    breakdown: dict         # 车辆数分解() 原始返回
    reason: str             # 人类可读理由（前端⑥直接显示）
    items: list[dict] = field(default_factory=list)
    # 🆕 v015.8 T3/T4/T5：dim_flags（车辆匹配层）与 permit_flags（法规层）**分列**；
    #   count_doctrine 记录车数口径（一件一车/拼轴/运输单元数）的可解释依据。
    dim_flags: list[str] = field(default_factory=list)
    permit_flags: list[str] = field(default_factory=list)
    count_doctrine: dict = field(default_factory=dict)
    # 🆕 v016 T-A：该组是否「靠『允许超限运输配车』开关 ON 才拿到车」；共车组合的整车外廓宽度
    #   （= max 件宽，**不叠加** —— 串联装载的外廓宽度与件数无关）；车数三重口径的另一半在
    #   count_doctrine（floor/four_const/packer）。
    oversize_released: bool = False
    pair_total_width_m: float | None = None
    # 🆕 v017 T-2：本组的**共车组合**（`{pair_id, line_ids, line_names, per_truck, trucks,
    #   rule_id, reason, accepted}`）—— 前端④「拼车核对」面板逐条勾选用；`accepted=false`
    #   表示该组合被显式不采纳（已按「不共车」重算：车型不变、车数上调）。
    pairs: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class FleetPlan:
    groups: list[FleetGroup]
    total_trucks: int
    primary_model_id: str | None
    mixed: bool
    needs_split: bool
    split_hint: str | None
    oversize: dict
    engine: str = ENGINE
    category_fallback: bool = False
    #: 🆕 A6（2026-11）可解体件的拆件建议（无/未标可解体 ⇒ None）
    divisibility: dict | None = None
    #: 🆕 A7-2（2026-11）计费体积（圆柱按实际形状 πr²L）与装车占位体积（外接方块）**分列**
    billed_volume_m3: float | None = None
    placed_volume_m3: float | None = None


def _dims_fallback(raw: dict) -> dict:
    """P2-4 接缝兜底：把设计契约格式（`dims_m{L,W,H}` / `w_total_t`）换算成 planner 口径。

    v015.8 之前：喂设计契约格式的行会被**静默清零**（尺寸/重量全 0）后照样"配车"。
    这里只做**兜底**：planner 口径（length_m/…/weight_kg）有值时优先，缺了才取 dims_m/w_total_t。
    """
    out = dict(raw)
    dims = raw.get("dims_m")
    if isinstance(dims, dict):
        for key_out, keys in (("length_m", ("L", "l")), ("width_m", ("W", "w")), ("height_m", ("H", "h"))):
            if out.get(key_out) not in (None, ""):
                continue
            for k in keys:
                v = dims.get(k)
                if v not in (None, ""):
                    try:
                        out[key_out] = float(v)
                    except (TypeError, ValueError):
                        pass
                    break
    if out.get("weight_kg") in (None, "") and raw.get("w_total_t") not in (None, ""):
        try:
            out["weight_kg"] = float(raw["w_total_t"]) * 1000.0
        except (TypeError, ValueError):
            pass
    return out


def _norm_items(items: list[dict] | None) -> list[dict]:
    out = []
    for it in items or []:
        it = _dims_fallback(it)          # 🆕 v015.8 T5（P2-4）：dims_m / w_total_t 兜底换算
        n = max(1, int(round(float(it.get("count") or 1))))
        out.append({
            "name": it.get("name") or "",
            "length_m": float(it.get("length_m") or 0),
            "width_m": float(it.get("width_m") or 0),
            "height_m": float(it.get("height_m") or 0),
            "weight_kg": float(it.get("weight_kg") or 0),
            "count": n,
            "stackable": bool(it.get("stackable", True)),
        })
    return out


def _candidates(cargo_type: str, models: list[VehicleModel]) -> tuple[list[VehicleModel], bool]:
    """按货型过滤候选车型；过滤后为空则回退全量并标记 fallback（绝不'选不出车'）。"""
    wanted = (cargo_type or "normal").strip() or "normal"
    hit = [m for m in models if wanted in (m.suitable_cargo_types or ())]
    if hit:
        return hit, False
    return list(models), True


def _estimate_cost(model: VehicleModel, count: int, distance_km: float | None) -> float:
    """选车用的粗估总成本（只用于车型之间比大小，不用于报价）。

    ⚠️ 无距离兜底（设计 §3.1 选择规则②）：前端 `fit-vehicles` 请求**不带距离**
    （`app.js::currentFitPayload` 只有重量/体积/货型/items），若按 d=0 算就只剩
    「固定调度费」→ 会把固定费为 0 的高价车型排到最前（实测曾选中 46,000 ₫/km 的
    高栏车 25t，报价 118,491,837，而同票货 12.5m 平板只要 72,240,602）。
    故 d<=0 时退化为**车型费率**比较。
    """
    rate = float(model.base_rate_vnd_per_km or 0.0)
    d = float(distance_km or 0.0)
    if d <= 0:
        return rate * count
    return (rate * d + (model.fixed_surcharge_vnd or 0.0)) * count


def _plan_one(pool: list[dict], models: list[VehicleModel],
              distance_km: float | None, *, partition: str,
              allow_oversized: bool = False) -> tuple[FleetGroup | None, bool, dict]:
    """对一组货（同一分区）按整票试算选型。返回 (最佳组, 有无候选不可分超载, 诊断)。

    🆕 2026-09-23：第三个返回值 `diag` 记录**每个候选为什么被跳过**（单件超载/长件超车厢/
    算不出车数）与候选集口径（最长车厢、最大载重）。此前这些信息被丢弃，导致
    「长件装不进车厢」被统一说成「单件超常规车型上限」，UI 打出「10 吨 > 38 吨」的矛盾文案。
    🆕 v015.8 T4：车数加**法定口径下限**（一件一车 / ceil(件数/单件可同车上限)），行间不共车。
    🆕 热修 v015.8（P2-1）：T3/T5 尺寸语义也管**整票路径** —— 任一货行对车型判「不可运」
    （超宽超可运上限 / 超总高硬上限 / 超长逾车厢+3m，与逐件路径 `_dim_verdict` 同源）⇒ 该车型不适用。
    🆕 v016：排序键 = `_rank_key`（车数 → GVM 档 → 总价 → 载重 → 字典序）+ 趟数豁免；
    `allow_oversized` 透传给 `_dim_verdict` / `pieces_per_truck_cap`。
    """
    total_w = sum(i["weight_kg"] * i["count"] for i in pool) / 1000.0
    total_v = sum(i["length_m"] * i["width_m"] * i["height_m"] * i["count"] for i in pool)
    feat = 公式.货物载荷特征完整(货物总重量吨=total_w, 货物总体积立方米=total_v, 单件货物=pool)

    scored: list[dict] = []
    diag = {
        "partition": partition,
        "candidates": len(models),
        "max_deck_m": max((m.length_m or 0.0 for m in models), default=0.0),
        "max_load_ton": max((m.max_load_ton or 0.0 for m in models), default=0.0),
        "skipped_overload": 0, "skipped_overlong": 0, "skipped_nocount": 0, "skipped_category": 0,
        "skipped_dim_no": 0, "skipped_hardcap": 0,
    }
    for m in models:
        if m.category == _SPECIAL_CATEGORY and partition != "oversized":
            diag["skipped_category"] += 1
            continue                      # 常规货不用特种车兜底
        if partition == "oversized" and m.category != _SPECIAL_CATEGORY:
            diag["skipped_category"] += 1
            continue
        # 🆕 热修 v015.8（P2-1）：T3/T5 尺寸闸（与逐件路径 `_dim_verdict` 同源）—— 宽超可运上限
        #   （T5 特批）/ 超总高硬上限 / 超长逾车厢+3m 的货行，任何车型都不得自动配车。
        if any(_dim_verdict(it, m, allow_oversized=allow_oversized)[0] == "no" for it in pool):
            diag["skipped_dim_no"] += 1
            continue
        # 🆕 v016：串联共车时占地面积改用「车板占用面积」（见 `_line_breakdown` 的口径说明）。
        #   ⚠️ 非串联时**必须原样用 `feat` 的口径**（`货物载荷特征完整` 只把**不可叠件**计入占地面积）
        #   —— 自己重算成 Σ(长×宽×件数) 会把可叠件也算进去，凭空多出一倍的面积约束。
        adj: list[float] = []
        for i in pool:
            k = _serial_cap(i, m) if (allow_oversized and line_tier(i) == 1) else 1
            if k >= 2 and m.width_m and float(i["length_m"] or 0.0) > 0:
                adj.append((float(i["count"]) * float(i["length_m"]) * float(m.width_m)) / float(k))
            elif not i.get("stackable", True):
                adj.append(float(i["length_m"]) * float(i["width_m"]) * float(i["count"]))
        total_area = sum(adj) if len(adj) == len(pool) else feat["总占地面积平方米"]
        bd = 公式.车辆数分解(
            货物总重量吨=total_w, 货物总体积立方米=total_v,
            最大单件长度米=feat["最大单件长度米"], 货物总占地面积平方米=total_area,
            车型最大载重吨=m.max_load_ton, 车型容积立方米=m.effective_volume_m3,
            车型地板长米=m.length_m, 车型地板面积平方米=m.floor_area_m2,
            装载效率=m.loading_efficiency, 最大单件重量吨=feat["最大单件重量吨"],
            # 🆕 A7：单件占满车厢的口径（一件一车 + 不折算装载效率）
            件总数=sum(int(i.get("count") or 1) for i in pool),
            最大单件宽度米=feat.get("最大单件宽度米"), 车型宽度米=m.width_m,
        )
        if bd.get("不可分"):
            diag["skipped_overload"] += 1
            continue                      # 单件 > 载重：这辆车根本不适用
        if feat["最大单件长度米"] and m.length_m and feat["最大单件长度米"] > m.length_m:
            diag["skipped_overlong"] += 1
            continue                      # 长件装不进车厢
        n_bd = int(bd.get("车数") or 0)   # v011: 源码键是「车数」（计划草稿的「总车数」不存在）
        if n_bd <= 0:
            diag["skipped_nocount"] += 1
            continue
        caps = [pieces_per_truck_cap(i, m, allow_oversized=allow_oversized) for i in pool]
        if any(c <= 0 for c in caps):
            diag["skipped_hardcap"] += 1
            continue                      # 池内有单件超核定载重 ⇒ 该车型不可用（开关不放松）
        # v015.8 T4：车数口径 —— 一件一车 + 守恒下限（ceil 规则；件不可再拆 ⇒ 各占运输单元）
        n_floor = sum(int(math.ceil(i["count"] / c)) for i, c in zip(pool, caps))
        n = max(n_bd, n_floor)
        scored.append({"m": m, "n": n, "bd": bd, "caps": caps, "floor": n_floor,
                       "four_const": n_bd, "fewer_trips_exemption": False,
                       # 🆕 v016：该组是否「只有靠开关 ON 才拿得到车」（OFF 时判 no）
                       "released": bool(allow_oversized and any(
                           _dim_verdict(i, m, allow_oversized=False)[0] == "no" for i in pool))})
    if not scored:
        return None, True, diag
    best = _pick_best(scored, distance_km)
    m, n, bd, n_bd = best["m"], best["n"], best["bd"], best["four_const"]
    reason = (f"整票 {total_w:g} t / 地板占用 {feat['总占地面积平方米'] or 0:g} m²"
              f" → {m.display_name}（载重 {m.max_load_ton:g} t、地板 {m.floor_area_m2 or 0:g} m²）"
              f" {n} 辆装完；主因 {bd.get('主因') or '重量'}"
              f"；车数口径 件守恒下限 {best['floor']} / 四约束估算 {n_bd} 取大"
              # ⚠️ 客户可见文案：不许出现「成本/利润/毛利」——这里是**比价口径**，不是成本口径
              f"（GVM 档 {gvm_tier(m)}，比价口径 {cost_caliber(distance_km)}）")
    permit = _permit_flags(pool[0], m, released=bool(best.get("released"))) if pool else []
    return FleetGroup(partition=partition, model_id=m.model_id, vehicle_count=n,
                      binding=str(bd.get("主因") or "重量"), payload=feat, breakdown=bd,
                      reason=reason, items=pool,
                      permit_flags=permit,
                      oversize_released=bool(best.get("released")),
                      count_doctrine={"one_piece_over_t": float(COLOAD_POLICY["one_piece_over_t"]),
                                      "axle_q_t": float(DIM_POLICY["axle_q_t"]),
                                      "transport_units": n,
                                      "pieces_per_truck_max": min(best["caps"]) if best["caps"] else None,
                                      "caliber": "max(floor,4const,packer)",
                                      "floor": int(best["floor"]),
                                      "four_const": int(n_bd),
                                      "packer": None,
                                      "gap_warn": None,                    # ③ 装车器实测由前端回填
            "gap_warn_threshold": float(COUNT_GAP_WARN),   # 单一真源：③ > ①×1.30 ⇒ 告警（不阻断）
                                      "unit_cap": int(min(best["caps"])) if best["caps"] else None,
                                      "pair_rule_id": "CO-6" if any(c >= 2 for c in best["caps"]) else None,
                                      "gvm_tier": gvm_tier(m),
                                      "cost_caliber": cost_caliber(distance_km),
                                      "fewer_trips_exemption": bool(best.get("fewer_trips_exemption")),
                                      "axle_shortfall": bool((_axle_info(pool[0], m) or {}).get("shortfall"))
                                      if pool else False}), False, diag


ENGINE_BY_ITEM = "fleet_planner@v016-form"   # v016：形态折算 + 阈值 v2 + 车数三重口径 + 共车 + 超限放行

# 形态层要用的行级键：`_norm_items` 只保留配车口径的键，折算器要的键从这里随身携带（不改 _norm_items，
# 免得动到 plan_fleet 共用口径）。
_FORM_INPUT_KEYS = ("inner_d_m", "split_n", "form", "shape_class", "shape", "line_id")

#: 显式分瓣（shape=nK）缺内径时的经验内径系数（专家表口径：本批 d/D = 底环 0.76 / 定子 0.74 / 顶盖 0.64）
_EXPERIENCE_INNER_RATIO = 0.75


# ══════════════════════════════════════════════════════════════════════════════
# v015.8 T3：阈值 v2（专家 §4.2；全部档位/公式集中在这里 —— 改这一处就是改口径）
# ══════════════════════════════════════════════════════════════════════════════

DIM_POLICY = {
    # 长：保留「装得下」判据 —— 单件长 ≤ 车厢长 + 3.0m（前后悬/伸缩板的工程余量）
    "len_over_m": 3.0,
    # 宽：自动配车上限（T4 顶）；4.5~5.5 是 T5 特批/专询（不自动配车，但给降档路径）；>5.5 强制三选一
    "width_haul_m": 4.5,
    # 高：【旧口径 · 仅台面高缺失时兜底】货高 ≤ 载货限高 + 1.5m
    "height_over_m": 1.5,
    # 高：总高 = 台面高 + 货高 + 垫木/悬架下沉（专家 §4.2b 建议 0.12~0.15，取下限 0.12）
    "height_reserve_m": 0.12,
    # 高：总高硬上限（>5.5 ⇒ 不自动配车：降台面（低床/SPMT）/拆件/水运/特批）
    "height_hard_m": 5.5,
    # 重：>32t（不可解体）⇒ **工程默认（提示级）一件一车** —— ⚠️ 32t 断点**已无法规依据**
    #   （旧 TT-46/2015 Điều 14 khoản 2 điểm c 已失效）。现行法定「超重货」= 整车总质量 >48t
    #   （`COLOAD_POLICY["one_piece_gross_t"]`，条号见 legal_refs.vn.d10k2 / vn.d12k2d）。
    "one_piece_over_t": 32.0,
    # 拼轴：公路按 8t/轴线（三联轴组 24t ÷ 3；条号见 legal_refs.vn.d14 —— 现行单轴 ≤10t、三联轴 24t）
    "axle_q_t": 8.0,
    # 组合长 = 货长 + 前后悬（工程余量）+ 主车长（专家 §4.2c：主车 6~7m，取中 6.5m）
    "overhang_m": 3.0,
    "prime_mover_m": 6.5,
    # 🆕 A2（2026-11，法条 `legal_refs.vn.d17` + 中国 62 号令 18.1m）：
    #   **常规装载长度上限**（无需大件许可）= min(1.1 × 车长, 20.0m 越南最大, 18.1m 中国认定线)，
    #   且前后各不超车长 10%。旧口径把「13m 车厢装 13.1~14.3m 货」一律标成「需许可」，
    #   属过度保守（客户被多算许可与审批周期），实测 13m 车厢法定常规上限 = 14.3m。
    "len_regular_ratio": 1.1,
    "len_regular_cap_m": 18.1,
    # 🆕 A5（2026-11）：专用超长车（可运/车厢 ≥40m，如叶片抽拉车/举升车）**只服务超长单件**。
    #   门槛 33m = 既有库最长常规车厢 32m + 1。不加这条的实测后果：加入 45m 叶片车后，
    #   30m 塔筒从 88,000 的「80t 30m 抽拉板」被换到 110,000 的「45m 叶片车」（GVM 档更低 →
    #   抢赢排序），等于新增车型反而把常规大件报贵 25%。
    "long_special_deck_m": 40.0,
    "long_special_min_cargo_m": 33.0,
}

#: 宽五档（专家 §4.2a）：(上限 m, 档名, 中侧动作, 越侧动作)；>5.5 ⇒ 强制「分瓣/水运/改设计」
WIDTH_TIERS: tuple[tuple[float, str, str, str], ...] = (
    (2.5, "常规", "—", "—"),
    (3.0, "T1 超宽", "许可（一类件，最易批）", "许可"),
    (3.5, "T2 超宽", "许可", "许可"),
    (3.75, "T3 超宽", "许可", "许可 + 护送"),
    (4.5, "T4 超宽", "许可 + 轮廓图/护送方案", "许可 + 勘路 + 护送"),
    (5.5, "T5 特批", "专询/专项评估", "逐段勘验 + 可能加固"),
)
#: T5 上限（> 此值 ⇒ 强制「分瓣 / 水运 / 改设计」三选一）—— 直接取档表末档（单一真源）；
#  4.5 是工程惯例上限而非法律硬墙（越/中两侧都没有 4.5m 以上不得通行的条文）
WIDTH_HARD_LIMIT_M = WIDTH_TIERS[-1][0]

# ══════════════════════════════════════════════════════════════════════════════
# 🆕 v016 T-A：分档 / GVM 档 / 共车层 的集中常量（改这一处 = 改口径）
# ══════════════════════════════════════════════════════════════════════════════

#: 车货总重档（GVM = max_load_ton + curb_weight_ton）：≤49 / ≤100 / ≤200 / >200 ⇒ 档 0/1/2/3。
#: ⚠️ 中国侧口径（《超限运输车辆超限超载认定标准》附件4：二轴 18t …六轴 49t，见 legal_refs.cn.limit_standard）；
#: 越南侧是另一张表（legal_refs.vn.d15，依赖 `wheelbase_m` / `saddle_to_first_axle_m`，数据留白中 ⇒
#: 只用中国口径 + 标注「越侧待补轴距」，**不许静默当越侧已通过**）。
GVM_TIERS_T: tuple[float, ...] = (49.0, 100.0, 200.0)

#: 共车策略（设计 §3.1）：三段 cap 与共车判据的**唯一阈值来源**
COLOAD_POLICY: dict = {
    # 超重件门槛（工程默认，提示级；法定口径见 one_piece_gross_t）
    "one_piece_over_t": 32.0,
    # 越南现行「超重货」= 装载后整车总质量 > 48t（legal_refs.vn.d10k2 / vn.d12k2d）
    "one_piece_gross_t": 48.0,
    # 开放车板允许前后悬（= DIM_POLICY["len_over_m"]，复用不新增真源）
    "overhang_open_m": 3.0,
    # 闭箱/高栏/集装箱/冷链：悬伸 = 0（硬闸 —— 闭箱车不吃超宽/超长件）
    "overhang_closed_m": 0.0,
    # 每车装载重量硬顶（载重 × 0.98；共车判据用；单件超**核定载重**才是 0）
    "load_hard_cap": 0.98,
    # 目标装载率（低于它继续从池里塞件；装车器/口径条用）
    "load_target_util": 0.90,
    # 闭箱类（不许悬伸）
    "closed_categories": ("small_box", "high_side", "container", "cold_chain"),
    # 组合长工程上限（货长合计 + 悬伸 3.0 + 主车 6.5 ≤ 22.0）；超则不许共车
    "max_pair_len_m": 22.0,
}

#: 档位枚举（排序用；`line_tier` 的取值）
LINE_PRIORITY: dict = {"tier_heavy": 0, "tier_oversize": 1, "tier_plain": 2}

#: 超限判据（工程/法定通用）：宽 >2.5m（越 2.5 / 中 2.55，配车**取严 2.5m**）、长 >20.0m、
#: 总高 >4.2m（越法定；中 4.0m）。条号见 legal_refs.vn.d10k1 / cn.oversize_rule。
PLAIN_WIDTH_M = float(WIDTH_TIERS[0][0])      # 2.5（越）/ 2.55（中）⇒ 取严 2.5
PLAIN_LENGTH_M = 20.0
PLAIN_TOTAL_HEIGHT_M = 4.2

#: 必须单走的货类（危化品/活体/实验件——本版**留空枚举**，由业务后补；CO-1 用）
MUST_SOLO_CLASS: tuple[str, ...] = ()

#: 趟数豁免（R9）：同 GVM 档内 车数降 ≥30% 且 总价涨 ≤15% ⇒ 选少趟（司机与限时通行段是真瓶颈）
TRIP_REDUCTION_TRIGGER = 0.30
COST_PREMIUM_FOR_FEWER_TRIPS = 0.15

#: 车数口径告警阈值：装车器实测 > 件守恒下限 × 1.30 ⇒ 前端出 `count_gap` 告警（不阻断）
COUNT_GAP_WARN = 0.30

# ══════════════════════════════════════════════════════════════════════════════
# 🆕 v016 T-D：「配不出的真因」集中枚举（E1–E7）—— **唯一真源**
#   `_line_block()` 与 `unfit_reason` 组装只引用本表（原因串 / 中文名 / 「最低成本第一步」不许散写）。
#   判定顺序（设计 §7 / 意见书 §6）：E1 重 → E5 轴荷 → E6 组合长 → E2 长 → E7 车型外形 →
#   宽(T5) → 高（后两项是 `_line_block` 的宽/高兜底分支；E3/E4 只在整票 `unfit_reason` 组装里出现）。
#   插入顺序 = 判定顺序（`list(UNFIT_REASONS)` 可验证）。
# ══════════════════════════════════════════════════════════════════════════════
UNFIT_REASONS: dict[str, dict] = {
    # ── E1（现状已有）：单件超库内最大载重 —— 是「库缺」，不是「运不了」（文案不许说死）──
    "piece_overload": {
        "num": "E1", "cn": "单件超载（超库内最大载重）",
        "first_step": "提装备等级（更大载重/更多轴线）或拆附件减重",
        "actions": ["需更高等级模块车（>250t 级）或拆附件减重",
                    "需水运（库区/内河驳船备选）或专询/特批"],
        "block_msg": ("超重：{w:.1f}t 超库内最大载重 {max_load:.0f}t（库缺 ⇒ 需 {w:.0f}t 级模块车/专询，"
                      "或水运；>200t 属专项方案）"),
        "msg": "单件 {w:.1f}t 超常规车型上限 {normal_max:.0f}t，需超限运输（特种车 + 超限许可）",
    },
    # ── E5（新增）：轴荷不足 —— 所需轴线条数 > 车辆轴线条数，且不可拼轴 ──
    #   本版库内无「拼轴扩容上限」数据（`couplable` 只给组合能力标志）⇒ 命中即按「不可拼轴」处理，
    #   处置第一步 = 提轴数/拼轴或换更大装备；轴荷/桥涵**只提示不放行**（设计 §5/§6.1 红线）。
    "gvm_axle_shortfall": {
        "num": "E5", "cn": "轴荷不足（所需轴线条数 > 车辆轴线条数，且不可拼轴）",
        "first_step": "提轴数/拼轴或换更大装备（250t 级）",
        "actions": ["提轴数/拼轴（模块车组合能力 couplable）或换 250t 级装备",
                    "桥涵必须先验算（不予许可情形）；或水运/专询"],
        "msg": ("单件 {w:.1f}t 需 ≥{lines_min} 轴线（{q:g}t/轴线口径）> 库载 {avail} 轴线"
                "（不可拼轴）⇒ 轴荷缺口 {gap} 轴线"),
    },
    # ── E6（新增）：组合长超路线工程上限（`COLOAD_POLICY["max_pair_len_m"]` = 22.0m）──
    "combo_length_over": {
        "num": "E6", "cn": "组合长超路线工程上限",
        "first_step": "改路线（避开城区/四级路）或分 2 段运",
        "actions": ["改路线（避开城区/四级路，先勘路核转弯半径/净空）",
                    "分 2 段运（现场对接/组焊，须设计院确认）",
                    "或专线询价"],
        "msg": ("组合长 {combo:.2f}m（货 {l:.2f} + 前后悬 {overhang:g} + 主车 {prime:g}）"
                "超路线工程上限 {cap:g}m"),
    },
    # ── E2（现状已有）：单件超长（超库内车厢 + 悬伸余量）──
    "piece_overlong": {
        "num": "E2", "cn": "单件超长（超车厢 + 悬伸余量）",
        "first_step": "换伸缩板/纵向分段（厂家书面确认）",
        "actions": ["需伸缩板/拆运（伸缩板可伸 30m）；或纵向分段（改设计，须制造厂书面确认）",
                    "或专线询价/专询"],
        "block_msg": ("超长：{l:.2f}m 超库内最长车厢 {max_deck:.2f}m 逾 {overhang:g}m"
                      "（需伸缩板/纵向分段（厂家书面确认）或专询/专线询价）"),
        "msg": ("单件长 {l:.1f}m 超常规候选车型最长车厢 {deck:.1f}m（单件仅 {w:.1f}t，"
                "未超 {normal_max:.0f}t 载重上限），已按特种车（超长/超限）处置"),
    },
    # ── E7（新增）：车型外形不匹配 —— 候选只剩闭箱/高栏/集装箱/冷链类，悬伸=0 ──
    "deck_unfit_closed": {
        "num": "E7", "cn": "车型外形不匹配（候选只剩闭箱/高栏/集装箱/冷链类，悬伸=0）",
        "first_step": "换开放车板（开放车板可悬伸/侧伸；闭箱类悬伸=0）",
        "actions": ["换开放车板（平板/低平板可前后悬；侧伸板可加宽）",
                    "若货确需闭箱/冷链：分体/降宽/降长，或专询"],
        "msg": "候选只剩闭箱/高栏/集装箱/冷链类（悬伸=0）：{dim}",
    },
    # ── E3（现状已有）：候选被货型收窄（只在整票组装用）──
    "candidate_narrowed": {
        "num": "E3", "cn": "候选被货型收窄",
        "first_step": "核对车型库该货型的候选（是否含低平板系列）",
        "actions": ["核对车型库「{cargo_type}」货型的候选车型（是否含低平板系列）",
                    "或专询/专线询价"],
        "msg": ("货型「{cargo_type}」的常规候选车型（最长车厢 {deck:.1f}m、最大载重 {load:.0f}t）"
                "装不下该单件，已按特种车处置"),
    },
    # ── E4（现状已有）：超长（超库内最长车厢，含特种车；只在整票组装用）──
    "piece_overlong_exceeds_all": {
        "num": "E4", "cn": "超长（超库内最长车厢，含特种车）",
        "first_step": "纵向分段（改设计，须制造厂书面确认）或水运",
        "actions": ["需纵向分段（改设计，须制造厂书面确认）",
                    "需水运（库区/内河驳船）或专询/专线询价"],
        "msg": "单件长 {l:.1f}m 超库内最长车厢（特种车最长 {deck:.1f}m），需拆单或专线询价",
    },
}


def unfit_msg(reason: str, **ctx) -> str:
    """按 `UNFIT_REASONS[reason]["msg"]` 模板渲染（整票 `unfit_reason` 组装用；键错 ⇒ 大声报错）。"""
    try:
        return str(UNFIT_REASONS[reason]["msg"]).format(**ctx)
    except KeyError as exc:
        raise KeyError(f"未知真因键 {reason!r}（合法键：{sorted(UNFIT_REASONS)}）") from exc


def unfit_block_msg(reason: str, **ctx) -> str:
    """`_line_block` 用文案：优先 `block_msg`（库内口径），缺省回落 `msg`。"""
    try:
        ent = UNFIT_REASONS[reason]
    except KeyError as exc:
        raise KeyError(f"未知真因键 {reason!r}（合法键：{sorted(UNFIT_REASONS)}）") from exc
    return str(ent.get("block_msg") or ent["msg"]).format(**ctx)


def unfit_text(reason: str, **ctx) -> str:
    """标记层统一文案：`E{n} {key}：{文案}；第一步：{最低成本第一步}`（唯一组装点，避免散写）。"""
    try:
        ent = UNFIT_REASONS[reason]
    except KeyError as exc:
        raise KeyError(f"未知真因键 {reason!r}（合法键：{sorted(UNFIT_REASONS)}）") from exc
    body = str(ent.get("msg")).format(**ctx)
    return f"{ent['num']} {reason}：{body}；第一步：{ent['first_step']}"


#: 总高硬上限：见 `DIM_POLICY["height_hard_m"]`（唯一真源）；阈值链 4.0（中）/4.2（越）/
#  4.5（许可）/4.75（勘路）/5.5（硬上限，> 此值不自动配车）见 `height_flags`

#: 重量分档（专家 §4.2d）：(上限 t, 档名, 动作)；禁用「库内最大载重」当"运不了"的理由。
#: ⚠️ 动作文案不再声称「法定」—— 32t 断点已无法规依据（工程默认 + 越侧「超重货」= 整车
#:   总质量 >48t，条号见 legal_refs.vn.d10k2 / vn.d12k2d）。
WEIGHT_TIERS: tuple[tuple[float, str, str], ...] = (
    (32.0, "非超重", "—"),
    (100.0, "超重·许可", "需许可（一件一车：工程默认；越侧「超重货」按整车总质量 >48t 判）"),
    (200.0, "超重·勘路+桥涵", "需许可 + 勘路 + 桥涵验算（一件一车：工程默认）"),
    (float("inf"), "超重·专项/水运", "需专项方案（桥涵验算/加固）或水运（库区驳船备选；一件一车：工程默认）"),
)

#: 组合长档位（专家 §4.2c）：中 ≤18.1 免 / ≤20 一类 / ≤28 二类 / >28 三类（轮廓图+护送方案）
LENGTH_COMBINED_CN_TIERS: tuple[tuple[float, str], ...] = (
    (18.1, "常规（≤18.1m 免许可）"),
    (20.0, "一类件（需许可）"),
    (28.0, "二类件（需许可）"),
    (float("inf"), "三类件（轮廓图 + 护送方案）"),
)
#: 组合长档位（越）：≤20 免 / >20 许可 / >25 护送 / >30 勘路
LENGTH_COMBINED_VN_TIERS: tuple[tuple[float, str], ...] = (
    (20.0, "常规（≤20m 免许可）"),
    (25.0, "许可"),
    (30.0, "许可 + 护送"),
    (float("inf"), "许可 + 护送 + 勘路"),
)

#: 挂车自重档（专家 §2.3 的 35/50/65t 口径；用于把"轴线条数"给成区间而不是假装精确）
AXLE_SELFWEIGHT_CANDIDATES_T: tuple[float, ...] = (35.0, 50.0, 65.0)
AXLE_SELFWEIGHT_DEFAULT_T = 50.0
#: 只有 >100t 级重货才输出拼轴核算（球阀 150t / 主变 225t 是本批金标准用例）
AXLE_REQUIRED_OVER_T = 100.0

# ══════════════════════════════════════════════════════════════════════════════
# 🆕 A3（2026-11）：中国大件运输许可三档 + 办理时限
#   依据《超限运输车辆行驶公路管理规定》（交通运输部令 2016 年第 62 号）第十五条：
#     一类：高 ≤4.2m、宽 ≤3.0m、长 ≤20m，且总质量/轴荷未超第三条/十七条 ⇒ 省内 2 个工作日（跨省 5）
#     二类：高 ≤4.5m、宽 ≤3.75m、长 ≤28m，且总质量 ≤100t               ⇒ 省内 5 个工作日（跨省 10）
#     三类：超过上述                                                     ⇒ 省内 15 个工作日（跨省 20）
#   另（第十条）：高 >4.5 或 宽 >3.75 或 长 >28 或 总质量 >100t ⇒ 还需轮廓图 + 护送方案。
#   为什么必须输出：办证周期直接决定交期承诺与报价里的等待成本，是客户最关心的变量之一；
#   旧口径只说「需许可」，客户无法预判 2 天还是 15 天。
# ══════════════════════════════════════════════════════════════════════════════

CN_PERMIT_TIERS: dict = {
    "tier1": {"name": "一类", "h_max": 4.2, "w_max": 3.0, "l_max": 20.0, "gross_max_t": None,
              "workdays_local": 2, "workdays_cross": 5},
    "tier2": {"name": "二类", "h_max": 4.5, "w_max": 3.75, "l_max": 28.0, "gross_max_t": 100.0,
              "workdays_local": 5, "workdays_cross": 10},
    "tier3": {"name": "三类", "h_max": None, "w_max": None, "l_max": None, "gross_max_t": None,
              "workdays_local": 15, "workdays_cross": 20},
}

#: 中国「超限运输」认定线（62 号令第三条）：高 >4.0m / 宽 >2.55m / 长 >18.1m / 总质量超按轴限值
CN_OVERSIZE_H_M = 4.0
CN_OVERSIZE_W_M = 2.55
CN_OVERSIZE_L_M = 18.1
#: 六轴及以上汽车列车 49t —— 按轴限值的保守上限（逐轴核验在 axle 通道）
CN_OVERSIZE_GROSS_T = 49.0


def cn_permit_tier(*, height_m: float | None, width_m: float, length_m: float,
                   gross_t: float) -> dict | None:
    """中国大件许可档位 + 办理时限。

    返回 None ⇒ 三向/质量均未超认定线，**无需许可**。
    入参用装载后的车货外廓（height_m = 台面高 + 货高 + 垫木；None ⇒ 判不了总高，
    只按宽/长/质量判并在 basis 里标注「高 未知」）。
    """
    h = float(height_m) if height_m is not None else None
    w, l, g = float(width_m), float(length_m), float(gross_t)

    over = (
        (h is not None and h > CN_OVERSIZE_H_M + _EPS)
        or w > CN_OVERSIZE_W_M + _EPS
        or l > CN_OVERSIZE_L_M + _EPS
        or g > CN_OVERSIZE_GROSS_T + _EPS
    )
    if not over:
        return None

    basis = [(f"高 {h:.2f}m" if h is not None else "高 未知"),
             f"宽 {w:.2f}m", f"长 {l:.2f}m", f"总质量 {g:.1f}t"]

    for key in ("tier1", "tier2"):
        t = CN_PERMIT_TIERS[key]
        if h is not None and h > t["h_max"] + _EPS:
            continue
        if w > t["w_max"] + _EPS or l > t["l_max"] + _EPS:
            continue
        if t["gross_max_t"] is not None and g > t["gross_max_t"] + _EPS:
            continue
        if key == "tier1" and g > CN_OVERSIZE_GROSS_T + _EPS:
            continue        # 一类还要求总质量未超按轴限值
        return {**t, "key": key, "basis": basis, "need_outline": False, "need_escort": False}

    t = CN_PERMIT_TIERS["tier3"]
    need_outline = ((h is not None and h > 4.5 + _EPS) or w > 3.75 + _EPS
                    or l > 28.0 + _EPS or g > 100.0 + _EPS)
    return {**t, "key": "tier3", "basis": basis,
            "need_outline": need_outline, "need_escort": need_outline}


def cn_permit_flag(*, height_m: float | None, width_m: float, length_m: float,
                   gross_t: float) -> str | None:
    """把档位拼成一行可读文案（进 permit_flags）；无需许可时返回 None。"""
    t = cn_permit_tier(height_m=height_m, width_m=width_m, length_m=length_m, gross_t=gross_t)
    if not t:
        return None
    extra = "；还需轮廓图 + 护送方案" if t["need_outline"] else ""
    return (f"中国许可：{t['name']}（省内 {t['workdays_local']} 个工作日 / "
            f"跨省 {t['workdays_cross']} 个工作日）{extra}"
            f" —— 判定依据 {'、'.join(t['basis'])}")


# ══════════════════════════════════════════════════════════════════════════════
# 🆕 A4（2026-11）：中国**轴荷**许可门槛（62 号令第十七条）
#   普通平板：单轴平均 >10t 或 最大 >13t ⇒ 需许可
#   多轴多轮液压平板：每轴线（一线两轴 8 轮）平均 >18t 或 最大 >20t ⇒ 需许可
#   与越南口径（单轴 ≤10t，`legal_refs.vn.d14`）**分开**：越南是硬限，中国是「超了要许可」。
#   本函数回答的不是「需要几条轴线」（那是 `axle_lines_required` 的事），而是
#   「这辆车的轴荷要不要单独办许可」——两者口径不同，不能互相替代。
# ══════════════════════════════════════════════════════════════════════════════

CN_AXLE_POLICY: dict = {
    "flatbed": {"avg_max_t": 10.0, "max_axle_t": 13.0, "label": "普通平板（单轴）"},
    "hydraulic": {"avg_max_t": 18.0, "max_axle_t": 20.0, "label": "多轴液压平板（每轴线）"},
    # 无逐轴分布数据时的峰值估算系数（工程经验：峰值约为平均的 1.3 倍）
    "peak_ratio": 1.3,
}


def cn_axle_permit(*, gross_t: float, axle_units: int | None,
                   hydraulic: bool) -> dict | None:
    """中国轴荷许可门槛。`axle_units`：普通车=轴数；液压车=轴线数。"""
    if not axle_units or axle_units <= 0 or gross_t <= 0:
        return None
    label = "hydraulic" if hydraulic else "flatbed"
    pol = CN_AXLE_POLICY[label]
    avg = float(gross_t) / float(axle_units)
    peak = avg * float(CN_AXLE_POLICY["peak_ratio"])
    return {
        "caliber": label, "label": pol["label"],
        "avg_t": round(avg, 2), "peak_t": round(peak, 2),
        "avg_max_t": pol["avg_max_t"], "max_axle_t": pol["max_axle_t"],
        "needs_permit": bool(avg > pol["avg_max_t"] + _EPS or peak > pol["max_axle_t"] + _EPS),
    }


def cn_axle_permit_flag(*, gross_t: float, axle_units: int | None,
                        hydraulic: bool) -> str | None:
    """轴荷门槛的客户可读文案；未触线时返回 None（不制造噪音）。"""
    a = cn_axle_permit(gross_t=gross_t, axle_units=axle_units, hydraulic=hydraulic)
    if not a or not a["needs_permit"]:
        return None
    return (f"中国轴荷：{a['label']}平均 {a['avg_t']:.1f}t（门槛 {a['avg_max_t']:g}t）、"
            f"峰值约 {a['peak_t']:.1f}t（门槛 {a['max_axle_t']:g}t）⇒ 需轴荷许可"
            f"（《超限运输车辆行驶公路管理规定》第十七条；按实车逐轴分布核定）")


#: 越许可两个坑（设计 §8.1 迁移后；条号唯一真源 = legal_refs）—— 凡出现许可级标记就必须随附
PERMIT_PITFALLS: tuple[str, ...] = (
    "越许可前置：需勘路并声明「无其他运输方式」（海运/空运/铁路/内河均不可行，"
    + legal_refs.citation("vn.d22k1dd") + "）；本批现实替代＝库区/内河驳船",
    "通过性费用：勘验/加固/恢复/护送/二次装卸由申请人承担（现行 "
    + legal_refs.citation("vn.d8k4") + "；原费用归属条号已失效、条文号待越南侧法务按 "
    + legal_refs.VN_CONSOLIDATED + " 核实）⇒ 报价单列，不摊入元/公里",
)

#: 🆕 热修 v015.8（P2-2）：台面高缺失警告 —— dim_flags **与 permit_flags 两条通道**都必须带（不许静默）。
_MISSING_DECK_WARN = ("台面高缺失（车辆库 deck_height_m 留白）⇒ 按旧口径（货高 ≤ 载货限高 + 1.5m）评定，"
                      "需补台面高后按总高口径复核")


def _dedup(seq) -> list[str]:
    """保序去重（flags 拼接用；保持可复算的确定性顺序）。"""
    out: list[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 🆕 v016 T-A：货行分档 / GVM 档 / 排序键 / 共车原语
# ══════════════════════════════════════════════════════════════════════════════

def _piece_weight_t(row: dict) -> float:
    return float(row.get("weight_kg") or 0.0) / 1000.0


def _piece_max_dim_m(row: dict) -> float:
    return max(float(row.get("length_m") or 0.0), float(row.get("width_m") or 0.0),
               float(row.get("height_m") or 0.0))


def _piece_volume_m3(row: dict) -> float:
    return (float(row.get("length_m") or 0.0) * float(row.get("width_m") or 0.0)
            * float(row.get("height_m") or 0.0))


# ══════════════════════════════════════════════════════════════════════════════
# 🆕 A7-2（2026-11）：圆柱/管件**计费体积**与**装车占位**分开
#   旧口径只有一个方块体积（长×宽×高）—— 对管件/筒体/辊子会高估 21%~50%：
#     2m 直径 × 12m 钢管：方块 37.70 m³，实际圆柱 29.61 m³（高估 27%）
#   但**两者用途不同，不能合并**：
#     · 装车占位（`_piece_volume_m3`）= 外接方块 —— 一根 2m 管在平板上确实占 2m 宽的床位；
#     · 计费体积（本函数）= 实际形状 —— 轻泡货按体积计费，用方块会多收客户的钱。
#   故：配车/装载一律走方块（不改车数），本函数只供计费与报价口径。
# ══════════════════════════════════════════════════════════════════════════════

#: 判定为圆柱件的名称关键词（先看 `shape_class`，缺省才按名称猜）
_CYLINDER_NAME_KEYS: tuple[str, ...] = ("管", "筒", "圆柱", "辊", "卷",
                                        "pipe", "tube", "cylinder", "drum", "roll")
#: 名称里出现这些词就不是圆柱（「管箱」「集装箱」这类会误命中「管/箱」）
_CYLINDER_NAME_EXCLUDE: tuple[str, ...] = ("箱", "柜", "架", "平台", "梯", "栏")


def _is_cylinder_row(row: dict) -> bool:
    """这件是否是圆柱形（管件/筒体/辊子）。`shape_class=ring` 优先；否则按名称判。"""
    sc = str(row.get("shape_class") or "").strip().lower()
    if sc in ("ring", "cylinder", "pipe", "tube"):
        return True
    if sc in ("integral", "beam", "box"):
        return False
    name = str(row.get("name") or "")
    if any(k in name for k in _CYLINDER_NAME_EXCLUDE):
        return False
    low = name.lower()
    return any(k in name or k in low for k in _CYLINDER_NAME_KEYS)


def _piece_billed_volume_m3(row: dict) -> float:
    """**计费**体积：圆柱按 π r² L（有内径则扣空心）；其余按外接方块。

    圆柱取 `min(width, height)` 作直径 —— 管件多为圆截面，长宽高里较小两向即截面；
    取小值是**保守**选择（避免把椭圆/带鞍座的件算大）。
    """
    l = float(row.get("length_m") or 0.0)
    w = float(row.get("width_m") or 0.0)
    h = float(row.get("height_m") or 0.0)
    if l <= 0 or w <= 0 or h <= 0:
        return 0.0
    if not _is_cylinder_row(row):
        return l * w * h
    d_out = min(w, h)
    d_in = row.get("inner_d_m")
    try:
        d_in = float(d_in) if d_in not in (None, "") else 0.0
    except (TypeError, ValueError):
        d_in = 0.0
    if d_in < 0 or d_in >= d_out:          # 内径非法 ⇒ 按实心圆柱（不放大小）
        d_in = 0.0
    return math.pi / 4.0 * (d_out ** 2 - d_in ** 2) * l


def line_class(row: dict) -> str:
    """货行分档（设计 §1③/§2）：`heavy`（档0 超重件）/ `oversize`（档1 超限件）/ `plain`（档2 常规件）。

    档0：单件 > `COLOAD_POLICY["one_piece_over_t"]`（32t，**工程默认**；法定「超重货」= 整车
         总质量 >48t ⇒ 与车型整备有关，故在 `pieces_per_truck_cap` 里逐车型判）。
    档1：单件任一向超限 —— 宽 >2.5m / 长 >20.0m / 总高（货高 + 垫木 0.12）>4.2m（越法定）。
    档2：其余（可整池共车的那一类）。

    行级判据只用**货本身的尺寸**（不拿车型台面高当输入）⇒ 排序与「先配谁」可复算。
    """
    if _piece_weight_t(row) > float(COLOAD_POLICY["one_piece_over_t"]) + _EPS:
        return "heavy"
    h_eff = float(row.get("height_m") or 0.0) + float(DIM_POLICY["height_reserve_m"])
    if (float(row.get("width_m") or 0.0) > PLAIN_WIDTH_M + _EPS
            or float(row.get("length_m") or 0.0) > PLAIN_LENGTH_M + _EPS
            or h_eff > PLAIN_TOTAL_HEIGHT_M + _EPS):
        return "oversize"
    return "plain"


def line_tier(row: dict) -> int:
    """档号：0 超重件 / 1 超限件 / 2 常规件（`LINE_PRIORITY`）。"""
    return int(LINE_PRIORITY["tier_" + line_class(row)])


def line_priority(row: dict) -> tuple:
    """货行排序键（设计 §2）：先难后易 —— 档 → -单件重 → -单件最大边 → -体积 → line_id。

    `line_id` 收尾兜底 ⇒ 同输入两次结果逐字段相同（确定性）。排序**只影响谁先挑车**，
    不改变任何单行的候选集与车数公式。
    """
    return (line_tier(row),
            -_piece_weight_t(row),
            -_piece_max_dim_m(row),
            -_piece_volume_m3(row),
            str(row.get("line_id") or ""))


# ══════════════════════════════════════════════════════════════════════════════
# 🆕 v017 T-2：配车契约扩展原语（逐行锁定车型 / 共车组合采纳）
#   ⚠️ 红线：这一层只改**配车组合与车型**（逐行锁定只在锁定车型上找形态；组合被显式
#   不采纳 ⇒ 车型不变、按逐行「不共车」重算）。车数唯一真源仍是 `车辆数分解()` +
#   件守恒下限（`max(floor, four_const)`）；`plan_confirmed` 只回显 + 审计，不参与金额。
# ══════════════════════════════════════════════════════════════════════════════

def line_id_of(raw, idx: int | str = 0) -> str:
    """行 `line_id` 的**唯一规范化口径**（API 校验 / planner 配对 / pair_id / confirm 共用）。

    行内 `line_id` 有值就用它，否则回落**行序号**（与 `plan_fleet_by_item` 里
    `view["line_id"]` 的兜底规则同源）；一律 `str()` —— JSON 对象键只能是字符串，
    前端 prefs 键 `veh:{lineId}` / `coload:{pairId}` 也按字符串存。
    """
    if isinstance(raw, dict):
        lid = raw.get("line_id")
        if lid is not None and str(lid).strip() != "":
            return str(lid).strip()
    return str(idx)


def pair_id_of(line_ids) -> str:
    """共车组合的**稳定 id**：组合内 line_id 排序 → 拼接 → sha1 截断。

    前端拿它存勾选态（prefs `coload:{pairId}`）⇒ **同输入必同 id**（与行序、排序键无关）；
    否则用户取消过的组合会在每次重算后「复活」（或勾选态错位）。
    """
    key = "|".join(sorted(str(x) for x in line_ids))
    return "pair-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def pair_accepted(pair_id: str, accepted_pairs) -> bool:
    """该共车组合是否被采纳（缺省 = **全采纳**，向后兼容 v016 口径）。

    · 缺省（None）⇒ True；
    · `{pair_id: bool}` ⇒ **显式 false 才不采纳**（没提到的组合默认采纳）；
    · `[pair_id, ...]` ⇒ **白名单**：只采纳列出的组合（`[]` = 全部不共车）。
    非法类型在 API 层 422 拦掉；planner 层拿不准时**保守按采纳**处理（不静默改车数）。
    """
    if accepted_pairs is None:
        return True
    if isinstance(accepted_pairs, dict):
        v = accepted_pairs.get(pair_id)
        return True if v is None else bool(v)
    if isinstance(accepted_pairs, (list, tuple, set)):
        return str(pair_id) in {str(x) for x in accepted_pairs}
    return True


def _payload_ton(m: VehicleModel) -> float:
    """核定载质量（t）：`registered_payload_ton` 留白 ⇒ 回落 `max_load_ton`。

    ⚠️ 这是**超载闸的唯一真源**（中国《认定标准》备注① / 越南 legal_refs.vn.d8k2d 的
    「设计载质量」）—— 开关 ON 也一字不放。
    """
    reg = getattr(m, "registered_payload_ton", None)
    if reg is not None and float(reg) > 0:
        return float(reg)
    return float(m.max_load_ton or 0.0)


def _overhang_m(m: VehicleModel) -> float:
    """该车型允许的前后悬（m）：开放车板 3.0；闭箱/高栏/集装箱/冷链 = 0（硬闸）。"""
    if m.category in COLOAD_POLICY["closed_categories"]:
        return float(COLOAD_POLICY["overhang_closed_m"])
    return float(COLOAD_POLICY["overhang_open_m"])


def gvm_tier(m: VehicleModel, count: int | None = None) -> int:
    """车货总重档：GVM = max_load_ton + curb_weight_ton 落 `GVM_TIERS_T` 哪一档（0/1/2/3）。

    数据留白（curb_weight_ton 空）⇒ 按已填值算（保守地偏低一档并不安全，故**如实相加**；
    前端/文档可用 `gvm_unknown` 标注数据缺口 —— 那是 T-B/E 的事，这里不猜）。
    """
    gvm = float(m.max_load_ton or 0.0) + float(m.curb_weight_ton or 0.0)
    for tier, bound in enumerate(GVM_TIERS_T):
        if gvm <= float(bound) + _EPS:
            return tier
    return len(GVM_TIERS_T)


def cost_caliber(distance_km: float | None) -> str:
    """成本口径：有距离 ⇒ `total`（费率×距离 + 固定调度费）；无 ⇒ `rate_only`（只比费率）。

    为什么要显式写出来：前端 `fit-vehicles` 长期不传距离，选型退化成「费率×车数」比较，
    这是**静默退化**（曾因此把固定费为 0 的高价车型排到最前）。口径进 `count_doctrine` 可追溯。
    """
    return "total" if float(distance_km or 0.0) > 0 else "rate_only"


def _stack_layers(it: dict, m: VehicleModel) -> int:
    """可叠层数：不可叠件（stackable=false）= 1；可叠件 = floor(载货限高 / 货高)（≥1）。"""
    if not it.get("stackable", True):
        return 1
    h = float(it.get("height_m") or 0.0)
    cap_h = float(m.max_cargo_height_m or 0.0)
    if h <= 0 or cap_h <= 0:
        return 1
    return max(1, int(cap_h // h))


def _rank_key(m: VehicleModel, n: int, distance_km: float | None) -> tuple:
    """车型排序键（v016）：① 车数 ② GVM 档 ③ 总价 ④ 载重富余 ⑤ 字典序。

    `价` = (base_rate × 距离 + 固定调度费) × 车数；无距离时退化为 费率 × 车数（口径见 `cost_caliber`）。
    `-max_load_ton` ⇒ 同档同价时**载重富余大者优先**（抗临时加货）。

    ⚠️ 与设计稿 §4「GVM 档为第一键」的差别（已在收尾报告说明）：落地时车数仍在第一键 ——
    冻结用例 `test_count_doctrine::test_two_pieces_share_a_truck_only_when_everything_fits`
    要求 20t×3 必须 <3 辆，而能给出 2 辆的只有把 GVM 推到 54t 的 40t 平板；若以档位为第一键，
    必然选出 3 辆（与 491 基线冲突）。档位仍**真实参与**排序（第二键）：同车数时「能不上更高
    许可档就绝不上」生效（顶盖/转轮/球阀 的 150t/250t 模块车否决就是这条）。
    """
    return (int(n), gvm_tier(m), _estimate_cost(m, n, distance_km),
            -float(m.max_load_ton or 0.0), str(m.model_id))


def _pick_best(scored: list[dict], distance_km: float | None) -> dict:
    """按 `_rank_key` 取最优 + **趟数豁免**（R9）：同 GVM 档内 少跑 ≥30% 且 价涨 ≤15% ⇒ 选少趟。

    记 `fewer_trips_exemption`（进 `count_doctrine`）便于审计「为什么不是最便宜的那辆」。
    """
    best = min(scored, key=lambda r: _rank_key(r["m"], r["n"], distance_km))
    b_price = _estimate_cost(best["m"], best["n"], distance_km)
    limit = float(best["n"]) * (1.0 - TRIP_REDUCTION_TRIGGER) + _EPS
    cands = [
        r for r in scored
        if r is not best and gvm_tier(r["m"]) == gvm_tier(best["m"])
        and float(r["n"]) <= limit
        and _estimate_cost(r["m"], r["n"], distance_km)
        <= b_price * (1.0 + COST_PREMIUM_FOR_FEWER_TRIPS) + _EPS
    ]
    if cands:
        pick = min(cands, key=lambda r: _rank_key(r["m"], r["n"], distance_km))
        pick["fewer_trips_exemption"] = True
        return pick
    return best


def width_tier(width_m: float) -> dict:
    """宽档位（专家 §4.2a）：返回 {tier, cn, vn, haul}。

    `haul=True` 表示仍在**自动配车上限**（T4 顶，4.5m）以内；>5.5 ⇒ 「超 T5」（强制三选一）。
    """
    w = float(width_m or 0.0)
    for bound, name, cn, vn in WIDTH_TIERS:
        if w <= bound + _EPS:
            return {"tier": name, "cn": cn, "vn": vn,
                    "haul": w <= float(DIM_POLICY["width_haul_m"]) + _EPS}
    return {"tier": "超 T5", "cn": "强制「分瓣 / 水运 / 改设计」三选一", "vn": "同上", "haul": False}


def height_total(cargo_h: float, deck_h: float | None) -> float | None:
    """总高口径（专家 §4.2b）：台面高 + 货高 + 垫木 reserve。

    台面高缺失（车型库 deck_height_m 留白）⇒ 返回 None：调用方必须退化到旧口径**并打警告标记**
    （不许静默 —— 旧口径把"台面 0.9 + 限高 3.0 + 1.5"算成 4.5m 总高，已经越过中/越许可现实区）。
    """
    if deck_h is None:
        return None
    return float(deck_h) + float(cargo_h) + float(DIM_POLICY["height_reserve_m"])


def height_flags(cargo_h: float, deck_h: float | None) -> tuple[list[str], bool]:
    """总高档位 → (flags, blocked)。

    阈值：≤4.0 中常规 / ≤4.2 越常规 / ≤4.5 许可 / ≤4.75 勘路 / >4.75 强制四选一 / >5.5 不自动配车。
    """
    total = height_total(cargo_h, deck_h)
    if total is None:
        return [], False
    reserve = float(DIM_POLICY["height_reserve_m"])
    prefix = f"总高 {total:.2f}m（台面 {float(deck_h):.2f} + 货 {float(cargo_h):.2f} + 垫木 {reserve:.2f}）"
    if total > float(DIM_POLICY["height_hard_m"]) + _EPS:
        return [f"{prefix} > {DIM_POLICY['height_hard_m']:g}m ⇒ 需强制降台面（低床/SPMT）/拆件/水运/特批"], True
    if total > 4.75 + _EPS:
        return [f"{prefix} > 4.75m ⇒ 需许可 + 勘路（并强制降台面/拆件/水运/特批）"], False
    if total > 4.5 + _EPS:
        return [f"{prefix} > 4.5m ⇒ 需许可并勘路（越路网净空 4.75m）"], False
    if total > 4.2 + _EPS:
        return [f"{prefix} > 4.2m（越法定）⇒ 需许可"], False
    if total > 4.0 + _EPS:
        return [f"{prefix} > 4.0m（中法定）⇒ 需许可（越侧 ≤4.2m 常规）"], False
    return [], False


def combined_length(cargo_l: float) -> float:
    """组合长 = 货长 + 前后悬（工程余量 3.0m）+ 主车长（6~7m 取中 6.5m）—— 专家 §4.2c。

    为什么要它：25m 大梁在 30m 台上"装得下"，但组合长 ≈34.5m ⇒ 中"三类件"、越"护送+勘路"；
    只看"车厢+3.0"会给用户一个**合法假方案**。
    """
    return float(cargo_l or 0.0) + float(DIM_POLICY["overhang_m"]) + float(DIM_POLICY["prime_mover_m"])


def length_flags(cargo_l: float) -> list[str]:
    """组合长档位（中/越两列）→ flags；组合长 ≤18.1m 时无标记。

    🆕 v016 T-D（E6）：组合长 > `COLOAD_POLICY["max_pair_len_m"]`（22.0m 路线工程上限）时，
    在同一 flag 内追加 E6 文案（键/中文名/第一步出自 `UNFIT_REASONS`，不散写）。
    """
    cl = combined_length(cargo_l)
    if cl <= 18.1 + _EPS:
        return []
    cn = next(name for bound, name in LENGTH_COMBINED_CN_TIERS if cl <= bound + _EPS)
    vn = next(name for bound, name in LENGTH_COMBINED_VN_TIERS if cl <= bound + _EPS)
    flag = (f"组合长 {cl:.2f}m（货 {float(cargo_l):.2f} + 前后悬 {DIM_POLICY['overhang_m']:g} "
            f"+ 主车 {DIM_POLICY['prime_mover_m']:g}）⇒ 中 {cn}；越 {vn}")
    if cl > float(COLOAD_POLICY["max_pair_len_m"]) + _EPS:
        # E6：超路线工程上限 ⇒ 第一步 改路线（避开城区/四级路）或分 2 段运
        flag += "；" + unfit_text("combo_length_over", combo=cl, l=float(cargo_l),
                                  overhang=float(DIM_POLICY["overhang_m"]),
                                  prime=float(DIM_POLICY["prime_mover_m"]),
                                  cap=float(COLOAD_POLICY["max_pair_len_m"]))
    return [flag]


def weight_tier(weight_t: float) -> dict:
    """重量档位：{tier, action, over_t}（over_t = 本档跨越的门槛吨位）。"""
    w = float(weight_t or 0.0)
    prev = 0.0
    for bound, name, action in WEIGHT_TIERS:
        if w <= bound + _EPS:
            return {"tier": name, "action": action, "over_t": prev}
        prev = bound
    return {"tier": "超重·专项/水运", "action": WEIGHT_TIERS[-1][2], "over_t": 200.0}


def weight_flags(weight_t: float) -> list[str]:
    """重量档 flags：≤32t 无标记；>32t 给档位 + 动作（含「一件一车（工程默认）」提示）。"""
    t = weight_tier(weight_t)
    if t["tier"] == "非超重":
        return []
    return [f"重 {float(weight_t):g}t ⇒ {t['tier']}（> {t['over_t']:g}t）：{t['action']}"]


def _single_required(it: dict, *, total_h: float | None) -> tuple[bool, str]:
    """是否 **一件一车**（返回 (True, 原因)）。

    依据（条号唯一真源 = `legal_refs`）：
      · 单件 >32t ⇒ **工程默认**（提示级）一件一车 —— 32t 断点**已无法规依据**；
        法定「超重货」= 整车总质量 >48t，只准 1 个单原（`legal_refs.vn.d10k2` + `vn.d12k2d`）。
      · 单件任一向超限（宽 >2.5 / 长 >20 / 总高 >4.2）⇒ 不满足「≥2 个单原」装载条件
        （`legal_refs.vn.d8k3`：纵向 ≤20m 且不超车厢、全宽 ≤2.5m）⇒ 退化为一件一车。
      · 旧一代条号（见 `legal_refs.VN_SUPERSESSION`）**已整体失效**，迁移映射见
        `legal_refs` 的 `MIGRATION_FROM_*` 表（旧通告的 Điều 11 只有 3 个 khoản，无此表述）。
    """
    w = float(it["weight_kg"]) / 1000.0
    if w > float(COLOAD_POLICY["one_piece_over_t"]) + _EPS:
        return True, (f"重 {w:.1f}t > {COLOAD_POLICY['one_piece_over_t']:g}t ⇒ 一件一车"
                      f"（工程默认；越侧法定「超重货」按整车总质量 >"
                      f"{COLOAD_POLICY['one_piece_gross_t']:g}t 判，{legal_refs.citation('vn.d12k2d')}）")
    if float(it["width_m"]) > PLAIN_WIDTH_M + _EPS:
        return True, (f"宽 {float(it['width_m']):.2f}m > {PLAIN_WIDTH_M:g}m ⇒ 不满足「≥2 个单原」装载条件"
                      f"（{legal_refs.citation('vn.d8k3')}）⇒ 一件一车")
    if float(it["length_m"]) > PLAIN_LENGTH_M + _EPS:
        return True, (f"长 {float(it['length_m']):.2f}m > {PLAIN_LENGTH_M:g}m ⇒ 纵向超限 ⇒ 一件一车"
                      f"（{legal_refs.citation('vn.d8k3')} / {legal_refs.citation('vn.d10k1')}）")
    if total_h is not None and total_h > PLAIN_TOTAL_HEIGHT_M + _EPS:
        return True, (f"总高 {total_h:.2f}m > {PLAIN_TOTAL_HEIGHT_M:g}m ⇒ 超高（越法定）⇒ 一件一车"
                      f"（{legal_refs.citation('vn.d10k1')} / {legal_refs.citation('vn.d8k3')}）")
    return False, ""


def _serial_cap(it: dict, m: VehicleModel) -> int:
    """**串联 cap**（档1 超限件，开关 ON 才启用）：沿车长串几件（宽度不叠加）。

        串联数 = min( floor((车厢长 + 悬伸) / 单件沿车长尺寸),   # 几何：串得下几件
                      floor((max_pair_len_m − 悬伸 − 主车) / 单件沿车长尺寸) )  # 组合长硬闸
        并排数 = 1                                              # 串联口径：宽度不叠加（取 max）
        重量闸 = floor(核定载重 / 单件重)
        cap    = max(1, min(串联数, 重量闸))
    硬闸：组合长 = 串联数 × 件长 + 悬伸 + 主车 ≤ `max_pair_len_m`（22.0m 工程上限）⇒ 超则 cap=1
          （一件一车）。闭箱类悬伸 = 0（`_overhang_m`）。
    """
    pl_len = float(it.get("length_m") or 0.0)
    payload = _payload_ton(m)
    w = _piece_weight_t(it)
    if pl_len <= 0 or payload <= 0:
        return 1
    overhang = _overhang_m(m)
    deck = float(m.length_m or 0.0)
    k_geom = int((deck + overhang) // pl_len)
    room = (float(COLOAD_POLICY["max_pair_len_m"]) - float(DIM_POLICY["overhang_m"])
            - float(DIM_POLICY["prime_mover_m"]))
    k_route = int(room // pl_len) if room > 0 else 0
    k = min(k_geom, k_route)
    if k < 1:
        return 1                       # 组合长硬闸不过 ⇒ 不许共车
    weight_cap = int(payload // w) if w > 0 else k
    return max(1, min(k, weight_cap))


def pieces_per_truck_cap(it: dict, m: VehicleModel, *, allow_oversized: bool = False) -> int:
    """一辆车最多装几件该货（「单件可同车上限」；≥1；**档0 超载 ⇒ 0**）。

    v016 三段口径（设计 §3.1；函数名保留，内部实现替换）：
      ① **单件超载**：单件重 > 核定载重（`registered_payload_ton` 回落 `max_load_ton`）⇒ **0**
         ——「该车型根本不可用」。⚠️ 开关 `allow_oversized` **一字不放**（超载中越两侧都无许可路径：
         中国《道路交通安全法》第 48 条；越南 legal_refs.vn.d8k2d + vn.d22k3a）。
      ② **档0 超重件**（单件 >32t 工程默认，或 单件重 + 该车整备 >48t 法定超重货）⇒ **1**（恒定）。
      ③ **档1 超限件** ⇒ `allow_oversized` ? 串联 cap（`_serial_cap`）: 1。
      ④ **档2 常规件** ⇒ min(载重商, 沿车长串联数 × 并排数 × 叠层数)。
         并排数只在**常规件**上叠加宽度（闭箱车宽有硬限；并排后仍须 ≤ 车厢宽）。
         闭箱类前后悬 = 0（`_overhang_m`）；不可叠件层数 = 1。

    用途：车数**守恒下限** n ≥ ceil(件数 / cap) —— 只作下限收敛，不追求装箱精度
    （精确装车是 `车辆数分解()`/装车器的活，INV-2 不破）；宁可偏大不可偏小，否则会虚报车数。
    """
    payload = _payload_ton(m)
    w = _piece_weight_t(it)
    if payload <= 0:
        return 1
    if w > payload + _EPS:
        return 0                                  # ① 单件超载 ⇒ 该车型不可用（开关不放松）
    tier = line_tier(it)
    if tier == 0:
        return 1                                  # ② 超重件：恒定一件一车
    if tier == 1:
        return _serial_cap(it, m) if allow_oversized else 1     # ③ 超限件：开关决定能否串联
    # ④ 档2 常规件：串联网格 + 并排 + 叠层（宽度只在并排口径下叠加）
    l, wid = float(it.get("length_m") or 0.0), float(it.get("width_m") or 0.0)
    cols = int((float(m.length_m or 0.0) + _overhang_m(m)) // l) if l > 0 else 1
    rows_deck = int(float(m.width_m or 0.0) // wid) if (m.width_m and wid > 0) else 1
    # 🆕 A1（2026-11，法条 `vn.d8k3`）：装载 ≥2 个单原同车时**合成全宽 ≤2.5m**。
    #   旧口径只判「不超车厢宽」——2.8m 车厢配 2×1.4m 货（合成 2.8m）会被放行，
    #   而法定上限是 2.5m（中国 2.55m，配车取严 2.5m）⇒ 并排列数还要受 2.5m 反推约束。
    #   实测旧值：低平板 13 米（车厢宽 2.8m）+ 1.4m 宽货 ⇒ rows=2（2.8m，违法）。
    rows_legal = int(PLAIN_WIDTH_M // wid) if wid > 0 else 1
    rows = max(1, min(rows_deck, rows_legal))
    grid = max(1, cols) * max(1, rows) * max(1, _stack_layers(it, m))
    weight_cap = int(payload // w) if w > 0 else grid
    return max(1, min(weight_cap, grid))


def _gvm_gross_t(it: dict, m: VehicleModel) -> float:
    """车货总重（t）= 单件重 + 该车整备 —— 越南「超重货」判据（>48t）的输入。"""
    return _piece_weight_t(it) + float(m.curb_weight_ton or 0.0)


def co_load_allowed(a: dict, b: dict, m: VehicleModel) -> tuple[bool, str, dict]:
    """两件货能不能同车（设计 §3.2 的 CO-1…CO-6）⇒ `(allowed, rule_id, 记录)`。

    ── 硬禁（任一命中 ⇒ False）──
    CO-1  A/B 属 `MUST_SOLO_CLASS`（危化品/活体/实验件——本版留空枚举，由业务后补）
    CO-2  A 或 B 为档0 超重件（单件 >32t；默认一件一车，本版不做「超重件串装放行」）
    CO-3  A 或 B 宽 > 4.5m（T5 特批件 —— 路线本身定死，加货会让勘验作废）
    CO-4  闭箱/高栏/集装箱/冷链 + 任一件超车厢（悬伸 = 0，硬闸）
    CO-5  `stackable=false` 的件要被压在另一件之上（装车器已硬拦，配车层同步标注）
    CO-6  允许：Σ单件重 ≤ 核定载重 × 0.98；Σ沿车长 ≤ 车厢长 + 悬伸；
          组合长 ≤ `max_pair_len_m`；车货总重不升档 ⇒ 记 rule_id = "CO-6"

    `记录` 里给 `mode`（serial/side）、`sum_weight_t`、`pair_total_width_m`（= max 件宽，
    **不叠加** —— 串联装载的整车外廓宽度与件数无关）、`gvm_tier`。
    """
    over_t = float(COLOAD_POLICY["one_piece_over_t"])
    payload = _payload_ton(m)
    hard = payload * float(COLOAD_POLICY["load_hard_cap"])
    overhang = _overhang_m(m)
    deck_l = float(m.length_m or 0.0)
    deck_w = float(m.width_m or 0.0)
    wa, wb = _piece_weight_t(a), _piece_weight_t(b)
    la, lb = float(a.get("length_m") or 0.0), float(b.get("length_m") or 0.0)
    wida, widb = float(a.get("width_m") or 0.0), float(b.get("width_m") or 0.0)
    pair_width = max(wida, widb)

    def _rec(mode: str, extra: dict | None = None) -> dict:
        rec = {"mode": mode, "sum_weight_t": round(wa + wb, 6),
               "pair_total_width_m": round(pair_width, 6),
               "gvm_tier": gvm_tier(m), "deck_len_m": deck_l, "overhang_m": overhang}
        rec.update(extra or {})
        return rec

    if getattr(m, "category", None) in MUST_SOLO_CLASS:
        return False, "CO-1", _rec("none", {"why": "must_solo_class"})
    if wa > over_t + _EPS or wb > over_t + _EPS:
        return False, "CO-2", _rec("none", {"why": "超重件默认一件一车"})
    if wida > float(DIM_POLICY["width_haul_m"]) + _EPS or widb > float(DIM_POLICY["width_haul_m"]) + _EPS:
        return False, "CO-3", _rec("none", {"why": "T5 特批件（宽 >4.5m）"})
    if m.category in COLOAD_POLICY["closed_categories"]:
        if (deck_l and (la > deck_l + _EPS or lb > deck_l + _EPS)) \
                or (deck_w and (wida > deck_w + _EPS or widb > deck_w + _EPS)):
            return False, "CO-4", _rec("none", {"why": "闭箱/高栏/集装箱/冷链不许悬伸"})
    serial_ok = bool(deck_l) and (la + lb <= deck_l + overhang + _EPS)
    # 🆕 A1（法条 `vn.d8k3`）：并排时合成全宽还要 ≤2.5m（中国 2.55m，取严）。
    #   只判「≤车厢宽」会放过 2.8m 车厢上的 2×1.4m 并排（=2.8m，超法定 2.5m）。
    side_ok = bool(deck_w) and (pair_width * 2 <= deck_w + _EPS) \
        and (pair_width * 2 <= PLAIN_WIDTH_M + _EPS)
    if not serial_ok and not side_ok:
        # 只能叠装：任一不可叠件 ⇒ 硬禁（CO-5）
        if not a.get("stackable", True) or not b.get("stackable", True):
            return False, "CO-5", _rec("stack", {"why": "不可叠件被压在另一件之上"})
        mode = "stack"
    else:
        mode = "serial" if serial_ok else "side"
    if payload <= 0 or wa + wb > hard + _EPS:
        return False, "CO-6", _rec(mode, {"why": f"Σ单件重 {wa + wb:.1f}t > 核定载重 × "
                                                  f"{COLOAD_POLICY['load_hard_cap']:g} = {hard:.1f}t"})
    along = la + lb if mode == "serial" else max(la, lb)
    if mode == "serial" and along > deck_l + overhang + _EPS:
        return False, "CO-6", _rec(mode, {"why": "Σ沿车长 > 车厢长 + 悬伸"})
    combo = along + float(DIM_POLICY["overhang_m"]) + float(DIM_POLICY["prime_mover_m"])
    if combo > float(COLOAD_POLICY["max_pair_len_m"]) + _EPS:
        return False, "CO-6", _rec(mode, {"why": f"组合长 {combo:.2f}m > "
                                                  f"{COLOAD_POLICY['max_pair_len_m']:g}m"})
    base_tier = gvm_tier(m)
    # 车货总重不升档（§4 的 gvm_tier 同档或更低）—— 车型 GVM 与件数无关，故按「整备 + Σ单件重」判
    if (float(m.curb_weight_ton or 0.0) + wa + wb) > float(GVM_TIERS_T[base_tier]) + _EPS:
        return False, "CO-6", _rec(mode, {"why": "车货总重升档（需更高许可档：勘路/桥涵/护送）"})
    return True, "CO-6", _rec(mode)


def _count_with_doctrine(it: dict, m: VehicleModel, n_breakdown: int,
                         *, allow_oversized: bool = False) -> tuple[int, int]:
    """车数口径（T4）：返回 (车数, 单件可同车上限)。

    n = max(车辆数分解().车数, ceil(件数 / 单件可同车上限))  —— 整数取整规则写死为 **ceil**。
    下限的物理含义：件不可再拆，一辆车装不下的那些件必须各占一个运输单元；
    行内单件 >32t 或三向超限 ⇒ 上限=1 ⇒ n ≥ 件数（一件一车）。
    🆕 v016：`cap = 0`（单件超核定载重 ⇒ 该车型不可用）时下限 = 件数（该行会在选型层被跳过）。
    """
    cap = pieces_per_truck_cap(it, m, allow_oversized=allow_oversized)
    count = max(1, int(it.get("count") or 1))
    n_floor = int(math.ceil(count / cap)) if cap > 0 else count
    return max(int(n_breakdown), n_floor), cap


def axle_lines_required(piece_w_t: float, *, selfweight_t: float | None = None) -> dict:
    """单件所需的**轴线条数**（拼轴口径，专家 §2.3）：n = ceil((货重 + 挂车自重) / q_轴)。

    q_轴 = 8t/轴线（三联轴组 24t ÷ 3；现行条号 legal_refs.vn.d14 —— 单轴 ≤10t、三联轴 24t，
    中国 GB1589 同族）；挂车自重按 35/50/65t 三档给成区间（不假装精确）：
    150t ⇒ 24–27 轴线、225t ⇒ 33–37 轴线。
    """
    q = float(DIM_POLICY["axle_q_t"])
    w = float(piece_w_t or 0.0)
    sw = float(selfweight_t) if selfweight_t is not None else AXLE_SELFWEIGHT_DEFAULT_T
    lines = int(math.ceil((w + sw) / q))
    lines_min = int(math.ceil((w + AXLE_SELFWEIGHT_CANDIDATES_T[0]) / q))
    lines_max = int(math.ceil((w + AXLE_SELFWEIGHT_CANDIDATES_T[-1]) / q))
    lo, hi = min(lines_min, lines), max(lines_max, lines)
    return {"lines": lines, "lines_min": lo, "lines_max": hi,
            "selfweight_t": sw, "q_axle_t": q,
            "note": (f"轴荷/桥涵：单件 {w:.1f}t 需 {lines_min}–{lines_max} 轴线"
                     f"（{q:g}t/轴线口径，挂自重 {AXLE_SELFWEIGHT_CANDIDATES_T[0]:g}–"
                     f"{AXLE_SELFWEIGHT_CANDIDATES_T[-1]:g}t；{legal_refs.citation('vn.d14')}）")}


def _axle_info(it: dict, m: VehicleModel) -> dict | None:
    """>100t 级重货的拼轴核算（**运输单元数 ≠ 轴线条数**，两个量分离输出）。

    库载轴线条数取车型 `axle_lines` 列；留白时按型号名解析（`..._20axle...`）或标"待补"。
    """
    w = float(it["weight_kg"]) / 1000.0
    if w <= AXLE_REQUIRED_OVER_T + _EPS:
        return None
    req = axle_lines_required(w)
    avail = m.axle_lines
    if avail is None:
        mx = re.search(r"(\d+)\s*axle", str(m.model_id or ""), re.I)
        avail = int(mx.group(1)) if mx else None
    info = dict(req)
    info["available"] = avail
    info["shortfall"] = bool(avail is not None and avail < req["lines_min"])
    if avail is None:
        info["note"] += "；库载轴线数待补（axle_lines 列留白）"
    elif info["shortfall"]:
        # 🆕 v016 T-D（E5）：轴荷缺口**进 permit_flags**（唯一文案处；结构化字段
        #   `count_doctrine.axle_shortfall` / 行级 `axle_lines.shortfall` 同源保留）——
        #   文案模板/第一步统一出自 `UNFIT_REASONS["gvm_axle_shortfall"]`（不散写）。
        info["note"] += ("；库载 " + str(avail) + " 轴线不足 ⇒ "
                         + unfit_text("gvm_axle_shortfall", w=w, lines_min=req["lines_min"],
                                      q=float(DIM_POLICY["axle_q_t"]), avail=avail,
                                      gap=int(req["lines_min"]) - int(avail)))
    else:
        info["note"] += f"；库载 {avail} 轴线"
    return info


def _permit_flags(it: dict, m: VehicleModel, *, released: bool = False) -> list[str]:
    """法规层标记（与 dim_flags **分列**）：许可 / 勘路 / 护送 / 桥涵 / 一件一车 / 轴荷 + 越许可两个坑。

    只在**选中的车型**上计算（高度档与台面高绑定）。🆕 热修 v015.8（P2-2）：车型 `deck_height_m`
    留白时，「台面高缺失…需补后按总高口径复核」警告**同时进本通道**（高度维不许在许可层静默）。
    🆕 v016（设计 §6.3）：
      · `released=True`（该组是靠「允许超限运输配车」开关 ON 放行的）⇒ **前置**一条放行警示
        （须持超限许可、按许可时间/路线/速度行驶；**不放松超载**）；
      · 车货总重 >48t ⇒ 越侧「超重货」标注（`legal_refs.vn.d10k2` / `vn.d12k2d`：只准 1 个单原）。
    """
    w = float(it["weight_kg"]) / 1000.0
    l, wid, h = float(it["length_m"]), float(it["width_m"]), float(it["height_m"])
    total = height_total(h, m.deck_height_m)
    out: list[str] = []
    if released:
        out.append("⚠ 超限放行（allow_oversized=ON）：本组方案含超限件 —— 出车/导出报价单前须确认已（或将）"
                   "办妥超限运输许可（中国《超限运输车辆通行证》；越南 giấy phép lưu hành xe，"
                   + legal_refs.citation("vn.d24") + "），并按许可指定的时间/路线/速度行驶；"
                   "本开关**不放松超载**（单件超核定载重仍不自动配车）")
    out += weight_flags(w)
    if wid > 2.5 + _EPS:
        t = width_tier(wid)
        out.append(f"宽 {wid:.2f}m ⇒ {t['tier']}（中：{t['cn']}；越：{t['vn']}）")
    out += height_flags(h, m.deck_height_m)[0]
    if m.deck_height_m is None:
        # 🆕 热修 v015.8（P2-2）：高度维在 permit 通道**不许静默** —— 缺台面高时 dim_flags 有警告，
        #   许可层也必须带同一条（此前 `height_flags(_, None) → ([], False)` 被本函数直接吞掉）。
        out.append(_MISSING_DECK_WARN)
    out += length_flags(l)
    single, why = _single_required(it, total_h=total)
    if single:
        out.append(why)
    gross = _gvm_gross_t(it, m)
    if gross > float(COLOAD_POLICY["one_piece_gross_t"]) + _EPS:
        # 🆕 v016：法定「超重货」= 整车总质量 >48t（旧 32t 单件断点已无法规依据）
        out.append(f"车货总重 {gross:.1f}t > {COLOAD_POLICY['one_piece_gross_t']:g}t ⇒ 越侧「超重货」"
                   f"（{legal_refs.citation('vn.d10k2')}）：只准 1 个单原（{legal_refs.citation('vn.d12k2d')}），"
                   f"加货/共车须重办许可")
    axle = _axle_info(it, m)
    if axle:
        out.append(axle["note"])
    # 🆕 A3（2026-11）：中国大件许可档位 + 办理时限（省内/跨省工作日）
    #   旧口径只说「需许可」，客户无法预判 2 天还是 15 天；办证周期直接决定交期承诺。
    _gross_all = w * int(it.get("count") or 1) + float(m.curb_weight_ton or 0.0)
    _cn = cn_permit_flag(
        height_m=total,
        width_m=max(wid, float(m.width_m or 0.0)),
        length_m=max(l, float(m.length_m or 0.0)),
        gross_t=_gross_all,
    )
    if _cn:
        out.append(_cn)
    # 🆕 A4（2026-11）：中国轴荷许可门槛
    #   液压多轴平板按「每轴线 18/20t」，普通车按「单轴 10/13t」—— 两个口径不能混用。
    #   ⚠️ 车型库没有 `axle_caliber` 列，这里只能按「可侧伸字段 + 名称关键词」判液压类；
    #   长期应在库里补一列（数据缺口已记入文档，不在代码里猜数值）。
    _hydraulic = (m.deck_width_extendable_m is not None
                  or any(k in str(m.display_name) for k in ("轴线", "模块", "桥式")))
    _axle_units = (m.axle_lines if _hydraulic else (m.axle_count or m.axle_lines))
    _ap = cn_axle_permit_flag(gross_t=_gross_all, axle_units=_axle_units, hydraulic=_hydraulic)
    if _ap:
        if m.curb_weight_ton is None:
            _ap += "（该车型整备质量留白 ⇒ 车货总重按货重计，实车须按行驶证整备质量复核）"
        out.append(_ap)
    # 越许可两个坑：出现任一许可级标记（超重/超宽/超高/组合长>20m）就随附
    if (w > float(COLOAD_POLICY["one_piece_over_t"]) + _EPS or wid > 2.5 + _EPS
            or (total is not None and total > 4.2 + _EPS) or combined_length(l) > 20.0 + _EPS):
        out += list(PERMIT_PITFALLS)
    return _dedup(out)


def _dim_verdict(it: dict, m: VehicleModel, *, allow_oversized: bool = False) -> tuple[str, list[str]]:
    """单件 长/宽/高 对车型载货空间：返回 ("ok"|"over"|"no", [标记/原因])。

    ok   = 三向都装得下（法规许可判定不在这里 —— 许可档在 permit_flags 里）；
    over = 超限但**可运**（超宽五档内 / 前后悬 / 总高勘路档），自动配车并打标；
    no   = 超出可运上限 ⇒ 不自动配车（点名走分瓣/伸缩板/T5 特批/专批）。

    🆕 v016（设计 §6.1）`allow_oversized=True` ⇒ **no 档在硬红线内降级为 over**：
      · 宽 4.5–5.5m ⇒ over（可配车 + 许可标）；宽 >5.5m ⇒ **仍 no**；
      · 总高 4.75–5.5m 现状已是 over（>5.5m 仍 no —— 硬红线不动）；
      · 超长逾车厢 +3.0m ⇒ 仍 no（不变）。
    红线依据：超限在中越两侧都有许可路径；**超载**（单件 > 核定载重）与**桥涵/轴荷**永不放行
    （中国《超限运输车辆行驶公路管理规定》第十七条不予许可情形；越南 legal_refs.vn.d22k3a）。

    阈值唯一真源 = DIM_POLICY + WIDTH_TIERS（判据 4：改策略常量 ⇒ 结果按预期变）。
    """
    l, w, h = it["length_m"], it["width_m"], it["height_m"]
    deck_l, deck_w = m.length_m or 0.0, m.width_m or 0.0
    cargo_h = m.max_cargo_height_m or 0.0
    flags: list[str] = []
    over = False
    # 🆕 A5（2026-11）：专用超长车（可运 ≥40m 的叶片车/举升车）不接常规短件 ——
    #   否则它的「GVM 档更低」会在 `_rank_key` 里压过价格，把 30m 塔筒这类常规大件
    #   报到更贵的专用车上（实测 88,000 → 110,000）。
    if deck_l >= float(DIM_POLICY["long_special_deck_m"]) \
            and l and l < float(DIM_POLICY["long_special_min_cargo_m"]) - _EPS:
        return "no", [f"专用超长车（可运 ≥{float(DIM_POLICY['long_special_min_cargo_m']):.0f}m 单件）"
                      f"不接 {l:.1f}m 常规件 ⇒ 换常规大件车型"]
    # 🆕 v016 T-D（E7 选型侧硬闸）：闭箱/高栏/集装箱/冷链类**不许悬伸**（悬伸=0，`_overhang_m`）——
    #   单件任一向超车厢（需悬伸）⇒ 该车型不适用（与 `co_load_allowed` 的 CO-4、cap 的 overhang=0 同口径）。
    #   旧行为是照样按 `over` 放行 ⇒ "闭箱车吃超宽件"；实车无法伸出/无法绑扎外廓，必须换开放车板。
    if m.category in COLOAD_POLICY["closed_categories"]:
        _parts = []
        if deck_w and w > deck_w + _EPS:
            _parts.append(f"宽 {float(w):.2f}m>车厢宽{float(deck_w):.2f}m")
        if deck_l and l > deck_l + _EPS:
            _parts.append(f"长 {float(l):.2f}m>车厢长{float(deck_l):.2f}m")
        if _parts:
            return "no", [f"闭箱/高栏/集装箱/冷链类不许悬伸（悬伸=0）：{'；'.join(_parts)}"
                          f" ⇒ 需换开放车板（{m.display_name} 装不了该件）"]
    if deck_l and l > deck_l:
        excess = l - deck_l
        # 🆕 A2（法条 vn.d17 + 中国 18.1m）：常规装载长度上限 = min(1.1×车长, 20.0, 18.1)。
        #   落在这条线内 = 法定允许的悬伸装载，**不需要大件许可**（旧口径一律判「需许可」）。
        _regular_max = min(deck_l * float(DIM_POLICY["len_regular_ratio"]),
                           20.0, float(DIM_POLICY["len_regular_cap_m"]))
        if l <= _regular_max + _EPS:
            flags.append(f"超长 {l:.2f}m>车厢{deck_l:.2f}m（法定常规悬伸 ≤{_regular_max:.2f}m，无需许可）")
        elif excess <= float(DIM_POLICY["len_over_m"]) + _EPS:
            flags.append(f"超长 {l:.2f}m>车厢{deck_l:.2f}m（前后悬/伸缩板，需许可；组合长另计）")
            over = True
        else:
            return "no", [f"超长：{l:.2f}m 超车厢 {deck_l:.2f}m 逾 {DIM_POLICY['len_over_m']:g}m"
                          f" ⇒ 需伸缩板/纵向分段（厂家书面确认）或专询"]
    if deck_w and w > deck_w + _EPS:
        if w <= float(DIM_POLICY["width_haul_m"]) + _EPS:
            t = width_tier(w)
            flags.append(f"超宽 {w:.2f}m>车宽{deck_w:.2f}m（{t['tier']}：中 {t['cn']}；越 {t['vn']}）")
            over = True
        elif w <= WIDTH_HARD_LIMIT_M + _EPS:
            if allow_oversized:
                # 🆕 v016：4.5~5.5m 的 T5 档在**开关 ON** 时降级为「超限可运」（硬红线内）
                t = width_tier(w)
                flags.append(f"超限放行（开关 ON）：宽 {w:.2f}m 超可运上限 "
                             f"{DIM_POLICY['width_haul_m']:g}m（{t['tier']}，≤{WIDTH_HARD_LIMIT_M:g}m）"
                             f" ⇒ 按「超限可运」配车，须持超限运输许可通行；"
                             f"中 {t['cn']}；越 {t['vn']}")
                over = True
            else:
                # T5 特批/专询（4.5~5.5m）：不是"不可运"，是**不自动配车 + 给降档路径**
                return "no", [f"超宽：{w:.2f}m 超可运上限 {DIM_POLICY['width_haul_m']:g}m ⇒ 需 T5 特批/专询"
                              f"（≤{WIDTH_HARD_LIMIT_M:g}m：中 专项评估；越 逐段勘验 + 可能加固；或分瓣降宽）"]
        else:
            return "no", [f"超宽：{w:.2f}m 超 T5 上限 {WIDTH_HARD_LIMIT_M:g}m"
                          f" ⇒ 需强制「分瓣 / 水运 / 改设计」三选一"]
    if m.deck_height_m is None:
        # 【退化旧口径】台面高缺失 ⇒ 按"货高 ≤ 载货限高 + 1.5m"评，并**打警告标记**（不许静默）
        if cargo_h and h > cargo_h + float(DIM_POLICY["height_over_m"]) + _EPS:
            return "no", [f"超高：{h:.2f}m 超载货限高 {cargo_h:.2f}m + {DIM_POLICY['height_over_m']:g}m 余量"
                          f" ⇒ 需降台面（低床/SPMT）/拆件/水运/特批（台面高缺失，按旧口径评定）"]
        flags.append(_MISSING_DECK_WARN)      # P2-2 热修：同一条警告也进 permit 通道（见 _permit_flags）
        if cargo_h and h > cargo_h + _EPS:
            flags.append(f"超高 {h:.2f}m>限高{cargo_h:.2f}m（旧口径：需勘路）")
            over = True
    else:
        hflags, blocked = height_flags(h, m.deck_height_m)
        if blocked:
            return "no", hflags
        if hflags:
            flags.extend(hflags)
            over = True
    return ("over" if over else "ok"), flags


def _line_payload(it: dict) -> dict:
    """把**一行**货折算成载荷特征（车数用同一套 车辆数分解，INV-2 不破）。"""
    return 公式.货物载荷特征完整(
        货物总重量吨=it["weight_kg"] * it["count"] / 1000.0,
        货物总体积立方米=it["length_m"] * it["width_m"] * it["height_m"] * it["count"],
        单件货物=[it],
    )


def _line_breakdown(it: dict, m: VehicleModel, *, allow_oversized: bool = False) -> dict | None:
    """喂给 `车辆数分解()` 的**单件参数**（INV-2：算法不变，只改喂进去的参数）。

    返回 `车辆数分解()` 结果；`不可分`（单件超载）或算不出车数 ⇒ None（该车型不适用）。

    🆕 v016 串联口径（**只对档1 超限件的串联共车生效**，开关 ON 时）：占地面积这一项改用
    「**车板占用面积**」而不是「单件外包络面积」——
        `面积 := Σ(件数 × 沿车长尺寸 × 车厢宽) / 串联数`
    为什么：超宽件（如定子机座 6 瓣 3.90m > 车厢宽）在车板上是**沿车长串联**摆放，宽度一部分
    悬在车外 ⇒ 真正占用车板的是「沿车长 × 车厢宽」，且一辆车放 `串联数` 件 ⇒ 单件等效占用
    再除以串联数。不改这一步的话，`面积` 约束会把「2 件串联」的 13m 平板算成 19 辆
    （= 每件一件一车的口径），串联共车等于白做。改完与设计稿 §3.3/§9 A3/A7 的实测数字一致
    （13m 平板 ×12 件、阈值 22→30m 时 17.5m 平板 ×8）。
    """
    feat = _line_payload(it)
    w = it["weight_kg"] * it["count"] / 1000.0
    v = it["length_m"] * it["width_m"] * it["height_m"] * it["count"]
    area = feat["总占地面积平方米"]
    serial_k = 1
    if allow_oversized and line_tier(it) == 1:
        serial_k = _serial_cap(it, m)
    if serial_k >= 2 and m.width_m and float(it["length_m"] or 0.0) > 0:
        area = (float(it["count"]) * float(it["length_m"]) * float(m.width_m)) / float(serial_k)
    bd = 公式.车辆数分解(
        货物总重量吨=w, 货物总体积立方米=v,
        最大单件长度米=feat["最大单件长度米"], 货物总占地面积平方米=area,
        车型最大载重吨=m.max_load_ton, 车型容积立方米=m.effective_volume_m3,
        车型地板长米=m.length_m, 车型地板面积平方米=m.floor_area_m2,
        装载效率=m.loading_efficiency, 最大单件重量吨=feat["最大单件重量吨"],
        # 🆕 A7：单件占满车厢的口径
        件总数=int(it.get("count") or 1),
        最大单件宽度米=(float(it.get("width_m") or 0) or None), 车型宽度米=m.width_m,
    )
    if bd.get("不可分") or int(bd.get("车数") or 0) <= 0:
        return None
    return bd


def _line_hit(it: dict, m: VehicleModel, bd: dict, distance_km: float | None,
              *, allow_oversized: bool = False, verdict: str, flags: list[str]) -> dict:
    """把「单行 × 单车型」的打分结果装成统一记录（`_pick_for_line` / `_pick_for_pool` 共用）。

    `released`：该行**只有靠开关 ON 才拿得到车**（OFF 时 `_dim_verdict` 判 no）⇒ 组级
    `oversize_released` 与许可警示都靠它；`pair_total_width` 只在真的共车（cap ≥ 2）时给。
    """
    n_bd = int(bd.get("车数") or 0)
    n, cap = _count_with_doctrine(it, m, n_bd, allow_oversized=allow_oversized)
    released = bool(allow_oversized and _dim_verdict(it, m, allow_oversized=False)[0] == "no"
                    and verdict != "no")
    return {"m": m, "n": n, "bd": bd, "flags": list(flags), "cap": cap,
            "verdict": verdict, "released": released,
            "pair_width": float(it.get("width_m") or 0.0) if cap >= 2 else None,
            "floor": int(math.ceil(max(1, int(it.get("count") or 1)) / cap)) if cap > 0
                     else max(1, int(it.get("count") or 1)),
            "four_const": n_bd, "fewer_trips_exemption": False}


def _pick_for_line(it: dict, bucket: list[VehicleModel], distance_km: float | None,
                   *, allow_oversized: bool = False) -> dict | None:
    """给**一行**货在给定车型桶里挑最优。

    返回 `_line_hit()` 记录（车型/车数/车辆数分解/dim_flags/单件可同车上限/放行标记）或 None。
    先按**长宽高全适配**（`_dim_verdict == "ok"`）挑；一个都没有 ⇒ 退到**超限可运**（"over"）；
    仍没有 ⇒ None（该行点名）。车数按 T4/v016 口径校准（一件一车 + 守恒下限 ceil）。
    排序键 = `_rank_key`（车数 → GVM 档 → 总价 → 载重 → 字典序）+ 趟数豁免。
    """
    ok_hits: list[dict] = []
    over_hits: list[dict] = []
    for m in bucket:
        verdict, flags = _dim_verdict(it, m, allow_oversized=allow_oversized)
        if verdict == "no":
            continue
        bd = _line_breakdown(it, m, allow_oversized=allow_oversized)
        if bd is None:
            continue                      # 单件 > 载重（不可分）或算不出车数
        hit = _line_hit(it, m, bd, distance_km, allow_oversized=allow_oversized,
                        verdict=verdict, flags=flags)
        (ok_hits if verdict == "ok" else over_hits).append(hit)
    hits = ok_hits or over_hits
    if not hits:
        return None
    return _pick_best(hits, distance_km)


# ── 🆕 v016 T-D：E5/E7 判定原语（`_line_block` 与选型/组装共用同一口径）────────────

def _axle_shortfall_anywhere(it: dict, models: list[VehicleModel]) -> dict | None:
    """E5 全局判据（「配不出」场景）：>100t 级件、**载重够的全部车型轴线条数都不够** ⇒ 命中。

    只在「所有 `payload ≥ 单件重` 的车型都 shortfall」时命中 —— 只要库里还有一辆载重/轴线都够的车，
    就不算 E5（那属于"该车型为什么没被选中"的别的问题）。数据留白（axle_lines 空）按「不算
    shortfall」处理（与 `_axle_info` 同口径），不拿缺数据当结论。本版无「拼轴扩容上限」数据 ⇒
    命中即视为**不可拼轴**，处置第一步 = 提轴数/拼轴或换更大装备（`UNFIT_REASONS` 单一真源）。

    返回 `{gap, lines_min, avail, model_id, note}` 或 None（note 带 `E5 gvm_axle_shortfall` 标记）。
    """
    w = _piece_weight_t(it)
    if w <= AXLE_REQUIRED_OVER_T + _EPS:
        return None
    viable = [m for m in models if _payload_ton(m) >= w - _EPS]
    if not viable:
        return None
    infos: list[tuple[VehicleModel, dict]] = []
    for m in viable:
        info = _axle_info(it, m)
        if not info or not info.get("shortfall"):
            return None                    # 存在够用的车 ⇒ 不判 E5
        infos.append((m, info))
    m_best, info_best = max(infos, key=lambda t: (t[1]["available"] or 0))
    gap = int(info_best["lines_min"]) - int(info_best["available"])
    return {"gap": gap, "lines_min": int(info_best["lines_min"]), "avail": int(info_best["available"]),
            "model_id": m_best.model_id,
            "note": unfit_text("gvm_axle_shortfall", w=w, lines_min=int(info_best["lines_min"]),
                               q=float(DIM_POLICY["axle_q_t"]), avail=int(info_best["available"]),
                               gap=gap)}


def _deck_unfit_closed(it: dict, candidates: list[VehicleModel] | None) -> dict | None:
    """E7 判据：**候选只剩**闭箱/高栏/集装箱/冷链类、且该件需悬伸（超宽/超长）装不下？

    条件（全真才命中）：
      · `candidates` 非空，且**每一辆**都是闭箱类（`COLOAD_POLICY["closed_categories"]`）；
      · 每一辆按**核定载重**都载得动该件（载重都不够 ⇒ 不是「外形（悬伸）」问题）；
      · 每一辆都被「悬伸=0」卡住（宽 > 车厢宽 或 长 > 车厢长）。

    返回 `{model_ids, axis("宽"|"长"), over_by, max_deck_w_m, max_deck_l_m}` 或 None。
    """
    if not candidates:
        return None
    w = _piece_weight_t(it)
    l = float(it.get("length_m") or 0.0)
    wid = float(it.get("width_m") or 0.0)
    closed: list[VehicleModel] = []
    for m in candidates:
        if m.category not in COLOAD_POLICY["closed_categories"]:
            return None                    # 候选里不只剩闭箱类 ⇒ 不判 E7
        if _payload_ton(m) < w - _EPS:
            return None                    # 载重就不够 ⇒ 不是「外形」问题
        closed.append(m)
    if not closed:
        return None
    if not all(((m.width_m and wid > m.width_m + _EPS) or (m.length_m and l > m.length_m + _EPS))
               for m in closed):
        return None                        # 有闭箱装得下（车厢内）⇒ 不判 E7
    max_w = max((m.width_m or 0.0) for m in closed)
    max_l = max((m.length_m or 0.0) for m in closed)
    axis = "宽" if wid > max_w + _EPS else "长"
    over = (wid - max_w) if axis == "宽" else (l - max_l)
    return {"model_ids": [m.model_id for m in closed], "axis": axis, "over_by": round(over, 3),
            "max_deck_w_m": max_w, "max_deck_l_m": max_l}


def _e7_dim_text(it: dict, e7: dict) -> str:
    """E7 文案里的「维度 + 差量」段（`_line_block` 与选型标记共用，防止两处写两套）。"""
    if e7["axis"] == "宽":
        return (f"宽 {float(it.get('width_m') or 0):.2f}m > 闭箱类最大车厢宽 "
                f"{e7['max_deck_w_m']:.2f}m")
    return (f"长 {float(it.get('length_m') or 0):.2f}m > 闭箱类最长车厢 "
            f"{e7['max_deck_l_m']:.2f}m")


def _open_deck_feasible(it: dict, models: list[VehicleModel]) -> bool:
    """E7 的前置：该件换成**开放车板**是否可行（宽 ≤自动配车上限 4.5m / 长 ≤车厢+悬伸 / 总高 ≤硬上限）。

    只有开放车板确实能接，E7 的「第一步：换开放车板」才是真出路（否则是 T5/高 等别的真因）。
    """
    w = _piece_weight_t(it)
    l = float(it.get("length_m") or 0.0)
    h = float(it.get("height_m") or 0.0)
    if w <= 0 or float(it.get("width_m") or 0.0) > float(DIM_POLICY["width_haul_m"]) + _EPS:
        return False
    for m in models:
        if m.category in COLOAD_POLICY["closed_categories"] or not m.length_m:
            continue
        if _payload_ton(m) < w - _EPS:
            continue
        if l > float(m.length_m) + float(DIM_POLICY["len_over_m"]) + _EPS:
            continue
        if m.deck_height_m is not None:
            total = height_total(h, m.deck_height_m)
            if total is not None and total > float(DIM_POLICY["height_hard_m"]) + _EPS:
                continue
        return True
    return False


def _line_block(it: dict, all_models: list[VehicleModel], fold, *, candidates=None) -> dict:
    """一行货为什么配不出车 ⇒ {reason, blocked_axis, over_by, permit_flags, actions}。

    🆕 v016 T-D 判定顺序（设计 §7 / 意见书 §6，分支自上而下）：
      `E1 重 → E5 轴荷 → E6 组合长 → E2 长 → E7 车型外形 → 宽(T5) → 高` → 数据/形态缺口兜底。
    文案统一「维度 + 差量 + 需…（处置路径）」；**禁止**用"库内最大载重"当"运不了"的理由
    （那是库缺，只可用于"需更高等级装备"，专家 §4.2d）。原因串/「最低成本第一步」只许出自
    `UNFIT_REASONS`（E5/E6/E7 三类为 v016 新增；`candidates` = 该行的**货型候选集**，E7 判据用它
    判断「候选只剩闭箱类」；既有调用不传 = 不判 E7，行为不变）。
    """
    w = float(it["weight_kg"]) / 1000.0
    l, wid, h = float(it["length_m"]), float(it["width_m"]), float(it["height_m"])
    max_load = max((m.max_load_ton or 0.0 for m in all_models), default=0.0)
    max_deck = max((m.length_m or 0.0 for m in all_models), default=0.0)
    decks = [m.deck_height_m for m in all_models if m.deck_height_m]
    min_deck = min(decks) if decks else None
    max_h = max((m.max_cargo_height_m or 0.0 for m in all_models), default=0.0)
    # ① E1 重：库内无单车可载 ⇒ 库缺（不是"运不了"）
    if w and max_load and w > max_load + _EPS:
        return {
            "blocked_axis": "重", "over_by": round(w - max_load, 3),
            "reason": unfit_block_msg("piece_overload", w=w, max_load=max_load),
            "permit_flags": weight_flags(w),
            "actions": list(UNFIT_REASONS["piece_overload"]["actions"]),
        }
    # ② E5 轴荷：>100t 级件、载重够的全部车型轴线条数都不够（且不可拼轴）⇒ 提轴数/拼轴或换更大装备
    e5 = _axle_shortfall_anywhere(it, all_models)
    if e5 is not None:
        return {
            "blocked_axis": "轴荷", "over_by": e5["gap"],
            "reason": e5["note"],
            "permit_flags": _dedup([*weight_flags(w), e5["note"]]),
            "actions": list(UNFIT_REASONS["gvm_axle_shortfall"]["actions"]),
        }
    # ③ E6 组合长：超路线工程上限（22.0m）但**仍装得进库内车厢 + 悬伸** ⇒ 改路线或分 2 段运
    #   （装不进库内车厢的件归 E2 长：既有冻结契约不许被 E6 抢答）
    combo = combined_length(l)
    if (l and combo > float(COLOAD_POLICY["max_pair_len_m"]) + _EPS
            and l <= max_deck + float(DIM_POLICY["len_over_m"]) + _EPS):
        return {
            "blocked_axis": "长", "over_by": round(combo - float(COLOAD_POLICY["max_pair_len_m"]), 3),
            "reason": unfit_text("combo_length_over", combo=combo, l=l,
                                 overhang=float(DIM_POLICY["overhang_m"]),
                                 prime=float(DIM_POLICY["prime_mover_m"]),
                                 cap=float(COLOAD_POLICY["max_pair_len_m"])),
            "permit_flags": length_flags(l),
            "actions": list(UNFIT_REASONS["combo_length_over"]["actions"]),
        }
    # ④ E2 长：超库内最长车厢 + 3.0m 余量
    if l and max_deck and l > max_deck + float(DIM_POLICY["len_over_m"]) + _EPS:
        over = l - max_deck - float(DIM_POLICY["len_over_m"])
        return {
            "blocked_axis": "长", "over_by": round(over, 3),
            "reason": unfit_block_msg("piece_overlong", l=l, max_deck=max_deck,
                                      overhang=float(DIM_POLICY["len_over_m"])),
            "permit_flags": length_flags(l),
            "actions": list(UNFIT_REASONS["piece_overlong"]["actions"]),
        }
    # ⑤ E7 车型外形：候选只剩闭箱/高栏/集装箱/冷链类（悬伸=0）、该件需悬伸装不下 ⇒ 换开放车板
    e7 = _deck_unfit_closed(it, candidates)
    if e7 is not None and _open_deck_feasible(it, all_models):
        return {
            "blocked_axis": e7["axis"], "over_by": e7["over_by"],
            "reason": unfit_text("deck_unfit_closed", dim=_e7_dim_text(it, e7)),
            "permit_flags": [],
            "actions": list(UNFIT_REASONS["deck_unfit_closed"]["actions"]),
        }
    # ⑥ 宽：4.5~5.5 T5 特批/专询（不是"不可运"）；>5.5 强制三选一
    if wid and wid > float(DIM_POLICY["width_haul_m"]) + _EPS:
        t = width_tier(wid)
        if wid <= WIDTH_HARD_LIMIT_M + _EPS:
            return {
                "blocked_axis": "宽", "over_by": round(wid - float(DIM_POLICY["width_haul_m"]), 3),
                "reason": (f"超宽：{wid:.2f}m 超可运上限 {DIM_POLICY['width_haul_m']:g}m ⇒ 需 T5 特批/专询"
                           f"（≤{WIDTH_HARD_LIMIT_M:g}m：中 专询/专项评估；越 逐段勘验 + 可能加固）"),
                "permit_flags": _dedup([f"宽 {wid:.2f}m ⇒ {t['tier']}（中：{t['cn']}；越：{t['vn']}）",
                                        *PERMIT_PITFALLS]),
                "actions": ["需 T5 特批/专询（专项评估 / 逐段勘验 + 可能加固）",
                            "降档路径（需分瓣/特批）：分瓣降宽（如座环-蜗壳分体拆运）",
                            "替代方式：库区/内河驳船（越许可前置需声明无其他运输方式）"],
            }
        return {
            "blocked_axis": "宽", "over_by": round(wid - WIDTH_HARD_LIMIT_M, 3),
            "reason": (f"超宽：{wid:.2f}m 超 T5 上限 {WIDTH_HARD_LIMIT_M:g}m"
                       f" ⇒ 需强制「分瓣 / 水运 / 改设计」三选一"),
            "permit_flags": [f"宽 {wid:.2f}m ⇒ 超 T5 上限 {WIDTH_HARD_LIMIT_M:g}m"],
            "actions": ["需分瓣降宽", "需水运（库区/内河驳船）", "需改设计（分段/分体）"],
        }
    # ④ 高：总高口径（按最优台面高仍超硬上限）
    if min_deck is not None:
        total = height_total(h, min_deck)
        if total is not None and total > float(DIM_POLICY["height_hard_m"]) + _EPS:
            return {
                "blocked_axis": "高", "over_by": round(total - float(DIM_POLICY["height_hard_m"]), 3),
                "reason": (f"超高：{h:.2f}m（按最低台面 {min_deck:.2f}m 的总高 {total:.2f}m 仍 > 上限 "
                           f"{DIM_POLICY['height_hard_m']:g}m）⇒ 需降台面（低床/SPMT）/拆件/水运/特批"),
                "permit_flags": height_flags(h, min_deck)[0],
                "actions": ["需降台面（低床/SPMT）或拆件运输",
                            "需分瓣/改工艺（环/盘件卧放）或水运（库区/内河驳船）",
                            "或特批/专询"],
            }
    elif h and max_h and h > max_h + float(DIM_POLICY["height_over_m"]) + _EPS:
        # 旧口径兜底（全库台面高都缺失时）
        return {
            "blocked_axis": "高", "over_by": round(h - max_h - float(DIM_POLICY["height_over_m"]), 3),
            "reason": (f"超高：{h:.2f}m 超载货限高 {max_h:.2f}m 逾 {DIM_POLICY['height_over_m']:g}m"
                       f"（需降台面/拆件/水运/特批；台面高缺失，按旧口径评定）"),
            "permit_flags": [f"高 {h:.2f}m（旧口径）⇒ 需勘路 + 特批/专询"],
            "actions": ["需降台面（低床/SPMT）/拆件/水运", "或特批/专询"],
        }
    # ⑤ 数据/形态缺口兜底（如缺内径 ⇒ 无法折算；不猜）
    return {
        "blocked_axis": None, "over_by": None,
        "reason": "数据/形态缺口（如缺内径 ⇒ 无法折算）：库内无可用车型 ⇒ 需补数据后折算，或专询/特批",
        "permit_flags": [],
        "actions": ["需补内径/分瓣图（D/d_i/h）后自动折算",
                    "或显式选瓣数（n2/n4/n6/n8；缺内径时按 0.75·D 经验内径试算并标注）",
                    "或专询/特批"],
    }


#: 旧式行级 `shape` 回退的**折叠词表**（P1-1 热修）：v013 起行级 `shape` 是**几何外形**契约
#: （box|cylinder|coil|pallet|bare —— desktop/renderer/app.js 每行都带），它的值只在词表内才被
#: 当作折叠形态转发；词表外的值一律**不当作折叠值、不报错、原样透传不管**。
_FOLD_VOCAB_PLAIN = ("auto", "integral", "整体")
_FOLD_VOCAB_RE = re.compile(r"n\d+|分\s*\d+\s*[瓣段]")


def _fold_vocab(value) -> str | None:
    """折叠词表过滤：是折叠词 ⇒ 原样返回（交 `line_folder._norm_shape` 归一/校验）；
    不是（几何值 box/cylinder/…、未知串）⇒ None（不当作折叠值、不报错、原样透传不管）。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in _FOLD_VOCAB_PLAIN or _FOLD_VOCAB_RE.fullmatch(s.lower()):
        return s
    return None


def _line_fold_shape(raw, *, default: str = "auto") -> str:
    """一行货的**折叠形态键**解析（P1-1 热修，优先级自上而下）：

    ① 行级 `fold_shape`（**权威键**）非空 ⇒ 用它 —— 非法值让形态层 `_norm_shape` 大声报错（护栏不丢）；
    ② 行级旧式 `shape` 仅在**折叠词表**内才回落转发（几何值 box/cylinder/… 原样透传不管，不报错）；
    ③ 其余 ⇒ 顶层缺省（python 形参 `shape=`；`reference.py` 从请求顶层 fold_shape/词表过滤后传入）。
    """
    if isinstance(raw, dict):
        v = raw.get("fold_shape")
        if v is not None and str(v).strip():
            return str(v)
        legacy = _fold_vocab(raw.get("shape"))
        if legacy is not None:
            return legacy
    return str(default or "auto")


def _is_explicit_split(shape) -> bool:
    """shape 是否为**显式**瓣数请求（nK，K≥2）——只有显式覆盖才允许经验内径试算（auto 严格不猜）。"""
    m = re.fullmatch(r"n(\d+)", str(shape or "").strip().lower())
    return bool(m and int(m.group(1)) >= 2)


def _form_input(it: dict, raw: dict, *, shape="auto", inner_d_default=None) -> tuple[dict, str]:
    """归一化行 + 原始行里的形态层键 → (折算器输入, 假设标注)。

    ① `_norm_items` 只保留配车口径的键（长度/重量/件数），会把 v015.8 的 `inner_d_m`/`split_n`/
       `shape` 丢掉 ⇒ 形态层要用的键从**原始行**随身带上（不动 `_norm_items`，免得碰到 `plan_fleet` 共用口径）。
    ② **P2-4 接缝兜底**：设计契约格式（`dims_m{L,W,H}` / `w_total_t`）喂进来时兜底换算成
       planner 口径（length_m/width_m/height_m/weight_kg）—— 旧行为是静默清零后被"配车"。
    ③ **T5 显式覆盖**：显式选了瓣数（shape=nK）但**缺内径**时，按专家表口径 d_i ≈ 0.75·D 试算，
       并返回标注「经验内径试算（0.75·D），需厂家分瓣图核实」——数字给用户、假设明说。
       auto 路径**保持严格**（缺内径 ⇒ 不折算并点名），不做这一步。
    """
    out = dict(it)
    if isinstance(raw, dict):
        out.update({k: raw[k] for k in _FORM_INPUT_KEYS if raw.get(k) is not None})
        # P2-4 兜底（与 _norm_items 同源函数）：dims_m / w_total_t ⇒ planner 口径，不静默清零
        out = _dims_fallback({**out, "dims_m": raw.get("dims_m"), "w_total_t": raw.get("w_total_t")})
    if out.get("inner_d_m") in (None, "") and inner_d_default is not None:
        out["inner_d_m"] = inner_d_default
    note = ""
    if out.get("inner_d_m") in (None, "") and _is_explicit_split(shape):
        plane = max(float(out.get("length_m") or 0.0), float(out.get("width_m") or 0.0))
        cls = line_folder.classify_shape(str(out.get("name") or ""))
        if plane > 0 and cls in ("ring", "unknown"):
            d_i = round(_EXPERIENCE_INNER_RATIO * plane, 2)
            out["inner_d_m"] = d_i
            note = (f"经验内径试算：d_i≈{_EXPERIENCE_INNER_RATIO:g}·D={d_i:.2f}m（D={plane:.2f}m）"
                    f" —— 需厂家分瓣图核实（厚壁环如顶盖 d/D≈0.64 会偏窄 W′，数字仅供参考）")
    return out, note


def _piece_item(it: dict, cand: line_folder.FormCandidate) -> dict:
    """候选形态 → 「单件」行：只替换尺寸/重量/件数，其余键不动。

    这样 `_pick_for_line` / `车辆数分解()` 的**调用口径一个字都没改**（INV-2）：变的是喂进去的
    单件参数，不是算法。
    """
    return {**it, "length_m": cand.L_m, "width_m": cand.W_m, "height_m": cand.H_m,
            "weight_kg": cand.w_t * 1000.0, "count": cand.count}


def _item_record(it: dict, cand: line_folder.FormCandidate, n: int, flags: list[str], *,
                 permit_flags=(), pieces_cap: int | None = None, axle: dict | None = None,
                 assumption: str = "") -> dict:
    """行记录：**保留原始尺寸**（前端要显示"货"本身），增加 v015.8 形态/口径字段（设计 §2① 契约）。

    分瓣后的单件尺寸/重量在 `piece_dims`/`piece_w_t`/`piece_count`；折算前尺寸另存 `orig_dims_m`，
    让前端能做"前 → 后"对照条（T9）。`dim_flags`（车辆匹配层）与 `permit_flags`（法规层）**分列**。
    """
    dim = list(flags)
    if assumption:
        dim.append(assumption)
    rec = {**it, "vehicle_count": n, "dim_flags": dim,
           "permit_flags": list(permit_flags),
           "form": cand.form, "split_n": cand.split_n,
           "piece_dims": {"L_m": cand.L_m, "W_m": cand.W_m, "H_m": cand.H_m},
           "piece_w_t": cand.w_t, "piece_count": cand.count, "placement": cand.placement}
    if pieces_cap is not None:
        rec["pieces_per_truck_max"] = int(pieces_cap)
    if axle:
        rec["axle_lines"] = dict(axle)
    if assumption:
        rec["assumption_flags"] = [assumption]
    if cand.split_n > 1:
        rec["orig_dims_m"] = {"L_m": it["length_m"], "W_m": it["width_m"], "H_m": it["height_m"]}
    return rec


def _unassigned_entry(it: dict, raw, all_models: list[VehicleModel], *,
                      shape: str = "auto", inner_d_default=None, candidates=None) -> dict:
    """「配不出车的行」点名记录（T5 契约：`blocked_axis`/`over_by`/`actions`/…）。

    🆕 热修 v015.8（P2-1）：逐件与整票两条路径**共用同一构造** —— 单行整票路径的 `unassigned`
    也必须带三件套 + `form/shape_class/min_feasible_n`，不许只给一句 reason（口径不许分叉）。
    🆕 v016 T-D：`candidates`（该行的货型候选集）透传给 `_line_block` 的 E7 判据
    （「候选只剩闭箱类」；不传 = 不判 E7，旧调用行为不变）。
    """
    form_in, assumption = _form_input(it, raw, shape=shape, inner_d_default=inner_d_default)
    fold = line_folder.fold_line(form_in, shape=shape)
    blk = _line_block(it, all_models, fold, candidates=candidates)
    note = fold.hint or "（分瓣后单件几何可达，但仍无车型可载 ⇒ 需更高等级装备或专线询价）"
    actions = list(blk["actions"])
    if fold.min_feasible_n:
        actions.insert(0, f"需 ≥{fold.min_feasible_n} 瓣（几何外推）或特批/专询")
    if assumption:
        actions.append(f"注：{assumption}")
    return {
        "name": it["name"] or "货物", "weight_ton": round(it["weight_kg"] / 1000.0, 3),
        "length_m": it["length_m"], "count": it["count"],
        "reason": f"{blk['reason']}；{note}",
        "blocked_axis": blk["blocked_axis"],           # 卡住的那一向（重/长/宽/高；数据缺口为 None）
        "over_by": blk["over_by"],                     # 超出的量（与 blocked_axis 同向）
        "actions": actions,                            # 处置路径（"需…"）
        "dim_flags": [blk["reason"]],
        "permit_flags": list(blk["permit_flags"]),
        "form": fold.candidates[0].form,               # 现状形态（整体 / 给定分N瓣）
        "shape_class": fold.shape_class,               # integral | ring | beam | unknown
        "min_feasible_n": fold.min_feasible_n,         # 「最小可行 n」建议值（几何外推）
    }


def _pick_for_pool(pieces: list[dict], bucket: list[VehicleModel], distance_km: float | None,
                   *, allow_oversized: bool = False, partition: str = "main") -> dict | None:
    """**档2 整池共车**：把池里所有件当成**一个装载单元**挑车型与车数（设计 §1⑤ / §3.3）。

    与 `_pick_for_line` 的区别：整车数按**池**算 ——
      `n = max(车辆数分解(池聚合), ceil(Σ_i 件数_i / cap_i))`
    池级守恒下限是「按需求求和后**一次** ceil」，不是逐行 ceil：行界是人为的（8 件小件分两行
    不该因此变成 2 车 —— 那正是现状「行间不共车」的虚增来源）；单车单行时两种算法完全等价
    （所以既有冻结口径一字不变）。
    """
    if not pieces:
        return None
    total_w = sum(i["weight_kg"] * i["count"] for i in pieces) / 1000.0
    total_v = sum(i["length_m"] * i["width_m"] * i["height_m"] * i["count"] for i in pieces)
    feat = 公式.货物载荷特征完整(货物总重量吨=total_w, 货物总体积立方米=total_v, 单件货物=pieces)
    ok_hits: list[dict] = []
    over_hits: list[dict] = []
    for m in bucket:
        if m.category == _SPECIAL_CATEGORY and partition != "oversized":
            continue
        if partition == "oversized" and m.category != _SPECIAL_CATEGORY:
            continue
        verdicts = [_dim_verdict(p, m, allow_oversized=allow_oversized) for p in pieces]
        if any(v == "no" for v, _f in verdicts):
            continue
        bd = 公式.车辆数分解(
            货物总重量吨=total_w, 货物总体积立方米=total_v,
            最大单件长度米=feat["最大单件长度米"], 货物总占地面积平方米=feat["总占地面积平方米"],
            车型最大载重吨=m.max_load_ton, 车型容积立方米=m.effective_volume_m3,
            车型地板长米=m.length_m, 车型地板面积平方米=m.floor_area_m2,
            装载效率=m.loading_efficiency, 最大单件重量吨=feat["最大单件重量吨"],
            # 🆕 A7：单件占满车厢的口径
            件总数=sum(int(p.get("count") or 1) for p in pieces),
            最大单件宽度米=feat.get("最大单件宽度米"), 车型宽度米=m.width_m,
        )
        if bd.get("不可分") or int(bd.get("车数") or 0) <= 0:
            continue
        caps = [pieces_per_truck_cap(p, m, allow_oversized=allow_oversized) for p in pieces]
        if any(c <= 0 for c in caps):
            continue
        demand = sum(float(p["count"]) / c for p, c in zip(pieces, caps))
        n = max(int(bd.get("车数") or 0), int(math.ceil(demand - _EPS)), 1)
        verdict = "ok" if all(v == "ok" for v, _f in verdicts) else "over"
        released = bool(allow_oversized and any(
            _dim_verdict(p, m, allow_oversized=False)[0] == "no" for p in pieces))
        hit = {"m": m, "n": n, "bd": bd, "caps": caps, "verdict": verdict,
               "flags": _dedup(f for _v, fs in verdicts for f in fs), "released": released,
               "floor": int(math.ceil(demand - _EPS)) if demand > 0 else 1,
               "four_const": int(bd.get("车数") or 0), "demand": demand,
               "pair_width": max((float(p.get("width_m") or 0.0) for p in pieces), default=0.0)
                             if any(c >= 2 for c in caps) else None,
               "fewer_trips_exemption": False}
        (ok_hits if verdict == "ok" else over_hits).append(hit)
    hits = ok_hits or over_hits
    if not hits:
        return None
    return _pick_best(hits, distance_km)


def _pool_group(pool_rows: list[dict], hit: dict, *,
                distance_km: float | None = None, allow_oversized: bool = False,
                dissolved: bool = False) -> FleetGroup:
    """档2 池 → 一个组：车数按**需求占比**分摊到各行（Σ行车数 == 组车数，守恒不破）。

    ⚠️ 池内行车数是**分摊值**（该行「占用」几辆池车），0 表示它被顺路捎走、不额外占车 ——
    这不是「配不出车」，池的权威车数看组级 `vehicle_count` / `count_doctrine.transport_units`。

    🆕 v017 T-2：`dissolved=True`（该共车组合被**显式不采纳**）⇒ **车型不变、车数上调**：
    每行按池车型单独算车数（逐行件守恒下限），Σ = 组车数；`pairs[]` 里该组合仍以
    `accepted=false` 回显（前端要能看见它、能再勾回来）。`pair_visible`（跨行组合且有
    任一 `cap ≥ 2`）才出 `pairs[]` 行 —— 没有真正共车可能的池不出组合行。
    """
    m: VehicleModel = hit["m"]
    caps = hit["caps"]
    n = int(hit["n"])
    per_line: list[dict | None] = [None] * len(pool_rows)
    if dissolved:
        for k, (r, cap) in enumerate(zip(pool_rows, caps)):
            sub = _pick_for_line(r["piece"], [m], distance_km, allow_oversized=allow_oversized)
            if sub is None:
                # 池级可行 ⇒ 单行理应可行；真到不了就用件守恒下限（不丢行、不虚报车数）
                cnt = max(1, int(r["piece"].get("count") or 1))
                cap_i = int(cap) if cap > 0 else 1
                n_i = int(math.ceil(cnt / cap_i))
                sub = {"n": n_i, "cap": cap_i, "flags": list(r["hit"].get("flags") or []),
                       "released": False, "floor": n_i, "four_const": 0}
            per_line[k] = sub
        shares = [int(h["n"]) for h in per_line]
        n = sum(shares)
    else:
        demands = [float(r["piece"]["count"]) / c for r, c in zip(pool_rows, caps)]
        total_d = sum(demands) or 1.0
        shares = [int(math.floor(n * d / total_d)) for d in demands]
        short = n - sum(shares)
        if short:
            idx_big = max(range(len(demands)), key=lambda k: (demands[k], -k))   # 需求最大者；并列取行序在前
            shares[idx_big] += short
    items: list[dict] = []
    flags: list[str] = []
    axle = None
    for k, (r, cap, share) in enumerate(zip(pool_rows, caps, shares)):
        it, cand = r["it"], r["cand"]
        sub = per_line[k]
        line_flags = list(sub["flags"]) if sub is not None else list(r["hit"]["flags"])
        rec = _item_record(it, cand, int(max(0, share)), line_flags,
                           permit_flags=_permit_flags(r["piece"], m, released=hit["released"]),
                           pieces_cap=cap, axle=_axle_info(r["piece"], m),
                           assumption=r.get("assumption") or "")
        axle_i = rec.get("axle_lines")
        if axle_i and (axle is None or axle_i["lines_max"] > axle["lines_max"]):
            axle = axle_i
        rec["line_id"] = line_id_of(r.get("view"), "")
        rec["line_class"] = line_class(r["view"])
        rec["pair_total_width_m"] = None if dissolved else (hit.get("pair_width") if cap >= 2 else None)
        items.append(rec)
        for f in line_flags:
            if f not in flags:
                flags.append(f)
    permit = _dedup(_permit_flags(pool_rows[0]["piece"], m, released=hit["released"]))
    what = "、".join(f"{r['it']['name'] or '货物'}×{r['it']['count']}件" for r in pool_rows)
    if dissolved:
        floors = [int((h or {}).get("floor") or 0) for h in per_line]
        fours = [int((h or {}).get("four_const") or 0) for h in per_line]
    else:
        floors = [int(hit["floor"])]
        fours = [int(hit["four_const"])]
    pairs: list[dict] = []
    if len(pool_rows) >= 2 and any(c >= 2 for c in caps):
        # line_ids/line_names **按 line_id 升序**（规范序 ⇒ 同内容必同输出，前端可直接对照）
        _named = sorted((line_id_of(r.get("view"), ""), r["it"]["name"] or "货物") for r in pool_rows)
        line_ids = [lid for lid, _n in _named]
        pairs.append({
            "pair_id": pair_id_of(line_ids),
            "line_ids": line_ids,
            "line_names": [n for _l, n in _named],
            "per_truck": int(min(caps)),
            "trucks": n,
            "rule_id": "CO-6",
            "reason": (f"共车组合未采纳：{what} 按「不共车」重算 ⇒ {n} 辆（车型不变，逐行各自成车）"
                       if dissolved else
                       f"整池共车：{what} → 同车 {n} 辆（每车最多 {int(min(caps))} 件；共车判据 CO-6）"),
            # ⚠️ 契约外附加字段：前端④勾选态回显用（契约 §3.2 七字段之外的唯一附加键）
            "accepted": not dissolved,
        })
    return FleetGroup(
        partition="main", model_id=m.model_id, vehicle_count=n,
        binding=str((hit["bd"] or {}).get("主因") or "重量"), payload={}, breakdown=hit["bd"] or {},
        reason=((f"{what} → {m.display_name}（载重 {m.max_load_ton:g} t） {n} 辆；"
                 f"主因 {(hit['bd'] or {}).get('主因') or '重量'}；共车组合未采纳 ⇒ 按「不共车」重算"
                 f"（逐行件守恒下限 Σ{sum(floors)}；车数由 {int(hit['n'])} 上调）；"
                 f"（GVM 档 {gvm_tier(m)}，比价口径 {hit.get('cost_caliber') or 'rate_only'}）")
                if dissolved else
                (f"{what} → 整池共车 {m.display_name}（载重 {m.max_load_ton:g} t） {n} 辆；"
                 f"主因 {(hit['bd'] or {}).get('主因') or '重量'}；"
                 f"车数口径 池守恒下限 {hit['floor']} / 四约束估算 {hit['four_const']} 取大"
                 f"（GVM 档 {gvm_tier(m)}，比价口径 {hit.get('cost_caliber') or 'rate_only'}）；"
                 f"共车判据 CO-6")),
        items=items, dim_flags=_dedup(flags), permit_flags=permit,
        oversize_released=bool(hit.get("released")),
        pair_total_width_m=(None if dissolved else hit.get("pair_width")),
        pairs=pairs,
        count_doctrine={
            "one_piece_over_t": float(COLOAD_POLICY["one_piece_over_t"]),
            "axle_q_t": float(DIM_POLICY["axle_q_t"]),
            "transport_units": n,
            "pieces_per_truck_max": min(caps) if caps else None,
            "caliber": "max(floor,4const,packer)",
            "floor": int(sum(floors)),
            "four_const": int(sum(fours)),
            "packer": None,
            "gap_warn": None,                    # ③ 装车器实测由前端回填
            "gap_warn_threshold": float(COUNT_GAP_WARN),   # 单一真源：③ > ①×1.30 ⇒ 告警（不阻断）
            "unit_cap": int(min(caps)) if caps else None,
            "pair_rule_id": (None if dissolved else
                             ("CO-6" if any(c >= 2 for c in caps) else None)),
            "gvm_tier": gvm_tier(m),
            "cost_caliber": hit.get("cost_caliber") or "rate_only",
            "fewer_trips_exemption": bool(hit.get("fewer_trips_exemption")),
            "axle_shortfall": bool((axle or {}).get("shortfall")),
        })


# ══════════════════════════════════════════════════════════════════════════════
# 🆕 A6（2026-11）：可解体性 —— 能拆的件优先「拆件分运」，别一上来就走超限许可
#   「可解体」在法规里有后果：只有不可解体大件才走超限许可（三类 15 个工作日 + 轮廓图/护送），
#   可解体设备（塔筒分节、模块化机组）本可拆运走常规车。赣州/鄂州事故的共同错法，
#   都是把「本可拆」或「本不该上路」的件硬拉超限。
#   判定必须有**行级输入**（`divisible: true`）：引擎不猜设备能不能拆 —— 拆件是工艺决定，
#   猜错会给出错误的省钱建议。未标注 ⇒ 不输出建议（None）。
#   本函数只产出建议，**不改动配车结果**（不静默改车数）。
# ══════════════════════════════════════════════════════════════════════════════

CN_DIVISIBLE_POLICY: dict = {
    "split_ks": (2, 3, 4),      # 试拆 2/3/4 段，取最小可行
    "assumed_deck_m": 1.2,      # 无车型上下文时按 1.2m 台面估总高
    "assumed_tare_t": 20.0,     # 无车型上下文时按 20t 台车自重估车货总重
}


def _item_needs_permit(it: dict) -> bool:
    """这件货是否触中国超限认定线（车货外廓；台面高按 1.2m、自重按 20t 估）。"""
    l = float(it.get("length_m") or 0.0)
    w = float(it.get("width_m") or 0.0)
    h = float(it.get("height_m") or 0.0)
    wt = float(it.get("weight_kg") or 0.0) / 1000.0 + CN_DIVISIBLE_POLICY["assumed_tare_t"]
    return (l > CN_OVERSIZE_L_M + _EPS or w > CN_OVERSIZE_W_M + _EPS
            or (h + CN_DIVISIBLE_POLICY["assumed_deck_m"]) > CN_OVERSIZE_H_M + _EPS
            or wt > CN_OVERSIZE_GROSS_T + _EPS)


def _item_permit_tier(it: dict) -> dict | None:
    """单件（按一件一车）的中国许可档位；估台面高 1.2m、自 20t。"""
    return cn_permit_tier(
        height_m=float(it.get("height_m") or 0.0) + CN_DIVISIBLE_POLICY["assumed_deck_m"],
        width_m=float(it.get("width_m") or 0.0),
        length_m=float(it.get("length_m") or 0.0),
        gross_t=float(it.get("weight_kg") or 0.0) / 1000.0 + CN_DIVISIBLE_POLICY["assumed_tare_t"],
    )


def divisibility_advice(*, item: dict, models, cargo_type: str = "normal",
                        distance_km: float | None = None,
                        allow_oversized: bool = False) -> dict | None:
    """可解体件的拆件建议。未标 `divisible` 或本就不超限 ⇒ None。

    ⚠️ 关键认知：**拆件通常避不开「超限」这件事**，而是把档位降下来 ——
    三类（15 个工作日 + 轮廓图/护送）→ 一类（2 个工作日）才是真正省钱省时的收益。
    所以 `avoids_permit` 的语义 = 「拆后不再需要许可」，另有 `tier_downgraded` 表示降档。
    """
    if not isinstance(item, dict) or not bool(item.get("divisible")):
        return None
    if not _item_needs_permit(item):
        return None

    l = float(item.get("length_m") or 0.0)
    w = float(item.get("weight_kg") or 0.0)
    cnt = int(item.get("count") or 1)

    def _run(it: dict):
        try:
            return plan_fleet_by_item(items=[it], models=models, cargo_type=cargo_type,
                                      distance_km=distance_km, allow_oversized=allow_oversized)
        except Exception:       # 建议功能绝不许弄挂主流程
            return None

    whole_tier = _item_permit_tier(item)
    whole = _run({**item, "divisible": False, "count": cnt})
    best = None
    tried: list[int] = []
    for k in CN_DIVISIBLE_POLICY["split_ks"]:
        piece = {**item, "divisible": False, "count": cnt,
                 "length_m": round(l / k, 2), "weight_kg": round(w / k, 3)}
        r = _run(piece)
        tried.append(k)
        if r is None or r.total_trucks == 0 or r.needs_split:
            continue
        pt = _item_permit_tier(piece)
        # 拆后：要么彻底不用许可，要么档位更低（工作日更少）才算改善
        if pt is None or (whole_tier is not None
                          and pt["workdays_local"] < whole_tier["workdays_local"]):
            best = (k, piece, r, pt)
            break

    if best is None:
        return {"divisible": True, "split_pieces": None,
                "whole": {"trucks": (whole.total_trucks if whole else 0),
                          "tier": (whole_tier or {}).get("name")},
                "split": None, "avoids_permit": False, "tier_downgraded": False,
                "tried_pieces": tried,
                "note": (f"可解体件「{item.get('name') or ''}」试拆 "
                         f"{'/'.join(map(str, tried)) or '—'} 段仍落同一超限档（或拆后无车可载）"
                         f"⇒ 建议按超限运输申报，并由工艺/厂家确认最小可拆单元。")}

    k, piece, r, pt = best
    whole_name = (whole_tier or {}).get("name") or "无需许可"
    split_name = (pt or {}).get("name") or "无需许可"
    return {
        "divisible": True, "split_pieces": k,
        "whole": {"trucks": (whole.total_trucks if whole else 0), "tier": whole_name},
        "split": {"trucks": r.total_trucks,
                  "piece_length_m": piece["length_m"],
                  "piece_weight_kg": piece["weight_kg"],
                  "tier": split_name,
                  "workdays_local": (pt or {}).get("workdays_local", 0),
                  "models": sorted({g.model_id for g in r.groups})},
        "avoids_permit": pt is None,
        "tier_downgraded": pt is not None and whole_tier is not None,
        "note": (f"可解体件「{item.get('name') or ''}」：按 {k} 段拆运，每段长 "
                 f"{piece['length_m']:g}m / 重 {piece['weight_kg'] / 1000:g}t，共 {r.total_trucks} 车；"
                 f"许可档位 {whole_name} → **{split_name}**"
                 + (f"（省内 {pt['workdays_local']} 个工作日，原 {whole_tier['workdays_local']} 个）"
                    if pt and whole_tier else "")
                 + "。是否可拆由工艺/厂家确认 —— 本建议不改动上面的配车结果。"),
    }


def plan_fleet_by_item(*, items, total_weight_kg=None, total_volume_m3=None, cargo_type="normal",
                       models, distance_km=None, shape="auto", inner_d_m=None,
                       allow_oversized: bool = False,
                       locked_models: dict | None = None, accepted_pairs=None) -> FleetPlan:
    """🆕 v015.6 **逐件配车** + 🆕 v015.8 **形态折算与形态搜索** + **阈值 v2 / 车数法定口径**
    + 🆕 v016 **货行分档排序 / 档2 整池共车 / GVM 档排序键 / 超限放行开关**。

    与 `plan_fleet()`（整票试算单一车型）的区别：一行超限只影响**那一行**，不再把整票判死
    （实测：9 类里一行 25m 大梁曾让整票 = 0 辆）。

    v015.8 新增：配车前插入形态层（`line_folder.fold_line()`）——判定树允许且参数齐备时，
    先试「整体」，进不了「超限可运」档就按 n=2→4→6→8 递增重跑，取**最小可行 n**；
    全不行 ⇒ 该行进 `oversize.unassigned`，reason 给「最小可行 n 建议值」
    + `{blocked_axis, over_by, actions[]}`（设计 §2④ 契约）。

    🆕 v016 新增（设计 §1 流水线）：
      · **排序**：先分档（档0 超重件 → 档1 超限件 → 档2 常规件）再按「单件重 → 最大边 → 体积 →
        line_id」排 —— 现场是「先钉最难的件」（特装档期/许可勘路周期是瓶颈）；
      · **档2 整池共车**：常规散件合并成一个池、池级选型（行界不该让人为地多出车）；
      · **开关** `allow_oversized`：`_dim_verdict` 的 no 档在硬红线内降级为 over（座环 4.98m 这类
        T5 超宽可配车 + 许可标），**超载/轴荷/桥涵一字不放**；
      · **车数三重口径**（`count_doctrine` 的 floor/four_const/packer）+ 组级 `oversize_released` /
        `pair_total_width_m`。

    契约：① 分桶「常规 → 特种」，两桶都挑不出 ⇒ 该行进 `oversize.unassigned` 并写进
    `split_hint`；② 同车型被多行选中 ⇒ 合并为一组（items 并列、车数相加）；
    ③ 档0/档1 行之间不共车（保守：大件一件一车为常态）；档2 行**整池共车**；
    ④ 车数一律出自 `车辆数分解()`（INV-2 不破）+ 守恒下限（ceil 规则）；
    ⑤ 折叠策略键 = **`fold_shape`**（auto|integral|nK）——行级 `fold_shape` 逐行覆盖
    （前端行内「整体·分N瓣」开关），形参 `shape=` 作顶层缺省；旧式行级/顶层 `shape` 只在
    **折叠词表**（auto|integral|整体|nK|分N瓣/段）内才回落转发
    （v013 几何值 box/cylinder/… 不当作折叠值、不报错、原样透传不管 —— P1-1 热修）；
    响应 items 每条带 `form/split_n/piece_dims/dim_flags/permit_flags/line_class`；
    ⑥ 顶层 `inner_d_m` 作为行级缺省注入（行级真值优先）。

    🆕 v017 T-2（配车契约扩展；缺省 = 与 v016 逐字节同口径）：
      · `locked_models = {line_id: model}`：命中行**只在锁定车型上**做形态搜索（挑不出 ⇒
        点名，原因注明「已锁定车型」，绝不静默改选别的车）；锁定行不进共车池；
      · `accepted_pairs`：共车组合（档2 池）的采纳态 —— 显式不采纳 ⇒ **车型不变、车数上调**
        （逐行「不共车」= 逐行件守恒下限），组合在 `groups[].pairs[]` 里以 `accepted=false` 回显；
      · 响应行记录新增 `line_id`（字符串口径 = `line_id_of`），供 `pairs[]`/`confirm{}` 对齐。
    """
    raw_items = list(items or [])
    pool = _norm_items(items)
    cands, fallback = _candidates(cargo_type, list(models))
    normal = [m for m in cands if m.category != _SPECIAL_CATEGORY]
    special = [m for m in cands if m.category == _SPECIAL_CATEGORY]
    special_all = special or [m for m in models if m.category == _SPECIAL_CATEGORY]
    all_pool = list(models)          # 判"为什么配不出"要用**全库**（含特种），否则文案会拿常规 38t 当上限
    # 🆕 v017 T-2：逐行锁定车型（键 = `line_id_of` 口径的字符串；API 层已校验合法性与行存在性）
    locks = ({str(k).strip(): str(v).strip() for k, v in locked_models.items()}
             if isinstance(locked_models, dict) else {})

    # ── ① v016：货行分档 + 排序（先难后易；只改「谁先挑车」，不改任何单行语义）──────────
    rows: list[tuple[int, dict, dict, dict]] = []
    for idx, it in enumerate(pool):
        raw = raw_items[idx] if idx < len(raw_items) else {}
        raw = raw if isinstance(raw, dict) else {}
        view = dict(it)
        lid = raw.get("line_id")
        view["line_id"] = lid if lid not in (None, "") else idx      # line_id 兜底 = 行号（确定性）
        rows.append((idx, it, raw, view))
    rows.sort(key=lambda t: line_priority(t[3]))

    slots: dict[str, dict] = {}
    unassigned: list[dict] = []
    pool_rows: list[dict] = []       # 🆕 v016：档2 行（整池共车）

    def _slot_put(it: dict, piece: dict, cand, hit: dict, partition: str, assumption: str) -> None:
        m = hit["m"]
        n = int(hit["n"])
        # ⚠️ 许可/轴荷标记算在**折算后的单件**上（与 v015.8 同口径）：高度/宽度档随形态变化，
        #   算在原始整件上会把「分2瓣后 2.75m」错报成「整件 5.5m ⇒ T5 特批」（金标准 底环 = T1 超宽）。
        permit = _permit_flags(piece, m, released=bool(hit.get("released")))
        slot = slots.setdefault(m.model_id, {"model": m, "count": 0, "lines": [], "bd": hit["bd"],
                                             "partition": partition, "flags": [], "permit": [],
                                             "axle": None, "caps": [], "floors": [],
                                             "pair_widths": [], "released": False})
        slot["count"] += n
        for f in hit["flags"]:
            if f not in slot["flags"]:
                slot["flags"].append(f)
        for f in permit:
            if f not in slot["permit"]:
                slot["permit"].append(f)
        axle = _axle_info(piece, m)
        if axle and (slot["axle"] is None or axle["lines_max"] > slot["axle"]["lines_max"]):
            slot["axle"] = axle
        slot["caps"].append(int(hit["cap"]))
        slot["floors"].append(int(hit.get("floor") or 0))
        slot["pair_widths"].append(hit.get("pair_width"))
        if hit.get("released"):
            slot["released"] = True
        rec = _item_record(it, cand, n, hit["flags"], permit_flags=permit,
                           pieces_cap=hit["cap"], axle=axle, assumption=assumption)
        rec["line_id"] = line_id_of(view_of(it), "")     # 🆕 v017：pairs[]/confirm{} 的配对键
        rec["line_class"] = line_class(view_of(it))
        rec["pair_total_width_m"] = hit.get("pair_width")
        rec["oversize_released"] = bool(hit.get("released"))     # 行级放行标记（policy.released 用它）
        slot["lines"].append(rec)

    _VIEWS: dict[int, dict] = {id(t[1]): t[3] for t in rows}   # 行 → 视图（line_class 用）

    def view_of(it: dict) -> dict:
        return _VIEWS.get(id(it), it)

    for idx, it, raw, view in rows:
        # 🆕 热修 v015.8（P1-1）：折叠键 = `fold_shape`（行级 > 顶层；旧式 `shape` 限折叠词表回落，
        #   几何值 box/cylinder/… 原样透传不管 —— 此前直接读 raw["shape"] 让真实前端 ≥2 行请求 500）
        per_shape = _line_fold_shape(raw, default=shape)
        form_in, assumption = _form_input(it, raw, shape=per_shape, inner_d_default=inner_d_m)
        fold = line_folder.fold_line(form_in, shape=per_shape)
        lock_model = locks.get(line_id_of(raw, idx))
        picked = None
        if lock_model:
            # 🆕 v017 T-2：逐行锁定车型 —— 只在锁定车型上做形态搜索（整体 → 2 → 4 → 6 → 8），
            #   挑不出 ⇒ 该行点名（原因注明「已锁定车型」），**绝不静默改选别的车**；
            #   锁定行也不进共车池（池会按自己的选型逻辑改车型 ⇒ 与锁定冲突）。
            m_lock = next((m for m in models if str(m.model_id) == lock_model), None)
            if m_lock is not None:
                for cand in fold.candidates:
                    piece = _piece_item(it, cand)
                    hit = _pick_for_line(piece, [m_lock], distance_km,
                                         allow_oversized=allow_oversized)
                    if hit is not None:
                        picked = {"hit": hit, "cand": cand,
                                  "partition": ("oversized" if m_lock.category == _SPECIAL_CATEGORY
                                                else "main"),
                                  "piece": piece}
                        break
        else:
            for cand in fold.candidates:                # 递增：整体 → 2 → 4 → 6 → 8（取最小可行）
                piece = _piece_item(it, cand)
                hit = _pick_for_line(piece, normal, distance_km, allow_oversized=allow_oversized)
                partition = "main"
                if hit is None:
                    hit = _pick_for_line(piece, special_all, distance_km, allow_oversized=allow_oversized)
                    partition = "oversized"
                    if hit is not None:
                        # 🆕 v016 T-D（E7）：该行是**靠开放车板才拿到车**的（按货型的候选只剩闭箱类、
                        #   悬伸=0 装不下该件）⇒ 打 E7 标记（dim_flags），说明"为什么不是闭箱车"。
                        e7 = _deck_unfit_closed(piece, normal)
                        if e7 is not None:
                            hit["flags"] = [*hit["flags"],
                                            unfit_text("deck_unfit_closed", dim=_e7_dim_text(piece, e7))]
                if hit is not None:
                    picked = {"hit": hit, "cand": cand, "partition": partition, "piece": piece}
                    break
        if picked is None:
            # 🆕 热修（P2-1）：点名记录改走共用构造（与整票路径逐字节同口径）
            # 🆕 v016 T-D：candidates 透传（E7「候选只剩闭箱类」判据用该行的货型候选集）
            entry = _unassigned_entry(it, raw, all_pool, shape=per_shape, inner_d_default=inner_d_m,
                                      candidates=normal)
            entry["line_class"] = line_class(view)
            if lock_model:
                # 🆕 v017：锁定的车型不可用 ⇒ 点名并写清「解除锁定」这条出路（不许静默换车）
                entry["locked_model"] = lock_model
                entry["reason"] = (f"{entry['reason']}；已锁定车型 {lock_model}：该车型对本行不可用"
                                   f" ⇒ 需解除锁定或改选车型")
                entry["actions"] = ["解除锁定或改选车型", *entry["actions"]]
            unassigned.append(entry)
            continue
        if line_tier(view) == 2 and not lock_model:
            # 🆕 v016：档2（常规件）**不立刻定组** —— 先进整池，池级选型在下面（整池共车）
            picked.update({"it": it, "view": view, "assumption": assumption})
            pool_rows.append(picked)
            continue
        _slot_put(it, picked["piece"], picked["cand"], picked["hit"], picked["partition"], assumption)

    # ── ② v016：档2 整池共车（池级选型；池级挑不出 ⇒ 退回逐行，绝不丢行）──────────────
    pool_group: FleetGroup | None = None
    if pool_rows:
        pieces = [r["piece"] for r in pool_rows]
        phit = _pick_for_pool(pieces, normal, distance_km, allow_oversized=allow_oversized)
        if phit is None:
            phit = _pick_for_pool(pieces, special_all, distance_km, allow_oversized=allow_oversized,
                                  partition="oversized")
        if phit is not None:
            phit["cost_caliber"] = cost_caliber(distance_km)
            # 🆕 v017 T-2：共车组合采纳 —— 组合 id 由**池内 line_id 排序后拼接哈希**（稳定可复现）。
            #   显式不采纳 ⇒ 车型不变、按逐行「不共车」重算（车数上调）；
            #   无跨行组合（单行池）或组合内没有任何可共车件（cap 全 ≤1）⇒ 不出组合行，
            #   此时 `accepted_pairs` 对该池无效（不静默改车数）。
            pool_ids = [line_id_of(r.get("view"), "") for r in pool_rows]
            pair_visible = len(pool_rows) >= 2 and any(c >= 2 for c in phit["caps"])
            dissolved = bool(pair_visible and not pair_accepted(pair_id_of(pool_ids), accepted_pairs))
            pool_group = _pool_group(pool_rows, phit, distance_km=distance_km,
                                     allow_oversized=allow_oversized, dissolved=dissolved)
        else:
            for r in pool_rows:                          # 保守回退：逐行定组（行界只在池级失败时恢复）
                _slot_put(r["it"], r["piece"], r["cand"], r["hit"], "main", r.get("assumption") or "")

    groups: list[FleetGroup] = []
    for mid, slot in slots.items():
        m: VehicleModel = slot["model"]
        lines = slot["lines"]
        what = "、".join(f"{l['name'] or '货物'}×{l['count']}件" for l in lines)
        dim_note = ("；" + "；".join(slot.get("flags") or [])) if slot.get("flags") else ""
        caps = slot["caps"] or []
        groups.append(FleetGroup(
            partition=slot["partition"], model_id=mid, vehicle_count=int(slot["count"]),
            binding=str((slot["bd"] or {}).get("主因") or "重量"),
            payload={}, breakdown=slot["bd"] or {},
            reason=(f"{what} → {m.display_name}（载重 {m.max_load_ton:g} t）"
                    f" {int(slot['count'])} 辆；主因 {(slot['bd'] or {}).get('主因') or '重量'}"
                    f"（GVM 档 {gvm_tier(m)}）" + dim_note),
            items=[dict(l) for l in lines],
            dim_flags=_dedup(f for l in lines for f in (l.get("dim_flags") or [])),
            permit_flags=list(slot["permit"]),
            oversize_released=bool(slot.get("released")),
            pair_total_width_m=(max([w for w in slot.get("pair_widths") or [] if w is not None],
                                    default=None)),
            count_doctrine={
                "one_piece_over_t": float(COLOAD_POLICY["one_piece_over_t"]),
                "axle_q_t": float(DIM_POLICY["axle_q_t"]),
                "pieces_per_truck_max": min(caps) if caps else None,
                "transport_units": int(slot["count"]),
                "caliber": "max(floor,4const,packer)",
                "floor": int(sum(slot.get("floors") or [])),
                "four_const": int((slot["bd"] or {}).get("车数") or 0),
                "packer": None,
                "gap_warn": None,                    # ③ 装车器实测由前端回填
            "gap_warn_threshold": float(COUNT_GAP_WARN),   # 单一真源：③ > ①×1.30 ⇒ 告警（不阻断）
                "unit_cap": min(caps) if caps else None,
                "pair_rule_id": "CO-6" if any(c >= 2 for c in caps) else None,
                "gvm_tier": gvm_tier(m),
                "cost_caliber": cost_caliber(distance_km),
                "fewer_trips_exemption": False,
                "axle_shortfall": bool((slot.get("axle") or {}).get("shortfall")),
            },
        ))
    if pool_group is not None:
        for rec in pool_group.items:
            rec["oversize_released"] = bool(pool_group.oversize_released)
        groups.append(pool_group)
    groups.sort(key=lambda g: (-g.vehicle_count, g.model_id))
    total = sum(g.vehicle_count for g in groups)
    primary = groups[0].model_id if groups else None
    hint = None
    if unassigned:
        parts = "、".join(f"{u['name']}（{u['reason']}）" for u in unassigned)
        hint = (f"以下货行库内无车可载：{parts} —— 需拆运或专线询价；"
                + (f"其余 {len(groups)} 组已按逐件口径配车。" if groups else ""))
    # 🆕 v016：开关的审计/回显真源 —— released（拿到车的超限件）/ hard_blocked（硬红线，开关也救不了）
    released_names = [it["name"] for g in groups for it in g.items
                      if it.get("oversize_released") and it["name"]]
    hard_blocked = [u["name"] for u in unassigned if _hard_blocked_row(u, pool)]
    # 🆕 A6：可解体件的拆件建议（仅行级 divisible=true；只给建议、不改配车结果）
    _div = None
    for _it in items:
        if isinstance(_it, dict) and _it.get("divisible"):
            _div = divisibility_advice(item=_it, models=models, cargo_type=cargo_type,
                                       distance_km=distance_km,
                                       allow_oversized=allow_oversized)
            if _div:
                break
    # 🆕 A7-2：计费体积（圆柱实际形状）vs 装车占位（外接方块）—— 两者分列，不合并
    #   ⚠️ 形状字段（`shape_class` / `inner_d_m`）在 pool 规范化时会丢，必须从原始行补回，
    #   否则空心筒体会被当成实心圆柱（实测 47.75 m³ 被算成 251.33 m³）。
    _raw_by_name = {str(it.get("name")): it for it in items if isinstance(it, dict)}

    def _vol_row(row: dict) -> dict:
        raw = _raw_by_name.get(str(row.get("name"))) or {}
        merged = dict(row)
        for k in ("shape_class", "inner_d_m"):
            if raw.get(k) not in (None, ""):
                merged[k] = raw[k]
        return merged

    _billed = sum(_piece_billed_volume_m3(_vol_row(it)) * int(it.get("count") or 1) for it in pool)
    _placed = sum(_piece_volume_m3(it) * int(it.get("count") or 1) for it in pool)
    return FleetPlan(
        groups=groups, total_trucks=total, primary_model_id=primary,
        mixed=len({g.model_id for g in groups}) > 1, needs_split=bool(unassigned),
        split_hint=hint,
        oversize={"unassigned": unassigned,
                  "max_piece_weight_ton": max((i["weight_kg"] for i in pool), default=0.0) / 1000.0 or None,
                  "max_piece_length_m": max((i["length_m"] for i in pool), default=0.0) or None,
                  "cargo_type": cargo_type,
                  "policy": {"allow_oversized": bool(allow_oversized),
                             "released": _dedup(released_names),
                             "hard_blocked": _dedup(hard_blocked),
                             "legal_basis": legal_refs.legal_basis()},
                  "doctrine": {"one_piece_over_t": float(COLOAD_POLICY["one_piece_over_t"]),
                               "axle_q_t": float(DIM_POLICY["axle_q_t"]),
                               "transport_units": total}},
        engine=ENGINE_BY_ITEM, category_fallback=fallback,
        divisibility=_div,
        billed_volume_m3=round(_billed, 3),
        placed_volume_m3=round(_placed, 3),
    )


def _hard_blocked_row(u: dict, pool: list[dict]) -> bool:
    """该点名行是否属**硬红线**（开关 ON 也救不了）：宽 >5.5m / 总高 >5.5m / 单件超库内最大载重。

    只用于 `oversize.policy.hard_blocked` 与 UI 警示 —— 4.5~5.5m 的 T5 档**不算**硬红线
    （开关 ON 时可放行，故它进 `released` 而不是这里）。
    """
    for it in pool:
        if (it.get("name") or "货物") != u.get("name"):
            continue
        total_h = height_total(it["height_m"], 0.9)      # 按库内最低台面 0.9m 估（与 _line_block 同源）
        if float(it["width_m"]) > WIDTH_HARD_LIMIT_M + _EPS:
            return True
        if total_h is not None and total_h > float(DIM_POLICY["height_hard_m"]) + _EPS:
            return True
    return u.get("blocked_axis") == "重"


def _split_extra(pool: list[dict], models: list[VehicleModel], cands: list[VehicleModel],
                 spec_max_deck: float, *, deck_cap: float | None = None) -> dict | None:
    """整票「需特种车/配不出」场景的附加真因（E5 轴荷 → E6 组合长 → E7 车型外形）—— 返回带文案。

    只在 E1/E2/E4 已判之后调用（判定顺序 §7；E6 的「装不进车厢 ⇒ 归长」边界与 `_line_block` 同口径）。
    deterministic：pool 原序 + 以「最重件/最长件」单点取件。
    """
    heavy = max(pool, key=lambda i: float(i.get("weight_kg") or 0.0), default=None)
    if heavy is not None:
        info = _axle_shortfall_anywhere(heavy, models)
        if info is not None:
            return {"reason": "gvm_axle_shortfall",
                    "msg": unfit_text("gvm_axle_shortfall", w=float(heavy["weight_kg"]) / 1000.0,
                                      lines_min=info["lines_min"], q=float(DIM_POLICY["axle_q_t"]),
                                      avail=info["avail"], gap=info["gap"])}
    longest = max(pool, key=lambda i: float(i.get("length_m") or 0.0), default=None)
    if longest is not None:
        l = float(longest.get("length_m") or 0.0)
        cap = float(deck_cap if deck_cap is not None else (spec_max_deck or 0.0))
        if (l and combined_length(l) > float(COLOAD_POLICY["max_pair_len_m"]) + _EPS
                and l <= cap + float(DIM_POLICY["len_over_m"]) + _EPS):
            return {"reason": "combo_length_over",
                    "msg": unfit_text("combo_length_over", combo=combined_length(l), l=l,
                                      overhang=float(DIM_POLICY["overhang_m"]),
                                      prime=float(DIM_POLICY["prime_mover_m"]),
                                      cap=float(COLOAD_POLICY["max_pair_len_m"]))}
    for i in pool:
        e7 = _deck_unfit_closed(i, cands)
        if e7 is not None and _open_deck_feasible(i, models):
            return {"reason": "deck_unfit_closed",
                    "msg": unfit_text("deck_unfit_closed", dim=_e7_dim_text(i, e7))}
    return None


def plan_fleet(*, items, total_weight_kg=None, total_volume_m3=None, cargo_type="normal",
               models, distance_km=None, allow_oversized: bool = False) -> FleetPlan:
    """整票试算选车。

    注：不做 `loading_efficiency` 形参 —— 装载效率由 `车辆数分解()` 逐车型取
    `m.loading_efficiency`（车型自带，权威），选车器不应再插一层可被误传的效率。
    `total_weight_kg` / `total_volume_m3` 保留以贴合既有 API 调用习惯；权重与体积
    一律按 items 明细重算，避免与明细不一致的入参污染判定。

    🆕 热修 v015.8（P2-1）：① T3/T5 尺寸闸与逐件路径同源（见 `_plan_one`）；
    ② `oversize["unassigned"]` **恒有键**（配得出车 = 空列表；配不出 = 逐行点名，含
    `blocked_axis/over_by/actions` 三件套）—— 单行请求也不许绕过 T5 契约。
    🆕 v016：`allow_oversized` 透传（no 档在硬红线内降级为 over）+ 排序键 = `_rank_key`
    + `oversize["policy"]`（开关真源）。
    """
    raw_items = list(items or [])
    pool = _norm_items(items)
    cands, fallback = _candidates(cargo_type, list(models))

    main, main_unfit, main_diag = _plan_one(pool, cands, distance_km, partition="main",
                                            allow_oversized=allow_oversized)
    spec_diag: dict = {}
    if main is not None:
        groups = [main]
        needs_split = False
        hint = None
    else:
        groups = []
        needs_split = True
        hint = "这批货无法由单一车型承载（单件超重/超长）：建议拆单报价，或走超限运输（特种车 + 超限许可）。"

    if main_unfit and not groups:
        spec, _, spec_diag = _plan_one(pool, [m for m in models if m.category == _SPECIAL_CATEGORY],
                                      distance_km, partition="oversized",
                                      allow_oversized=allow_oversized)
        if spec is not None:
            groups = [spec]
            needs_split = False
            hint = "单件超常规车型上限：按特种车（超限运输）处置。"   # 下面按**真实理由**改写

    total = sum(g.vehicle_count for g in groups)
    primary = max(groups, key=lambda g: g.vehicle_count).model_id if groups else None
    special_ids = [g.model_id for g in groups
                   if any(m.model_id == g.model_id and m.category == _SPECIAL_CATEGORY for m in models)]
    normal_max = max((m.max_load_ton for m in models if m.category != _SPECIAL_CATEGORY), default=0.0)
    max_piece = max((i["weight_kg"] for i in pool), default=0.0) / 1000.0
    max_piece_len = max((i["length_m"] for i in pool), default=0.0)
    over_normal_max = bool(max_piece and max_piece > normal_max + 1e-9)
    # ── 🆕 2026-09-23：真实「不适合」理由（此前一律说成"单件超常规车型上限"）──
    # 🆕 v016 T-D：键与文案**只引用 `UNFIT_REASONS`**（E1–E7）；E6/E7 为新增（E5 在 permit_flags，
    #   整票「配不出」时才作为 `unfit_reason` —— 见 `_split_extra`）。
    cand_max_deck = float(main_diag.get("max_deck_m") or 0.0)     # 本次**常规候选集**口径
    cand_max_load = float(main_diag.get("max_load_ton") or 0.0)
    spec_max_deck = float(spec_diag.get("max_deck_m") or 0.0)
    extra: dict | None = None
    if special_ids:
        if over_normal_max:
            unfit_reason = "piece_overload"              # E1 真·单件超重
        elif max_piece_len and cand_max_deck and max_piece_len > cand_max_deck + 1e-9:
            unfit_reason = "piece_overlong"              # E2 长件装不进常规候选车厢
        else:
            # 🆕 T-D：E5 轴荷 → E6 组合长 → E7 车型外形 → E3 收窄（顺序同 §7；E2 已判）
            extra = _split_extra(pool, models, cands, spec_max_deck,
                                 deck_cap=(cand_max_deck or spec_max_deck))
            unfit_reason = (extra or {}).get("reason") or "candidate_narrowed"
    elif needs_split:
        if max_piece_len and spec_max_deck and max_piece_len > spec_max_deck + 1e-9:
            unfit_reason = "piece_overlong_exceeds_all"  # E4 超库内最长车厢（含特种车）
        else:
            # 🆕 T-D：E5 → E6 → E7（整票真的配不出时才有这些）
            extra = _split_extra(pool, models, cands, spec_max_deck)
            unfit_reason = (extra or {}).get("reason") or "no_candidate"
    else:
        unfit_reason = None

    msg = ""
    if unfit_reason in UNFIT_REASONS:
        if extra is not None and extra.get("reason") == unfit_reason:
            msg = extra["msg"]
        else:
            msg = unfit_msg(unfit_reason, w=max_piece, normal_max=normal_max, l=max_piece_len,
                            deck=(spec_max_deck if unfit_reason == "piece_overlong_exceeds_all"
                                  else cand_max_deck),
                            load=cand_max_load, cargo_type=cargo_type)
    if msg and not groups:
        hint = msg
    elif msg and groups and any(g.partition == "oversized" for g in groups):
        hint = msg
    oversize = {
        # 🆕 热修 v015.8（P2-1）：`unassigned` 恒有键（空列表也带键）；配不出车时逐行点名，
        #   记录构造与逐件路径共用（`_unassigned_entry`）—— 单行请求的 T5 契约不打折。
        # 🆕 v016 T-D：`candidates` 透传（E7「候选只剩闭箱类」判据用本次货型候选集）。
        "unassigned": ([] if groups else [
            {**_unassigned_entry(it, raw_items[idx] if idx < len(raw_items) else {}, list(models),
                                 candidates=cands),
             "line_class": line_class(it)}
            for idx, it in enumerate(pool)
        ]),
        "max_piece_weight_ton": max_piece or None,
        "max_piece_length_m": max_piece_len or None,
        "normal_max_ton": normal_max,                       # 全库常规车最大载重（≠ 候选集口径，勿拿它做单件比较）
        "candidate_max_load_ton": cand_max_load or None,    # 本次候选集最大载重
        "candidate_max_deck_m": cand_max_deck or None,      # 本次候选集最长车厢
        "candidate_count": main_diag.get("candidates"),
        "cargo_type": cargo_type,
        "unfit_reason": unfit_reason,
        "skipped": {k[8:]: main_diag.get(k) for k in
                    ("skipped_overload", "skipped_overlong", "skipped_nocount", "skipped_category")},
        "library_max_ton": max((m.max_load_ton for m in models), default=0.0),
        "over_normal_max": over_normal_max,
        "need_special": bool(special_ids or over_normal_max),
        "special_model_ids": special_ids,
        "splittable": not over_normal_max,
        "message": msg,
        # 🆕 v016：开关真源（与逐件路径同结构）—— released 在整票路径上由组级标记给出
        "policy": {"allow_oversized": bool(allow_oversized),
                   "released": _dedup([it["name"] for g in groups if g.oversize_released
                                       for it in g.items if it.get("name")]),
                   "hard_blocked": _dedup([it["name"] for it in pool
                                           if _hard_blocked_row({"name": it["name"]}, pool)]),
                   "legal_basis": legal_refs.legal_basis()},
        "doctrine": {"one_piece_over_t": float(COLOAD_POLICY["one_piece_over_t"]),
                     "axle_q_t": float(DIM_POLICY["axle_q_t"]),
                     "transport_units": total},
    }
    # 🆕 A6：可解体件拆件建议。
    #   ⚠️ 这段原本只写在 `plan_fleet_by_item` 里，而 API 层 `len(items) >= 2` 才走它
    #   （reference.py `_planner = ... if len(items) >= 2 else plan_fleet`）⇒ **单件大件永远拿不到
    #   拆件建议**，而可解体件最常见的正是单件。实测：30m 塔筒 divisible=true 走本函数 = divisibility null。
    _div = None
    for _it in items:
        if isinstance(_it, dict) and _it.get("divisible"):
            _div = divisibility_advice(item=_it, models=models, cargo_type=cargo_type,
                                       distance_km=distance_km,
                                       allow_oversized=allow_oversized)
            if _div:
                break

    return FleetPlan(groups=groups, total_trucks=total, primary_model_id=primary,
                     mixed=len({g.model_id for g in groups}) > 1, needs_split=needs_split,
                     split_hint=hint, oversize=oversize, category_fallback=fallback,
                     divisibility=_div)
