"""packer.py — 重心感知贪心自动装载内核 (Python 移植自 packer.js, 1:1 确定性)

契约与 packer.js 完全一致 (golden tests 逐件比对保证):
  pack(truck, cargo_list, opts) -> {"placements": [...], "unplaced": [...]}
  输入单位: cm/kg; truck: {L,W,H,maxWeight,type}; cargo item: {id,name,l,w,h,weight,qty,color,group}
  策略: balanced | volume | weight | priority
  坐标语义: x=车长(前壁→车门), y=高, z=宽; 原点=前壁左下角

⚠️ 移植纪律 (改动必须过 golden tests):
  - 排序用 cmp 语义复刻 JS comparator (functools.cmp_to_key), 不用简单 key (会改平局序)
  - 舍入用 js_round (Math.round 语义: 半值远离零), 不用 Python round (银行家舍入)
  - 朝向选择 = 首个能放下的朝向 (oriented_dims 顺序), 超限件平局取第一个
  - 贪心游标 pack_zone 的推进顺序/边界 epsilon 1e-6 原样保留
"""
from __future__ import annotations

import math
from functools import cmp_to_key
from typing import Any, Dict, List, Optional


def js_round(x: float) -> float:
    """Math.round 语义: 正半值进位, 负半值远离零."""
    if x >= 0:
        return math.floor(x + 0.5)
    return math.ceil(x - 0.5)


def _vol(it: Dict[str, Any]) -> float:
    return it["l"] * it["w"] * it["h"]


