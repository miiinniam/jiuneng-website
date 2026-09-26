"""实时汇率服务 — 每日自动更新 + 文件持久化。

数据源: https://api.exchangerate-api.com/v4/latest/CNY (免费)
持久化: data/exchange_rate.json（服务重启不丢失）
刷新策略: 每天 08:00 自动刷新（后台任务），API 失败时使用本地文件缓存
降级链: API → 本地文件缓存 → fixed_fees.json → 3500
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── 配置 ──
_EXCHANGE_API_URL = "https://api.exchangerate-api.com/v4/latest/CNY"
_REFRESH_HOUR = 8          # 每天北京时间 8:00 刷新
_REFRESH_MINUTE = 0
_REQUEST_TIMEOUT = 10.0

# ── 持久化路径 ──
from app.services._paths import resource_dir  # noqa: E402

_DATA_DIR = resource_dir() / "data"
_CACHE_FILE = _DATA_DIR / "exchange_rate.json"
_FIXED_FEES_FILE = _DATA_DIR / "fixed_fees.json"


@dataclass
class RateCache:
    vnd_per_rmb: float
    updated: str            # ISO 时间戳
    source: str             # "api" | "file_cache" | "fixed_fees" | "hardcoded"
    api_date: str = ""


# ── 模块级缓存 ──
_rate: Optional[RateCache] = None
_refresh_task: Optional[asyncio.Task] = None


# ═══════════════════════════════════════════
# 文件 I/O
# ═══════════════════════════════════════════

def _save_to_file(rate: RateCache) -> None:
    """持久化到 data/exchange_rate.json。"""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "vnd_per_rmb": rate.vnd_per_rmb,
                "updated": rate.updated,
                "source": rate.source,
                "api_date": rate.api_date,
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"汇率已持久化: {rate.vnd_per_rmb} VND/CNY (来源: {rate.source})")
    except Exception:
        logger.exception("汇率文件写入失败")


def _load_from_file() -> Optional[RateCache]:
    """从持久化文件加载汇率。"""
    if not _CACHE_FILE.exists():
        return None
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return RateCache(
            vnd_per_rmb=float(data["vnd_per_rmb"]),
            updated=data.get("updated", ""),
            source="file_cache",
            api_date=data.get("api_date", ""),
        )
    except Exception:
        logger.exception("汇率文件读取失败")
        return None


def _load_fallback() -> float:
    """降级链最后一环：fixed_fees.json → 3500。"""
    try:
        with open(_FIXED_FEES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return float(data["exchange_rate"]["vnd_per_rmb"])
    except Exception:
        logger.exception("fixed_fees.json 读取失败")
        return 3500.0


# ═══════════════════════════════════════════
# API 调用
# ═══════════════════════════════════════════

async def _fetch_from_api() -> tuple[float, str]:
    """从外部 API 获取实时汇率。Returns (vnd_per_rmb, api_date)。"""
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.get(_EXCHANGE_API_URL)
        resp.raise_for_status()
        data = resp.json()

    if "rates" not in data or "VND" not in data["rates"]:
        raise ValueError(f"API 响应缺少 VND 汇率字段")

    rate = float(data["rates"]["VND"])
    api_date = data.get("date", "")
    return rate, api_date


# ═══════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════

async def get_exchange_rate() -> dict:
    """获取当前汇率（优先模块缓存，必要时刷新）。

    Returns:
        {"vnd_per_rmb": float, "source": str, "updated": str}
    """
    global _rate

    if _rate is not None:
        return {
            "vnd_per_rmb": _rate.vnd_per_rmb,
            "source": _rate.source,
            "updated": _rate.updated,
        }

    # 首次调用：尝试从文件加载 → API → 降级
    return await _init_rate()


async def _init_rate() -> dict:
    """初始化汇率（启动时调用）。"""
    global _rate

    # 尝试从持久化文件加载
    cached = _load_from_file()
    if cached is not None:
        _rate = cached
        logger.info(f"从文件加载汇率: {cached.vnd_per_rmb} (更新于 {cached.updated})")
        return {
            "vnd_per_rmb": cached.vnd_per_rmb,
            "source": "file_cache",
            "updated": cached.updated,
        }

    # 尝试从 API 获取
    try:
        rate_val, api_date = await _fetch_from_api()
        now_iso = datetime.now().isoformat()
        _rate = RateCache(vnd_per_rmb=rate_val, updated=now_iso, source="api", api_date=api_date)
        _save_to_file(_rate)
        return {
            "vnd_per_rmb": _rate.vnd_per_rmb,
            "source": "api",
            "updated": now_iso,
        }
    except Exception as exc:
        logger.warning(f"初始化汇率 API 失败: {exc}")

    # 降级
    fallback = _load_fallback()
    _rate = RateCache(vnd_per_rmb=fallback, updated="", source="fixed_fees")
    return {
        "vnd_per_rmb": fallback,
        "source": "fixed_fees",
        "updated": "",
    }


async def force_refresh() -> dict:
    """强制刷新汇率（绕过文件缓存），供管理员手动触发。"""
    global _rate

    try:
        rate_val, api_date = await _fetch_from_api()
        now_iso = datetime.now().isoformat()
        _rate = RateCache(vnd_per_rmb=rate_val, updated=now_iso, source="api", api_date=api_date)
        _save_to_file(_rate)
        return {
            "vnd_per_rmb": rate_val,
            "source": "api",
            "updated": now_iso,
            "message": "刷新成功",
        }
    except Exception as exc:
        logger.exception("手动刷新汇率失败")
        if _rate is not None:
            return {
                "vnd_per_rmb": _rate.vnd_per_rmb,
                "source": _rate.source,
                "updated": _rate.updated,
                "message": f"刷新失败({exc})，继续使用现有汇率",
            }
        fallback = _load_fallback()
        return {
            "vnd_per_rmb": fallback,
            "source": "fixed_fees",
            "updated": "",
            "message": f"刷新失败({exc})，降级到默认值",
        }


# ═══════════════════════════════════════════
# 每日定时刷新
# ═══════════════════════════════════════════

async def _daily_refresh_loop() -> None:
    """后台循环：每天 08:00 自动刷新汇率。"""
    global _rate

    while True:
        now = datetime.now()
        # 计算下一个 08:00
        next_run = now.replace(hour=_REFRESH_HOUR, minute=_REFRESH_MINUTE, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"汇率下次自动刷新: {next_run.isoformat()} (等待 {wait_seconds:.0f}s)")
        await asyncio.sleep(wait_seconds)

        # 执行刷新
        try:
            rate_val, api_date = await _fetch_from_api()
            now_iso = datetime.now().isoformat()
            _rate = RateCache(vnd_per_rmb=rate_val, updated=now_iso, source="api", api_date=api_date)
            _save_to_file(_rate)
            logger.info(f"✅ 每日自动刷新成功: 1 CNY = {rate_val} VND (日期: {api_date})")
        except Exception as exc:
            logger.warning(f"⚠️ 每日自动刷新失败: {exc}，保留现有汇率")


async def start_daily_refresh() -> None:
    """启动后台每日刷新任务（在 FastAPI lifespan 中调用）。"""
    global _refresh_task

    # 先初始化汇率（从文件或 API）
    await _init_rate()

    # 启动后台循环
    _refresh_task = asyncio.create_task(_daily_refresh_loop())
    logger.info("汇率每日自动刷新任务已启动 (每天 08:00)")


async def stop_daily_refresh() -> None:
    """停止后台刷新任务。"""
    global _refresh_task
    if _refresh_task:
        _refresh_task.cancel()
        try:
            await _refresh_task
        except asyncio.CancelledError:
            pass
        _refresh_task = None
