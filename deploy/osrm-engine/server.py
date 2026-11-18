"""
官网专用：OSRM++ 引擎的**窄暴露**入口（Render 独立服务）。

为什么不直接把引擎 app 挂上去：
  引擎是给桌面版用的完整后端，暴露着车型库后台（/api/v1/vehicles，role=internal）、
  费率/税则（/api/v1/rates、/border/*）、报价单导出（/quote/export）、AI 代理（/ai/*）等端点。
  官网只需要三类能力，所以这里做两件事：
    1) 端点白名单 —— 只放行下表 5 个业务端点，其余一律 404（不暴露引擎能力面）：
         GET  /health                            （存活探测）
         POST /api/v1/route/cost                 （线路测算）
         GET  /api/v1/border/fees-only           （v7：报关区间/分项）
         POST /api/v1/reference/fit-vehicles     （v7：车辆匹配）
         GET  /api/v1/reference/exchange-rate    （v7：DDP 折算汇率，拿不到就不给 DDP）
    2) 密钥校验 —— 除 /health 与 /gateway/health 外**必须**带 X-API-Key 头
       （值取自环境变量 ENGINE_API_KEY）；未配置密钥时拒绝启动，避免「忘了设密钥」导致引擎裸奔。
       ⚠️ v7 新放行的三个端点**不进 KEY_FREE**：它们会回业务金额口径，必须带钥。
  另加一层每 IP 每分钟限流，防止被刷。

本文件不修改引擎任何源码，只在其前面包一层 ASGI 中间件。
"""
import os
import secrets
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "engine"))
# 资源目录：引擎读 data/ 与 车辆型号库.csv 都从这里找（见 engine/app/services/_paths.py）
os.environ.setdefault("OSRM_RESOURCE_DIR", str(HERE))

API_KEY = os.environ.get("ENGINE_API_KEY", "").strip()
ALLOWED = {
    ("GET", "/health"),
    ("POST", "/api/v1/route/cost"),
    ("GET", "/api/v1/border/fees-only"),         # v7：报关区间 / 分项明细
    ("POST", "/api/v1/reference/fit-vehicles"),  # v7：车辆匹配
    ("GET", "/api/v1/reference/exchange-rate"),  # v7：DDP 汇率（缺失时站点给 null，不猜）
}
# Render 健康检查不会带自定义头，所以健康端点免密钥（只回 {"status":"ok"}，不含任何业务信息）
KEY_FREE = {("GET", "/health"), ("GET", "/gateway/health")}
RATE_LIMIT_PER_MIN = int(os.environ.get("ENGINE_RATE_LIMIT", "60"))

if not API_KEY:
    print("[engine-gateway] ENGINE_API_KEY 未配置，拒绝启动（避免引擎公开裸奔）。", flush=True)
    sys.exit(2)

from app.main import app as engine_app  # noqa: E402  （引擎本体，原样挂载）

app = FastAPI(title="JIUNENG OSRM++ gateway (website-only)")

_hits: dict[str, list[float]] = {}


def _rate_ok(ip: str) -> bool:
    now = time.time()
    bucket = [t for t in _hits.get(ip, []) if now - t < 60]
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        _hits[ip] = bucket
        return False
    bucket.append(now)
    _hits[ip] = bucket
    if len(_hits) > 500:  # 简单防膨胀
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > 300]:
            _hits.pop(k, None)
    return True


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    key = (request.method, path)
    if key not in ALLOWED and key not in KEY_FREE:
        return JSONResponse({"detail": "not found"}, status_code=404)
    if key not in KEY_FREE and not secrets.compare_digest(request.headers.get("x-api-key", ""), API_KEY):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    ip = (request.client.host if request.client else "unknown")
    if not _rate_ok(ip):
        return JSONResponse({"detail": "too many requests"}, status_code=429)
    return await call_next(request)


@app.get("/gateway/health")
async def gateway_health() -> dict:
    return {"status": "ok", "gateway": "jiuneng-osrm-gateway"}


# 引擎本体挂在根路径：白名单与密钥由上面的中间件先行拦截
app.mount("/", engine_app)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "18000"))
    print(f"[engine-gateway] listening on 0.0.0.0:{port}"
          f"（放行 {len(ALLOWED)} 个端点：/health、route/cost、border/fees-only、"
          f"reference/fit-vehicles、reference/exchange-rate）", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
