from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.exchange_rate import force_refresh, get_exchange_rate
from app.services.presets import CARGO_IMPORT_EXPORT_ESTIMATES, CARGO_TYPE_RATES
from app.services.vehicle_registry import models_by_category, get_model, VEHICLE_MODELS, VehicleModel
from app.services import 费用计算公式 as 公式
from app.services.border_fees import calc_border_fees, save_border_fees_config, VEHICLE_SCALING_ITEMS
from app.schemas import BorderFeesSaveRequest
from app.services.ai_client import AIClient, AIClientError

router = APIRouter()


@router.get("/reference/vehicle-models")
async def list_vehicle_models() -> dict:
    return {
        category: [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "max_load_ton": m.max_load_ton,
                "volume_capacity_m3": m.volume_capacity_m3,
                "length_m": m.length_m,
                "width_m": m.width_m,
                "height_m": m.height_m,
                "max_cargo_height_m": m.max_cargo_height_m,
                "loading_efficiency": m.loading_efficiency,
                "curb_weight_ton": m.curb_weight_ton,
                "floor_area_m2": m.floor_area_m2,
                "effective_volume_m3": m.effective_volume_m3,
                "base_rate_vnd_per_km": m.base_rate_vnd_per_km,
                "fuel_l_per_100km": m.fuel_l_per_100km,
                "fuel_penalty": m.fuel_penalty,
                "fixed_surcharge_vnd": m.fixed_surcharge_vnd,
                "toll_rate_vnd_per_km": m.toll_rate_vnd_per_km,
                "osrm_profile": m.osrm_profile,
                # 🆕 v015：车型下拉（app.js 取本接口）也要带标准车型列，否则装车 3D 的组合车
                #   四条路径（rigid/articulated/center_axle/full_trailer）在现网永远喂不进数据。
                "axle_config": m.axle_config,
                "suitable_cargo_types": list(m.suitable_cargo_types),
                "notes": m.notes,
            }
            for m in models
        ]
        for category, models in models_by_category().items()
    }


# ── 自动选车：按尺寸+重量（四约束）匹配，支持逐货物分组到不同车型 ──
# v011: 已由 fleet_planner 取代，保留供对比
def _item_fit_model(item: dict) -> VehicleModel | None:
    """为单件货物找"最小能装下"的车型（载重优先，其次地板长接近）。"""
    L = float(item.get("length_m") or 0)
    W = float(item.get("width_m") or 0)
    H = float(item.get("height_m") or 0)
    w_ton = float(item.get("weight_kg") or 0) / 1000
    stackable = bool(item.get("stackable"))
    area = L * W
    vol = L * W * H

    best: VehicleModel | None = None
    for m in VEHICLE_MODELS:
        if w_ton > m.max_load_ton:
            continue
        if m.length_m is not None and L > m.length_m:
            continue
        if m.floor_area_m2 is not None and (not stackable) and area > m.floor_area_m2 * m.loading_efficiency:
            continue
        if m.effective_volume_m3 is not None and vol > m.effective_volume_m3 * m.loading_efficiency:
            continue
        if best is None or m.max_load_ton < best.max_load_ton or (
            m.max_load_ton == best.max_load_ton and (m.length_m or 0) < (best.length_m or 0)
        ):
            best = m
    return best


