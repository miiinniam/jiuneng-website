"""v009 费率与价格 API —— 公式价格反算 + 周期性需求调价（契约 §2 的 14 个端点）。

职责划分（本项目非 git，文件独占）：
* `services/rates_store.py`  数据层：样本 / 需求期间 / 价格版本 / 车辆型号库 CSV 安全写回
* `services/price_factor.py` 价格系数：clamp(1 + λ×(需求比−1)) + 冻结文案
* `services/calibration.py`  反算引擎（`fit_rates`）+ 五道护栏（复用，不重写算法）
* 本文件                      HTTP 薄层：校验转 400 / 反馈审计留痕 / 组装响应

写动作（应用费率 / 回滚 / 改 λ / 增删期间）都落 `data/ai_audit.jsonl`（复用既有审计机制）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.schemas import (
    RatesApplyRequest,
    RatesFitRequest,
    RatesPeriodCreateRequest,
    RatesSampleCreateRequest,
    RatesSampleImportRequest,
    RatesSettingsRequest,
)
from app.services import calibration, price_factor, rates_store, vehicle_registry
from app.services.audit_log import log_call

router = APIRouter(prefix="/rates")


def _audit(tool: str, *, ok: bool, args: dict | None = None, note: str = "") -> None:
    log_call(tool=tool, role="internal", ok=ok, args=args or {}, note=note)


# ── 1. 当前费率与价格系数 ──────────────────────────────────────────
@router.get("/current")
async def rates_current() -> dict:
    """侧栏/弹窗首屏：当期价格系数 + 各车型费率一览 + 数据量统计。"""
    models = [
        {
            "model_id": m.model_id,
            "display_name": m.display_name,
            "category": m.category,
            "base_rate_vnd_per_km": m.base_rate_vnd_per_km,
            "fixed_surcharge_vnd": m.fixed_surcharge_vnd,
        }
        for m in vehicle_registry.VEHICLE_MODELS
    ]
    return {
        "price_factor": price_factor.current_price_factor(),
        "models": models,
        "samples_count": len(rates_store.list_samples()),
        "versions_count": len(rates_store.list_versions()),
    }


# ── 2. 样本列表 ────────────────────────────────────────────────────
@router.get("/samples")
async def rates_samples() -> dict:
    return {"samples": rates_store.list_samples(), "stats": rates_store.sample_stats()}


# ── 3. 新增样本 ────────────────────────────────────────────────────
@router.post("/samples")
async def rates_add_sample(request: RatesSampleCreateRequest) -> dict:
    payload = request.model_dump(exclude_none=True)
    try:
        sample = rates_store.add_sample(payload)
    except rates_store.RatesError as exc:
        _audit("rates.samples.add", ok=False, args=payload, note=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("rates.samples.add", ok=True, args={"id": sample["id"], "date": sample["date"]})
    return {"ok": True, "sample": sample, "stats": rates_store.sample_stats()}


# ── 4. 删除样本 ────────────────────────────────────────────────────
@router.delete("/samples/{sample_id}")
async def rates_delete_sample(sample_id: int) -> dict:
    if not rates_store.delete_sample(sample_id):
        raise HTTPException(status_code=404, detail=f"样本 {sample_id} 不存在")
    _audit("rates.samples.delete", ok=True, args={"id": sample_id})
    return {"ok": True, "stats": rates_store.sample_stats()}


# ── 5. CSV 模板下载 ────────────────────────────────────────────────
@router.get("/template.csv")
async def rates_template() -> Response:
    """UTF-8 BOM + CRLF 的 CSV 模板，Excel 双击即可编辑。"""
    return Response(
        content=rates_store.template_csv().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="rates_template.csv"'},
    )


# ── 6. 导入 CSV ────────────────────────────────────────────────────
@router.post("/samples/import")
async def rates_import_samples(request: RatesSampleImportRequest) -> dict:
    try:
        valid, failed = rates_store.parse_samples_csv(request.content, request.filename)
    except rates_store.RatesError as exc:
        _audit("rates.samples.import", ok=False, args={"filename": request.filename}, note=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not valid and not failed:
        raise HTTPException(status_code=400, detail="文件里没有可导入的数据行")

    imported = 0
    for payload in valid:
        try:
            rates_store.add_sample(payload)
            imported += 1
        except rates_store.RatesError as exc:  # pragma: no cover - parse 阶段已校验过
            failed.append({"line": 0, "reason": str(exc)})

    _audit("rates.samples.import", ok=True,
           args={"filename": request.filename, "imported": imported, "failed": len(failed)})
    return {
        "ok": True,
        "imported": imported,
        "failed": failed,
        "stats": rates_store.sample_stats(),
    }


# ── 7. 反算建议（护栏 P1~P5） ──────────────────────────────────────
@router.post("/fit")
async def rates_fit(request: RatesFitRequest) -> dict:
    records = rates_store.list_samples()
    pending = _records_needing_km(records)
    if pending:
        try:  # 缺里程的样本按 OSRM 补算（best-effort：失败就不参与反算）
            await calibration.resolve_missing_distances(pending, limit=3)
        except Exception:  # noqa: BLE001 —— 网络问题不许把拟合打成 500
            pass
    return rates_store.fit_suggestions(request.model_ids, records=records)


def _records_needing_km(records: list[dict], min_samples: int = 3) -> list[dict]:
    """挑出「缺里程且该车型样本还不足 P1 门槛」的样本 —— 才值得花网络去 OSRM 补算。

    限流保护：一次拟合最多补 3 条（见调用处），离线环境下最多 ~60s 就返回，
    不会把 `POST /rates/fit` 拖成"转圈不响应"。
    """
    usable: dict[str, int] = {}
    pending: dict[str, list[dict]] = {}
    for record in records:
        model_id = str(record.get("vehicle_model_id") or "")
        if record.get("distance_km"):
            usable[model_id] = usable.get(model_id, 0) + 1
        else:
            pending.setdefault(model_id, []).append(record)
    picked: list[dict] = []
    for model_id, rows in pending.items():
        if usable.get(model_id, 0) >= min_samples:
            continue          # 该车型已经不缺样本，补里程对护栏结论没影响
        picked.extend(rows)
    return picked


# ── 8. 应用建议费率（护栏 P5 未过且未 force → 400） ─────────────────
@router.post("/apply")
async def rates_apply(request: RatesApplyRequest) -> dict:
    items = [item.model_dump() for item in request.items]
    try:
        result = rates_store.apply_rates(items, note=request.note or "", force=bool(request.force))
    except rates_store.RatesError as exc:
        _audit("rates.apply", ok=False, args={"items": items, "force": request.force}, note=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("rates.apply", ok=True,
           args={"version": result["version"], "applied": result["applied"], "forced": result["forced"]},
           note=request.note or "")
    return result


# ── 9. 价格版本列表（倒序） ────────────────────────────────────────
@router.get("/versions")
async def rates_versions() -> dict:
    return {"versions": rates_store.list_versions()}


# ── 10. 回滚到历史版本（回滚也留痕） ────────────────────────────────
@router.post("/versions/{version}/rollback")
async def rates_rollback(version: int) -> dict:
    try:
        result = rates_store.rollback_version(version)
    except rates_store.RatesError as exc:
        _audit("rates.rollback", ok=False, args={"version": version}, note=str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit("rates.rollback", ok=True,
           args={"from": version, "version": result["version"], "noop": result["noop"]})
    return result


# ── 11. 需求期间 + 弹性设置 ────────────────────────────────────────
@router.get("/periods")
async def rates_periods() -> dict:
    return {"periods": rates_store.list_periods(), "settings": rates_store.get_settings()}


# ── 12. 新增期间 ───────────────────────────────────────────────────
@router.post("/periods")
async def rates_add_period(request: RatesPeriodCreateRequest) -> dict:
    payload = request.model_dump(exclude_none=True)
    try:
        period = rates_store.add_period(payload)
    except rates_store.RatesError as exc:
        _audit("rates.periods.add", ok=False, args=payload, note=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("rates.periods.add", ok=True,
           args={"id": period["id"], "start": period["start"], "end": period["end"],
                 "trips": period["trips"]})
    return {"ok": True, "period": period}


# ── 13. 删除期间 ───────────────────────────────────────────────────
@router.delete("/periods/{period_id}")
async def rates_delete_period(period_id: int) -> dict:
    if not rates_store.delete_period(period_id):
        raise HTTPException(status_code=404, detail=f"期间 {period_id} 不存在")
    _audit("rates.periods.delete", ok=True, args={"id": period_id})
    return {"ok": True}


# ── 14. 弹性设置（λ / 上下限 / 基线取数月数） ──────────────────────
@router.put("/settings")
async def rates_update_settings(request: RatesSettingsRequest) -> dict:
    payload = request.model_dump(exclude_none=True)
    try:
        settings = rates_store.update_settings(payload)
    except rates_store.RatesError as exc:
        _audit("rates.settings", ok=False, args=payload, note=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("rates.settings", ok=True, args=settings)
    return {"ok": True, "settings": settings}
