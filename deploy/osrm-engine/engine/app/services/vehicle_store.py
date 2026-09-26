"""v011 车辆库写入（型号级 CRUD）。

写盘铁律（**复用 `rates_store` 既有通道，不发明第二套**）：

1. 先在内存里算出「每个目标文件的完整新内容」并校验 → 任何校验不过都在**动盘之前**抛错；
2. `.bak` 备份 → `rates_store._write_csv_rows()`（utf-8-sig 保 BOM + CRLF + DictWriter + 原子替换）；
3. 写回后**逐行读回比对**（行数 + 每个单元格）→ 再比对**双份 md5 一致**；
4. 任何一步失败 → 用备份还原**所有**目标文件，再把异常抛成 `VehicleStoreError`（中文，可直接给前端看）；
5. 成功 → `vehicle_registry.reload_registry()`（**就地**刷新 `VEHICLE_MODELS`；重新赋值无效，
   因为 `cost_engine` 等模块是 `from ... import VEHICLE_MODELS` 持有列表对象）→ 追加审计行。

⚠️ 序列化格式（侦察结论，别猜）：`suitable_cargo_types` 列在磁盘上是**分号分隔**的字符串
（`normal;other`），**不是** JSON 数组；`vehicle_registry._load_registry()` 就是 `split(";")` 读的。
数值列原样存文本（`3.0` 不能退化成 `3`）—— 所以「值没变」时必须**保留磁盘原文**，
否则一次 no-op 写入就会改动主数据字节
（`tests/test_vehicle_store.py::test_roundtrip_noop_update_keeps_bytes_identical`）。

口径边界：`floor_area_m2` / `effective_volume_m3` 是 `VehicleModel` 的**派生属性**，不是 CSV 列，
任何写入都拒绝（否则会被 `DictWriter(extrasaction="ignore")` 静默丢弃，形成"看似改了、其实没改"）。
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.services import rates_store as rs
from app.services.presets import CARGO_TYPE_RATES
from app.services.vehicle_registry import (
    VEHICLE_CATEGORIES,
    VEHICLE_MODELS,
    _AXLE_CONFIG_RE,
    reload_registry as _reload_registry,
)

#: 车辆型号库 CSV 的规范列（= 真实文件表头，逐列同序）—— 模板/导入校验的基准
CSV_COLUMNS: tuple[str, ...] = (
    "category",
    "model_id",
    "display_name",
    "max_load_ton",
    "volume_capacity_m3",
    "length_m",
    "width_m",
    "height_m",
    "base_rate_vnd_per_km",
    "fuel_l_per_100km",
    "fuel_penalty",
    "fixed_surcharge_vnd",
    "toll_rate_vnd_per_km",
    "osrm_profile",
    "suitable_cargo_types",
    "notes",
    "max_cargo_height_m",
    "loading_efficiency",
    "curb_weight_ton",
    # 🆕 2026-09-23：标准车型代码（14 种组合之一）——必须在此列白名单内，
    #   否则 DictWriter(extrasaction="ignore") 会在任何一次写入时把这一列静默丢掉
    "axle_config",
)

#: 数值列：写入时做「非数字 / 负数」校验；值未变时保留原文
_NUMERIC_COLUMNS: frozenset[str] = frozenset({
    "max_load_ton", "volume_capacity_m3", "length_m", "width_m", "height_m",
    "max_cargo_height_m", "base_rate_vnd_per_km", "fuel_l_per_100km", "fuel_penalty",
    "fixed_surcharge_vnd", "toll_rate_vnd_per_km", "loading_efficiency", "curb_weight_ton",
})

#: 必须严格 > 0 的数值列（其余只要 ≥ 0）
_POSITIVE_COLUMNS: frozenset[str] = frozenset({"max_load_ton", "length_m", "width_m", "height_m"})

#: 新增车型必填（`vehicle_registry._load_registry()` 会直接取这些键，缺一个就整库解析失败）
_REQUIRED_ON_CREATE: tuple[str, ...] = (
    "category", "model_id", "display_name", "max_load_ton",
    "base_rate_vnd_per_km", "fuel_l_per_100km", "osrm_profile",
)

#: 新增时缺省值（让新行的键齐全，避免 registry 取键 KeyError）
_CREATE_DEFAULTS: dict[str, str] = {
    "fuel_penalty": "0",
    "fixed_surcharge_vnd": "0",
    "toll_rate_vnd_per_km": "0",
    "suitable_cargo_types": "",
    "notes": "",
    "axle_config": "",          # 🆕 标准车型代码：新增时可留白，之后由车型库编辑/脚本补
}

#: model_id 合法形式（小写字母 / 数字 / 下划线）
MODEL_ID_RE = re.compile(r"^[a-z0-9_]+$")

#: 导入时至少要认出的列
_IMPORT_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"category", "model_id", "display_name", "max_load_ton", "base_rate_vnd_per_km"}
)

#: 模板示例行（注释行提示导入前删除；品类取得全，直接导入不会让任何大类归零）
_TEMPLATE_EXAMPLES: tuple[dict[str, str], ...] = (
    {
        "category": "small_box", "model_id": "example_small_box", "display_name": "示例：小卡车 1.5吨厢货",
        "max_load_ton": "1.5", "volume_capacity_m3": "8", "length_m": "3.0", "width_m": "1.6",
        "height_m": "1.7", "base_rate_vnd_per_km": "8000", "fuel_l_per_100km": "7.0",
        "fuel_penalty": "0", "fixed_surcharge_vnd": "1500000", "toll_rate_vnd_per_km": "0",
        "osrm_profile": "driving", "suitable_cargo_types": "normal;other",
        "notes": "示例行：导入前请删除", "max_cargo_height_m": "1.7",
        "loading_efficiency": "0.90", "curb_weight_ton": "",
    },
    {
        "category": "flatbed", "model_id": "example_flatbed", "display_name": "示例：平板车 13m",
        "max_load_ton": "25", "volume_capacity_m3": "", "length_m": "13.0", "width_m": "2.4",
        "height_m": "2.0", "base_rate_vnd_per_km": "18000", "fuel_l_per_100km": "28.0",
        "fuel_penalty": "0", "fixed_surcharge_vnd": "2000000", "toll_rate_vnd_per_km": "0",
        "osrm_profile": "driving", "suitable_cargo_types": "oversized;heavy_equipment",
        "notes": "示例行：导入前请删除", "max_cargo_height_m": "2.0",
        "loading_efficiency": "0.90", "curb_weight_ton": "",
    },
)

#: mutate 处理器签名：吃 (path, header, rows) → 返回 (header, rows)
Mutate = Callable[[Path, list[str], list[dict]], tuple[list[str], list[dict]]]


class VehicleStoreError(Exception):
    """写入被拒（校验 / 删除保护 / md5 漂移 / 回滚）。

    message 是**中文可读**的，可直接给前端或接口原样返回。
    """


# ══════════════════════════ 可 monkeypatch 的钩子 ══════════════════════════

def csv_write_targets() -> list[Path]:
    """要写的车辆型号库路径（测试把它 monkeypatch 到临时目录）。"""
    return rs.csv_write_targets()


def reload_registry() -> list:
    """就地热重载车型库（测试可 monkeypatch；见 `vehicle_registry.reload_registry`）。"""
    return _reload_registry()


def reload_registry_fn() -> list:      #: 兼容别名（T5 路由 / 旧调用方）
    return reload_registry()


def audit_path() -> Path:
    """审计落点：`backend/data/vehicle_audit.jsonl`（测试 monkeypatch 到 tmp）。"""
    return Path(__file__).resolve().parents[2] / "data" / "vehicle_audit.jsonl"


# ══════════════════════════ 单元格 ↔ 值 转换 ══════════════════════════

def _cell_to_value(column: str, cell: str | None):
    """磁盘文本 → 给前端/调用方的值（数值列转数字，货型列转列表，其余原样）。

    * 空数值单元 → `None`（不是 0！「没有」和「零」必须分得清）；
    * 数字文本 → `int`（整数值，如 `8000`）或 `float`（`1.5`）；
    * 坏数据（数值列里塞了非数字）→ 原样返回字符串，绝不在这里抛异常。
    """
    text = "" if cell is None else str(cell)
    if column in _NUMERIC_COLUMNS:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            number = float(stripped)
        except ValueError:
            return text
        if number.is_integer() and abs(number) < 2 ** 53:
            return int(number)
        return number
    if column == "suitable_cargo_types":
        return [t.strip() for t in text.split(";") if t.strip()]
    return text


def _coerce_cell(column: str, value, current: str | None) -> str:
    """payload 值 → 写盘文本。**值没变时返回磁盘原文**（no-op 写入不得改字节）。"""
    current_text = "" if current is None else str(current)

    if column == "category":
        category = "" if value is None else str(value).strip()
        if category not in VEHICLE_CATEGORIES:
            raise VehicleStoreError(
                f"category 非法：{category or '空'}（可选 {list(VEHICLE_CATEGORIES)}）"
            )
        return category

    if column in _NUMERIC_COLUMNS:
        if value is None or (isinstance(value, str) and not value.strip()):
            return current_text                       # 不传 = 不改
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            raise VehicleStoreError(f"{column} 必须是数字：{value!r}") from None
        if number != number or number in (float("inf"), float("-inf")):
            raise VehicleStoreError(f"{column} 不是有效数字：{value!r}")
        if number < 0:
            raise VehicleStoreError(f"{column} 不能为负：{number:g}")
        if column in _POSITIVE_COLUMNS and number <= 0:
            raise VehicleStoreError(f"{column} 必须 > 0：{number:g}")
        if column == "loading_efficiency" and number > 1:
            raise VehicleStoreError(f"loading_efficiency 必须在 (0, 1] 之间：{number:g}")
        try:
            stored = float(current_text.strip())
        except ValueError:
            stored = None
        if stored is not None and stored == number:
            return current_text                       # 数值没变 → 保留原文（"3.0" 不退化成 "3"）
        return rs._format_number(number)

    if column == "suitable_cargo_types":
        if value is None or (isinstance(value, str) and not value.strip()):
            return current_text
        if isinstance(value, str):
            items = [t.strip() for t in value.split(";") if t.strip()]
        elif isinstance(value, (list, tuple, set)):
            items = [str(t).strip() for t in value if str(t).strip()]
        else:
            raise VehicleStoreError(f"suitable_cargo_types 必须是列表或分号分隔字符串：{value!r}")
        unknown = [t for t in items if t not in CARGO_TYPE_RATES]
        if unknown:
            raise VehicleStoreError(
                f"suitable_cargo_types 含未知货型：{unknown}（可选 {list(CARGO_TYPE_RATES)}）"
            )
        if [t.strip() for t in current_text.split(";") if t.strip()] == items:
            return current_text                       # 内容顺序都没变 → 保留原文
        return ";".join(items)

    if column == "axle_config":
        if value is None or (isinstance(value, str) and not value.strip()):
            return current_text                       # 不传 / 传空 = 不改（留白合法：中置轴·全挂暂无车型）
        code = str(value).strip().upper()
        if not _AXLE_CONFIG_RE.match(code):
            raise VehicleStoreError(
                f"axle_config 格式非法：{code}（应为 TR-02 或 TR-0N-X，"
                f"X ∈ C 中置轴 / A 铰接 / R 载货 / F 全挂）"
            )
        return current_text if code == current_text.strip().upper() else code

    if value is None:
        return current_text
    return str(value)


def _sane_row(row: dict, header: list[str]) -> dict:
    """行 dict 补齐成「表头全列 + 全字符串」（DictReader 短行会给 None，逐行比对会误判）。"""
    return {column: ("" if row.get(column) is None else str(row.get(column))) for column in header}


# ══════════════════════════ 读 ══════════════════════════

def _read_header(path: Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        raise VehicleStoreError(
            f"车辆型号库.csv 不存在：{path}（请检查 OSRM_RESOURCE_DIR / 部署布局）"
        )
    header, _ = rs._read_csv_rows(path)
    if not header:
        raise VehicleStoreError(f"{path.name} 表头为空，拒绝读写")
    return header


def list_models() -> list[dict]:
    """读**当前磁盘**的车辆库（不是内存注册表），供后台面板编辑。"""
    path = csv_write_targets()[0]
    header, rows = rs._read_csv_rows(path)
    return [{column: _cell_to_value(column, row.get(column)) for column in header} for row in rows]


def export_csv() -> str:
    """导出当前 CSV 原文（utf-8 BOM，Excel 双击可编辑）。

    ⚠️ 必须走 `read_bytes().decode()`：`read_text()` 在 Windows 上做**通用换行翻译**，
    会把 `\\r\\n` 变成 `\\n` —— 导出的文件就和磁盘真源不是一个字节了。
    """
    path = Path(csv_write_targets()[0])
    if not path.exists():
        raise VehicleStoreError(f"车辆型号库.csv 不存在：{path}")
    return "\ufeff" + path.read_bytes().decode("utf-8-sig")


def template_csv() -> str:
    """下载模板：规范表头 + 2 行示例 + 注释行（`#` 开头，导入时忽略）。"""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), lineterminator="\r\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in _TEMPLATE_EXAMPLES:
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    buffer.write("# 本行是注释，导入时会被忽略；上面 2 行是示例，导入前请删除\r\n")
    return "\ufeff" + buffer.getvalue()


# ══════════════════════════ 校验 ══════════════════════════

def _rows_problems(rows: list[dict], header: list[str]) -> list[str]:
    """整库不变量检查（与 `vehicle_registry._validate()` 同口径 + 数值可解析）。

    返回问题清单；空列表 = 可以写盘。**写盘前**对「即将写入的内容」跑一遍，
    非法内容永远到不了磁盘。
    """
    problems: list[str] = []
    missing_columns = [c for c in ("category", "model_id", "max_load_ton",
                                   "base_rate_vnd_per_km", "fuel_l_per_100km")
                       if c not in header]
    if missing_columns:
        problems.append(f"表头缺少必需列 {missing_columns}")
    seen: set[str] = set()
    per_category: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        model_id = str(row.get("model_id", "")).strip()
        category = str(row.get("category", "")).strip()
        label = model_id or f"第 {index} 行"
        if not model_id:
            problems.append(f"第 {index} 行 model_id 为空")
        elif model_id in seen:
            problems.append(f"第 {index} 行 model_id 重复：{model_id}")
        seen.add(model_id)
        if category not in VEHICLE_CATEGORIES:
            problems.append(f"{label} 的 category 非法：{category or '空'}")
        else:
            per_category[category] = per_category.get(category, 0) + 1
        for column in ("max_load_ton", "base_rate_vnd_per_km", "fuel_l_per_100km"):
            text = str(row.get(column, "")).strip()
            if not text:
                problems.append(f"{label} 的 {column} 为空")
                continue
            try:
                float(text)
            except ValueError:
                problems.append(f"{label} 的 {column} 不是数字：{text!r}")
        unknown_types = [t.strip() for t in str(row.get("suitable_cargo_types", "")).split(";")
                         if t.strip() and t.strip() not in CARGO_TYPE_RATES]
        if unknown_types:
            problems.append(f"{label} 的 suitable_cargo_types 含未知货型：{unknown_types}")
    empty_categories = [c for c in VEHICLE_CATEGORIES if not per_category.get(c)]
    if empty_categories:
        problems.append(f"以下车辆大类一个型号都没有：{empty_categories}")
    return problems


def _check_keys(payload: dict, header: list[str]) -> None:
    unknown = sorted(k for k in payload if k not in header)
    if unknown:
        raise VehicleStoreError(
            "不可编辑字段：" + ", ".join(unknown)
            + f"（可改列：{', '.join(c for c in header if c != 'model_id')}）"
        )


def _find(rows: list[dict], model_id: str) -> dict | None:
    return next((row for row in rows if str(row.get("model_id", "")).strip() == model_id), None)


# ══════════════════════════ 写（备份 → 写 → 校验 → 失败回滚） ══════════════════════════

def _write_rows(path: Path, header: list[str], rows: list[dict]) -> None:
    """唯一写盘出口（测试会 monkeypatch 它来模拟「第二份被写坏」）。"""
    rs._write_csv_rows(path, header, rows)


def _commit(*, mutate: Mutate) -> dict:
    """把 `mutate(path, header, rows)` 的意图落到**所有**目标文件上。

    成功返回 `{"md5", "count", "paths", "rows"}`；失败**保证**所有目标文件已还原到写前状态，
    并抛 `VehicleStoreError`。审计由调用方在写盘后再写（审计失败不回滚已成功的数据）。
    """
    targets = [Path(p) for p in csv_write_targets()]
    existing = [p for p in targets if p.exists()]
    if not existing:
        raise VehicleStoreError(
            "车辆型号库.csv 不存在，无法写入（请检查 OSRM_RESOURCE_DIR / 部署布局）"
        )

    # ① 先在内存里算好每个文件的新内容 + 校验（此阶段失败 = 一个字节都没动）
    plans: list[tuple[Path, list[str], list[dict]]] = []
    for path in existing:
        header, rows = rs._read_csv_rows(path)
        if not header:
            raise VehicleStoreError(f"{path.name} 表头为空，拒绝写入")
        rows = [_sane_row(row, header) for row in rows]
        new_header, new_rows = mutate(path, list(header), rows)
        if list(new_header) != list(header):
            raise VehicleStoreError(f"内部错误：{path.name} 表头被改（表头不参与 CRUD）")
        new_rows = [_sane_row(row, header) for row in new_rows]
        problems = _rows_problems(new_rows, header)
        if problems:
            raise VehicleStoreError("写盘前校验未通过（未改动任何文件）：" + "；".join(problems))
        plans.append((path, list(header), new_rows))

    backups: list[tuple[Path, Path]] = []
    try:
        for path, _, _ in plans:
            backup = path.with_name(path.name + ".bak")
            shutil.copy2(path, backup)
            backups.append((path, backup))

        for path, header, new_rows in plans:
            _write_rows(path, header, new_rows)
            _, written = rs._read_csv_rows(path)
            if len(written) != len(new_rows):
                raise VehicleStoreError(
                    f"{path.name} 写回后行数从 {len(new_rows)} 变成 {len(written)}，已回滚"
                )
            for got, want in zip(written, new_rows):
                got_row, want_row = _sane_row(got, header), _sane_row(want, header)
                if got_row != want_row:
                    raise VehicleStoreError(
                        f"{path.name} 写回后内容与预期不符（车型 {want_row.get('model_id')}），已回滚"
                    )

        digests = {str(path): rs._md5(path) for path, _, _ in plans}
        if len(set(digests.values())) != 1:
            raise VehicleStoreError(
                "两份车辆型号库.csv 写完后 md5 不一致（双份漂移），已用备份回滚本次写入："
                + ", ".join(f"{Path(k).name}={v[:8]}" for k, v in digests.items())
            )

        try:
            reload_registry()                          # 就地刷新，报价立刻用上新库
        except Exception as exc:                       # noqa: BLE001
            raise VehicleStoreError(f"写盘后车辆库热重载失败（已回滚）：{exc}") from exc
        if not VEHICLE_MODELS:
            raise VehicleStoreError("写盘后车辆库为空，已回滚")
    except Exception as exc:                           # noqa: BLE001
        for path, backup in backups:
            try:
                shutil.copy2(backup, path)
            except OSError:
                pass
        try:
            reload_registry()
        except Exception:                              # noqa: BLE001 —— 回滚尽力而为
            pass
        if isinstance(exc, VehicleStoreError):
            raise
        raise VehicleStoreError(f"写入失败已回滚：{exc}") from exc

    return {
        "ok": True,
        "md5": digests,
        "count": len(plans[0][2]),
        "paths": [str(path) for path, _, _ in plans],
        "rows": [dict(row) for row in plans[0][2]],
    }


def _audit(*, action: str, model_id: str, before, after, md5: dict, extra: dict | None = None) -> None:
    """追加审计行（尽力而为：审计写失败不回滚已成功落盘的写动作）。"""
    try:
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "operator": rs.operator_name(),
            "action": action,
            "model_id": model_id,
            "before": before,
            "after": after,
            "md5": md5,
        }
        record.update(extra or {})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:                                  # noqa: BLE001
        pass


def _row_of(model_id: str) -> dict | None:
    return _find(list_models(), model_id)


# ══════════════════════════ CRUD ══════════════════════════

def update_model(model_id: str, payload: dict) -> dict:
    """改一个车型的参数。返回写盘后**重新读回**的该行（数值列已是数字类型）。"""
    model_id = str(model_id or "").strip()
    if not model_id:
        raise VehicleStoreError("model_id 不能为空")
    payload = dict(payload or {})
    header = _read_header(csv_write_targets()[0])
    _check_keys(payload, header)
    if "model_id" in payload and str(payload["model_id"]).strip() != model_id:
        raise VehicleStoreError(
            f"不能修改 model_id（{model_id} → {payload['model_id']}）：model_id 是主键，"
            "如需改名请先新增再删除"
        )
    before_row = _row_of(model_id)
    if before_row is None:
        raise VehicleStoreError(f"车型不存在：{model_id}")

    edits = {key: value for key, value in payload.items() if key != "model_id"}

    def mutate(path: Path, header_: list[str], rows: list[dict]):
        found = False
        out: list[dict] = []
        for row in rows:
            if str(row.get("model_id", "")).strip() != model_id:
                out.append(row)
                continue
            if found:                              # 主数据里已有重复主键 → 先修数据
                raise VehicleStoreError(f"车辆型号库里存在重复的 model_id：{model_id}，请先修数据")
            found = True
            new_row = dict(row)
            for column, value in edits.items():
                new_row[column] = _coerce_cell(column, value, row.get(column, ""))
            out.append(new_row)
        if not found:
            raise VehicleStoreError(f"车型不存在：{model_id}")
        return header_, out

    result = _commit(mutate=mutate)
    after_row = _row_of(model_id)
    _audit(action="update", model_id=model_id, before=before_row, after=after_row,
           md5=result["md5"], extra={"changed": sorted(edits)})
    return after_row or {}


def create_model(payload: dict) -> dict:
    """新增一个车型（model_id 为主键，必须唯一且形如 `[a-z0-9_]+`）。"""
    payload = dict(payload or {})
    model_id = str(payload.get("model_id") or "").strip()
    if not model_id:
        raise VehicleStoreError("model_id 不能为空")
    if not MODEL_ID_RE.match(model_id):
        raise VehicleStoreError(f"model_id 只能用「小写字母 / 数字 / 下划线」：{model_id!r}")
    header = _read_header(csv_write_targets()[0])
    _check_keys(payload, header)
    if _row_of(model_id) is not None:
        raise VehicleStoreError(f"model_id 已存在：{model_id}")
    missing = [k for k in _REQUIRED_ON_CREATE
               if not str(payload.get(k) if payload.get(k) is not None else "").strip()]
    if missing:
        raise VehicleStoreError(f"缺少必填字段：{', '.join(missing)}")
    _coerce_cell("category", payload["category"], "")        # category 枚举校验（提前抛出）

    def mutate(path: Path, header_: list[str], rows: list[dict]):
        new_row = {column: "" for column in header_}
        for column in header_:
            if column == "model_id":
                new_row[column] = model_id
            elif column in payload and payload[column] is not None:
                new_row[column] = _coerce_cell(column, payload[column], "")
            elif column in _CREATE_DEFAULTS:
                new_row[column] = _CREATE_DEFAULTS[column]
        return header_, rows + [new_row]

    result = _commit(mutate=mutate)
    after_row = _row_of(model_id)
    _audit(action="create", model_id=model_id, before=None, after=after_row, md5=result["md5"])
    return after_row or {}


def delete_model(model_id: str) -> dict:
    """删除一个车型（**删除保护**：某大类删到 0 款 → 拒绝并说明原因）。"""
    model_id = str(model_id or "").strip()
    if not model_id:
        raise VehicleStoreError("model_id 不能为空")
    rows = list_models()
    target = _find(rows, model_id)
    if target is None:
        raise VehicleStoreError(f"车型不存在：{model_id}")
    same_category = [row for row in rows if row.get("category") == target.get("category")]
    if len(same_category) <= 1:
        raise VehicleStoreError(
            f"每个车辆大类至少保留 1 款车型：{target.get('category')} 删掉「{model_id}」"
            "后就一款不剩了（拼货匹配会永远选不到该类车）"
        )

    def mutate(path: Path, header_: list[str], rows_: list[dict]):
        kept = [row for row in rows_ if str(row.get("model_id", "")).strip() != model_id]
        if len(kept) == len(rows_):
            raise VehicleStoreError(f"车型不存在：{model_id}")
        return header_, kept

    result = _commit(mutate=mutate)
    _audit(action="delete", model_id=model_id, before=target, after=None,
           md5=result["md5"], extra={"category": target.get("category")})
    return {"ok": True, "action": "delete", "model_id": model_id, "md5": result["md5"],
            "count": result["count"]}


# ══════════════════════════ CSV 导入 ══════════════════════════

def _normalize_import_row(raw: dict) -> dict:
    """导入行 → 规范列 + 字符串（顺带做列级校验，抛 VehicleStoreError 即该行失败）。"""
    category = str(raw.get("category", "")).strip()
    if category not in VEHICLE_CATEGORIES:
        raise VehicleStoreError(f"category 非法：{category or '空'}（可选 {list(VEHICLE_CATEGORIES)}）")
    model_id = str(raw.get("model_id", "")).strip()
    if not model_id:
        raise VehicleStoreError("model_id 不能为空")
    if not MODEL_ID_RE.match(model_id):
        raise VehicleStoreError(f"model_id 只能用「小写字母 / 数字 / 下划线」：{model_id!r}")
    return {column: _coerce_cell(column, raw.get(column, ""), "") for column in CSV_COLUMNS}


def _parse_csv(text: str) -> tuple[list[dict], list[str]]:
    """解析导入文本 → (规范行, 失败原因清单)。失败行不挡合法行，但调用方会整体拒绝导入。"""
    raw_text = text or ""
    if not raw_text.strip():
        raise VehicleStoreError("文件是空的，没有可导入的内容")
    if raw_text[:2] == "PK" or "\x00" in raw_text[:200]:
        raise VehicleStoreError(
            "文件内容不是文本 CSV（可能是 .xlsx 直接改了后缀）。请用 Excel「另存为 CSV UTF-8」再导入。"
        )
    try:
        lines = [line for line in csv.reader(io.StringIO(raw_text.lstrip("\ufeff"), newline=""))]
    except csv.Error as exc:
        raise VehicleStoreError(f"CSV 解析失败：{exc}") from exc
    useful = [line for line in lines
              if any(str(cell).strip() for cell in line)
              and not str(line[0] or "").lstrip().startswith("#")]
    if not useful:
        raise VehicleStoreError("文件里没有可导入的内容（只有空行/注释行）")
    header = [str(cell).strip() for cell in useful[0]]
    if not _IMPORT_REQUIRED_COLUMNS.issubset(set(header)):
        raise VehicleStoreError(
            "表头无法识别，至少要包含这些列：" + ",".join(CSV_COLUMNS)
            + "（请先下载本系统的车辆库模板）"
        )
    parsed: list[dict] = []
    failures: list[str] = []
    seen: set[str] = set()
    for offset, line in enumerate(useful[1:], start=2):
        if len(line) < len(header):
            line = list(line) + [""] * (len(header) - len(line))
        raw_row = dict(zip(header, line))
        try:
            row = _normalize_import_row(raw_row)
        except VehicleStoreError as exc:
            failures.append(f"第 {offset} 行：{exc}")
            continue
        if row["model_id"] in seen:
            failures.append(f"第 {offset} 行：model_id 重复：{row['model_id']}")
            continue
        seen.add(row["model_id"])
        parsed.append(row)
    if not parsed and not failures:
        raise VehicleStoreError("文件里没有可导入的车型数据")
    return parsed, failures


def import_csv(text: str, *, mode: str = "merge") -> dict:
    """CSV 导入（**先全量校验，再写盘**；任何一行非法 → 一个字节都不写）。

    * `mode="merge"`：按 `model_id` 覆盖已有行（位置不变），新 id 追加到末尾；
    * `mode="replace"`：整表替换为导入内容（仍要过「每个大类 ≥ 1 款」等整库校验）。
    """
    if mode not in ("merge", "replace"):
        raise VehicleStoreError(f"mode 只能是 merge / replace，收到：{mode!r}")
    parsed, failures = _parse_csv(text)
    if failures:
        raise VehicleStoreError(
            f"导入内容有 {len(failures)} 行校验未通过（未改动任何文件）：" + "；".join(failures)
        )
    if not parsed:
        raise VehicleStoreError("文件里没有可导入的车型数据")

    rows = list_models()
    before_ids = {str(row.get("model_id", "")).strip() for row in rows}
    import_ids = {row["model_id"] for row in parsed}
    created = len(import_ids - before_ids)
    updated = len(import_ids & before_ids)
    removed = len(before_ids - import_ids) if mode == "replace" else 0

    def mutate(path: Path, header_: list[str], rows_: list[dict]):
        if mode == "replace":
            return header_, [dict(row) for row in parsed]
        incoming = {row["model_id"]: row for row in parsed}
        out: list[dict] = []
        placed: set[str] = set()
        for row in rows_:
            current_id = str(row.get("model_id", "")).strip()
            patch = incoming.get(current_id)
            if patch is None:
                out.append(row)
                continue
            merged = dict(row)
            for column in header_:
                if column in patch:
                    merged[column] = patch[column]
            out.append(merged)
            placed.add(current_id)
        for row in parsed:                                  # 新 id 追加（保持导入顺序）
            if row["model_id"] not in placed:
                out.append(dict(row))
        return header_, out

    result = _commit(mutate=mutate)
    _audit(action="import", model_id=f"{mode}:{len(parsed)}", before=None, after=None,
           md5=result["md5"], extra={"mode": mode, "created": created,
                                     "updated": updated, "removed": removed})
    result.update({"mode": mode, "total": len(parsed), "created": created,
                   "updated": updated, "removed": removed})
    return result
