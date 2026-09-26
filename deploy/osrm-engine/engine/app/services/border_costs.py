"""边境费用与关税计算引擎 —— DDP 全链路报价 — 中国端/越南端分开。

数据来源：
  - hs_tariff_2026.json：从 HS VN BIEU THUE XNK 2026.xlsx 提取的 12,000 条 HS 税率
  - fixed_fees.json：从回转窑报价单、中冶国贸标书、变压器海运报价 + 市场行情

使用方式：
  from app.services.border_costs import calc_ddp_full, lookup_tariff
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── 数据加载 ──

from app.services._paths import resource_dir  # noqa: E402

_DATA_DIR = resource_dir() / "data"


def _load_json(filename: str) -> dict | list:
    path = _DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _safe_load_json(filename: str, fallback: dict | list) -> dict | list:
    try:
        return _load_json(filename)
    except FileNotFoundError:
        import logging
        logging.getLogger(__name__).warning(f"数据文件不存在: {filename}，使用降级默认值")
        return fallback

_HS_TARIFF: list[dict] = _safe_load_json("hs_tariff_2026.json", [])

# 🆕 v008：内置默认配置 —— 加载 fixed_fees.json 时与它**深度合并**。
# 为什么：旧版/半截的用户配置文件（如 userData 里 8 月的旧 fixed_fees.json，或测试写的最小文件）
# 会让下面的 `cn["unloading_fee_per_vehicle"]` 之类取键抛 KeyError → 整个报价 500。
# 深度合并后：用户改过的值保留，缺的键自动用内置默认补齐。
_FIXED_FEES_DEFAULTS: dict = {
    "china_side": {"customs_declaration_per_vehicle": 1500, "yard_fee_per_vehicle": 300, "unloading_fee_per_vehicle": 800, "transloading_fee_per_vehicle": 1000},
    "vietnam_side": {"customs_clearance_per_vehicle": 2500, "yard_fee_per_vehicle": 800, "inspection_fee_per_container": 370, "detention": {"rate_day1_3_vnd": 3000000, "rate_day4_plus_vnd": 4000000}, "heavy_lift": {"tier_under_5t_per_ton": 500, "tier_5t_20t_per_ton": 800}},
    "container": {}, "breakbulk": {"port_charge_per_ton": 26, "customs_clearance_per_ton": 10},
    "tax_defaults": {"vat_rate_vn": 0.08, "export_tax_rebate_cn_typical": 0.08, "import_duty_fallback_pct": 0.05},
    "exchange_rate": {"vnd_per_rmb": 3500},
    "_updated": "fallback",
}


def _deep_merge(base: dict, override) -> dict:
    """递归合并：override 有的键取 override，缺的键用 base 兜底；子项非 dict 时整体覆盖。"""
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override if override is not None else base
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_FIXED_FEES: dict = _deep_merge(_FIXED_FEES_DEFAULTS, _safe_load_json("fixed_fees.json", {}))

_HS_INDEX: dict[str, dict] = {entry["hs"]: entry for entry in _HS_TARIFF}


# ── 数据结构 ──

@dataclass
class TariffResult:
    hs_code: str
    desc_vn: str
    desc_en: str
    import_duty_rate: float | None
    vat_rate: float
    duty_source: str  # "acfta" | "atiga" | "mfn" | "normal" | "fallback"


@dataclass
class SideBreakdown:
    """单端费用明细"""
    items: dict = field(default_factory=dict)   # {费用名称: 金额(RMB)}
    subtotal: float = 0.0


@dataclass
class DDPResult:
    """DDP 全链路两端分开报价结果"""
    china_side: SideBreakdown
    vietnam_side: SideBreakdown
    china_total: float
    vietnam_total: float
    ddp_total: float


# ── HS 税率查询 ──

def _parse_vat(vat_val) -> float:
    if vat_val is None:
        return _FIXED_FEES["tax_defaults"]["vat_rate_vn"]
    if isinstance(vat_val, (int, float)):
        return float(vat_val) / 100.0 if float(vat_val) > 1 else float(vat_val)
    if isinstance(vat_val, list) and vat_val:
        return min(float(v) for v in vat_val) / 100.0
    return _FIXED_FEES["tax_defaults"]["vat_rate_vn"]


def lookup_tariff(hs_code: str) -> Optional[TariffResult]:
    """根据 HS Code 查询进口关税和增值税税率。

    优先级: ACFTA(中国-东盟) > ATIGA(东盟) > MFN(最惠国) > Normal(普通)
    """
    entry = _HS_INDEX.get(hs_code)
    if entry is None:
        hs6 = hs_code[:6]
        candidates = [e for e in _HS_TARIFF if e["hs"].startswith(hs6)]
        if candidates:
            entry = candidates[0]
        else:
            return None

    duty_rate = None
    duty_source = "fallback"

    for source, val in [
        ("acfta", entry.get("acfta")),
        ("atiga", entry.get("atiga")),
        ("mfn", entry.get("nk_ud")),
        ("normal", entry.get("nk_tt")),
    ]:
        if val is not None and isinstance(val, (int, float)):
            duty_rate = float(val) / 100.0 if float(val) > 1 else float(val)
            duty_source = source
            break

    if duty_rate is None:
        duty_rate = _FIXED_FEES["tax_defaults"]["import_duty_fallback_pct"]
        duty_source = "fallback"

    vat_rate = _parse_vat(entry.get("vat"))

    return TariffResult(
        hs_code=hs_code,
        desc_vn=entry.get("desc_vn", ""),
        desc_en=entry.get("desc_en", ""),
        import_duty_rate=duty_rate,
        vat_rate=vat_rate,
        duty_source=duty_source,
    )


# ── 中国端费用计算 ──

def calc_china_side(
    vehicle_count: int = 1,
    domestic_transport_rmb: float = 0.0,
    cargo_value_rmb: float = 0.0,
    include_rebate: bool = False,
) -> SideBreakdown:
    """计算中国端全部费用。

    Args:
        vehicle_count: 车辆数
        domestic_transport_rmb: 中国境内运输费（用户输入或按距离估算）
        cargo_value_rmb: 货值（用于出口退税）
        include_rebate: 是否包含出口退税估算
    """
    cn = _FIXED_FEES["china_side"]
    items = {
        "customs_declaration": cn["customs_declaration_per_vehicle"] * vehicle_count,
        "yard_fee": cn["yard_fee_per_vehicle"] * vehicle_count,
        "unloading": cn["unloading_fee_per_vehicle"] * vehicle_count,
        "transloading": cn["transloading_fee_per_vehicle"] * vehicle_count,
    }
    if domestic_transport_rmb > 0:
        items["domestic_transport"] = round(domestic_transport_rmb, 2)
    if include_rebate and cargo_value_rmb > 0:
        rebate = cargo_value_rmb * _FIXED_FEES["tax_defaults"]["export_tax_rebate_cn_typical"]
        items["export_tax_rebate"] = -round(rebate, 2)

    subtotal = sum(items.values())
    return SideBreakdown(items=items, subtotal=round(subtotal, 2))


# ── 越南端费用计算 ──

def calc_vietnam_side(
    *,
    vehicle_count: int = 1,
    container_count: int = 0,
    container_type: str | None = None,
    is_breakbulk: bool = False,
    breakbulk_tons: float = 0.0,
    cargo_value_rmb: float = 0.0,
    hs_code: str = "",
    transport_cost_vnd: float = 0.0,
    detention_days: int = 0,
    heavy_lift_tons: float = 0.0,
) -> SideBreakdown:
    """计算越南端全部费用（不含运输费时可用 transport_cost_vnd=0）。

    Args:
        vehicle_count: 车辆数
        container_count: 集装箱数（海运）
        container_type: 柜型 (20gp/40gp_hq/40ot/40fr)
        is_breakbulk: 是否件杂货
        breakbulk_tons: 件杂货计费吨
        cargo_value_rmb: 货值(RMB)
        hs_code: HS编码
        transport_cost_vnd: 越南境内运输费(VND) — 由 OSRM++ 计算后传入
        detention_days: 滞留天数（0=无滞留）
        heavy_lift_tons: 需要吊装的货物吨数
    """
    vn = _FIXED_FEES["vietnam_side"]
    exchange = _FIXED_FEES["exchange_rate"]["vnd_per_rmb"]

    items = {
        "customs_clearance": vn["customs_clearance_per_vehicle"] * vehicle_count,
        "yard_fee": vn["yard_fee_per_vehicle"] * vehicle_count,
    }

    # 查验费（仅海运集装箱）
    if container_count > 0:
        items["inspection"] = vn["inspection_fee_per_container"] * container_count

    # 越南境内运输费（OSRM++ 结果）
    if transport_cost_vnd > 0:
        items["domestic_transport"] = round(transport_cost_vnd / exchange, 2)

    # 保险费
    if cargo_value_rmb > 0:
        items["insurance"] = round(cargo_value_rmb * 0.003, 2)

    # 进口关税 + 增值税
    if cargo_value_rmb > 0 and hs_code:
        tariff = lookup_tariff(hs_code)
        duty_rate = tariff.import_duty_rate if tariff else _FIXED_FEES["tax_defaults"]["import_duty_fallback_pct"]
        vat_rate = tariff.vat_rate if tariff else _FIXED_FEES["tax_defaults"]["vat_rate_vn"]
        import_duty = cargo_value_rmb * (duty_rate or 0.05)
        vat = (cargo_value_rmb + import_duty) * vat_rate
        items["import_duty"] = round(import_duty, 2)
        items["vat"] = round(vat, 2)

    # 车辆滞留费
    if detention_days > 0:
        det = vn["detention"]
        rate = det["rate_day1_3_vnd"] if detention_days <= 3 else det["rate_day4_plus_vnd"]
        items["detention"] = round(rate * detention_days / exchange, 2)

    # 吊装费（大件/超重）—— >20t 用 tier_over_20t_per_ton（自动出价），无则落 None
    if heavy_lift_tons > 0:
        hl = vn["heavy_lift"]
        if heavy_lift_tons < 5:
            rate = hl["tier_under_5t_per_ton"]
        elif heavy_lift_tons <= 20:
            rate = hl["tier_5t_20t_per_ton"]
        else:
            rate = hl.get("tier_over_20t_per_ton")  # 🆕 大件：>20t 档（如 1000/吨）
        if rate:
            items["heavy_lift"] = round(rate * heavy_lift_tons, 2)

    # 集装箱港口费
    if container_count > 0 and container_type:
        ct = _FIXED_FEES["container"].get(container_type, {})
        if ct:
            items["port_charge"] = ct.get("port_charge", 0) * container_count
            items["trucking_to_site"] = ct.get("trucking_to_site", 0) * container_count

    # 件杂货港口费
    if is_breakbulk and breakbulk_tons > 0:
        bb = _FIXED_FEES["breakbulk"]
        items["breakbulk_port"] = round(
            (bb["port_charge_per_ton"] + bb["customs_clearance_per_ton"]) * breakbulk_tons, 2
        )

    subtotal = sum(items.values())
    return SideBreakdown(items=items, subtotal=round(subtotal, 2))


# ── 纯口岸费用（不含税）—— 两端分开 ──

def calc_fees_china_side(vehicle_count: int = 1, domestic_transport_rmb: float = 0.0) -> SideBreakdown:
    """中国端纯口岸费用（不含出口退税）"""
    cn = _FIXED_FEES["china_side"]
    items = {
        "customs_declaration": cn["customs_declaration_per_vehicle"] * vehicle_count,
        "yard_fee": cn["yard_fee_per_vehicle"] * vehicle_count,
        "unloading": cn["unloading_fee_per_vehicle"] * vehicle_count,
        "transloading": cn["transloading_fee_per_vehicle"] * vehicle_count,
    }
    if domestic_transport_rmb > 0:
        items["domestic_transport"] = round(domestic_transport_rmb, 2)
    subtotal = sum(items.values())
    return SideBreakdown(items=items, subtotal=round(subtotal, 2))


def calc_fees_vietnam_side(
    *,
    vehicle_count: int = 1,
    container_count: int = 0,
    container_type: str | None = None,
    detention_days: int = 0,
    heavy_lift_tons: float = 0.0,
) -> SideBreakdown:
    """越南端纯口岸费用（不含关税/增值税/保险/运输费）"""
    vn = _FIXED_FEES["vietnam_side"]
    exchange = _FIXED_FEES["exchange_rate"]["vnd_per_rmb"]

    items = {
        "customs_clearance": vn["customs_clearance_per_vehicle"] * vehicle_count,
        "yard_fee": vn["yard_fee_per_vehicle"] * vehicle_count,
    }

    if container_count > 0:
        items["inspection"] = vn["inspection_fee_per_container"] * container_count

    if detention_days > 0:
        det = vn["detention"]
        rate = det["rate_day1_3_vnd"] if detention_days <= 3 else det["rate_day4_plus_vnd"]
        items["detention"] = round(rate * detention_days / exchange, 2)

    if heavy_lift_tons > 0:
        hl = vn["heavy_lift"]
        if heavy_lift_tons < 5:
            rate = hl["tier_under_5t_per_ton"]
        elif heavy_lift_tons <= 20:
            rate = hl["tier_5t_20t_per_ton"]
        else:
            rate = hl.get("tier_over_20t_per_ton")
        if rate:
            items["heavy_lift"] = round(rate * heavy_lift_tons, 2)

    if container_count > 0 and container_type:
        ct = _FIXED_FEES["container"].get(container_type, {})
        if ct:
            items["port_charge"] = ct.get("port_charge", 0) * container_count
            items["trucking_to_site"] = ct.get("trucking_to_site", 0) * container_count

    subtotal = sum(items.values())
    return SideBreakdown(items=items, subtotal=round(subtotal, 2))


def calc_ddp_fees_only(
    *,
    vehicle_count: int = 1,
    domestic_transport_rmb: float = 0.0,
    container_count: int = 0,
    container_type: str | None = None,
    detention_days: int = 0,
    heavy_lift_tons: float = 0.0,
) -> DDPResult:
    """🆕 纯口岸费用 DDP 报价 — 不含关税/增值税/出口退税。

    这是前端 DDP 模式的主入口，只算两端的口岸操作费用。
    """
    china = calc_fees_china_side(
        vehicle_count=vehicle_count,
        domestic_transport_rmb=domestic_transport_rmb,
    )
    vietnam = calc_fees_vietnam_side(
        vehicle_count=vehicle_count,
        container_count=container_count,
        container_type=container_type,
        detention_days=detention_days,
        heavy_lift_tons=heavy_lift_tons,
    )
    return DDPResult(
        china_side=china,
        vietnam_side=vietnam,
        china_total=china.subtotal,
        vietnam_total=vietnam.subtotal,
        ddp_total=round(china.subtotal + vietnam.subtotal, 2),
    )

def calc_ddp_full(
    *,
    vehicle_count: int = 1,
    domestic_transport_rmb: float = 0.0,
    cargo_value_rmb: float = 0.0,
    hs_code: str = "",
    transport_cost_vnd: float = 0.0,
    container_count: int = 0,
    container_type: str | None = None,
    is_breakbulk: bool = False,
    breakbulk_tons: float = 0.0,
    detention_days: int = 0,
    heavy_lift_tons: float = 0.0,
    include_export_rebate: bool = False,
) -> DDPResult:
    """一站式计算 DDP 全链路报价 — 中国端+越南端分开。

    Args:
        vehicle_count: 车辆数
        domestic_transport_rmb: 中国境内运输费(RMB)
        cargo_value_rmb: 货值(RMB)
        hs_code: HS编码
        transport_cost_vnd: 越南境内运输费(VND) — 由 OSRM++ 计算
        container_count: 集装箱数
        container_type: 柜型
        is_breakbulk: 是否件杂货
        breakbulk_tons: 件杂货计费吨
        detention_days: 滞留天数
        heavy_lift_tons: 吊装吨数
        include_export_rebate: 是否包含出口退税
    """
    china = calc_china_side(
        vehicle_count=vehicle_count,
        domestic_transport_rmb=domestic_transport_rmb,
        cargo_value_rmb=cargo_value_rmb,
        include_rebate=include_export_rebate,
    )

    vietnam = calc_vietnam_side(
        vehicle_count=vehicle_count,
        container_count=container_count,
        container_type=container_type,
        is_breakbulk=is_breakbulk,
        breakbulk_tons=breakbulk_tons,
        cargo_value_rmb=cargo_value_rmb,
        hs_code=hs_code,
        transport_cost_vnd=transport_cost_vnd,
        detention_days=detention_days,
        heavy_lift_tons=heavy_lift_tons,
    )

    ddp_total = china.subtotal + vietnam.subtotal

    return DDPResult(
        china_side=china,
        vietnam_side=vietnam,
        china_total=china.subtotal,
        vietnam_total=vietnam.subtotal,
        ddp_total=round(ddp_total, 2),
    )


# ── 向后兼容的旧接口 ──

@dataclass
class BorderCostBreakdown:
    """旧版接口，保留兼容"""
    china_export: dict
    border_crossing: dict
    vietnam_import: dict
    import_duty: float
    vat: float
    total: float


def calc_china_export_fees(vehicle_count: int = 1) -> dict:
    """旧接口：中国段出口费用"""
    cn = _FIXED_FEES["china_side"]
    items = {
        "customs_declaration": cn["customs_declaration_per_vehicle"] * vehicle_count,
        "yard_fee": cn["yard_fee_per_vehicle"] * vehicle_count,
        "unloading": cn["unloading_fee_per_vehicle"] * vehicle_count,
    }
    items["total"] = sum(items.values())
    return items


def calc_border_fees(vehicle_count: int = 1) -> dict:
    """旧接口：口岸过境费用"""
    cn = _FIXED_FEES["china_side"]
    total = cn["transloading_fee_per_vehicle"] * vehicle_count
    return {"transloading": total, "total": total}


def calc_vietnam_import_fees(vehicle_count: int = 1, container_count: int = 0) -> dict:
    """旧接口：越南段进口清关费用"""
    vn = _FIXED_FEES["vietnam_side"]
    items = {
        "customs_clearance": vn["customs_clearance_per_vehicle"] * vehicle_count,
        "yard_fee": vn["yard_fee_per_vehicle"] * vehicle_count,
    }
    if container_count > 0:
        items["inspection"] = vn["inspection_fee_per_container"] * container_count
    items["total"] = sum(items.values())
    return items


def calc_import_duty_and_vat(
    cargo_value_rmb: float,
    hs_code: str,
    exchange_rate_vnd_to_rmb: float = 3786.0,
) -> dict:
    """计算进口关税和增值税。"""
    tariff = lookup_tariff(hs_code)

    if tariff is None:
        duty_rate = _FIXED_FEES["tax_defaults"]["import_duty_fallback_pct"]
        vat_rate = _FIXED_FEES["tax_defaults"]["vat_rate_vn"]
        duty_source = "fallback"
    else:
        duty_rate = tariff.import_duty_rate or _FIXED_FEES["tax_defaults"]["import_duty_fallback_pct"]
        vat_rate = tariff.vat_rate
        duty_source = tariff.duty_source

    import_duty = cargo_value_rmb * duty_rate
    vat = (cargo_value_rmb + import_duty) * vat_rate

    return {
        "cargo_value_rmb": cargo_value_rmb,
        "hs_code": hs_code,
        "duty_rate": duty_rate,
        "duty_source": duty_source,
        "vat_rate": vat_rate,
        "import_duty_rmb": round(import_duty, 2),
        "vat_rmb": round(vat, 2),
        "total_tax_rmb": round(import_duty + vat, 2),
        "tariff_desc": f"{tariff.desc_en} | {tariff.desc_vn}" if tariff else "未查到该HS编码",
    }


def calc_export_tax_rebate(cargo_value_rmb: float, rebate_rate: float = None) -> dict:
    """中国出口退税估算"""
    if rebate_rate is None:
        rebate_rate = _FIXED_FEES["tax_defaults"]["export_tax_rebate_cn_typical"]
    rebate = cargo_value_rmb * rebate_rate
    return {"rebate_rate": rebate_rate, "rebate_rmb": round(rebate, 2)}


def calc_ddp_border_costs(
    *,
    vehicle_count: int = 1,
    container_count: int = 0,
    container_type: str | None = None,
    cargo_value_rmb: float = 0.0,
    hs_code: str = "",
    is_breakbulk: bool = False,
    breakbulk_tons: float = 0.0,
) -> BorderCostBreakdown:
    """旧接口：保持向后兼容"""
    china = calc_china_export_fees(vehicle_count)
    border = calc_border_fees(vehicle_count)
    vn_import = calc_vietnam_import_fees(vehicle_count, container_count)
    tax = calc_import_duty_and_vat(cargo_value_rmb, hs_code)

    container_fees = {}
    if container_count > 0 and container_type:
        ct = _FIXED_FEES["container"].get(container_type, {})
        if ct:
            container_fees = {
                "port_charge": ct["port_charge"] * container_count,
                "customs": ct["customs_clearance"] * container_count,
                "inspection": ct["inspection"] * container_count,
                "trucking": ct["trucking_to_site"] * container_count,
            }

    breakbulk_fees = {}
    if is_breakbulk and breakbulk_tons > 0:
        bb = _FIXED_FEES["breakbulk"]
        breakbulk_fees = {
            "port_charge": bb["port_charge_per_ton"] * breakbulk_tons,
            "customs": bb["customs_clearance_per_ton"] * breakbulk_tons,
        }

    all_items = {**china, **border, **vn_import, **container_fees, **breakbulk_fees}
    total_border = sum(all_items.values()) + tax["total_tax_rmb"]

    return BorderCostBreakdown(
        china_export=china,
        border_crossing=border,
        vietnam_import={**vn_import, **container_fees} if container_fees else vn_import,
        import_duty=tax["import_duty_rmb"],
        vat=tax["vat_rmb"],
        total=round(total_border, 2),
    )


# ── 搜索辅助 ──

def search_hs(keyword: str, limit: int = 20) -> list[dict]:
    """搜索 HS 编码（支持中英文关键词）。"""
    kw = keyword.lower()
    results = []
    for entry in _HS_TARIFF:
        if kw in entry["desc_en"].lower() or kw in entry["desc_vn"].lower():
            results.append({
                "hs": entry["hs"],
                "desc_vn": entry["desc_vn"],
                "desc_en": entry["desc_en"],
                "acfta": entry.get("acfta"),
                "vat": _parse_vat(entry.get("vat")),
            })
            if len(results) >= limit:
                break
    return results
