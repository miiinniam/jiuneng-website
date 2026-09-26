"""v011 车型库 API（`/api/v1/vehicles`）—— **薄 HTTP 层**，业务全在 `services/vehicle_store.py`。

职责划分（本项目非 git，文件独占）：

* `services/vehicle_store.py` 数据层：型号级 CRUD + 双份 CSV 写盘 / 回滚 / 审计（**不在此文件重写任何写盘逻辑**）；
* 本文件                    HTTP 薄层：① 角色门禁 ② `VehicleStoreError` → 400（消息**原样**给前端显示）
                                      ③ CSV / 模板响应组装。

## 角色门禁（internal only）——沿用项目现有约定，不发明第二套

侦察结论（证据）：
* 角色枚举只有两个值 `internal` / `customer`：`schemas.py:378`（`QuoteExportRequest.role: Literal["customer","internal"] = "customer"`）、
  `ai/spec.py:37`（`roles: tuple[str, ...] = ("internal", "customer")`）；
* 「internal only」的既有表达方式是 `roles=("internal",)` 元数据 + 调用点检查：
  `ai/ui_spec.py:144/157/175`（`set_pricing` / `set_oversize_trip_fee` / `save_border_fees_default`）、
  `ai/registry.py:31 ROLE_ENFORCEMENT = True`、`ai/registry.py:159`（`if ROLE_ENFORCEMENT and role not in spec.roles:`）
  → 拒绝文案「当前角色（{role}）无权调用 {name}」（`registry.py:162`）；
* 角色的**传递方式**是「随请求上报、缺省 internal」：`ai_chat.py:54-55`
  （`frontend_role = str((app_state or {}).get("role") or "internal")`）、
  `schemas.py:354`（`ActionAuditRequest.role: str = "internal"`）。
  HTTP 层此前**没有任何**角色门禁（`api/*.py` 里 `role` 只出现在审计记录的固定值 `rates.py:32`），
  本文件按上面同一套语义补齐车型库这一处。

carrier 优先级（三者取先命中者）：请求头 `X-AIOSRM-Role` → query `?role=` → 请求体字段 `role`。
非 `internal`（含未知值如 `admin`）→ **403**，文案对齐 `registry.py:162` / `ai_chat.py:119`；
判定发生在**进入数据层之前**，因此客户角色的请求一个字节都不会写盘。

⚠️ 信任模型（与既有代码一致，不是本文件新引入的口子）：MVP 免登录（`ai/ui_spec.py:128` 注释
「两种角色都允许：set_role 只是视图切换，MVP 本就免密码」），角色是**前端上报的声明**而非服务端凭证；
本门禁的作用是「客户视角拿不到车型库的修改能力」（入口不渲染 + 调用被拒），不是防伪造的鉴权。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.schemas import VehicleImportRequest, VehicleUpsertRequest
from app.services import vehicle_store
from app.services.rates_store import _md5
from app.services.vehicle_registry import VEHICLE_CATEGORIES

router = APIRouter(prefix="/vehicles")

#: 角色声明的三种载体（优先级见模块头）
ROLE_HEADER = "X-AIOSRM-Role"
ROLE_QUERY = "role"
#: 请求体里的角色声明字段名（`VehicleUpsertRequest` / `VehicleImportRequest` 的 `role`）
ROLE_FIELD = "role"
#: 缺省角色：与 `ActionAuditRequest.role` / `ai_chat.py` 快照缺省一致（内部）
DEFAULT_ROLE = "internal"
#: 车型库只允许的角色（同 `ui_spec.py` 里 `roles=("internal",)` 的用法）
INTERNAL_ONLY: tuple[str, ...] = ("internal",)

_CSV_MIME = "text/csv; charset=utf-8"
_EXPORT_NAME = "车辆型号库_导出.csv"
_TEMPLATE_NAME = "车辆型号库_导入模板.csv"

T = TypeVar("T")


# ── 角色门禁 ───────────────────────────────────────────────────────────────

def _deny(role: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail=(
            f"当前角色（{role}）无权调用车型库管理接口：该接口仅限 {list(INTERNAL_ONLY)}，"
            "请让内部人员在内部视角下操作。"
        ),
    )


async def require_internal_role(request: Request) -> str:
    """车型库接口的角色门禁：声明为 `internal`（或缺省）才放行，否则 403。"""
    role = ""
    for carrier in (request.headers.get(ROLE_HEADER), request.query_params.get(ROLE_QUERY)):
        if carrier and str(carrier).strip():
            role = str(carrier).strip()
            break
    if not role:                                   # 请求体字段 `role`（POST/PUT/import 用）
        try:
            body = await request.json()
        except Exception:                          # noqa: BLE001 —— 无请求体 / 非法 JSON 都不算声明
            body = None
        if isinstance(body, dict) and body.get("role"):
            role = str(body["role"]).strip()
    if role and role not in INTERNAL_ONLY:
        raise _deny(role)
    return role or DEFAULT_ROLE


# ── 数据层调用：异常 → 400（消息原样给前端） ────────────────────────────────

def _call(func: Callable[[], T]) -> T:
    """跑一次 `vehicle_store` 调用；`VehicleStoreError` → HTTP 400，`detail` 就是中文原话。"""
    try:
        return func()
    except vehicle_store.VehicleStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _edit_payload(body: VehicleUpsertRequest) -> dict:
    """请求体 → 可编辑列 payload（`role` 是门禁字段，不写进车辆库）。

    列白名单**不在这里做**：`vehicle_store._check_keys()` 以磁盘表头为唯一权威
    （未知列 → 400「不可编辑字段」），两处白名单会漂移。
    """
    return {key: value for key, value in body.model_dump().items() if key != ROLE_FIELD}


# ── 1. 列表（含品类分组、双份路径与 md5 状态） ─────────────────────────────

@router.get("")
async def vehicles_list(role: str = Depends(require_internal_role)) -> dict:
    models = _call(vehicle_store.list_models)
    files: list[dict] = []
    for target in _call(vehicle_store.csv_write_targets):
        path = Path(target)
        exists = path.exists()
        files.append({"path": str(path), "name": path.name, "exists": exists,
                      "md5": _md5(path) if exists else None})
    grouped: dict[str, list[str]] = {}
    for model in models:
        grouped.setdefault(str(model.get("category") or ""), []).append(str(model.get("model_id") or ""))
    return {
        "count": len(models),
        "models": models,
        "grouped": grouped,                                   # 品类 → 型号 ID（面板按类折叠用）
        "categories": [{"category": category, "count": len(grouped.get(category, []))}
                       for category in VEHICLE_CATEGORIES],
        "files": files,
        "md5_consistent": bool(files) and all(f["exists"] for f in files)
        and len({f["md5"] for f in files}) == 1,
        "editable_columns": [c for c in vehicle_store.CSV_COLUMNS if c != "model_id"],
        "role": role,
    }


# ── 2. 新增 ────────────────────────────────────────────────────────────────

@router.post("")
async def vehicles_create(body: VehicleUpsertRequest, role: str = Depends(require_internal_role)) -> dict:
    """新增一个车型；返回写盘后**重新读回**的那一行（数值列已是数字类型）。"""
    return _call(lambda: vehicle_store.create_model(_edit_payload(body)))


# ── 3. 改参数 ──────────────────────────────────────────────────────────────

@router.put("/{model_id}")
async def vehicles_update(model_id: str, body: VehicleUpsertRequest,
                          role: str = Depends(require_internal_role)) -> dict:
    """改参数（费率 / 载重 / 尺寸 / 货型 / 备注…）；未知 `model_id` → 400（**不是 500**）。"""
    return _call(lambda: vehicle_store.update_model(model_id, _edit_payload(body)))


# ── 4. 删除（带保护） ──────────────────────────────────────────────────────

@router.delete("/{model_id}")
async def vehicles_delete(model_id: str, role: str = Depends(require_internal_role)) -> dict:
    return _call(lambda: vehicle_store.delete_model(model_id))


# ── 5. 导入（merge / replace，先校验后写） ─────────────────────────────────

@router.post("/import")
async def vehicles_import(body: VehicleImportRequest, role: str = Depends(require_internal_role)) -> dict:
    """CSV 导入。`mode` 不做 schema 级枚举校验：`vehicle_store.import_csv()` 是唯一权威
    （非法 mode 抛 `VehicleStoreError` → 400 中文原话），避免两处校验漂移。"""
    result = _call(lambda: vehicle_store.import_csv(body.content, mode=body.mode))
    summary = {key: value for key, value in result.items() if key != "rows"}   # 回整表太重，只回摘要
    summary["action"] = "import"
    summary["filename"] = body.filename
    return summary


# ── 6. 导出 / 7. 模板 ──────────────────────────────────────────────────────

@router.get("/export")
async def vehicles_export(role: str = Depends(require_internal_role)) -> Response:
    """导出当前车辆库 CSV（**与磁盘同一份字节**：utf-8-sig BOM + CRLF 原文）。

    文件名用 `filename*=UTF-8''…`（同 `api/quote.py:27` 的既有写法）：HTTP 头只能 latin-1，
    中文文件名直接塞进 `filename="…"` 会让 starlette 抛 `UnicodeEncodeError`。
    """
    data = _call(vehicle_store.export_csv)
    return Response(content=data.encode("utf-8"), media_type=_CSV_MIME,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(_EXPORT_NAME)}"})


@router.get("/template")
async def vehicles_template(role: str = Depends(require_internal_role)) -> Response:
    """下载导入模板（规范表头 + 2 行示例 + 注释行）。"""
    data = _call(vehicle_store.template_csv)
    return Response(content=data.encode("utf-8"), media_type=_CSV_MIME,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(_TEMPLATE_NAME)}"})
