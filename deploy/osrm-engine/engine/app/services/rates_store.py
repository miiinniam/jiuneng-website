"""v009 费率与价格 —— 数据层（反算样本 / 需求期间 / 价格版本 / 车辆型号库 CSV 读写）。

设计原则（与 `border_costs.py` 的既有风格保持一致）：

* 数据文件全部落在 `data_dir()` 下；模块级 `_DATA_DIR` 是唯一入口，测试 monkeypatch
  这一个变量即可把全部读写重定向到临时目录，绝不碰真实数据；
* **读文件永不抛异常**：费率数据坏了/缺了不能把报价接口打成 500 → 回落到内置默认值；
* 写文件先写 `.tmp` 再 `os.replace`（避免半个 JSON）；
* 改 `车辆型号库.csv` 前**必须先备份**（`车辆型号库.csv.bak`），写完做
  **双份 md5 一致**校验，不一致立刻用备份回滚本次写入（历史踩坑：两份 CSV 漂移）。

车主数据（`车辆型号库.csv`）是正算/反算共用的唯一费率真源 —— 本模块只负责"改这两列"：
`base_rate_vnd_per_km` / `fixed_surcharge_vnd`，其它列原样写回。
"""

from __future__ import annotations

import calendar
import copy
import csv
import hashlib
import io
import json
import os
import shutil
import statistics
from datetime import date, datetime
from pathlib import Path

from app.services._paths import data_dir
from app.services.presets import CARGO_TYPE_RATES
from app.services.vehicle_registry import get_model

SAMPLES_FILE = "calibration_samples.json"
PERIODS_FILE = "demand_periods.json"
VERSIONS_FILE = "price_versions.json"
VEHICLE_CSV_NAME = "车辆型号库.csv"

#: 允许写回 CSV 的两列（整车一口价模型的两个参数）
CSV_RATE_COLUMNS = ("base_rate_vnd_per_km", "fixed_surcharge_vnd")

#: 需求调价默认参数（冻结：λ=0.30，系数夹在 [0.85, 1.20]）
DEFAULT_SETTINGS: dict = {
    "lambda": 0.30,
    "min_factor": 0.85,
    "max_factor": 1.20,
    "baseline_months": 6,
}

#: 下载模板表头（冻结，Excel 双击可编辑）
TEMPLATE_HEADER = [
    "日期", "起点", "终点", "车型ID", "总价VND", "计价口径",
    "实际里程km", "重量t", "货物类型", "数据来源", "备注",
]
TEMPLATE_EXAMPLE_ROW = [
    "2026-09-15", "河内", "海防", "flatbed_13m", "6000000", "整车",
    "110.3", "12.5", "normal", "供应商报价", "示例行：导入前请删除",
]

#: 数据文件位置（测试 monkeypatch 这个变量）
_DATA_DIR = data_dir()


class RatesError(ValueError):
    """费率/样本/期间相关的业务校验错误（API 层统一转 400）。"""


# ══════════════════════════ 通用 JSON 读写 ══════════════════════════

def data_path(name: str) -> Path:
    return Path(_DATA_DIR) / name


