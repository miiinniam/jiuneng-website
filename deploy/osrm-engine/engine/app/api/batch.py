import asyncio
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.route import build_quote_response
from app.config import settings
from app.schemas import BatchRequest, BatchResponse, BatchRowInput, BatchRowResult
from app.services.cost_engine import (
    NoFittingVehicleModel,
    UnknownCargoType,
    UnknownVehicleModel,
    compute_cost_consolidated,
    compute_cost_full_truck,
    compute_vehicle_count,
)
from app.services.osrm_client import OSRMClient, OSRMError
from app.services.vehicle_registry import get_model, profile_for_model

router = APIRouter()

MAX_BATCH_ROWS = 500
MAX_CONCURRENT_OSRM_REQUESTS = 8

# 内存中的任务状态存储（重启后丢失，适用于单机轻量部署）
# TTL 保护：已完成/失败的任务 1 小时后自动清理，防止内存泄漏
MAX_JOBS = 1000
JOB_TTL_SECONDS = 3600

_jobs: dict[str, dict] = {}


def _cleanup_expired_jobs() -> None:
    """删除超过 TTL 的已完成/失败任务，并限制总容量。"""
    now = time.time()
    # 1) 按 TTL 清理
    expired = [
        jid for jid, job in _jobs.items()
        if job["status"] in ("completed", "failed")
        and now - job.get("_finished_at", 0) > JOB_TTL_SECONDS
    ]
    for jid in expired:
        del _jobs[jid]
    # 2) 容量上限 — 如果仍然超限，删最老的已完成任务
    if len(_jobs) > MAX_JOBS:
        finished = [
            (jid, job.get("_finished_at", 0))
            for jid, job in _jobs.items()
            if job["status"] in ("completed", "failed")
        ]
        finished.sort(key=lambda x: x[1])
        overflow = len(_jobs) - MAX_JOBS
        for jid, _ in finished[:overflow]:
            del _jobs[jid]


async def _process_row(index: int, raw_row: dict, client: OSRMClient, semaphore: asyncio.Semaphore) -> BatchRowResult:
    # BatchRowInput 的构造放在这里（而不是请求体级别一次性解析），是因为新增的
    # loading_mode 条件必填校验（整车需要 vehicle_model_id / 拼货需要 volume_m3）
    # 让"某一行数据不完整"变得常见，必须是"该行失败、其他行照常算"，不能因为一行没填对
    # 就让整个批量请求 422。
    try:
        row = BatchRowInput(**raw_row)
    except ValidationError as exc:
        return BatchRowResult(row_index=index, success=False, error=str(exc))

    async with semaphore:
        try:
            # 🆕 v015.4：批量行也带 vehicle_model_id ⇒ 与单条报价**同口径**按车型 profile 取路线。
            # 否则批量结果会「看起来正常、其实没按车型限高限重校验」（原先两处都是裸 OSRMClient()）。
            # profile_for_model 对未知/空车型返回 None（不发散），此时沿用传入的默认 client，零回归。
            row_profile = profile_for_model(row.vehicle_model_id)
            row_client = OSRMClient(profile=row_profile) if row_profile else client
            route_result = await row_client.get_route(
                [(row.origin_lng, row.origin_lat), (row.dest_lng, row.dest_lat)]
            )
        except OSRMError as exc:
            return BatchRowResult(row_index=index, success=False, error=str(exc))

        common_kwargs = dict(
            distance_m=route_result.distance_m,
            duration_s=route_result.duration_s,
            cargo_weight_ton=row.weight_kg / 1000,
            cargo_type=row.cargo_type,
            empty_return=row.empty_return,
            need_loading=row.need_loading,
            avoid_restricted_zones=row.avoid_restricted_zones,
            avoid_construction_zones=row.avoid_construction_zones,
            via_mountain_road=row.via_mountain_road,
            via_port=row.via_port,
            cargo_items=row.cargo_items,
            fuel_price_vnd=row.fuel_price_vnd or settings.default_fuel_price_vnd,
            wage_hourly_vnd=row.wage_hourly_vnd or settings.default_wage_hourly_vnd,
            cargo_value_vnd=row.cargo_value_vnd,
            toll_rate_vnd_per_km=row.toll_rate_vnd_per_km,
            misc_cost_vnd=row.misc_cost_vnd,
            loading_rate_vnd_per_ton=settings.loading_rate_vnd_per_ton,
            insurance_rate=settings.insurance_rate,
        )
        try:
            vehicle_count = 1
            if row.loading_mode == "full_truck":
                # 🆕 四约束车辆数（重量/体积/长件/面积）
                model = get_model(row.vehicle_model_id)
                if model:
                    vehicle_count = compute_vehicle_count(
                        model=model,
                        cargo_weight_ton=row.weight_kg / 1000,
                        cargo_volume_m3=row.volume_m3,
                        cargo_items=row.cargo_items,
                    )
                per_vehicle_weight = (row.weight_kg / 1000) / vehicle_count
                common_kwargs["cargo_weight_ton"] = per_vehicle_weight
                result = compute_cost_full_truck(vehicle_model_id=row.vehicle_model_id, **common_kwargs)
            else:
                result = compute_cost_consolidated(cargo_volume_m3=row.volume_m3, **common_kwargs)
        except (UnknownVehicleModel, UnknownCargoType, NoFittingVehicleModel) as exc:
            return BatchRowResult(row_index=index, success=False, error=str(exc))

        return BatchRowResult(
            row_index=index, success=True,
            quote=build_quote_response(route_result, result, vehicle_count),
        )