# v011: 已由 fleet_planner 取代，保留供对比
def _items_per_truck(model: VehicleModel, item: dict) -> int:
    """估算一辆车里能装几件该货物（按重量/长度/面积/体积取最小，至少 1）。"""
    L = float(item.get("length_m") or 0)
    W = float(item.get("width_m") or 0)
    H = float(item.get("height_m") or 0)
    w_ton = float(item.get("weight_kg") or 0) / 1000
    stackable = bool(item.get("stackable"))

    cap = []
    vol = L * W * H
    if model.max_load_ton:
        cap.append(max(1, int(model.max_load_ton // w_ton)))
    if model.length_m and L:
        cap.append(max(1, int(model.length_m // L)) if stackable or L < model.length_m else 1)
    if model.floor_area_m2 and L and W and not stackable:
        cap.append(max(1, int((model.floor_area_m2 * model.loading_efficiency) // (L * W))))
    if model.effective_volume_m3 and vol:
        cap.append(max(1, int((model.effective_volume_m3 * model.loading_efficiency) // vol)))
    per = min(cap) if cap else 1
    return max(1, per)


@router.post("/reference/fit-vehicles")
async def fit_vehicles(payload: dict) -> dict:
    """输入货物信息，自动选车。

    v011 起本端点是 **薄壳**：车数一律由 `services/fleet_planner.plan_fleet()` 按整票
    试算得出（内部调 `费用计算公式.车辆数分解()`，与 `route/cost` 同一函数 → INV-1 同源）。
    旧实现为「逐件挑最小车」，8 件×2.5t 被拆成 8 辆小卡（报价虚高 2.35 倍），已废弃。

    payload:
      { weight_kg, volume_m3?, cargo_type?,
        allow_oversized?: bool,                              # 🆕 v016：允许超限运输配车（默认 false）
        distance_km?: float,                                 # 🆕 v016：有距离才比总价（否则 rate_only）
        locked_models?: {line_id: model_id},                 # 🆕 v017：逐行锁定车型（默认无）
        accepted_pairs?: [pair_id] | {pair_id: bool},        # 🆕 v017：共车组合采纳（默认全采纳）
        plan_confirmed?: bool,                               # 🆕 v017：只回显 + 审计（不参与金额）
        fold_shape?: "auto"|"integral"|"n2"|"n4"|"n6"|"n8",   # 🆕 v015.8 T5：顶层折叠形态
        shape?: ...                                          # 旧式键：只在**折叠词表**内才当折叠值；
                                                             # v013 几何值 box/cylinder/… 原样透传不管
        inner_d_m?: float,                                   # 🆕 T5：顶层内径缺省（行级 inner_d_m 优先）
        items?: [{name?, length_m, width_m, height_m?, weight_kg, count, stackable,
                  fold_shape?, shape?, inner_d_m?, split_n?}] }
    返回:
      { recommended, groups: [{model_id, display_name, category, max_load_ton,
                               vehicle_count, transport_units, reason,
                               dim_flags, permit_flags, count_doctrine, axle_lines,
                               breakdown,   # 🆕 v023：本组四约束分解 {车数,重量,体积,长度,面积,主因}
                               oversize_released, pair_total_width_m,
                               pairs: [{pair_id, line_ids, line_names, per_truck, trucks,
                                        rule_id, reason, accepted}],   # 🆕 v017：共车组合
                               locked: {line_id: model_id},            # 🆕 v017：逐行锁定回显
                               items:[...]}],
        fits, total_trucks, vehicle_breakdowns,
        confirm: {total_trucks, one_item_trucks, multi_item_trucks,  # 🆕 v017：确认回显
                  lines: [{line_id, model, locked}], plan_confirmed},
        oversize: {..., policy: {allow_oversized, released, hard_blocked, legal_basis}},
        # ── v011 新增（前端⑥口径卡 / INV-1 追溯）──
        reason, mixed, needs_split, split_hint, engine, category_fallback }
    """
    from app.services import fleet_planner as pl

    items = payload.get("items") or []
    # 🆕 v016：「允许超限运输配车」开关 —— 逐单决策，非法值**大声报错**（照 fold_shape 的惯例，
    #   不静默按 False 跑；错值静默反而会让用户以为开关生效了）。
    allow_oversized = payload.get("allow_oversized", False)
    if allow_oversized is None:
        allow_oversized = False
    if not isinstance(allow_oversized, bool):
        raise HTTPException(422, f"allow_oversized 必须是 true/false（收到 {allow_oversized!r}）—— "
                                 "该开关只放宽「超限」（4.5~5.5m 宽 / 4.75~5.5m 总高可配车 + 许可标），"
                                 "不放松「超载」（单件超核定载重仍不自动配车）")
    # 🆕 v017 T-2：配车契约扩展（三项都可缺省 ⇒ 与 v016 逐字节同口径）。
    #   `locked_models` 逐行锁定车型：非法车型 / 未知 line_id ⇒ 422 带中文原因（照 allow_oversized
    #   的「大声报错」惯例，不静默忽略 —— 静默忽略会让用户以为锁定生效了）。
    locked_models_in = payload.get("locked_models")
    locked_models: dict[str, str] = {}
    if locked_models_in is not None:
        if not isinstance(locked_models_in, dict):
            raise HTTPException(422, f"locked_models 必须是 {{line_id: 车型}} 映射（收到 {locked_models_in!r}）"
                                     " —— line_id 取货物行的 line_id（缺省为行序号从 0 起），"
                                     "车型取车辆库 model_id")
        known_ids = [pl.line_id_of(raw, i) for i, raw in enumerate(items)]
        for k in locked_models_in:
            if str(k).strip() not in known_ids:
                raise HTTPException(422, f"locked_models 里的 line_id {k!r} 不存在于本次货物清单"
                                         f"（合法 line_id：{known_ids}）—— 逐行锁定必须指向本票的某一货行")
        bad_models = [str(v) for v in locked_models_in.values() if get_model(str(v or "").strip()) is None]
        if bad_models:
            raise HTTPException(422, f"locked_models 里的车型 {bad_models!r} 不在车辆库中 —— "
                                     "合法车型 = /api/v1/reference/vehicle-models 返回的 model_id")
        locked_models = {str(k).strip(): str(v).strip() for k, v in locked_models_in.items()}
    #   `accepted_pairs` 共车组合采纳：缺省 = 全采纳；`{pair_id: false}` ⇒ 该组合不共车（车数上调）；
    #   `[pair_id]` 列表 = 白名单（只采纳列出的组合，`[]` = 全部不共车）。非法值大声报错。
    accepted_pairs_in = payload.get("accepted_pairs")
    accepted_pairs = None
    if accepted_pairs_in is not None:
        if isinstance(accepted_pairs_in, dict):
            for k, v in accepted_pairs_in.items():
                if not isinstance(v, bool):
                    raise HTTPException(422, f"accepted_pairs[{k!r}] 必须是 true/false（收到 {v!r}）—— "
                                             "显式 false 表示该共车组合不采纳（按「不共车」重算，车数上调）")
            accepted_pairs = {str(k): bool(v) for k, v in accepted_pairs_in.items()}
        elif isinstance(accepted_pairs_in, (list, tuple)):
            for v in accepted_pairs_in:
                if isinstance(v, (dict, list, tuple)) or v is None:
                    raise HTTPException(422, f"accepted_pairs 列表的元素必须是 pair_id 字符串（收到 {v!r}）——"
                                             " pair_id 取本接口 groups[].pairs[].pair_id")
            accepted_pairs = [str(v) for v in accepted_pairs_in]
        else:
            raise HTTPException(422, f"accepted_pairs 必须是 [pair_id] 列表或 {{pair_id: true/false}} 映射"
                                     f"（收到 {accepted_pairs_in!r}）")
    #   `plan_confirmed` 只用于回显 + 审计（「已确认车型与车数」动作），**不参与任何金额**。
    plan_confirmed = payload.get("plan_confirmed", False)
    if plan_confirmed is None:
        plan_confirmed = False
    if not isinstance(plan_confirmed, bool):
        raise HTTPException(422, f"plan_confirmed 必须是 true/false（收到 {plan_confirmed!r}）—— "
                                 "该字段只用于回显与审计（记录「已确认车型与车数」动作），不参与金额计算")
    plan_confirmed = bool(plan_confirmed)
    # 🆕 热修 v015.8（P1-1）：折叠策略键 = **`fold_shape`**（行级与顶层均支持；顶层 python 形参名 `shape=` 保留）。
    #   旧式顶层 `shape` 只在**折叠词表**内才被转发（v013 几何值 box/cylinder/… 原样透传不管、不报错）；
    #   非法 `fold_shape` 值由形态层 `_norm_shape` 大声报错（本端点译成 422，不静默）。
    top_fold = payload.get("fold_shape")
    if top_fold is None or not str(top_fold).strip():
        top_fold = pl._fold_vocab(payload.get("shape")) or "auto"
    shape = str(top_fold)
    top_inner_d = payload.get("inner_d_m")
    try:
        top_inner_d = float(top_inner_d) if top_inner_d is not None else None
    except (TypeError, ValueError):
        top_inner_d = None
    # 🆕 v015.6：≥2 行货 ⇒ **逐件配车**（每行按自己的尺寸/重量单独配车，混编车队）；动机：实测一条 25m 大梁曾把整票判成 0 辆。
    # 🆕 热修 v015.8（P2-1）：1 行货在**带形态层数据**时也走逐件路径（fold_shape/inner_d_m/split_n/shape_class/
    #   折叠词 `shape` 行级键，或顶层给形态/内径）—— 形态折算只在逐件路径上；其余 1 行走整票路径，
    #   该路径已同步 T3/T5 尺寸闸 + `unassigned` 恒有键（单行口径与逐件路径不许分叉）。
    _planner = pl.plan_fleet_by_item if len(items) >= 2 else pl.plan_fleet

    def _row_has_fold_data(it) -> bool:
        if not isinstance(it, dict):
            return False
        for k in ("inner_d_m", "split_n", "shape_class"):
            if it.get(k) not in (None, ""):
                return True
        # 行级 `fold_shape`（权威折叠键）：**任何非空值**都过形态层 —— 合法值生效、非法值大声报错（422，不静默）
        fs = it.get("fold_shape")
        if fs is not None and str(fs).strip():
            return True
        # 旧式行级 `shape`：只在折叠词表（且非 auto）内才需要形态层
        for k in ("shape", "form"):
            v = pl._fold_vocab(it.get(k))
            if v is not None and v.strip().lower() != "auto":
                return True
        return False

    # 显式形态（integral|nK）、顶层内径、或行级形态数据一旦出现，1 行货也得过形态层 ⇒ 强制走逐件路径
    if str(shape).strip().lower() not in ("", "auto") or top_inner_d is not None \
            or any(_row_has_fold_data(it) for it in items):
        _planner = pl.plan_fleet_by_item
    # 🆕 v017 T-2：`locked_models` 是**逐行**约束（整票路径没有行概念）⇒ 非空时一律走逐件路径
    if locked_models:
        _planner = pl.plan_fleet_by_item
    _common = dict(
        items=items,
        total_weight_kg=payload.get("weight_kg"),
        total_volume_m3=payload.get("volume_m3"),
        cargo_type=payload.get("cargo_type") or "normal",
        models=VEHICLE_MODELS,
        distance_km=payload.get("distance_km"),
        allow_oversized=allow_oversized,          # 🆕 v016：开关透传（两条路径都要带）
    )
    if _planner is pl.plan_fleet_by_item:
        try:
            plan = _planner(**_common, shape=shape or "auto", inner_d_m=top_inner_d,
                            locked_models=locked_models or None,   # 🆕 v017：逐行锁定车型
                            accepted_pairs=accepted_pairs)         # 🆕 v017：共车组合采纳
        except ValueError as exc:
            # 形态层护栏（非法 fold_shape / 内径口径）⇒ 明确报错（422 带原因），不把 500 吐给前端
            raise HTTPException(422, str(exc)) from exc
    else:
        plan = _planner(**_common)

    def _group_out(g) -> dict:
        """分组响应组装：车型属性一次查表，避免在推导式里重复调 get_model()。"""
        m = get_model(g.model_id)
        axles = [it.get("axle_lines") for it in g.items if it.get("axle_lines")]
        # 🆕 v017：本组的逐行锁定回显（只有本组内**确实锁定**的行；键 = line_id 字符串口径）
        locked = {it.get("line_id"): locked_models[it["line_id"]]
                  for it in g.items if it.get("line_id") in locked_models}
        return {
            "model_id": g.model_id,
            "display_name": m.display_name if m else g.model_id,
            "category": m.category if m else "",
            "max_load_ton": m.max_load_ton if m else 0.0,
            "vehicle_count": g.vehicle_count,
            "transport_units": g.vehicle_count,   # 🆕 T4：运输单元数（一次许可对一个单元；≠ 轴线条数）
            "reason": g.reason,          # v011：选车理由（前端车队行⑥直接显示）
            "items": g.items,
            # 🆕 v015.8 T3/T4/T5：dim_flags（车辆匹配层）与 permit_flags（法规层）**分列**
            "dim_flags": list(g.dim_flags),
            "permit_flags": list(g.permit_flags),
            "count_doctrine": dict(g.count_doctrine),
            "axle_lines": max(axles, key=lambda a: a.get("lines_max") or 0) if axles else None,
            # 🆕 v016：靠「允许超限运输配车」开关拿到的组（前端据此出常驻警示条 + 报价单文案）
            "oversize_released": bool(getattr(g, "oversize_released", False)),
            "pair_total_width_m": getattr(g, "pair_total_width_m", None),
            # 🆕 v017 T-2：共车组合（前端④「拼车核对」面板逐条勾选用）+ 逐行锁定回显
            "pairs": [dict(p) for p in (getattr(g, "pairs", None) or [])],
            "locked": locked,
            # 🆕 v023：本组的**四约束车辆数分解**（`{车数,重量,体积,长度,面积,主因,不可分}`）——
            #   顶层 `vehicle_breakdowns` 是 `{model_id: ...}` 映射，同型号出现两组（main/oversized）
            #   会互相覆盖，且 group 里拿不到「这份台计属于哪一组」。纯透传 `FleetGroup.breakdown`
            #   （三处构造点均为 dict，见 fleet_planner :282/:1819/:2057），前端改读组内即无歧义。
            #   ⚠️ 只读：`bd.车数` 是**四约束侧**的估算，权威车数是 `count_doctrine.caliber`
            #   = `max(floor, 4const, packer)`，两者不等时以 count_doctrine 为准。
            "breakdown": dict(g.breakdown),
        }

    result_groups = [_group_out(g) for g in plan.groups]
    total = plan.total_trucks
    vehicle_breakdowns = {g.model_id: g.breakdown for g in plan.groups}
    oversize = plan.oversize

    primary = next((g for g in result_groups if g["model_id"] == plan.primary_model_id), None)
    recommended = primary or (result_groups[0] if result_groups else None)
    primary_reason = (primary or {}).get("reason") or (result_groups[0]["reason"] if result_groups else "")

    message = ("自动匹配完成（整票试算）" if result_groups
               else "所有货物均无合适车型，请拆车或联系专线")
    if plan.split_hint:
        message += f"；{plan.split_hint}"

    # 🆕 v016：「允许超限运输配车」每次 ON 必落一条审计（复用 audit_log.log_call，不新建文件）。
    #   审计只记**决策与清单**，失败不影响配车（log_call 内部吞异常）。
    policy = dict(oversize.get("policy") or {})
    if allow_oversized:
        from app.services import audit_log
        audit_log.log_call(
            tool="fleet_planner.allow_oversized", role="reference.fit-vehicles", ok=True,
            args={"allow_oversized": True,
                  "cargo_type": _common["cargo_type"],
                  "distance_km": _common["distance_km"],
                  "released": list(policy.get("released") or []),
                  "hard_blocked": list(policy.get("hard_blocked") or []),
                  "items": [{"name": i.get("name"), "count": i.get("count"),
                             "L": i.get("length_m"), "W": i.get("width_m"), "H": i.get("height_m")}
                            for i in items[:10]],
                  "total_trucks": total},
            note=("超限放行：只放宽超限（宽 >4.5m 且 ≤5.5m / 总高 >4.75m 且 ≤5.5m 降级为可运 + "
                  "超限件可沿车长串联共车）；单件超核定载重、宽/总高 >5.5m、轴荷/桥涵一律不放行。"
                  f"命中车型：{[g['model_id'] for g in result_groups]}"),
        )
        message += ("；⚠️ 已启用超限放行：本次配车含超限方案 —— 出车/导出报价单前请确认已（或将）"
                    "办妥超限运输许可（本开关不放松「超载」）")

    # 🆕 v017 T-2：确认回显 `confirm{}`（设计 §3.2）—— 前端⑤「确认车型与车数」两组小计 + 逐行
    #   车型/锁定态 + `planSig` 的原料。**车数只搬运 plan.total_trucks 与组内行车数，不重算**。
    line_model: dict[str, str] = {}
    for g in result_groups:
        for it in g["items"]:
            lid = it.get("line_id")
            if lid:
                line_model[str(lid)] = g["model_id"]
    one_item = 0
    multi_item = 0
    for g in result_groups:
        for it in g["items"]:
            n_i = int(it.get("vehicle_count") or 0)
            cap = it.get("pieces_per_truck_max")
            if cap is not None and int(cap) >= 2:
                multi_item += n_i
            else:
                one_item += n_i
    input_line_ids = [pl.line_id_of(raw, i) for i, raw in enumerate(items)]
    confirm = {
        "total_trucks": int(total),
        "one_item_trucks": int(one_item),      # 一车一件（行级 pieces_per_truck_max = 1）
        "multi_item_trucks": int(multi_item),  # 一车多件（行级上限 ≥ 2）
        "lines": [{"line_id": lid, "model": line_model.get(lid),
                   "locked": lid in locked_models} for lid in input_line_ids],
        "plan_confirmed": plan_confirmed,      # 🆕 回显（不参与金额）
    }

    # 🆕 v017 T-2：`plan_confirmed=true` ⇒ 落一条审计（复用 audit_log.log_call，不新建文件；
    #   只记**确认动作 + 配车结果**，不参与任何金额；log_call 内部吞异常，失败不影响配车）。
    if plan_confirmed:
        from app.services import audit_log
        audit_log.log_call(
            tool="fleet_planner.plan_confirmed", role="reference.fit-vehicles", ok=True,
            args={"total_trucks": int(total),
                  "one_item_trucks": int(one_item), "multi_item_trucks": int(multi_item),
                  "locked_models": dict(locked_models),
                  "accepted_pairs": (list(accepted_pairs) if isinstance(accepted_pairs, (list, tuple))
                                     else dict(accepted_pairs or {})),
                  "lines": confirm["lines"],
                  "models": [g["model_id"] for g in result_groups]},
            note=("已确认车型与车数：本票配车结果如下（该确认只用于记录/追溯，不参与任何金额计算）；"
                  f"共 {int(total)} 辆（一车一件 {int(one_item)} / 一车多件 {int(multi_item)}）"),
        )

    return {
        "recommended": recommended,
        "groups": result_groups,
        "fits": result_groups,
        "total_trucks": total,
        "vehicle_breakdowns": vehicle_breakdowns,   # model_id -> {车数,重量,体积,长度,面积,主因,不可分}
        "oversize": oversize,                       # 超限/大件处置依据
        "message": message,
        # ── v011 新增字段 ──────────────────────────────────────────
        "reason": primary_reason,                   # 主组选车理由
        "mixed": plan.mixed,                        # 组内是否多车型（自动路径恒为 False）
        "needs_split": plan.needs_split,            # 互斥/超限：建议拆单而非静默拼车
        "split_hint": plan.split_hint,
        # 🆕 A6：可解体件的拆件建议（顶层：不属于任何一组，也不改配车结果）。
        #   语义提醒：拆件通常不是「避开超限」，而是把三类（15 工作日 + 护送）降到一类（2 工作日）。
        #   未标 divisible 或本就不超限 ⇒ None。
        "divisibility": plan.divisibility,
        "engine": plan.engine,                      # 口径串 fleet_planner@v011
        "category_fallback": plan.category_fallback,
        # ── 🆕 v017 T-2：确认回显（车数三口径与组内行车数同源；plan_confirmed 不参与金额）──
        "confirm": confirm,
        "plan_confirmed": plan_confirmed,           # 顶层回显（与 confirm.plan_confirmed 同值）
    }


@router.get("/reference/cargo-types")
async def list_cargo_types() -> dict:
    return {
        cargo_type: {"rate_multiplier": r.rate_multiplier, "fuel_penalty": r.fuel_penalty}
        for cargo_type, r in CARGO_TYPE_RATES.items()
    }


@router.get("/reference/fuel-price")
async def get_fuel_price() -> dict:
    # TODO: Phase 4 接入 Petrolimex 自动同步，目前是系统默认值
    return {"price_vnd": settings.default_fuel_price_vnd, "source": "manual_default"}


@router.get("/reference/cargo-estimates")
async def get_cargo_estimates(cargo_type: str | None = None) -> dict:
    """返回货物类型进出口费用快速估算（非 HS 码精确查询）。
    
    不传 cargo_type 返回全部货物类型；传入则只返回该类型的估算。
    """
    if cargo_type:
        est = CARGO_IMPORT_EXPORT_ESTIMATES.get(cargo_type)
        if est is None:
            from fastapi import HTTPException
            raise HTTPException(404, f"未知货物类型: {cargo_type}")
        return {
            "cargo_type": cargo_type,
            "export_fee_rmb_per_vehicle": est.export_fee_rmb_per_vehicle,
            "import_fee_rmb_per_vehicle": est.import_fee_rmb_per_vehicle,
            "estimated_duty_rate": est.estimated_duty_rate,
            "estimated_vat_rate": est.estimated_vat_rate,
            "description_zh": est.description_zh,
            "description_vi": est.description_vi,
        }
    return {
        ct: {
            "export_fee_rmb_per_vehicle": est.export_fee_rmb_per_vehicle,
            "import_fee_rmb_per_vehicle": est.import_fee_rmb_per_vehicle,
            "estimated_duty_rate": est.estimated_duty_rate,
            "estimated_vat_rate": est.estimated_vat_rate,
            "description_zh": est.description_zh,
            "description_vi": est.description_vi,
        }
        for ct, est in CARGO_IMPORT_EXPORT_ESTIMATES.items()
    }


# ── 进出口口岸费：预填明细（供前端编辑预置默认值）────────────────
DERIVED_BORDER_ITEMS = {
    "inspection", "heavy_lift", "detention", "port_charge", "trucking_to_site",
    "domestic_transport", "insurance", "import_duty", "vat",
}

BORDER_FEE_NAMES = {
    "customs_declaration": "出口报关", "yard_fee": "货场费", "unloading": "堆场卸货",
    "transloading": "装车费", "domestic_transport": "境内运输",
    "customs_clearance": "报关费", "inspection": "检验费", "detention": "滞箱费",
    "heavy_lift": "吊装费", "port_charge": "港口费", "trucking_to_site": "到货场运输",
    "insurance": "保险费", "import_duty": "进口关税", "vat": "增值税",
}


@router.get("/reference/border-fees")
async def get_border_fees_named(vehicle_count: int = 1, heavy_lift_tons: float = 0.0) -> dict:
    """返回自动口岸费明细（RMB 总额），标注哪些是派生项（按车/吨/柜/天自动）。供定价区预填。"""
    data = await calc_border_fees(vehicle_count=vehicle_count, heavy_lift_tons=heavy_lift_tons)

    def _side(side_key):
        s = data[side_key]
        scaling = VEHICLE_SCALING_ITEMS.get(side_key, set())
        return {
            "items": [
                {"key": k, "name": BORDER_FEE_NAMES.get(k, k),
                 "amount_rmb": v, "derived": k in DERIVED_BORDER_ITEMS,
                 # 🆕 v021：该行是否随「车次」×N（前端据此分组显示「可×车次 / 按量」，
                 #   避免用户以为改车次吊装费也会变）
                 "per_vehicle": k in scaling}
                for k, v in s["items"].items()
            ],
            "subtotal_rmb": s["subtotal_rmb"],
        }

    return {
        "vehicle_count": vehicle_count,
        "china_side": _side("china_side"),
        "vietnam_side": _side("vietnam_side"),
        "total_rmb": data["total_rmb"],
        "total_vnd": data["total_vnd"],
        "exchange_rate": data["exchange_rate"],
    }


@router.post("/reference/border-fees/save")
async def save_border_fees_named(req: BorderFeesSaveRequest) -> dict:
    """把当前口岸费保存为默认（写回 fixed_fees.json，每车固定项折算 per_vehicle）。"""
    from fastapi import HTTPException
    try:
        return save_border_fees_config(
            vehicle_count=req.vehicle_count,
            china_side=req.china_side,
            vietnam_side=req.vietnam_side,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"保存失败：{exc}") from exc


# ── AI 判货推荐车型（真调 DeepSeek，按货物指纹缓存）─────────────
_recommend_cache: dict[str, dict] = {}
_RECOMMEND_TTL = 300  # 5 分钟

CATEGORY_ZH = {
    "small_box": "厢式货车", "flatbed": "平板车", "high_side": "高栏/仓栅车",
    "container": "集装箱车", "cold_chain": "冷藏车",
}


@router.post("/reference/recommend-vehicle")
async def recommend_vehicle(payload: dict) -> dict:
    """根据货物信息（AI 判断）推荐车身类型。

    payload: { items?: [{name,type,length_m,width_m,height_m,weight_kg,count,stackable}],
               weight_kg, volume_m3, cargo_type }
    返回: { ai, preferred_category, reason, categories, model_ids }
      - ai=False: 未配 Key / 调用失败 / 命中缓存降级，前端用 fit-vehicles 物理结果。
    """
    import hashlib
    import json

    items = payload.get("items") or []
    weight_kg = float(payload.get("weight_kg") or 0)
    volume_m3 = float(payload.get("volume_m3") or 0)
    cargo_type = payload.get("cargo_type") or "normal"

    fingerprint = hashlib.sha1(
        json.dumps({"items": items, "w": weight_kg, "v": volume_m3, "t": cargo_type},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    cached = _recommend_cache.get(fingerprint)
    if cached:
        return {**cached, "cache": True}

    result_base = {"ai": False, "preferred_category": None, "reason": "", "categories": []}

    client = AIClient()
    if not client.api_key or not items:
        return result_base

    lines = []
    for it in items:
        lines.append(
            f"- {it.get('name') or '货物'}（{it.get('type') or 'normal'}）："
            f"{float(it.get('weight_kg') or 0)}kg · {float(it.get('length_m') or 0)}x"
            f"{float(it.get('width_m') or 0)}x{float(it.get('height_m') or 0)}m × {it.get('count') or 1}件"
            f"{'（不可堆叠）' if not it.get('stackable', True) else ''}"
        )
    cargo_desc = f"总重 {weight_kg}kg，总体积 {volume_m3}m³，主货型 {cargo_type}\n" + "\n".join(lines)

    system = (
        "你是玖能国际的货运车辆选型专家。根据货物信息判断最适合的车身类型。"
        f"可选车身分类：{', '.join(f'{k}({v})' for k, v in CATEGORY_ZH.items())}。\n"
        "规则参考：超限/大件/重型设备→flatbed 或 high_side；冷链/温控→cold_chain；"
        "危险品→container 或 small_box；普通件杂货→small_box 或 high_side；长件管材→high_side。\n"
        "只返回 JSON：{\"preferred_category\":\"<分类>\",\"reason\":\"<一句话中文理由>\","
        "\"categories\":[\"<首选>\",\"<次选>\"...]}。categories 最多 3 个，首选放第一个。"
    )

    try:
        out = await client.achat_json([{"role": "user", "content": cargo_desc}],
                                      system=system, temperature=0.0, max_tokens=400)
        preferred = str(out.get("preferred_category") or "").strip()
        categories = [c for c in (out.get("categories") or []) if c in CATEGORY_ZH] or ([preferred] if preferred else [])
        if preferred not in categories and preferred:
            categories = [preferred] + categories[:2]
        reason = str(out.get("reason") or "").strip()

        # 由车身分类 → 具体车型候选（首选类别多给几款，其余各 1 款）
        # 按"最大单件重量/长度"过滤，确保候选车装得下（避免单件超载 422）
        max_w = max((float(it.get("weight_kg") or 0) for it in items), default=0) / 1000.0
        max_l = max((float(it.get("length_m") or 0) for it in items), default=0)

        def _fits(m):
            if m.max_load_ton and max_w > m.max_load_ton:
                return False
            if m.length_m and max_l > m.length_m:
                return False
            return True

        model_ids: list[str] = []
        by_cat = models_by_category()
        for cat in categories[:3]:
            models = [m for m in by_cat.get(cat, []) if _fits(m)]
            take = 3 if cat == preferred else 1
            for m in models[:take]:
                if m.model_id not in model_ids:
                    model_ids.append(m.model_id)

        result = {
            "ai": bool(preferred), "preferred_category": preferred,
            "reason": reason, "categories": categories, "model_ids": model_ids,
        }
        _recommend_cache[fingerprint] = result
        return result
    except (AIClientError, ValueError, Exception) as exc:  # noqa: BLE001
        return {**result_base, "reason": f"AI 判断失败：{exc}"}
