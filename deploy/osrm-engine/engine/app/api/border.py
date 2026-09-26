"""边境费用与关税 API — 新增中国端/越南端分开报价端点"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.services.border_costs import (
    calc_china_export_fees,
    calc_border_fees,
    calc_vietnam_import_fees,
    calc_import_duty_and_vat,
    calc_export_tax_rebate,
    calc_ddp_border_costs,
    calc_ddp_full,
    calc_ddp_fees_only,
    calc_china_side,
    calc_vietnam_side,
    lookup_tariff,
    search_hs,
)
from app.services.exchange_rate import get_exchange_rate, force_refresh
from app.services._paths import resource_dir

router = APIRouter()

# 汇率数据（模块级加载）
_DATA_DIR = resource_dir() / "data"
with open(_DATA_DIR / "fixed_fees.json", encoding="utf-8") as _f:
    _FIXED_FEES = json.load(_f)


# ── 旧端点（保持向后兼容） ──

@router.get("/border/hs-lookup")
async def hs_lookup(hs_code: str = Query(..., min_length=4, max_length=10)):
    """查询 HS 编码的进口关税和增值税税率"""
    result = lookup_tariff(hs_code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到 HS 编码: {hs_code}")
    return {
        "hs_code": result.hs_code,
        "desc_vn": result.desc_vn,
        "desc_en": result.desc_en,
        "import_duty_rate": result.import_duty_rate,
        "vat_rate": result.vat_rate,
        "duty_source": result.duty_source,
    }


@router.get("/border/hs-search")
async def hs_search(q: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=100)):
    """搜索 HS 编码（支持中英文关键词）"""
    return search_hs(q, limit=limit)


@router.post("/border/import-tax")
async def calc_tax(
    cargo_value_rmb: float = Query(..., gt=0),
    hs_code: str = Query(..., min_length=4),
):
    """计算进口关税 + 增值税"""
    return calc_import_duty_and_vat(cargo_value_rmb, hs_code)


@router.get("/border/export-rebate")
async def export_rebate(
    cargo_value_rmb: float = Query(..., gt=0),
    rebate_rate: float | None = None,
):
    """中国出口退税估算"""
    return calc_export_tax_rebate(cargo_value_rmb, rebate_rate)


@router.get("/border/ddp-costs")
async def ddp_costs(
    vehicle_count: int = Query(1, ge=1),
    container_count: int = Query(0, ge=0),
    container_type: str | None = Query(None),
    cargo_value_rmb: float = Query(0.0, ge=0),
    hs_code: str = Query(""),
    is_breakbulk: bool = Query(False),
    breakbulk_tons: float = Query(0.0, ge=0),
) -> dict:
    """旧端点：一站式计算 DDP 全链路非运输费用（保持兼容）"""
    result = calc_ddp_border_costs(
        vehicle_count=vehicle_count,
        container_count=container_count,
        container_type=container_type,
        cargo_value_rmb=cargo_value_rmb,
        hs_code=hs_code,
        is_breakbulk=is_breakbulk,
        breakbulk_tons=breakbulk_tons,
    )
    return {
        "china_export": result.china_export,
        "border_crossing": result.border_crossing,
        "vietnam_import": result.vietnam_import,
        "import_duty_rmb": result.import_duty,
        "vat_rmb": result.vat,
        "total_rmb": result.total,
    }


# ── 🆕 纯口岸费用（不含税） —— 前端 DDP 模式主入口 ──

@router.get("/border/fees-only")
async def fees_only(
    vehicle_count: int = Query(1, ge=1),
    domestic_transport_rmb: float = Query(0.0, ge=0),
    container_count: int = Query(0, ge=0),
    container_type: str | None = Query(None),
    detention_days: int = Query(0, ge=0),
    heavy_lift_tons: float = Query(0.0, ge=0),
) -> dict:
    """纯口岸费用报价 — 中国端+越南端，不含关税/增值税/出口退税。

    只需传车辆数，立即返回两端费用。不需要货值或HS编码。
    """
    result = calc_ddp_fees_only(
        vehicle_count=vehicle_count,
        domestic_transport_rmb=domestic_transport_rmb,
        container_count=container_count,
        container_type=container_type,
        detention_days=detention_days,
        heavy_lift_tons=heavy_lift_tons,
    )
    return {
        "china_side": {
            "items": result.china_side.items,
            "subtotal": result.china_side.subtotal,
        },
        "vietnam_side": {
            "items": result.vietnam_side.items,
            "subtotal": result.vietnam_side.subtotal,
        },
        "china_total": result.china_total,
        "vietnam_total": result.vietnam_total,
        "ddp_total": result.ddp_total,
    }


# ── 中国端/越南端单独查询（用于调试或前端分段加载） ──

@router.get("/border/china-side")
async def china_side_only(
    vehicle_count: int = Query(1, ge=1),
    domestic_transport_rmb: float = Query(0.0, ge=0),
    cargo_value_rmb: float = Query(0.0, ge=0),
    include_rebate: bool = Query(False),
) -> dict:
    """仅计算中国端费用"""
    result = calc_china_side(
        vehicle_count=vehicle_count,
        domestic_transport_rmb=domestic_transport_rmb,
        cargo_value_rmb=cargo_value_rmb,
        include_rebate=include_rebate,
    )
    return {"items": result.items, "subtotal": result.subtotal}


@router.get("/border/vietnam-side")
async def vietnam_side_only(
    vehicle_count: int = Query(1, ge=1),
    container_count: int = Query(0, ge=0),
    container_type: str | None = Query(None),
    is_breakbulk: bool = Query(False),
    breakbulk_tons: float = Query(0.0, ge=0),
    cargo_value_rmb: float = Query(0.0, ge=0),
    hs_code: str = Query(""),
    transport_cost_vnd: float = Query(0.0, ge=0),
    detention_days: int = Query(0, ge=0),
    heavy_lift_tons: float = Query(0.0, ge=0),
) -> dict:
    """仅计算越南端费用"""
    result = calc_vietnam_side(
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
    return {"items": result.items, "subtotal": result.subtotal}


@router.get("/border/reference-fees")
async def reference_fees():
    """获取当前所有固定费用参数表"""
    import json
    from pathlib import Path
    _DATA_DIR = resource_dir() / "data"
    with open(_DATA_DIR / "fixed_fees.json", encoding="utf-8") as f:
        return json.load(f)


@router.get("/reference/exchange-rate")
async def exchange_rate():
    """获取 VND↔RMB 实时汇率（优先缓存，每小时自动刷新）"""
    return await get_exchange_rate()


@router.post("/reference/exchange-rate/refresh")
async def exchange_rate_refresh():
    """手动刷新汇率缓存（从外部 API 强制拉取）"""
    return await force_refresh()
