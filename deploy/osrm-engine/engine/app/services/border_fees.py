"""进出口口岸费（中国段 + 越南段）计算 —— 单列、可切 RMB/VND。

复用 border_costs.calc_fees_china_side / calc_fees_vietnam_side（RMB），
并按当日汇率（exchange_rate.get_exchange_rate）折算 VND。
"""
from app.services.border_costs import calc_fees_china_side, calc_fees_vietnam_side
from app.services.exchange_rate import get_exchange_rate


async def calc_border_fees(
    *,
    vehicle_count: int = 1,
    heavy_lift_tons: float = 0.0,
    inspection: bool = False,
    detention_days: int = 0,
    container_type: str | None = None,
) -> dict:
    """算中越进出口口岸费。

    返回: {
        china_side:   {items: {费用名: RMB}, subtotal_rmb},
        vietnam_side: {items: {费用名: RMB}, subtotal_rmb},
        total_rmb:    合计(RMB),
        total_vnd:    按当日汇率折算 VND,
        exchange_rate: 当日 vnd_per_rmb（失败回退 3500）,
    }
    """
    cn = calc_fees_china_side(vehicle_count=vehicle_count)
    vn = calc_fees_vietnam_side(
        vehicle_count=vehicle_count,
        container_count=1 if inspection else 0,
        container_type=container_type,
        detention_days=detention_days,
        heavy_lift_tons=heavy_lift_tons,
    )
    total_rmb = round(cn.subtotal + vn.subtotal, 2)

    rate = None
    try:
        rate = (await get_exchange_rate()).get("vnd_per_rmb")
    except Exception:
        rate = None
    if not rate:
        rate = 3500.0  # 回退默认
    total_vnd = round(total_rmb * rate)

    return {
        "china_side": {"items": cn.items, "subtotal_rmb": round(cn.subtotal, 2)},
        "vietnam_side": {"items": vn.items, "subtotal_rmb": round(vn.subtotal, 2)},
        "total_rmb": total_rmb,
        "total_vnd": total_vnd,
        "exchange_rate": rate,
    }


async def build_manual_border_fees(total_rmb: float) -> dict:
    """🆕 手动设定进出口费（总金额 RMB）：单行结构（manual=True）+ 当日汇率折算 VND。

    保留为兼容；新版前端改用 border_fees_override 逐项覆盖（见 apply_border_fees_override）。
    """
    total_rmb = round(float(total_rmb), 2)

    rate = None
    try:
        rate = (await get_exchange_rate()).get("vnd_per_rmb")
    except Exception:
        rate = None
    if not rate:
        rate = 3500.0  # 回退默认
    total_vnd = round(total_rmb * rate)

    return {
        "china_side": {"items": {}, "subtotal_rmb": 0.0},
        "vietnam_side": {"items": {}, "subtotal_rmb": 0.0},
        "total_rmb": total_rmb,
        "total_vnd": total_vnd,
        "exchange_rate": rate,
        "manual": True,
        "manual_total_rmb": total_rmb,
    }


# 每车固定费项（可保存为默认；除以 vehicle_count 得 per_vehicle 费率）
VEHICLE_SCALING_ITEMS = {
    "china_side": {"customs_declaration", "yard_fee", "unloading", "transloading"},
    "vietnam_side": {"customs_clearance", "yard_fee"},
}


def apply_border_fees_override(base: dict, override) -> dict:
    """把逐项覆盖合并进自动算好的 base（RMB 总额），重算小计/合计/VND。

    base 来自 calc_border_fees() 的 dict。override 为 BorderFeesOverride（或同构 dict）。
    只覆盖传了的项；每车固定项、派生项未传则保持自动值。返回新的 base。
    """
    if not override:
        return base
    total_rmb = 0.0
    for side_key in ("china_side", "vietnam_side"):
        side = dict(base.get(side_key, {"items": {}, "subtotal_rmb": 0.0}))
        items = dict(side.get("items", {}))
        if hasattr(override, side_key):                      # pydantic 对象 / 测试对象
            side_ov = getattr(override, side_key) or {}
        elif isinstance(override, dict):                     # 纯 dict
            side_ov = override.get(side_key) or {}
        else:
            side_ov = {}
        for k, v in side_ov.items():
            if v is not None:
                items[k] = round(float(v), 2)
        subtotal = round(sum(items.values()), 2)
        base[side_key] = {"items": items, "subtotal_rmb": subtotal}
        total_rmb += subtotal
    base["total_rmb"] = round(total_rmb, 2)
    rate = base.get("exchange_rate") or 3500
    base["total_vnd"] = round(base["total_rmb"] * rate)
    base["manual"] = True
    base["manual_total_rmb"] = base["total_rmb"]
    return base


def save_border_fees_config(*, vehicle_count: int, china_side: dict, vietnam_side: dict) -> dict:
    """把当前口岸费保存为默认（写回 fixed_fees.json）。

    只写每车固定费项（VEHICLE_SCALING_ITEMS），按 vehicle_count 折算 per_vehicle 费率；
    派生项（吊装/滞箱/检验/港口费）不写入，避免污染公司默认。返回更新后的配置。
    """
    import json
    from datetime import date

    from app.services import border_costs

    path = border_costs._DATA_DIR / "fixed_fees.json"
    vc = max(1, int(vehicle_count or 1))
    if path.exists():
        fe = json.loads(path.read_text(encoding="utf-8"))
    else:
        fe = {}

    for side_key, keys in VEHICLE_SCALING_ITEMS.items():
        side = fe.setdefault(side_key, {})
        provided = china_side if side_key == "china_side" else vietnam_side
        for k in keys:
            if k in provided and provided[k] is not None:
                side[f"{k}_per_vehicle"] = round(float(provided[k]) / vc, 2)

    fe["_updated"] = date.today().isoformat()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fe, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同步内存态（border_costs._FIXED_FEES 是模块级缓存，保存后立即生效）
    try:
        border_costs._FIXED_FEES = fe
    except Exception:
        pass
    return {"saved": True, "updated": fe.get("_updated"), "file": str(path)}
