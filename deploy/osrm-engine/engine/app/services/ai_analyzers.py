"""
AI 分析器
=========

基于 DeepSeek V4 Flash 的高层分析函数，每个函数完成一个完整的分析任务。

使用方式:
    from app.services.ai_analyzers import analyze_price_deviations
    result = await analyze_price_deviations(predictions, vehicle_models)
"""

import csv
import io
from typing import Any

from app.config import settings
from app.services.ai_client import AIClient, get_ai_client
from app.services.ai_prompts import (
    FORMULA_OPTIMIZATION_SYSTEM,
    PRICE_DEVIATION_SYSTEM,
    QUOTE_EXTRACTION_SYSTEM,
    ROUTE_FEATURE_SYSTEM,
    build_formula_optimization_prompt,
    build_price_deviation_prompt,
    build_quote_extraction_prompt,
    build_route_feature_prompt,
)
from app.services.vehicle_registry import VEHICLE_MODELS, VehicleModel


def _load_vehicle_models_for_ai() -> dict[str, dict]:
    """加载车型参数供 AI 分析使用。"""
    return {
        m.model_id: {
            "display_name": m.display_name,
            "category": m.category,
            "max_load_ton": m.max_load_ton,
            "base_rate_vnd_per_km": m.base_rate_vnd_per_km,
            "fixed_surcharge_vnd": m.fixed_surcharge_vnd,
            "fuel_l_per_100km": m.fuel_l_per_100km,
        }
        for m in VEHICLE_MODELS
    }


# ══════════════════════════════════════════════════════════════
# 1. 价格偏差分析
# ══════════════════════════════════════════════════════════════

async def analyze_price_deviations(
    predictions: list[dict],
    vehicle_models: dict[str, dict] | None = None,
    context: str = "",
    client: AIClient | None = None,
) -> dict[str, Any]:
    """分析预测偏差，返回结构化的分析结果。

    predictions 格式:
        [{"vehicle_model_id": "flatbed_12m5", "dest": "Hai Phong",
          "distance_km": 170, "actual_vnd": 11000000,
          "predicted_vnd": 7954000, "error_pct": -27.7}, ...]
    """
    if client is None:
        client = get_ai_client()
    if vehicle_models is None:
        vehicle_models = _load_vehicle_models_for_ai()

    prompt = build_price_deviation_prompt(predictions, vehicle_models, context)
    result = await client.achat_json(
        messages=[{"role": "user", "content": prompt}],
        system=PRICE_DEVIATION_SYSTEM,
        max_tokens=4096,
    )
    return result


# ══════════════════════════════════════════════════════════════
# 2. 路线特征识别
# ══════════════════════════════════════════════════════════════

async def classify_route_features(
    destinations: list[str],
    client: AIClient | None = None,
) -> dict[str, Any]:
    """根据目的地地址自动识别港口/边境/山区等路线特征。

    用于批量导入时自动标记 via_port / via_mountain_road 等字段。
    """
    if client is None:
        client = get_ai_client()

    prompt = build_route_feature_prompt(destinations)
    result = await client.achat_json(
        messages=[{"role": "user", "content": prompt}],
        system=ROUTE_FEATURE_SYSTEM,
    )
    return result


# ══════════════════════════════════════════════════════════════
# 3. 供应商报价智能提取
# ══════════════════════════════════════════════════════════════

async def extract_quote_from_text(
    raw_text: str,
    client: AIClient | None = None,
) -> dict[str, Any]:
    """从非结构化的报价文本中智能提取报价数据。

    支持: Excel/PDF 文本提取、OCR 结果、聊天记录、邮件正文等。
    """
    if client is None:
        client = get_ai_client()

    prompt = build_quote_extraction_prompt(raw_text)
    result = await client.achat_json(
        messages=[{"role": "user", "content": prompt}],
        system=QUOTE_EXTRACTION_SYSTEM,
        max_tokens=8192,
    )
    return result


# ══════════════════════════════════════════════════════════════
# 4. 公式优化建议
# ══════════════════════════════════════════════════════════════

async def suggest_formula_optimizations(
    current_params: dict | None = None,
    error_analysis: dict | None = None,
    client: AIClient | None = None,
) -> dict[str, Any]:
    """基于当前参数和误差分析，给出公式优化建议。"""
    if client is None:
        client = get_ai_client()
    if current_params is None:
        current_params = _load_vehicle_models_for_ai()

    prompt = build_formula_optimization_prompt(
        current_params, error_analysis or {}
    )
    result = await client.achat_json(
        messages=[{"role": "user", "content": prompt}],
        system=FORMULA_OPTIMIZATION_SYSTEM,
        max_tokens=4096,
    )
    return result


# ══════════════════════════════════════════════════════════════
# 5. 校准报告 AI 评审（一站式：偏差分析 + 路线特征 + 优化建议）
# ══════════════════════════════════════════════════════════════

async def ai_review_calibration(
    predictions: list[dict],
    unique_destinations: list[str] | None = None,
    context: str = "",
    client: AIClient | None = None,
) -> dict[str, Any]:
    """一站式校准评审：偏差分析 + 路线特征识别 + 公式优化建议。

    这是最常用的入口——把校准结果扔进来，AI 给出完整的分析报告。
    """
    if client is None:
        client = get_ai_client()

    vehicle_models = _load_vehicle_models_for_ai()

    # 并行执行偏差分析和路线特征识别
    import asyncio

    tasks = [
        analyze_price_deviations(predictions, vehicle_models, context, client),
    ]

    if unique_destinations:
        tasks.append(classify_route_features(unique_destinations, client))

    results = await asyncio.gather(*tasks)
    deviation_report = results[0]
    route_report = results[1] if len(results) > 1 else None

    # 基于偏差分析结果做公式优化建议
    optimization = await suggest_formula_optimizations(
        current_params=vehicle_models,
        error_analysis=deviation_report,
        client=client,
    )

    return {
        "deviation_analysis": deviation_report,
        "route_features": route_report,
        "optimization_suggestions": optimization,
    }
