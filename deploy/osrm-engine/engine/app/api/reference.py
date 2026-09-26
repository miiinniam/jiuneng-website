from fastapi import APIRouter

from app.config import settings
from app.services.exchange_rate import force_refresh, get_exchange_rate
from app.services.presets import CARGO_IMPORT_EXPORT_ESTIMATES, CARGO_TYPE_RATES
from app.services.vehicle_registry import models_by_category, get_model, VEHICLE_MODELS, VehicleModel
from app.services import 费用计算公式 as 公式
from app.services.border_fees import calc_border_fees, save_border_fees_config
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
        items?: [{name?, length_m, width_m, height_m?, weight_kg, count, stackable}] }
    返回:
      { recommended, groups: [{model_id, display_name, category, max_load_ton,
                               vehicle_count, reason, items:[...]}],
        fits, total_trucks, vehicle_breakdowns, oversize, message,
        # ── v011 新增（前端⑥口径卡 / INV-1 追溯）──
        reason, mixed, needs_split, split_hint, engine, category_fallback }
    """
    from app.services import fleet_planner as pl

    items = payload.get("items") or []
    plan = pl.plan_fleet(
        items=items,
        total_weight_kg=payload.get("weight_kg"),
        total_volume_m3=payload.get("volume_m3"),
        cargo_type=payload.get("cargo_type") or "normal",
        models=VEHICLE_MODELS,
        distance_km=payload.get("distance_km"),
    )

    def _group_out(g) -> dict:
        """分组响应组装：车型属性一次查表，避免在推导式里重复调 get_model()。"""
        m = get_model(g.model_id)
        return {
            "model_id": g.model_id,
            "display_name": m.display_name if m else g.model_id,
            "category": m.category if m else "",
            "max_load_ton": m.max_load_ton if m else 0.0,
            "vehicle_count": g.vehicle_count,
            "reason": g.reason,          # v011：选车理由（前端车队行⑥直接显示）
            "items": g.items,
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
        "engine": plan.engine,                      # 口径串 fleet_planner@v011
        "category_fallback": plan.category_fallback,
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

    def _side(s):
        return {
            "items": [
                {"key": k, "name": BORDER_FEE_NAMES.get(k, k),
                 "amount_rmb": v, "derived": k in DERIVED_BORDER_ITEMS}
                for k, v in s["items"].items()
            ],
            "subtotal_rmb": s["subtotal_rmb"],
        }

    return {
        "vehicle_count": vehicle_count,
        "china_side": _side(data["china_side"]),
        "vietnam_side": _side(data["vietnam_side"]),
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
