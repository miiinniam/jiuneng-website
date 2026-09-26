"""v011 整票试算选车器（纯函数、无 IO）。

铁律（设计 §3.2 INV-2）：本模块**不实现任何**"装得下"判断，
车数一律由 费用计算公式.车辆数分解() 得出 —— 与计价同源。

口径修正记录（T1 实现期，以源码为准）：
  `车辆数分解()` 的真实返回键是 **「车数」**（另有 重量/体积/长度/面积/主因/不可分/
  最大单件重量吨/车型最大载重吨）；实施计划草稿里写的「总车数」在源码中不存在。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import 费用计算公式 as 公式
from app.services.vehicle_registry import VehicleModel

ENGINE = "fleet_planner@v011"

# 判定用的常量（不参与调价，只决定"能不能同车"）
_SPECIAL_CATEGORY = "special"


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


def _norm_items(items: list[dict] | None) -> list[dict]:
    out = []
    for it in items or []:
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
              distance_km: float | None, *, partition: str) -> tuple[FleetGroup | None, bool, dict]:
    """对一组货（同一分区）按整票试算选型。返回 (最佳组, 有无候选不可分超载, 诊断)。

    🆕 2026-09-23：第三个返回值 `diag` 记录**每个候选为什么被跳过**（单件超载/长件超车厢/
    算不出车数）与候选集口径（最长车厢、最大载重）。此前这些信息被丢弃，导致
    「长件装不进车厢」被统一说成「单件超常规车型上限」，UI 打出「10 吨 > 38 吨」的矛盾文案。
    """
    total_w = sum(i["weight_kg"] * i["count"] for i in pool) / 1000.0
    total_v = sum(i["length_m"] * i["width_m"] * i["height_m"] * i["count"] for i in pool)
    feat = 公式.货物载荷特征完整(货物总重量吨=total_w, 货物总体积立方米=total_v, 单件货物=pool)

    scored: list[tuple] = []
    diag = {
        "partition": partition,
        "candidates": len(models),
        "max_deck_m": max((m.length_m or 0.0 for m in models), default=0.0),
        "max_load_ton": max((m.max_load_ton or 0.0 for m in models), default=0.0),
        "skipped_overload": 0, "skipped_overlong": 0, "skipped_nocount": 0, "skipped_category": 0,
    }
    for m in models:
        if m.category == _SPECIAL_CATEGORY and partition != "oversized":
            diag["skipped_category"] += 1
            continue                      # 常规货不用特种车兜底
        if partition == "oversized" and m.category != _SPECIAL_CATEGORY:
            diag["skipped_category"] += 1
            continue
        bd = 公式.车辆数分解(
            货物总重量吨=total_w, 货物总体积立方米=total_v,
            最大单件长度米=feat["最大单件长度米"], 货物总占地面积平方米=feat["总占地面积平方米"],
            车型最大载重吨=m.max_load_ton, 车型容积立方米=m.effective_volume_m3,
            车型地板长米=m.length_m, 车型地板面积平方米=m.floor_area_m2,
            装载效率=m.loading_efficiency, 最大单件重量吨=feat["最大单件重量吨"],
        )
        if bd.get("不可分"):
            diag["skipped_overload"] += 1
            continue                      # 单件 > 载重：这辆车根本不适用
        if feat["最大单件长度米"] and m.length_m and feat["最大单件长度米"] > m.length_m:
            diag["skipped_overlong"] += 1
            continue                      # 长件装不进车厢
        n = int(bd.get("车数") or 0)      # v011: 源码键是「车数」（计划草稿的「总车数」不存在）
        if n <= 0:
            diag["skipped_nocount"] += 1
            continue
        scored.append((n, _estimate_cost(m, n, distance_km), m.max_load_ton, m.model_id, m, bd))
    if not scored:
        return None, True, diag
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))   # 车数 → 成本 → 载重 → 字典序
    n, _, _, _, m, bd = scored[0]
    reason = (f"整票 {total_w:g} t / 地板占用 {feat['总占地面积平方米'] or 0:g} m²"
              f" → {m.display_name}（载重 {m.max_load_ton:g} t、地板 {m.floor_area_m2 or 0:g} m²）"
              f" {n} 辆装完；主因 {bd.get('主因') or '重量'}")
    return FleetGroup(partition=partition, model_id=m.model_id, vehicle_count=n,
                      binding=str(bd.get("主因") or "重量"), payload=feat, breakdown=bd,
                      reason=reason, items=pool), False, diag


def plan_fleet(*, items, total_weight_kg=None, total_volume_m3=None, cargo_type="normal",
               models, distance_km=None) -> FleetPlan:
    """整票试算选车。

    注：不做 `loading_efficiency` 形参 —— 装载效率由 `车辆数分解()` 逐车型取
    `m.loading_efficiency`（车型自带，权威），选车器不应再插一层可被误传的效率。
    `total_weight_kg` / `total_volume_m3` 保留以贴合既有 API 调用习惯；权重与体积
    一律按 items 明细重算，避免与明细不一致的入参污染判定。
    """
    pool = _norm_items(items)
    cands, fallback = _candidates(cargo_type, list(models))

    main, main_unfit, main_diag = _plan_one(pool, cands, distance_km, partition="main")
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
                                      distance_km, partition="oversized")
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
    cand_max_deck = float(main_diag.get("max_deck_m") or 0.0)     # 本次**常规候选集**口径
    cand_max_load = float(main_diag.get("max_load_ton") or 0.0)
    spec_max_deck = float(spec_diag.get("max_deck_m") or 0.0)
    if special_ids:
        if over_normal_max:
            unfit_reason = "piece_overload"              # 真·单件超重
        elif max_piece_len and cand_max_deck and max_piece_len > cand_max_deck + 1e-9:
            unfit_reason = "piece_overlong"              # 长件装不进常规候选车厢
        else:
            unfit_reason = "candidate_narrowed"          # 常规候选被货型/口径收窄
    elif needs_split:
        unfit_reason = ("piece_overlong_exceeds_all"
                        if (max_piece_len and spec_max_deck and max_piece_len > spec_max_deck + 1e-9)
                        else "no_candidate")
    else:
        unfit_reason = None

    if unfit_reason == "piece_overload":
        msg = (f"单件 {max_piece:.1f}t 超常规车型上限 {normal_max:.0f}t，需超限运输（特种车 + 超限许可）")
    elif unfit_reason == "piece_overlong":
        msg = (f"单件长 {max_piece_len:.1f}m 超常规候选车型最长车厢 {cand_max_deck:.1f}m"
               f"（单件仅 {max_piece:.1f}t，未超 {normal_max:.0f}t 载重上限），已按特种车（超长/超限）处置")
    elif unfit_reason == "candidate_narrowed":
        msg = (f"货型「{cargo_type}」的常规候选车型（最长车厢 {cand_max_deck:.1f}m、"
               f"最大载重 {cand_max_load:.0f}t）装不下该单件，已按特种车处置")
    elif unfit_reason == "piece_overlong_exceeds_all":
        msg = (f"单件长 {max_piece_len:.1f}m 超库内最长车厢（特种车最长 {spec_max_deck:.1f}m），"
               f"需拆单或专线询价")
    else:
        msg = ""
    if msg and not groups:
        hint = msg
    elif msg and groups and any(g.partition == "oversized" for g in groups):
        hint = msg
    oversize = {
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
    }
    return FleetPlan(groups=groups, total_trucks=total, primary_model_id=primary,
                     mixed=len({g.model_id for g in groups}) > 1, needs_split=needs_split,
                     split_hint=hint, oversize=oversize, category_fallback=fallback)
