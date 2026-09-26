"""v009 周期性需求调价 —— 当期「价格系数」。

冻结公式（契约 §2）：

    需求比   = 当期用车台次 / 基线台次
    价格系数 = clamp(1 + λ × (需求比 − 1), min_factor, max_factor)

* 默认 `λ = 0.30`、系数夹在 `[0.85, 1.20]`（需求 +50% → 价 +15%；需求 −30% → 价 −9%）；
* **基线**：`baseline_trips` 手填优先；不填 → 取「近 N 个月（默认 6）有数据期间」的中位数
  （见 `rates_store.effective_baseline_trips` 的四步细则）；
* **期间命中**：`start <= 今天 <= end`，多个并存时按 `start` 升序取第一个；
* 无命中期间 → `factor = 1.0, active = false`；
* 生效范围：系数**只乘运输费**（距离成本 + 固定调度费 + 路桥费 + 三项路况附加），
  **不乘**装卸费 / 保险费 / 杂费（口岸费、关税本来就不在这套 breakdown 里）；
* 人在环：期间必须由操作员手工建立（写动作 + 审计），系统不做全自动浮动。
"""

from __future__ import annotations

from datetime import date

from app.services import rates_store

#: 「无命中期间」时的文案（冻结风格，与生效文案同一句式）
NO_PERIOD_NOTE = "当前无生效的用车需求期间，价格系数 ×1.00"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_factor(demand_ratio: float, settings: dict | None = None) -> dict:
    """需求比 → 价格系数（含夹紧信息）。"""
    s = settings or rates_store.get_settings()
    lam = float(s.get("lambda") or rates_store.DEFAULT_SETTINGS["lambda"])
    low = float(s.get("min_factor") or rates_store.DEFAULT_SETTINGS["min_factor"])
    high = float(s.get("max_factor") or rates_store.DEFAULT_SETTINGS["max_factor"])
    raw = 1.0 + lam * (float(demand_ratio) - 1.0)
    factor = clamp(raw, low, high)
    return {
        "factor": round(factor, 4),
        "raw_factor": round(raw, 4),
        "demand_ratio": round(float(demand_ratio), 4),
        "lambda": lam,
        "min_factor": low,
        "max_factor": high,
        "clamped": abs(factor - raw) > 1e-9,
    }


def factor_note(factor: float, period_name: str, demand_ratio: float, lam: float) -> str:
    """冻结文案：`当期价格系数 ×1.15（2026-10旺季，需求 +50%，λ=0.30）`。"""
    return (
        f"当期价格系数 ×{factor:.2f}（{period_name}，"
        f"需求 {(float(demand_ratio) - 1) * 100:+.0f}%，λ={float(lam):.2f}）"
    )


def current_price_factor(today: date | None = None) -> dict:
    """当期价格系数快照（`GET /rates/current` 的 `price_factor` 字段）。"""
    settings = rates_store.get_settings()
    period, baseline = rates_store.match_active_period(today)
    snapshot = {
        "factor": 1.0,
        "active": False,
        "period": None,
        "demand_ratio": None,
        "lambda": settings["lambda"],
        "min_factor": settings["min_factor"],
        "max_factor": settings["max_factor"],
        "clamped": False,
        "note": NO_PERIOD_NOTE,
    }
    if period is None:
        return snapshot

    period_info = {
        "id": int(period.get("id") or 0),
        "name": str(period.get("name") or ""),
        "start": str(period.get("start") or ""),
        "end": str(period.get("end") or ""),
    }
    snapshot["period"] = period_info
    snapshot["active"] = True

    trips = period.get("trips")
    if not baseline or float(baseline) <= 0 or trips is None:
        snapshot["note"] = (
            f"期间「{period_info['name']}」的基线台次未知（未手填且取不到近月数据），价格系数按 ×1.00 计"
        )
        return snapshot

    ratio = float(trips) / float(baseline)
    computed = compute_factor(ratio, settings)
    snapshot.update({
        "factor": computed["factor"],
        "demand_ratio": computed["demand_ratio"],
        "clamped": computed["clamped"],
        "note": factor_note(computed["factor"], period_info["name"], ratio, settings["lambda"]),
    })
    return snapshot


def non_transport_cost(*, cost_loading: float, cost_insurance: float, cost_misc: float = 0.0) -> float:
    """不参与价格系数的费用项 = 装卸费 + 保险费 + 杂费。

    价格系数的生效范围就靠这一个函数界定（`route.build_quote_response` 调用），
    避免正算链路里出现第二个口径。
    """
    return float(cost_loading) + float(cost_insurance) + float(cost_misc)