@router.post("/batch/quote", response_model=BatchResponse)
async def batch_quote(request: BatchRequest) -> BatchResponse:
    if not request.rows:
        raise HTTPException(status_code=400, detail="没有可计算的行")
    if len(request.rows) > MAX_BATCH_ROWS:
        raise HTTPException(status_code=400, detail=f"单次批量最多支持 {MAX_BATCH_ROWS} 行")

    client = OSRMClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_OSRM_REQUESTS)
    results = await asyncio.gather(
        *[_process_row(i, row, client, semaphore) for i, row in enumerate(request.rows)]
    )
    return BatchResponse(results=list(results))


@router.post("/batch/submit")
async def batch_submit(request: BatchRequest) -> dict:
    """提交批量报价任务，立即返回 job_id，异步在后台处理。

    前端轮询 GET /batch/status/{job_id} 获取进度。
    """
    if not request.rows:
        raise HTTPException(status_code=400, detail="没有可计算的行")
    if len(request.rows) > MAX_BATCH_ROWS:
        raise HTTPException(status_code=400, detail=f"单次批量最多支持 {MAX_BATCH_ROWS} 行")

    _cleanup_expired_jobs()

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "processing",
        "total": len(request.rows),
        "done": 0,
        "results": [None] * len(request.rows),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # 启动后台异步处理（FastAPI 的 BackgroundTasks 更正规，但这里用 asyncio.create_task 保持简单）
    asyncio.create_task(_run_batch_job(job_id, request.rows))

    return {"job_id": job_id, "total": len(request.rows)}


@router.get("/batch/status/{job_id}")
async def batch_status(job_id: str) -> dict:
    """查询批量报价任务进度。"""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {
        "job_id": job_id,
        "status": job["status"],
        "total": job["total"],
        "done": job["done"],
        "results": job["results"] if job["status"] == "completed" else None,
    }


async def _run_batch_job(job_id: str, rows: list[dict]) -> None:
    """后台执行批量报价，逐行更新进度。"""
    job = _jobs.get(job_id)
    if not job:
        return

    client = OSRMClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_OSRM_REQUESTS)

    async def _process_and_update(i: int, raw: dict) -> None:
        result = await _process_row(i, raw, client, semaphore)
        job["results"][i] = result
        job["done"] += 1

    try:
        tasks = [_process_and_update(i, row) for i, row in enumerate(rows)]
        await asyncio.gather(*tasks)
        job["status"] = "completed"
    except Exception:
        job["status"] = "failed"
    finally:
        job["_finished_at"] = time.time()
