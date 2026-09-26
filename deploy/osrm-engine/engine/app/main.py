import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ai, batch, border, geocode, packing, quote, rates, reference, route, templates, vehicles
from app.db import Base, engine
from app.services.exchange_rate import start_daily_refresh, stop_daily_refresh

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载持久化 AI Key、初始化每日汇率刷新，关闭时停止。"""
    from app.services.ai_config import load_ai_config
    load_ai_config()  # 加载设置弹窗里保存的 DeepSeek API Key
    await start_daily_refresh()
    yield
    await stop_daily_refresh()


app = FastAPI(
    title="OSRM++ 越南运输费用预测 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 白名单：默认本地开发地址；生产环境通过 CORS_ORIGINS 环境变量注入（逗号分隔）
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:47820,http://127.0.0.1:47820,http://localhost:3000,http://127.0.0.1:3000,https://jiuneng.space,https://www.jiuneng.space",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 简单滑动窗口限流（内存中，重启后重置） ──
# 全局 60 req/min，批处理 5 req/min（在 batch.py 路由层检查）。
# 适用于单机轻量部署；多实例部署时请换用 Redis 后端。
_WINDOW_S = 60
# 🆕 v009：可用 AIOSRM_RATE_LIMIT_PER_MIN 覆盖（默认仍 60，正式版行为不变）。
#   存在的理由：真机 E2E 脚本一次费率流程就要 8~12 次请求，加上重算报价很容易撞窗
#   （实测：冒烟脚本 40 秒打 40 次会被 429 打回，误判成功能失败）。
_MAX_REQUESTS = int(os.environ.get("AIOSRM_RATE_LIMIT_PER_MIN", "60"))
_rate_buckets: dict[str, list[float]] = {}  # client_ip → [timestamps]


@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):
    """简单滑动窗口限流：每 60s 最多 60 个请求。"""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # 清理过期记录
    bucket = _rate_buckets.get(client_ip, [])
    bucket = [ts for ts in bucket if now - ts < _WINDOW_S]

    if len(bucket) >= _MAX_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后重试", "retry_after": _WINDOW_S},
        )

    bucket.append(now)
    _rate_buckets[client_ip] = bucket

    # 定期清理过期 IP 条目（每 100 个请求触发一次），防止 _rate_buckets 无限增长
    if len(_rate_buckets) > 500:
        _rate_buckets.clear()  # 简单策略：超量时全清，下次请求自动重建

    return await call_next(request)

app.include_router(route.router, prefix="/api/v1", tags=["route"])
app.include_router(reference.router, prefix="/api/v1", tags=["reference"])
app.include_router(geocode.router, prefix="/api/v1", tags=["geocode"])
app.include_router(templates.router, prefix="/api/v1", tags=["templates"])
app.include_router(batch.router, prefix="/api/v1", tags=["batch"])
app.include_router(border.router, prefix="/api/v1", tags=["border"])
app.include_router(ai.router, prefix="/api/v1", tags=["ai"])
app.include_router(quote.router, prefix="/api/v1", tags=["quote"])
app.include_router(rates.router, prefix="/api/v1", tags=["rates"])  # 🆕 v009 费率与价格
app.include_router(vehicles.router, prefix="/api/v1", tags=["vehicles"])  # 🆕 v011 车型库后台（internal only）
app.include_router(packing.router, prefix="/api/v1", tags=["packing"])  # 🆕 v013 装箱单 docx（逐车一页）


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
