from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.schemas import QuoteExportRequest
from app.services import company_profile, quote_docx_builder, quote_number

router = APIRouter()

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/quote/export")
async def export_quote(request: QuoteExportRequest):
    """生成正式 docx 报价单，返回文件流。"""
    try:
        profile = company_profile.get_profile()
        quote_no = quote_number.next_number()
        data = quote_docx_builder.build(request, profile, quote_no)
    except Exception as exc:  # noqa: BLE001 —— 对外只给中文提示，不暴露堆栈
        return JSONResponse(status_code=500, content={"detail": f"报价单生成失败：{exc}"})
    filename = f"报价单_{quote_no}.docx"
    return Response(
        content=data,
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
