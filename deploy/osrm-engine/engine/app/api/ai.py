"""
AI 分析 API
===========

提供 DeepSeek V4 Flash 驱动的智能分析端点：
- POST /ai/chat               对话式 AI 助手（SSE 流式）
- POST /ai/analyze-deviations  价格偏差分析
- POST /ai/classify-routes     路线特征识别
- POST /ai/extract-quote       供应商报价智能提取
- POST /ai/review-calibration  校准报告 AI 评审（一站式）
- GET  /ai/status              AI 服务状态
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas import (
    AIChatMessage,
    AIChatRequest,
    AIConfigRequest,
    AIConfigResponse,
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIExtractQuoteRequest,
    AIExtractQuoteResponse,
    AIRouteClassifyRequest,
    AIRouteClassifyResponse,
    AIStatusResponse,
    ActionAuditRequest,
)
from app.services.ai_analyzers import (
    ai_review_calibration,
    analyze_price_deviations,
    classify_route_features,
    extract_quote_from_text,
)
from app.services.ai_chat import run_chat
from app.services.ai_client import AIClient, AIClientError
from app.services.ai_config import get_ai_config, save_ai_config
from app.services.audit_log import log_call

router = APIRouter()


def _get_client():
    try:
        return AIClient()
    except AIClientError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/ai/status", response_model=AIStatusResponse, tags=["ai"])
async def ai_status() -> AIStatusResponse:
    """检查 AI 服务状态（API Key 是否配置、连接是否正常）。"""
    try:
        client = AIClient()
        client.chat(
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=10,
            timeout=10.0,
            max_retries=0,
        )
        return AIStatusResponse(
            status="ok",
            model=client.model,
            message="AI 服务正常",
        )
    except AIClientError as e:
        return AIStatusResponse(
            status="error",
            model="",
            message=str(e),
        )
    except Exception as e:
        # 兜底：任何异常都返回错误状态而非 500（如非法 Key 导致 httpx 编码失败）
        return AIStatusResponse(
            status="error",
            model="",
            message=f"AI 状态检测异常: {e}",
        )


@router.get("/ai/config", response_model=AIConfigResponse, tags=["ai"])
async def ai_get_config() -> AIConfigResponse:
    """读取当前 AI 配置（Key 掩码显示）。"""
    return AIConfigResponse(**get_ai_config())


@router.post("/ai/config", response_model=AIConfigResponse, tags=["ai"])
async def ai_set_config(request: AIConfigRequest) -> AIConfigResponse:
    """保存 DeepSeek API Key（立即生效 + 持久化，重启后由 lifespan 加载）。"""
    res = save_ai_config(request.api_key, request.model, request.base_url)
    return AIConfigResponse(**res)


@router.post("/ai/analyze-deviations", response_model=AIAnalysisResponse, tags=["ai"])
async def api_analyze_deviations(
    request: AIAnalysisRequest,
) -> AIAnalysisResponse:
    """分析预测偏差，AI 给出根因和建议。"""
    try:
        client = _get_client()
        result = await analyze_price_deviations(
            predictions=[p.model_dump() for p in request.predictions],
            context=request.context or "",
            client=client,
        )
        return AIAnalysisResponse(
            deviation_analysis=result,
            route_features=None,
            optimization_suggestions=None,
        )
    except AIClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/ai/classify-routes", response_model=AIRouteClassifyResponse, tags=["ai"])
async def api_classify_routes(
    request: AIRouteClassifyRequest,
) -> AIRouteClassifyResponse:
    """AI 自动识别目的地路线特征（港口/边境/山区/工业区）。"""
    try:
        client = _get_client()
        result = await classify_route_features(
            destinations=request.destinations,
            client=client,
        )
        return AIRouteClassifyResponse(route_features=result)
    except AIClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/ai/extract-quote", response_model=AIExtractQuoteResponse, tags=["ai"])
async def api_extract_quote(
    request: AIExtractQuoteRequest,
) -> AIExtractQuoteResponse:
    """从非结构化报价文本中智能提取报价数据。"""
    try:
        client = _get_client()
        result = await extract_quote_from_text(
            raw_text=request.raw_text,
            client=client,
        )
        return AIExtractQuoteResponse(extracted=result)
    except AIClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/ai/review-calibration", response_model=AIAnalysisResponse, tags=["ai"])
async def api_review_calibration(
    request: AIAnalysisRequest,
) -> AIAnalysisResponse:
    """一站式校准评审：偏差分析 + 路线特征 + 优化建议。"""
    try:
        client = _get_client()
        unique_dests = list({p.dest for p in request.predictions if p.dest})
        result = await ai_review_calibration(
            predictions=[p.model_dump() for p in request.predictions],
            unique_destinations=unique_dests if unique_dests else None,
            context=request.context or "",
            client=client,
        )
        return AIAnalysisResponse(
            deviation_analysis=result.get("deviation_analysis"),
            route_features=result.get("route_features"),
            optimization_suggestions=result.get("optimization_suggestions"),
        )
    except AIClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ══════════════════════════════════════════════════════════════
# AI 对话聊天（SSE 流式）
# ══════════════════════════════════════════════════════════════

@router.post("/ai/action-audit", tags=["ai"])
async def action_audit(payload: ActionAuditRequest) -> dict:
    """前端动作审计（v006 第 2 步）。前端执行 dispatch 后回报，只落审计、不改任何状态。"""
    log_call(
        tool=payload.action,
        role=payload.role,
        ok=payload.ok,
        args=payload.args,
        note=("frontend:" + payload.note) if payload.note else "frontend_ok",
    )
    return {"status": "ok"}


@router.post("/ai/chat", tags=["ai"])
async def ai_chat(request: AIChatRequest):
    """AI 对话助手 — SSE 流式端点。

    接收消息历史（可带界面状态快照 app_state），返回 Server-Sent Events 流：
      event: tool_start  → {"name": "...", "params": {...}}
      event: tool_done   → {"name": "...", "result": {...}}
      event: action      → {"action": "...", "args": {...}, "kind": "...", "confirm": true|false}
      event: text        → {"content": "..."}
      event: error       → {"message": "..."}
      event: done        → {"usage": {...}}
    """

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    async def event_stream():
        try:
            async for event in run_chat(
                messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                app_state=request.app_state,          # 🆕 v006
            ):
                evt_type = event["event"]
                data_str = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {evt_type}\ndata: {data_str}\n\n"
        except AIClientError as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': f'内部错误: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