def _cmp_balanced(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    d = (b["weight"] - a["weight"]) or (_vol(b) - _vol(a))
    return (d > 0) - (d < 0)


def _cmp_volume(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    d = (_vol(b) - _vol(a)) or (b["weight"] - a["weight"])
    return (d > 0) - (d < 0)


def _cmp_priority(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    d = ((a["group"] or 0) - (b["group"] or 0)) or (b["weight"] - a["weight"]) or (_vol(b) - _vol(a))
    return (d > 0) - (d < 0)


def pack(
    truck: Dict[str, Any],
    cargo_list: List[Dict[str, Any]],
    opts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    L = float(truck["L"])
    W = float(truck["W"])
    H = float(truck["H"])
    allow_overflow = bool(opts.get("allowOverflow")) if opts else (truck.get("type") == "flatbed")
    strategy = (opts or {}).get("strategy") or "balanced"

    placements: List[Dict[str, Any]] = []
    unplaced: List[Dict[str, Any]] = []
    overflow_items: List[Dict[str, Any]] = []
    seq = 1
    total_weight = 0.0

    # ---- 展开实例 ----
    instances: List[Dict[str, Any]] = []
    for c in cargo_list:
        for _ in range(int(c.get("qty") or 1)):
            instances.append({
                "cargoId": c["id"],
                "name": c.get("name") or "",
                "l": float(c["l"]), "w": float(c["w"]), "h": float(c["h"]),
                "weight": float(c.get("weight") or 0),
                "color": c.get("color"),
                "group": int(c.get("group") or 0),
            })

    # ---- 排序 (复刻 JS comparator) ----
    if strategy == "volume":
        instances.sort(key=cmp_to_key(_cmp_volume))
    elif strategy == "priority":
        instances.sort(key=cmp_to_key(_cmp_priority))
    else:
        instances.sort(key=cmp_to_key(_cmp_balanced))

    def oriented_dims(item: Dict[str, Any]) -> List[Dict[str, float]]:
        return [
            {"dx": item["l"], "dy": item["h"], "dz": item["w"]},
            {"dx": item["w"], "dy": item["h"], "dz": item["l"]},
        ]

    def too_big(item: Dict[str, Any]) -> bool:
        for d in oriented_dims(item):
            if d["dy"] <= H and d["dx"] <= L and d["dz"] <= W:
                return False
        return True

    def overlaps_any(x: float, y: float, z: float, dx: float, dy: float, dz: float) -> bool:
        for p in placements:
            if not (x + dx <= p["x"] or p["x"] + p["dx"] <= x or
                    y + dy <= p["y"] or p["y"] + p["dy"] <= y or
                    z + dz <= p["z"] or p["z"] + p["dz"] <= z):
                return True
        return False

    def fits_here(item: Dict[str, Any], x: float, z: float, y: float, end_x: float, check_overlap: bool) -> Optional[Dict[str, float]]:
        for d in oriented_dims(item):
            if d["dy"] > H or d["dx"] > L or d["dz"] > W:
                continue
            if x + d["dx"] <= end_x + 1e-6 and z + d["dz"] <= W + 1e-6 and y + d["dy"] <= H + 1e-6:
                if not check_overlap or not overlaps_any(x, y, z, d["dx"], d["dy"], d["dz"]):
                    return d
        return None

    def is_supported(x: float, y: float, z: float, dx: float, dz: float) -> bool:
        if y < 0.01:
            return True
        for q in placements:
            if abs(q["y"] + q["dy"] - y) > 0.01:
                continue
            if q["x"] + q["dx"] <= x or x + dx <= q["x"]:
                continue
            if q["z"] + q["dz"] <= z or z + dz <= q["z"]:
                continue
            return True
        return False

    def emit(item: Dict[str, Any], d: Dict[str, float], x: float, y: float, z: float) -> None:
        nonlocal seq, total_weight
        placements.append({
            "id": "p" + str(seq),
            "cargoId": item["cargoId"],
            "name": item["name"],
            "color": item["color"],
            "weight": item["weight"],
            "group": item["group"] or 0,
            "x": x, "y": y, "z": z,          # 不四舍五入 (与 JS 一致: 舍入会误判重叠)
            "dx": d["dx"], "dy": d["dy"], "dz": d["dz"],
        })
        seq += 1
        total_weight += item["weight"]

    # ---- 分区 shelf 装载 ----
    def pack_zone(items: List[Dict[str, Any]], start_x: float, end_x: float, check_overlap: bool) -> List[Dict[str, Any]]:
        x, y, z = start_x, 0.0, 0.0
        layer_h, row_d = 0.0, 0.0
        remain: List[Dict[str, Any]] = []
        for item in items:
            if too_big(item):
                if allow_overflow:
                    overflow_items.append(item)
                else:
                    unplaced.append({"cargoId": item["cargoId"], "name": item["name"], "reason": "尺寸超限"})
                continue
            placed = False
            guard = 0
            while not placed and guard < 100000:
                guard += 1
                if x >= end_x - 1e-6:
                    z += row_d
                    x = start_x
                    row_d = 0.0
                if z >= W - 1e-6:
                    y += max(layer_h, 1.0)
                    x = start_x
                    z = 0.0
                    layer_h = 0.0
                    row_d = 0.0
                if y >= H - 1e-6:
                    break
                d = fits_here(item, x, z, y, end_x, check_overlap)
                if d is not None and not is_supported(x, y, z, d["dx"], d["dz"]):
                    d = None
                if d is not None:
                    emit(item, d, x, y, z)
                    x += d["dx"]
                    layer_h = max(layer_h, d["dy"])
                    row_d = max(row_d, d["dz"])
                    placed = True
                else:
                    if x > start_x:
                        z += row_d
                        x = start_x
                        row_d = 0.0
                    else:
                        y += max(layer_h, 1.0)
                        x = start_x
                        z = 0.0
                        layer_h = 0.0
                        row_d = 0.0
            if not placed:
                remain.append(item)
        return remain

    # ---- 分区策略 ----
    use_zones = strategy == "balanced" and L >= 800
    heavy: List[Dict[str, Any]] = []
    light: List[Dict[str, Any]] = []
    if use_zones:
        total_w = sum(it["weight"] for it in instances)
        max_w = max((it["weight"] for it in instances), default=0.0)
        all_equal = len(instances) > 1 and all(it["weight"] == max_w for it in instances)
        cum = 0.0
        for it in instances:
            if (not all_equal and it["weight"] > max_w * 0.3) or (all_equal and cum < total_w * 0.6):
                heavy.append(it)
            else:
                light.append(it)
            cum += it["weight"]
    else:
        heavy = instances
        light = []

    rem_rear: List[Dict[str, Any]] = []
    if use_zones:
        mid_x0 = L * 0.35
        mid_x1 = L * 0.65
        rem_mid = pack_zone(heavy, mid_x0, mid_x1, True)
        rem_front = pack_zone(light, 0, mid_x0, True)
        rem_rear = pack_zone(rem_mid + rem_front, mid_x1, L, True)
    elif strategy == "priority":
        by_group: Dict[int, List[Dict[str, Any]]] = {}
        for it in instances:
            by_group.setdefault(it["group"] or 0, []).append(it)
        rem_all: List[Dict[str, Any]] = []
        g_start = 0.0
        for g in sorted(by_group.keys()):
            rem_all.extend(pack_zone(by_group[g], g_start, L, True))
            g_start = max(g_start, max((p["x"] + p["dx"] for p in placements), default=0.0))
        rem_rear = rem_all
    else:
        rem_rear = pack_zone(heavy, 0, L, True)

    # ---- 兜底: 全局空隙填充 ----
    def uniq_sorted(values: List[float]) -> List[float]:
        out: List[float] = []
        seen = set()
        for v in values:
            if v not in seen:
                seen.add(v)
                out.append(v)
        out.sort()
        return out

    def fill_gaps(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        remain: List[Dict[str, Any]] = []
        for item in items:
            if too_big(item):
                if allow_overflow:
                    overflow_items.append(item)
                else:
                    unplaced.append({"cargoId": item["cargoId"], "name": item["name"], "reason": "尺寸超限"})
                continue
            placed = False
            ys = uniq_sorted([0.0] + [p["y"] + p["dy"] for p in placements])
            zs = uniq_sorted([0.0] + [p["z"] + p["dz"] for p in placements])
            xs = uniq_sorted([0.0] + [p["x"] + p["dx"] for p in placements])
            for y in ys:
                if placed:
                    break
                for z in zs:
                    if placed:
                        break
                    for x in xs:
                        d = fits_here(item, x, z, y, L, True)
                        if d is not None and not is_supported(x, y, z, d["dx"], d["dz"]):
                            d = None
                        if d is not None:
                            emit(item, d, x, y, z)
                            placed = True
                            break
            if not placed:
                remain.append(item)
        return remain

    rem = fill_gaps(rem_rear)
    for item in rem:
        unplaced.append({"cargoId": item["cargoId"], "name": item["name"], "reason": "空间不足"})

    # ---- 平板车超限件: 居中堆顶 ----
    if overflow_items:
        top_y = max((p["y"] + p["dy"] for p in placements), default=0.0)
        for item in overflow_items:
            dims = oriented_dims(item)
            best = dims[0]
            best_ov = 1e18
            for d in dims:
                ov = max(0.0, d["dx"] - L) + max(0.0, d["dz"] - W)
                if ov < best_ov:
                    best_ov = ov
                    best = d
            px = (L - best["dx"]) / 2 if best["dx"] > L else 0.0
            pz = (W - best["dz"]) / 2 if best["dz"] > W else 0.0
            placements.append({
                "id": "p" + str(seq),
                "cargoId": item["cargoId"],
                "name": item["name"],
                "color": item["color"],
                "weight": item["weight"],
                "x": js_round(px * 10) / 10,
                "y": js_round(top_y * 10) / 10,
                "z": js_round(pz * 10) / 10,
                "dx": best["dx"], "dy": best["dy"], "dz": best["dz"],
            })
            seq += 1
            top_y += best["dy"]
            total_weight += item["weight"]

    # ---- 安全网: 最终碰撞校验 ----
    final_list: List[Dict[str, Any]] = []
    for p in placements:
        conflict = any(
            not (p["x"] + p["dx"] <= q["x"] or q["x"] + q["dx"] <= p["x"] or
                 p["y"] + p["dy"] <= q["y"] or q["y"] + q["dy"] <= p["y"] or
                 p["z"] + p["dz"] <= q["z"] or q["z"] + q["dz"] <= p["z"])
            for q in final_list
        )
        if conflict:
            unplaced.append({"cargoId": p["cargoId"], "name": p["name"], "reason": "空间不足"})
        else:
            final_list.append(p)

    return {"placements": final_list, "unplaced": unplaced}


# ---- 统计薄封装 (对齐 data.js getStats 口径) ----
def stats(truck: Dict[str, Any], placements: List[Dict[str, Any]], cargo_total_qty: Optional[int] = None) -> Dict[str, Any]:
    L, W, H = float(truck["L"]), float(truck["W"]), float(truck["H"])
    vol_total = L * W * H
    placed_count = len(placements)
    total_weight = sum(p.get("weight") or 0 for p in placements)
    vol_used = sum(p["dx"] * p["dy"] * p["dz"] for p in placements)
    util = vol_used / vol_total if vol_total > 0 else 0.0
    return {
        "placedCount": placed_count,
        "totalQty": cargo_total_qty if cargo_total_qty is not None else placed_count,
        "pendingCount": (cargo_total_qty if cargo_total_qty is not None else placed_count) - placed_count,
        "totalWeight": total_weight,
        "maxWeight": float(truck.get("maxWeight") or 0),
        "overweight": total_weight > float(truck.get("maxWeight") or 0),
        "volUsed": vol_used,
        "volTotal": vol_total,
        "volumeUtil": util,
        "volumeUtilPct": util * 100,
        "remainVol": max(0.0, vol_total - vol_used),
    }