def _load_json(name: str, default):
    """读 JSON；缺失/损坏/类型不符 → 内置默认值（绝不抛）。"""
    try:
        payload = json.loads(data_path(name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return copy.deepcopy(default)
    except Exception:  # noqa: BLE001 —— 数据坏了也不能拖垮报价
        return copy.deepcopy(default)
    if not isinstance(payload, type(default)):
        return copy.deepcopy(default)
    return payload


def _save_json(name: str, payload) -> None:
    p = data_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ══════════════════════════ 字段解析与校验 ══════════════════════════

_MODE_ALIASES = {
    "fulltruck": "full_truck", "full": "full_truck", "ft": "full_truck",
    "整车": "full_truck", "包车": "full_truck", "整车一口价": "full_truck",
    "consolidated": "consolidated", "consol": "consolidated", "ltl": "consolidated",
    "拼货": "consolidated", "拼车": "consolidated", "零担": "consolidated",
}

_CARGO_ALIASES = {
    "normal": "normal", "普通": "normal", "普货": "normal", "普通货物": "normal",
    "coldchain": "cold_chain", "cold": "cold_chain", "冷链": "cold_chain", "冷藏": "cold_chain",
    "hazardous": "hazardous", "危险品": "hazardous", "危品": "hazardous",
    "oversized": "oversized", "大件": "oversized", "超限": "oversized", "超长": "oversized",
    "heavyequipment": "heavy_equipment", "重货设备": "heavy_equipment",
    "重型设备": "heavy_equipment", "设备": "heavy_equipment",
    "other": "other", "其他": "other",
}


def _clean_key(value) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def normalize_loading_mode(value) -> str:
    if value is None or not str(value).strip():
        return "full_truck"
    mode = _MODE_ALIASES.get(_clean_key(value))
    if mode is None:
        raise RatesError(
            f"计价口径（{value!r}）无法识别，请填「整车」或「拼货」（也接受 full_truck / consolidated）"
        )
    return mode


def normalize_cargo_type(value) -> str:
    """货物类型不认识时**不报错**，回落 normal（避免整行导入失败）。"""
    if value is None or not str(value).strip():
        return "normal"
    raw = str(value).strip()
    if raw in CARGO_TYPE_RATES:
        return raw
    key = _clean_key(raw)
    if key in _CARGO_ALIASES:
        return _CARGO_ALIASES[key]
    if "冷链" in raw or "冷" in raw:
        return "cold_chain"
    if "危险" in raw or "危品" in raw:
        return "hazardous"
    if "大件" in raw or "超限" in raw:
        return "oversized"
    if "设备" in raw or "重" in raw:
        return "heavy_equipment"
    return "normal"


def _norm_date(value, field: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value or "").strip().replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise RatesError(f"{field}（{value!r}）不是有效日期，请用 2026-09-15 这种格式")


def _norm_number(value, field: str, *, required: bool = True, default=None,
                 minimum: float | None = None, maximum: float | None = None) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise RatesError(f"{field} 不能为空")
        return default
    raw = str(value).replace(",", "").replace(" ", "").replace("₫", "").replace("元", "")
    try:
        num = float(raw)
    except ValueError:
        raise RatesError(f"{field}（{value!r}）不是数字") from None
    if minimum is not None and num < minimum:
        raise RatesError(f"{field}（{num:g}）不能小于 {minimum:g}")
    if maximum is not None and num > maximum:
        raise RatesError(f"{field}（{num:g}）不能大于 {maximum:g}")
    return num


def _norm_text(value, field: str, *, required: bool = True, maximum: int = 200) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise RatesError(f"{field} 不能为空")
        return ""
    return text[:maximum]


# ══════════════════════════ 反算样本 ══════════════════════════

def load_samples_data() -> dict:
    payload = _load_json(SAMPLES_FILE, {"next_id": 1, "samples": []})
    if not isinstance(payload.get("samples"), list):
        payload["samples"] = []
    try:
        payload["next_id"] = int(payload.get("next_id") or 1)
    except (TypeError, ValueError):
        payload["next_id"] = 1
    return payload


def list_samples() -> list[dict]:
    return list(load_samples_data()["samples"])


def validate_sample(payload: dict) -> dict:
    """校验并归一化一条样本；不合法 → RatesError（API 层转 400）。"""
    if not isinstance(payload, dict):
        raise RatesError("样本必须是一个 JSON 对象")
    date_text = _norm_date(payload.get("date"), "日期")
    origin = _norm_text(payload.get("origin"), "起点")
    destination = _norm_text(payload.get("destination"), "终点")
    model_id = _norm_text(payload.get("vehicle_model_id"), "车型ID")
    if get_model(model_id) is None:
        raise RatesError(f"车型ID不存在：{model_id}（请从车辆型号库的下拉里选）")
    total_vnd = _norm_number(payload.get("total_vnd"), "总价VND", minimum=1)
    loading_mode = normalize_loading_mode(payload.get("loading_mode"))
    distance_km = _norm_number(payload.get("distance_km"), "实际里程km",
                               required=False, default=None, minimum=0.1, maximum=20000)
    weight_ton = _norm_number(payload.get("weight_ton"), "重量t",
                              required=False, default=None, minimum=0.001, maximum=200)
    return {
        "date": date_text,
        "origin": origin,
        "destination": destination,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        "vehicle_model_id": model_id,
        "total_vnd": total_vnd,
        "loading_mode": loading_mode,
        "weight_ton": weight_ton,
        "cargo_type": normalize_cargo_type(payload.get("cargo_type")),
        "source": _norm_text(payload.get("source"), "数据来源", required=False, maximum=80),
        "note": _norm_text(payload.get("note"), "备注", required=False, maximum=200),
    }


def add_sample(payload: dict) -> dict:
    record = validate_sample(payload)
    state = load_samples_data()
    record["id"] = int(state["next_id"])
    state["next_id"] = record["id"] + 1
    state["samples"].append(record)
    _save_json(SAMPLES_FILE, state)
    return record


def add_samples(payloads: list[dict]) -> tuple[list[dict], list[dict]]:
    """批量新增（导入用）：逐条校验，坏的进 failures（带行号由调用方补）。"""
    added: list[dict] = []
    failures: list[dict] = []
    for item in payloads:
        try:
            added.append(add_sample(item))
        except RatesError as exc:  # pragma: no cover - 调用方已先校验
            failures.append({"line": 0, "reason": str(exc)})
    return added, failures


def delete_sample(sample_id: int) -> bool:
    state = load_samples_data()
    kept = [s for s in state["samples"] if int(s.get("id", -1)) != int(sample_id)]
    if len(kept) == len(state["samples"]):
        return False
    state["samples"] = kept
    _save_json(SAMPLES_FILE, state)
    return True


def sample_stats() -> dict:
    samples = list_samples()
    by_model: dict[str, int] = {}
    for s in samples:
        mid = str(s.get("vehicle_model_id", ""))
        by_model[mid] = by_model.get(mid, 0) + 1
    dates = sorted(str(s.get("date")) for s in samples if s.get("date"))
    return {
        "total": len(samples),
        "by_model": by_model,
        "date_range": [dates[0], dates[-1]] if dates else None,
    }


# ══════════════════════════ 需求期间 + 弹性设置 ══════════════════════════

def _norm_settings(raw) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for key in DEFAULT_SETTINGS:
            if raw.get(key) is not None:
                settings[key] = raw[key]
    try:
        settings["lambda"] = float(settings["lambda"])
        settings["min_factor"] = float(settings["min_factor"])
        settings["max_factor"] = float(settings["max_factor"])
        settings["baseline_months"] = int(settings["baseline_months"])
    except (TypeError, ValueError):
        return dict(DEFAULT_SETTINGS)
    return settings


def load_periods_data() -> dict:
    payload = _load_json(PERIODS_FILE, {"periods": [], "settings": dict(DEFAULT_SETTINGS)})
    if not isinstance(payload.get("periods"), list):
        payload["periods"] = []
    payload["settings"] = _norm_settings(payload.get("settings"))
    return payload


def get_settings() -> dict:
    return load_periods_data()["settings"]


def update_settings(payload: dict) -> dict:
    """PUT /rates/settings —— 部分字段也接受（None/缺省 = 保留当前值）。"""
    current = get_settings()
    merged = dict(current)
    renamed = {"lambda_": "lambda"}  # Pydantic 里 lambda 是关键字 → 别名字段
    for key, value in (payload or {}).items():
        merged[renamed.get(key, key)] = value
    lam = _norm_number(merged.get("lambda"), "λ（价格弹性）", minimum=0.0, maximum=0.60)
    min_factor = _norm_number(merged.get("min_factor"), "价格系数下限", minimum=0.50, maximum=1.50)
    max_factor = _norm_number(merged.get("max_factor"), "价格系数上限", minimum=0.50, maximum=2.00)
    if min_factor >= max_factor:
        raise RatesError(f"价格系数下限（{min_factor:g}）必须小于上限（{max_factor:g}）")
    baseline_months = _norm_number(merged.get("baseline_months"), "基线取数月数",
                                   minimum=1, maximum=36)
    settings = {
        "lambda": float(lam),
        "min_factor": float(min_factor),
        "max_factor": float(max_factor),
        "baseline_months": int(baseline_months),
    }
    state = load_periods_data()
    state["settings"] = settings
    _save_json(PERIODS_FILE, state)
    return settings


def _shift_months(day: date, months: int) -> date:
    year = day.year + (day.month - 1 - months) // 12
    month = (day.month - 1 - months) % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _median(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    return statistics.median(clean) if clean else None


def period_hits(period: dict, today: date) -> bool:
    """期间命中判据：start <= today <= end（自由起止日，跨月也成立）。"""
    try:
        start = datetime.strptime(str(period.get("start")), "%Y-%m-%d").date()
        end = datetime.strptime(str(period.get("end")), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return start <= today <= end


def match_active_period(today: date | None = None):
    """按 `start` 升序取第一个命中今天的期间 → (period, 有效基线台次)。无命中 → (None, None)。"""
    today = today or today_date()
    state = load_periods_data()
    hits = [p for p in state["periods"] if period_hits(p, today)]
    if not hits:
        return None, None
    hits.sort(key=lambda p: (str(p.get("start") or ""), int(p.get("id") or 0)))
    period = hits[0]
    return period, effective_baseline_trips(period, state["periods"], state["settings"], today)


def today_date() -> date:
    """今天（可用环境变量 AIOSRM_PRICE_TODAY 覆盖，方便复现某一天的调价结果）。"""
    override = os.getenv("AIOSRM_PRICE_TODAY", "").strip()
    if override:
        try:
            return datetime.strptime(override, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()


def effective_baseline_trips(period: dict, periods: list[dict], settings: dict,
                            today: date) -> float | None:
    """基线台次：手填优先；否则取「近 N 个月有数据期间」的中位数。

    细则（避免需求比永远持平）：
    1. 近 N 个月 = start 落在 [今天-N 个月, 今天] 的期间（**未开始的期间不算**：旺季自己
       不能当自己的基线）；
    2. 先从这堆里剔除「今天落在其中的期间」（当期不能拿自己当基线）；
    3. 剔完为空 → 退回全部近 N 个月期间；再为空 → 退回所有有台次的期间；
    4. 仍然取不到 → None（价格系数不生效，文案里说明基线未知）。
    """
    explicit = period.get("baseline_trips")
    if explicit:
        try:
            value = float(explicit)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    months = int(settings.get("baseline_months") or DEFAULT_SETTINGS["baseline_months"])
    cutoff = _shift_months(today, months)
    with_trips = []
    for p in periods:
        trips = p.get("trips")
        try:
            value = float(trips)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        try:
            start = datetime.strptime(str(p.get("start")), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if cutoff <= start <= today:
            with_trips.append(value)

    non_current = [
        float(p["trips"]) for p in periods
        if p.get("trips") and not period_hits(p, today)
        and _in_window(p, cutoff, today)
    ]
    pool = non_current or with_trips
    if not pool:
        pool = [float(p["trips"]) for p in periods if _is_positive(p.get("trips"))]
    return _median(pool)


def _is_positive(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _in_window(period: dict, cutoff: date, today: date) -> bool:
    try:
        start = datetime.strptime(str(period.get("start")), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return cutoff <= start <= today


def add_period(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise RatesError("期间必须是一个 JSON 对象")
    name = _norm_text(payload.get("name"), "期间名称", maximum=40)
    start = _norm_date(payload.get("start"), "开始日期")
    end = _norm_date(payload.get("end"), "结束日期")
    if start > end:
        raise RatesError(f"开始日期（{start}）不能晚于结束日期（{end}）")
    trips = _norm_number(payload.get("trips"), "当期用车台次", minimum=0.01, maximum=100000)
    baseline = _norm_number(payload.get("baseline_trips"), "基线台次",
                           required=False, default=None, minimum=0.01, maximum=100000)
    note = _norm_text(payload.get("note"), "备注", required=False, maximum=120)
    state = load_periods_data()
    next_id = max([int(p.get("id") or 0) for p in state["periods"]] or [0]) + 1
    record = {
        "id": next_id,
        "name": name,
        "start": start,
        "end": end,
        "trips": trips,
        "baseline_trips": baseline,
        "note": note,
    }
    state["periods"].append(record)
    _save_json(PERIODS_FILE, state)
    return record


def delete_period(period_id: int) -> bool:
    state = load_periods_data()
    kept = [p for p in state["periods"] if int(p.get("id") or -1) != int(period_id)]
    if len(kept) == len(state["periods"]):
        return False
    state["periods"] = kept
    _save_json(PERIODS_FILE, state)
    return True


def list_periods(today: date | None = None) -> list[dict]:
    """期间列表（含「有效基线台次」与「今天是否命中」），按 start 升序。"""
    today = today or today_date()
    state = load_periods_data()
    active, _ = match_active_period(today)
    active_id = int(active["id"]) if active else None
    out = []
    for p in sorted(state["periods"], key=lambda x: (str(x.get("start") or ""), int(x.get("id") or 0))):
        out.append({
            "id": int(p.get("id") or 0),
            "name": p.get("name", ""),
            "start": p.get("start", ""),
            "end": p.get("end", ""),
            "trips": p.get("trips"),
            "baseline_trips": effective_baseline_trips(p, state["periods"], state["settings"], today),
            "note": p.get("note", ""),
            "active": int(p.get("id") or 0) == active_id,
        })
    return out


# ══════════════════════════ 价格版本 ══════════════════════════

def load_versions_data() -> dict:
    payload = _load_json(VERSIONS_FILE, {"next_version": 1, "versions": []})
    if not isinstance(payload.get("versions"), list):
        payload["versions"] = []
    try:
        payload["next_version"] = int(payload.get("next_version") or 1)
    except (TypeError, ValueError):
        payload["next_version"] = 1
    return payload


def list_versions() -> list[dict]:
    """版本列表，倒序（最新在前）。"""
    versions = load_versions_data()["versions"]
    return sorted(versions, key=lambda v: int(v.get("version") or 0), reverse=True)


def find_version(version: int) -> dict | None:
    for item in load_versions_data()["versions"]:
        if int(item.get("version") or -1) == int(version):
            return item
    return None


def append_version(*, scope: list[str], changed: dict, samples: dict, quality: dict,
                   operator: str, note: str = "", rolled_back_from: int | None = None) -> dict:
    state = load_versions_data()
    version = int(state["next_version"])
    record = {
        "version": version,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "scope": list(scope),
        "changed": changed,
        "samples": samples,
        "quality": quality,
        "operator": operator,
        "note": note,
        "rolled_back_from": rolled_back_from,
    }
    state["versions"].append(record)
    state["next_version"] = version + 1
    _save_json(VERSIONS_FILE, state)
    return record


def operator_name() -> str:
    """操作人（写动作留痕用）：环境变量优先，否则取系统用户名，兜底「本地用户」。"""
    for key in ("AIOSRM_OPERATOR", "USERNAME", "USER"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return "本地用户"


# ══════════════════════════ 车辆型号库 CSV ══════════════════════════

def csv_write_targets() -> list[Path]:
    """apply / rollback 要写的车辆型号库路径。

    ① **运行时真源**：`vehicle_registry._resolve_csv_path()` 解析出的那份
       （打包版由 Electron 传 `OSRM_RESOURCE_DIR` 指向用户数据目录；只写 `backend/` 与
       `resources/` 的话，打包版永远读不到新费率 —— main.js 是「缺失才拷」）；
    ② 仓库镜像：`backend/车辆型号库.csv` 与 `resources/车辆型号库.csv`（存在才写）。
    写完对所有实际写入的文件做 md5 一致性校验。

    `VEHICLE_REGISTRY_CSV_PATH` 显式指定时只写那一份（测试/自定义部署用）。
    """
    env_override = os.getenv("VEHICLE_REGISTRY_CSV_PATH")
    if env_override:
        return [Path(env_override)]

    from app.services import vehicle_registry as registry

    targets: list[Path] = [Path(registry._resolve_csv_path())]  # noqa: SLF001 —— 复用同一套解析规则
    repo_root = Path(__file__).resolve().parents[3]
    for candidate in (repo_root / "backend" / VEHICLE_CSV_NAME, repo_root / "resources" / VEHICLE_CSV_NAME):
        if not candidate.exists():
            continue
        if candidate.resolve() in {p.resolve() for p in targets}:
            continue
        targets.append(candidate)
    return targets


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict]]:
    """读 CSV 为 (表头, 行 dict)。

    notes 列里有裸逗号的历史行会被 DictReader 塞进 `None` 键 —— 这里按契约丢弃 `None` 键
    （否则 DictWriter 会直接抛 ValueError），丢弃前把残值并回 notes，避免整段文字被吃掉。
    """
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    rows: list[dict] = []
    for row in reader:
        if not any(str(v).strip() for v in row.values() if v is not None):
            continue
        extras = row.pop(None, None)
        if extras:
            tail = [str(x) for x in extras if str(x).strip()]
            base = str(row.get("notes") or "").rstrip()
            if base or tail:
                row["notes"] = ",".join([base] + tail)
        rows.append(row)
    return header, rows


def _format_number(value: float) -> str:
    num = float(value)
    return str(int(round(num))) if abs(num - round(num)) < 1e-9 else f"{num:g}"


def _write_csv_rows(path: Path, header: list[str], rows: list[dict]) -> None:
    """写回 CSV：utf-8-sig（保留 BOM）+ CRLF（保留原行尾），DictWriter 自动加引号。

    ⚠️ 必须走 `write_bytes`：`Path.write_text` 在 Windows 上会把 `\\n` 再翻成 `\\r\\n`，
    结果每行多一个空行（实测：35 行变 70 行），双份 md5 也必然对不上。
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in header})
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(("\ufeff" + buffer.getvalue()).encode("utf-8"))
    os.replace(tmp, path)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _verify_csv_rows(path: Path, updates: dict[str, dict[str, float]], expected_rows: int) -> None:
    _, rows = _read_csv_rows(path)
    if len(rows) != expected_rows:
        raise RatesError(f"{path.name} 写回后行数从 {expected_rows} 变成 {len(rows)}，已回滚")
    index = {str(r.get("model_id", "")).strip(): r for r in rows}
    for model_id, values in updates.items():
        row = index.get(model_id)
        if row is None:
            raise RatesError(f"{path.name} 写回后找不到车型 {model_id}，已回滚")
        for column, value in values.items():
            try:
                actual = float(str(row.get(column, "")).strip())
            except ValueError:
                raise RatesError(f"{path.name} 的 {model_id}.{column} 写回后不是数字，已回滚") from None
            if abs(actual - float(value)) > 1e-6:
                raise RatesError(
                    f"{path.name} 的 {model_id}.{column} 写回后是 {actual:g}"
                    f"（期望 {float(value):g}），已回滚"
                )


def update_model_rates(updates: dict[str, dict[str, float]]) -> dict:
    """把费率写回车辆型号库 CSV（备份 → 写 → 校验 → 失败回滚）。

    updates = {model_id: {"base_rate_vnd_per_km": x, "fixed_surcharge_vnd": y}}
    返回 {"paths", "backups", "md5", "models"}；任何一步失败都先还原备份再抛 RatesError。
    """
    if not updates:
        raise RatesError("没有要写入的费率变更")
    targets = [Path(p) for p in csv_write_targets()]
    existing = [p for p in targets if p.exists()]
    if not existing:
        raise RatesError("车辆型号库.csv 不存在，无法写回费率（请检查 OSRM_RESOURCE_DIR）")

    backups: list[tuple[Path, Path]] = []
    for path in existing:
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
        backups.append((path, backup))

    try:
        touched: set[str] = set()
        for path in existing:
            header, rows = _read_csv_rows(path)
            if not header:
                raise RatesError(f"{path.name} 表头为空，已回滚")
            missing = [c for c in CSV_RATE_COLUMNS if c not in header]
            if missing:
                raise RatesError(f"{path.name} 缺少列 {missing}，已回滚")
            for row in rows:
                model_id = str(row.get("model_id", "")).strip()
                values = updates.get(model_id)
                if not values:
                    continue
                for column, value in values.items():
                    row[column] = _format_number(value)
                touched.add(model_id)
            _write_csv_rows(path, header, rows)
            _verify_csv_rows(path, {m: updates[m] for m in touched if m in updates}, len(rows))

        if not touched:
            raise RatesError(f"车辆型号库里没有这些车型：{sorted(updates)}，已回滚")

        digests = {str(path): _md5(path) for path in existing}
        if len(set(digests.values())) != 1:
            raise RatesError(
                "两份车辆型号库.csv 写完后 md5 不一致（双份漂移），已用备份回滚本次写入："
                + ", ".join(f"{Path(k).name}={v[:8]}" for k, v in digests.items())
            )

        # 写完立刻本进程生效（打包版/开发版都不需要重启后端）
        reload_vehicle_registry()

        return {
            "paths": [str(p) for p in existing],
            "backups": [str(b) for _, b in backups],
            "md5": digests,
            "models": sorted(touched),
        }
    except Exception:
        for path, backup in backups:
            try:
                shutil.copy2(backup, path)
            except Exception:  # noqa: BLE001 —— 回滚尽力而为
                pass
        # CSV 已还原 → 注册表也还原成还原后的文件内容（失败则说明要重启后端）
        try:
            reload_vehicle_registry()
        except Exception:  # noqa: BLE001
            pass
        raise


def reload_vehicle_registry() -> bool:
    """热重载注册表，使 `GET /rates/current`、`POST /route/cost` 立刻用上新费率。

    注册表里解析失败会**保留旧缓存**并抛可读异常 —— 这种情况下写盘结果不可用，
    调用方（update_model_rates）已经把 CSV 用备份还原。
    """
    from app.services import vehicle_registry as registry

    registry.reload_registry()
    return True


# ══════════════════════════ CSV 模板 + 导入解析 ══════════════════════════

_TEMPLATE_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("日期", "date", "运输日期", "报价日期"),
    "origin": ("起点", "出发地", "origin", "from"),
    "destination": ("终点", "目的地", "destination", "dest", "to"),
    "vehicle_model_id": ("车型id", "车型", "modelid", "vehiclemodelid", "车型编号"),
    "total_vnd": ("总价vnd", "总价", "totalvnd", "total", "成交价", "成本价"),
    "loading_mode": ("计价口径", "口径", "loadingmode", "loadmode", "计价方式"),
    "distance_km": ("实际里程km", "里程km", "实际里程", "distancekm", "里程", "distance"),
    "weight_ton": ("重量t", "重量", "weightton", "weight", "吨位"),
    "cargo_type": ("货物类型", "cargotype", "货物"),
    "source": ("数据来源", "来源", "source"),
    "note": ("备注", "note", "notes", "说明"),
}


def _match_header(row: list[str]) -> tuple[dict[str, int], int] | tuple[None, None]:
    """把表头行映射成 {字段: 列号}；认不出 → (None, None)。"""
    normalized = [_clean_key(c) for c in row]
    mapping: dict[str, int] = {}
    for field, aliases in _TEMPLATE_ALIASES.items():
        for index, cell in enumerate(normalized):
            if cell and cell in aliases and field not in mapping:
                mapping[field] = index
                break
    required = {"date", "origin", "destination", "vehicle_model_id", "total_vnd"}
    if not required.issubset(mapping):
        return None, None
    return mapping, 1


def template_csv() -> str:
    """下载模板（UTF-8 BOM，Excel 双击可编辑）。"""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(TEMPLATE_HEADER)
    writer.writerow(TEMPLATE_EXAMPLE_ROW)
    return "\ufeff" + buffer.getvalue()


def _repair_mojibake(text: str) -> str:
    """GBK 文件被当 UTF-8 读时会出现 U+FFFD —— 尽力还原（还原失败就保持原样）。"""
    if "\ufffd" not in text:
        return text
    try:
        repaired = text.encode("latin-1", errors="ignore").decode("gb18030", errors="ignore")
    except Exception:  # noqa: BLE001
        return text
    return repaired if repaired.count("\ufffd") < text.count("\ufffd") else text


def _mojibake_candidates(text: str) -> list[str]:
    """导入文本的候选解码：① 原样 ② 修复 U+FFFD 乱码 ③ latin-1 直通后按 GB18030 解。

    前端可能用 UTF-8 读了一个 GBK 文件（或反之）；这里尽力还原，避免用户明明导出的
    是「GBK CSV」却因为编码报 400。
    """
    candidates = [text]
    repaired = _repair_mojibake(text)
    if repaired != text:
        candidates.append(repaired)
    try:
        via_latin1 = text.encode("latin-1", errors="ignore").decode("gb18030", errors="ignore")
    except Exception:  # noqa: BLE001
        via_latin1 = ""
    if via_latin1 and via_latin1 not in candidates:
        candidates.append(via_latin1)
    return candidates


def parse_samples_csv(content: str, filename: str = "") -> tuple[list[dict], list[dict]]:
    """解析导入的 CSV 文本 → (合法样本, 失败清单[{line, reason}])。

    * `.xlsx/.xls` 二进制 → RatesError（提示另存为 CSV）
    * 表头认不出 → RatesError（提示下载模板）
    * 单行错误只影响该行，行号按文件真实行号（含表头，从 1 开始）
    """
    name = (filename or "").strip().lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        raise RatesError("检测到 Excel 二进制文件（.xlsx/.xls）。请用 Excel 打开后【另存为 CSV UTF-8】再导入。")
    raw_text = content or ""
    if raw_text[:2] == "PK" or "\x00" in raw_text[:200]:
        raise RatesError("文件内容不是文本 CSV（可能是 .xlsx 直接改了后缀）。请另存为 CSV 后再导入。")

    rows: list[list[str]] = []
    header_index: int | None = None
    mapping: dict[str, int] | None = None
    for text in _mojibake_candidates(raw_text):
        candidate_rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"), newline="")))
        for index, row in enumerate(candidate_rows[:5]):
            found, _ = _match_header(row)
            if found:
                rows, header_index, mapping = candidate_rows, index, found
                break
        if mapping is not None:
            break
    if mapping is None or header_index is None:
        if raw_text.strip():
            raise RatesError(
                "表头无法识别。请先下载本系统的 CSV 模板，表头为：" + ",".join(TEMPLATE_HEADER)
            )
        raise RatesError("文件是空的，没有可导入的内容")

    valid: list[dict] = []
    failed: list[dict] = []
    for offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not any(str(cell).strip() for cell in row):
            continue
        raw = {field: (row[index].strip() if index < len(row) else "")
               for field, index in mapping.items()}
        if not any(raw.values()):
            continue
        try:
            valid.append(validate_sample(raw))
        except RatesError as exc:
            failed.append({"line": offset, "reason": str(exc)})
    return valid, failed


# ══════════════════════════ 反算建议（护栏）+ 应用 / 回滚 ══════════════════════════

def _guards_unavailable(detail: str) -> dict:
    """样本不足/车型不存在时的护栏占位（与 calibration.evaluate_guards 同结构）。"""
    guard = {"pass": False, "detail": detail}
    return {
        "p1_samples": dict(guard),
        "p2_long_haul": dict(guard),
        "p3_error": dict(guard),
        "p4_magnitude": dict(guard),
        "p5_anchor": {"pass": False, "detail": "待人工核对"},
        "appliable": False,
    }


def _anchors(usable: list[dict], limit: int = 3) -> list[dict]:
    """样本里出现过的起终点（按出现次数取前几个）→ 供人工核对的市场锚点候选。"""
    buckets: dict[str, list[float]] = {}
    for sample in usable:
        route = f"{sample.get('origin')}→{sample.get('destination')}"
        buckets.setdefault(route, []).append(float(sample["distance_km"]))
    ordered = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
    return [{"route": route, "osrm_km": round(statistics.median(kms), 1)} for route, kms in ordered]


def _fit_one(model, group: list[dict]) -> dict:
    """单个车型的反算建议（一个车型一次 lstsq，沿用 calibration.fit_rates）。"""
    from app.services import calibration

    old = {
        "base_rate_vnd_per_km": float(model.base_rate_vnd_per_km),
        "fixed_surcharge_vnd": float(model.fixed_surcharge_vnd),
    }
    full_truck = [s for s in group if str(s.get("loading_mode")) == "full_truck"]
    usable = [s for s in full_truck if s.get("distance_km")]
    skipped = len(group) - len(usable)
    note_extra = f"；另有 {skipped} 条拼货/缺里程样本未参与反算" if skipped else ""

    suggested = dict(old)
    quality = {"rmse_vnd": None, "median_error_pct": None}
    guards: dict | None = None
    if usable:
        resolved = [calibration.resolved_from_record(s) for s in usable]
        try:
            result = calibration.fit_full_truck_samples(resolved)
        except Exception as exc:  # noqa: BLE001 —— 单个车型拟合失败不影响其它车型
            item = _fit_item_failed(model, old, f"拟合失败：{exc}{note_extra}", usable, skipped)
            return item
        fitted = result.base_rate_vnd_per_km.get(model.model_id)
        if fitted is not None:
            suggested["base_rate_vnd_per_km"] = float(round(fitted))
        median_error = calibration.median_abs_error_pct(resolved, result.predictions)
        quality = {
            "rmse_vnd": round(float(result.rmse_vnd)),
            "median_error_pct": round(float(median_error), 2) if median_error is not None else None,
        }
        guards = calibration.evaluate_guards(
            samples=resolved,
            predictions=result.predictions,
            old_base_rate=old["base_rate_vnd_per_km"],
            suggested_base_rate=suggested["base_rate_vnd_per_km"],
        )
    if guards is None:
        guards = _guards_unavailable(f"没有可用于反算的样本（需整车口径 + 实际里程）{note_extra}")
    elif note_extra and not guards["p1_samples"]["pass"]:
        guards["p1_samples"]["detail"] += note_extra

    long_haul = len([s for s in usable if float(s["distance_km"]) > calibration.LONG_HAUL_KM])
    old_base = old["base_rate_vnd_per_km"]
    old_fixed = old["fixed_surcharge_vnd"]
    return {
        "model_id": model.model_id,
        "display_name": model.display_name,
        "old": old,
        "suggested": suggested,
        "change_pct": {
            "base_rate_pct": round((suggested["base_rate_vnd_per_km"] / old_base - 1) * 100, 2) if old_base else 0.0,
            "fixed_pct": round((suggested["fixed_surcharge_vnd"] / old_fixed - 1) * 100, 2) if old_fixed else 0.0,
        },
        "samples": {"total": len(group), "long_haul": long_haul},
        "quality": quality,
        "anchors": _anchors(usable),
        "guards": guards,
        "appliable": bool(guards["appliable"]),
    }


def _fit_item_failed(model, old: dict, detail: str, usable: list[dict], skipped: int) -> dict:
    from app.services import calibration

    return {
        "model_id": model.model_id,
        "display_name": model.display_name,
        "old": old,
        "suggested": dict(old),
        "change_pct": {"base_rate_pct": 0.0, "fixed_pct": 0.0},
        "samples": {
            "total": len(usable) + skipped,
            "long_haul": len([s for s in usable if float(s["distance_km"]) > calibration.LONG_HAUL_KM]),
        },
        "quality": {"rmse_vnd": None, "median_error_pct": None},
        "anchors": _anchors(usable),
        "guards": _guards_unavailable(detail),
        "appliable": False,
    }


def _fit_item_unknown_model(model_id: str) -> dict:
    return {
        "model_id": model_id,
        "display_name": model_id,
        "old": {"base_rate_vnd_per_km": 0.0, "fixed_surcharge_vnd": 0.0},
        "suggested": {"base_rate_vnd_per_km": 0.0, "fixed_surcharge_vnd": 0.0},
        "change_pct": {"base_rate_pct": 0.0, "fixed_pct": 0.0},
        "samples": {"total": 0, "long_haul": 0},
        "quality": {"rmse_vnd": None, "median_error_pct": None},
        "anchors": [],
        "guards": _guards_unavailable(f"车型ID不存在：{model_id}"),
        "appliable": False,
    }


def fit_suggestions(model_ids: list[str] | None = None, records: list[dict] | None = None) -> dict:
    """`POST /rates/fit` 的响应体：逐车型 旧值/建议值/变动/样本/质量/护栏。

    `records` 传入时用这份样本（调用方可能刚给缺里程的样本补过 OSRM 里程），否则重新读盘。
    """
    samples = list(records) if records is not None else list_samples()
    groups: dict[str, list[dict]] = {}
    for sample in samples:
        groups.setdefault(str(sample.get("vehicle_model_id") or ""), []).append(sample)

    targets = [str(m).strip() for m in model_ids] if model_ids else sorted(groups)
    items = []
    for model_id in targets:
        if not model_id:
            continue
        model = get_model(model_id)
        if model is None:
            items.append(_fit_item_unknown_model(model_id))
            continue
        items.append(_fit_one(model, groups.get(model_id, [])))
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": items}


def _norm_route_key(text: str) -> str:
    clean = str(text or "").strip().lower()
    for token in ("->", "→", "—", "－", "-", "~", "至", "到", " ", "\t", "\u3000"):
        clean = clean.replace(token, "→")
    while "→→" in clean:
        clean = clean.replace("→→", "→")
    return clean.strip("→")


def find_route_samples(route: str, model_id: str | None = None) -> dict:
    """在已导入样本里找这条路线 → 里程 / 典型载重 / 货物类型（锚点实算口径的来源）。

    匹配规则：起终点归一化（`→` `->` `-` `至` `到` 都算路线分隔）后，完全相等或互相包含。
    """
    key = _norm_route_key(route)
    result = {"route": str(route or ""), "count": 0, "distance_km": None,
              "weight_ton": None, "cargo_type": "normal"}
    if not key:
        return result
    distances: list[float] = []
    weights: list[float] = []
    cargo_types: list[str] = []
    for sample in list_samples():
        if model_id and str(sample.get("vehicle_model_id")) != str(model_id):
            continue
        if not sample.get("distance_km"):
            continue
        candidate = _norm_route_key(f"{sample.get('origin')}→{sample.get('destination')}")
        if candidate == key or (len(key) >= 2 and (key in candidate or candidate in key)):
            distances.append(float(sample["distance_km"]))
            if sample.get("weight_ton"):
                weights.append(float(sample["weight_ton"]))
            cargo_types.append(str(sample.get("cargo_type") or "normal"))
    if not distances:
        return result
    result["count"] = len(distances)
    result["distance_km"] = round(statistics.median(distances), 1)
    result["weight_ton"] = round(statistics.median(weights), 2) if weights else None
    if cargo_types:
        result["cargo_type"] = statistics.mode(cargo_types)
    return result


def find_route_distance(route: str, model_id: str | None = None) -> float | None:
    """这条路线在样本里的里程中位数（找不到 → None）。"""
    return find_route_samples(route, model_id)["distance_km"]


def check_anchor(anchor: dict | None, model, base_rate_vnd_per_km: float,
                 fixed_surcharge_vnd: float) -> dict:
    """护栏 P5 的人工锚点核对。

    里程来源优先级：锚点自带的 `distance_km`/`osrm_km` → 样本里同起终点路线的里程中位数。
    **取不到里程就直接判不过并说明原因**，绝不用另一套口径硬算出一个偏差数字（历史踩坑）。
    """
    from app.services import calibration

    anchor = anchor or {}
    route = str(anchor.get("route") or "").strip()
    if not route:
        return {
            "route": route, "distance_km": None, "quoted_vnd": None, "actual_vnd": None,
            "error_pct": None, "pass": False,
            "detail": "未填写市场锚点核对（标杆路线 + 你熟悉的报价）",
        }

    hints = find_route_samples(route, model.model_id)
    km = None
    for candidate in (anchor.get("distance_km"), anchor.get("osrm_km"), hints["distance_km"]):
        try:
            if candidate is not None and float(candidate) > 0:
                km = float(candidate)
                break
        except (TypeError, ValueError):
            continue
    quoted = anchor.get("quoted_vnd")
    if km is None:
        return {
            "route": route, "distance_km": None, "quoted_vnd": quoted, "actual_vnd": None,
            "error_pct": None, "pass": False,
            "detail": (
                f"锚点「{route}」缺里程，无法按报价链路实算 —— 请先导入一条同起终点的样本，"
                "或随锚点一起传 distance_km（osrm_km）"
            ),
        }
    try:
        quoted_value = float(quoted)
    except (TypeError, ValueError):
        return {
            "route": route, "distance_km": km, "quoted_vnd": None, "actual_vnd": None,
            "error_pct": None, "pass": False,
            "detail": f"锚点「{route}」没有有效报价金额（quoted_vnd）",
        }

    # 车辆数口径：默认单车（锚点就是「这条线路一辆车的运输价」）；
    # 只有锚点显式给了载重、或样本里的典型载重本身就超过车型载重（真实多车场景）时才按四约束算。
    weight_ton = anchor.get("weight_ton") or hints["weight_ton"]
    explicit_weight = anchor.get("weight_ton") is not None
    if not explicit_weight and (not weight_ton or float(weight_ton) <= float(model.max_load_ton)):
        vehicle_count, weight_ton = 1, None
    else:
        vehicle_count = None
    try:
        toll = float(model.toll_rate_vnd_per_km or 0.0)
    except (TypeError, ValueError):
        toll = 0.0
    return calibration.check_market_anchor(
        route=route,
        quoted_vnd=quoted_value,
        distance_km=km,
        vehicle_model_id=model.model_id,
        base_rate_vnd_per_km=base_rate_vnd_per_km,
        fixed_surcharge_vnd=fixed_surcharge_vnd,
        cargo_type=str(anchor.get("cargo_type") or hints["cargo_type"] or "normal"),
        weight_ton=float(weight_ton) if weight_ton else None,
        vehicle_count=vehicle_count,
        toll_rate_vnd_per_km=toll,
    )


def apply_rates(items: list[dict], *, note: str = "", force: bool = False) -> dict:
    """`POST /rates/apply`：P5 锚点核对 → 写双份 CSV（备份+md5 校验）→ 追加价格版本。

    护栏 P5 不通过且没有 `force=true` → 抛 RatesError（API 层转 400）。
    `force=true` 时照样写盘 + 留痕（版本记录里说明），但**单次变动 >5 倍或 <0.2 倍**这种
    明显离谱的值也只在 force 下放行，避免把 CSV 写成废数。
    """
    if not items:
        raise RatesError("没有要应用的费率条目")

    targets: dict[str, dict[str, float]] = {}
    before: dict[str, dict[str, float]] = {}
    anchors: dict[str, dict] = {}
    problems: list[str] = []

    for raw in items:
        if not isinstance(raw, dict):
            raise RatesError("费率条目必须是 JSON 对象")
        model_id = str(raw.get("model_id") or "").strip()
        model = get_model(model_id)
        if model is None:
            raise RatesError(f"车型ID不存在：{model_id}")
        base_rate = _norm_number(raw.get("base_rate_vnd_per_km"), f"{model_id} 的 base_rate_vnd_per_km",
                                minimum=0.01, maximum=100_000_000)
        fixed = _norm_number(raw.get("fixed_surcharge_vnd"), f"{model_id} 的 fixed_surcharge_vnd",
                             minimum=0.0, maximum=100_000_000_000)
        targets[model_id] = {
            "base_rate_vnd_per_km": float(base_rate),
            "fixed_surcharge_vnd": float(fixed),
        }
        before[model_id] = {
            "base_rate_vnd_per_km": float(model.base_rate_vnd_per_km),
            "fixed_surcharge_vnd": float(model.fixed_surcharge_vnd),
        }

        if model.base_rate_vnd_per_km:
            ratio = float(base_rate) / float(model.base_rate_vnd_per_km)
            if not (0.20 <= ratio <= 5.00):
                problems.append(f"{model_id}：基价变动到 {ratio:.2f} 倍，超出单次允许的 [0.20, 5.00] 倍")

        anchor_result = check_anchor(raw.get("anchor_check"), model, float(base_rate), float(fixed))
        anchors[model_id] = anchor_result
        if not anchor_result["pass"]:
            problems.append(f"{model_id}：市场锚点核对未通过 —— {anchor_result['detail']}")

    if problems and not force:
        raise RatesError(
            "；".join(problems)
            + "。请先修正数据或改锚点；确需强制应用请显式传 force=true（同样留痕）。"
        )

    write = update_model_rates(targets)
    sample_counts, quality = _version_stats(sorted(targets))
    changed = {
        model_id: {"before": before[model_id], "after": targets[model_id]}
        for model_id in targets
    }
    record = append_version(
        scope=sorted(targets),
        changed=changed,
        samples=sample_counts,
        quality=quality,
        operator=operator_name(),
        note=note or "费率反算应用",
    )
    return {
        "ok": True,
        "version": record["version"],
        "applied": sorted(targets),
        "csv_verified": True,
        "paths": write["paths"],
        "backups": write["backups"],
        "anchors": anchors,
        "forced": bool(problems and force),
    }


def rollback_version(version: int, *, note: str = "") -> dict:
    """`POST /rates/versions/{version}/rollback`：用历史版本的 before 值覆盖当前值。

    * 回滚**也留痕**：新增一条版本记录（`rolled_back_from` 指向被回滚的版本）；
    * **幂等**：当前值已经等于目标值时不再写盘、不再加版本，返回上次那次回滚的版本号 ——
      连续两次回滚结果完全一致。
    """
    record = find_version(version)
    if record is None:
        raise RatesError(f"价格版本 v{version} 不存在")
    changed = record.get("changed") or {}
    if not changed:
        raise RatesError(f"价格版本 v{version} 没有可回滚的变更记录")

    targets: dict[str, dict[str, float]] = {}
    for model_id, pair in changed.items():
        model = get_model(model_id)
        if model is None:
            raise RatesError(f"车型ID不存在：{model_id}（车辆型号库可能被手工改过）")
        past = pair.get("before") or {}
        targets[model_id] = {
            "base_rate_vnd_per_km": float(past.get("base_rate_vnd_per_km", model.base_rate_vnd_per_km)),
            "fixed_surcharge_vnd": float(past.get("fixed_surcharge_vnd", model.fixed_surcharge_vnd)),
        }

    def _same_as_current() -> bool:
        for model_id, values in targets.items():
            model = get_model(model_id)
            if model is None:
                return False
            if abs(float(model.base_rate_vnd_per_km) - values["base_rate_vnd_per_km"]) > 1e-6:
                return False
            if abs(float(model.fixed_surcharge_vnd) - values["fixed_surcharge_vnd"]) > 1e-6:
                return False
        return True

    if _same_as_current():
        previous = [
            int(item.get("version") or 0)
            for item in load_versions_data()["versions"]
            if int(item.get("rolled_back_from") or -1) == int(version)
        ]
        return {
            "ok": True,
            "version": previous[-1] if previous else int(version),
            "restored": {mid: dict(values) for mid, values in targets.items()},
            "noop": True,
            "csv_verified": True,
        }

    current = {
        model_id: {
            "base_rate_vnd_per_km": float(get_model(model_id).base_rate_vnd_per_km),
            "fixed_surcharge_vnd": float(get_model(model_id).fixed_surcharge_vnd),
        }
        for model_id in targets
    }
    write = update_model_rates(targets)
    new_record = append_version(
        scope=sorted(targets),
        changed={
            model_id: {"before": current[model_id], "after": targets[model_id]}
            for model_id in targets
        },
        samples=record.get("samples") or {},
        quality=record.get("quality") or {},
        operator=operator_name(),
        note=note or f"回滚至版本 v{version}",
        rolled_back_from=int(version),
    )
    return {
        "ok": True,
        "version": new_record["version"],
        "restored": {mid: dict(values) for mid, values in targets.items()},
        "noop": False,
        "csv_verified": True,
        "rolled_back_from": int(version),
        "paths": write["paths"],
        "backups": write["backups"],
    }


def _version_stats(model_ids: list[str]) -> tuple[dict, dict]:
    """价格版本留痕用的「样本数 + 拟合质量」（取各车型最差值，保守）。"""
    from app.services import calibration

    samples = list_samples()
    counts: dict[str, int] = {}
    rmse_values: list[float] = []
    error_values: list[float] = []
    for model_id in model_ids:
        usable = [
            s for s in samples
            if str(s.get("vehicle_model_id")) == model_id
            and str(s.get("loading_mode")) == "full_truck"
            and s.get("distance_km")
        ]
        counts[model_id] = len(usable)
        if not usable:
            continue
        try:
            resolved = [calibration.resolved_from_record(s) for s in usable]
            result = calibration.fit_full_truck_samples(resolved)
        except Exception:  # noqa: BLE001 —— 质量数据取不到就留空，不影响写盘
            continue
        rmse_values.append(float(result.rmse_vnd))
        median_error = calibration.median_abs_error_pct(resolved, result.predictions)
        if median_error is not None:
            error_values.append(float(median_error))
    quality = {
        "rmse_vnd": round(max(rmse_values)) if rmse_values else None,
        "median_error_pct": round(max(error_values), 2) if error_values else None,
    }
    return counts, quality
