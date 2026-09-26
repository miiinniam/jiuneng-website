"""v013 装箱单导出端点（`POST /api/v1/packing-list`）。

契约（**已对接前端，字段名不许改**，见 `desktop/renderer` 的导出流程）：

请求 JSON：`{ "job": {origin,destination,border_crossing,date}, "role": "client|internal",
"trucks": [ {index, model_name?, loading_rate?, truck:{L,W,H,maxWeight,type},
placements:[{cargoId,name,x,y,z,dx,dy,dz,weight,stackable}], unplaced:[{cargoId,name,reason}],
snapshot_png?} ] }` —— 坐标单位 cm、原点=前壁左下角、y==0 落地（与 `services/packer.py` 同源）。

响应：docx 字节流；`Content-Disposition` **同时**给 ASCII 兜底名与 RFC 5987 的中文名：
  `attachment; filename="packing_list.docx"; filename*=UTF-8''<urlencoded 装箱单_起点_终点_日期.docx>`
（只写中文名会让部分客户端/E2E 脚本拿到乱码文件名 —— 报价单那边踩过，这里照同一写法。）

行为约定：
  * `trucks == []` → **400** + 中文 detail（不生成空单页：没有车厢数据时页面毫无意义，
    而且前端导出失败需要明确信号去回退 CSV）；
  * 其余异常 → **500** + 中文 detail（不暴露堆栈，与 `api/quote.py` 同一处理）。
"""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.schemas import PackingListRequest
from app.services import company_profile, packing_list_docx

router = APIRouter()

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/packing-list")
async def export_packing_list(request: PackingListRequest):
    """生成装箱单 docx（中越双语 · 逐车一页 · 含摆放清单与装车示意图），返回文件流。"""
    if not request.trucks:
        return JSONResponse(status_code=400, content={"detail": packing_list_docx.EMPTY_TRUCKS_DETAIL})
    try:
        profile = company_profile.get_profile()
        data = packing_list_docx.build(request, profile)
    except Exception as exc:  # noqa: BLE001 —— 对外只给中文提示，不暴露堆栈
        return JSONResponse(status_code=500, content={"detail": f"装箱单生成失败：{exc}"})
    filename = packing_list_docx.filename_for(request)
    return Response(
        content=data,
        media_type=_DOCX_MIME,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"packing_list.docx\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
