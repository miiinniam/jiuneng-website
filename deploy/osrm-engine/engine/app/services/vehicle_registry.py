"""车辆型号库 —— 从 CSV 加载具体车型（5大类，每类多个具体型号）。

替代旧 presets.py 里的 VEHICLE_PRESETS + BODY_TYPE_PRESETS 两张表（那两张表描述的是
"吨位档位 × 车身类型"的抽象组合，本模块改为直接维护"具体真实车型"的清单，用户在
Excel 里手工维护 车辆型号库.csv，改完重启后端生效——不做热重载，见下方说明）。

CARGO_TYPE_RATES 不受影响，继续留在 presets.py。
"""

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.services._paths import vehicle_csv_path

VEHICLE_CATEGORIES = ("small_box", "flatbed", "high_side", "container", "cold_chain", "special")


@dataclass(frozen=True)
class VehicleModel:
    category: str
    model_id: str
    display_name: str
    max_load_ton: float
    volume_capacity_m3: float | None
    length_m: float | None
    width_m: float | None
    height_m: float | None
    base_rate_vnd_per_km: float
    fuel_l_per_100km: float
    fuel_penalty: float
    fixed_surcharge_vnd: float
    toll_rate_vnd_per_km: float
    osrm_profile: str
    suitable_cargo_types: tuple[str, ...]
    notes: str
    # 🆕 载荷能力字段（2026-08-09）——带默认值，向后兼容旧构造方式
    max_cargo_height_m: float | None = None  # 货物最大堆高（平板=道路限高-货台；厢式=内高）
    loading_efficiency: float = 0.90         # 装载效率系数（0-1）
    curb_weight_ton: float | None = None     # 裸车/整备重量（吨）——用户要求字段，值由车队数据提供
    # 🆕 2026-09-23：标准车型代码（《公路货运车辆超限超载认定标准》14 种组合）
    #   TR-02 2轴载货 / TR-0N-R 载货 / TR-0N-A 铰接列车 / TR-0N-C 中置轴挂车列车 / TR-0N-F 全挂汽车列车
    #   用途：3D 装车视图按标准车型画轴数、轴荷与超限判定同源；值由 scripts/_v015_add_axle_config.py 生成
    axle_config: str | None = None
    # 🆕 2026-09-29（v015.8 T6）：大件配车字段（专家 §3.3 字段缺口表）——全部带默认值，旧构造方式不受影响
    #   deck_height_m 台面高：总高 = 台面高 + 货高 + 垫木（0.12–0.15），大件的命门（§4.2b）
    deck_height_m: float | None = None
    axle_lines: int | None = None                # 轴线数（模块车拼轴 / 轴·天计价 / 桥涵验算）
    axle_load_per_line_t: float | None = None    # 单轴线轴荷上限（吨；公路口径 8–10 t/轴）
    deck_width_extendable_m: float | None = None # 侧伸后车宽（如 3.0 → 4.4 m）；不可侧伸留白
    couplable: bool | None = None                # 可否拼轴（模块车组合能力）
    min_turn_radius_m: float | None = None       # 最小转弯半径（进山路线可行性）
    rate_model: str | None = None                # 费率口径：per_km | per_trip | per_axle_day
    # 🆕 2026-09-29（v016 T-B）：越南 TT12/2025 Điều 15 与超载闸的 4 个数据底座字段 ——
    #   全部带默认值且**可空**（旧构造方式不受影响；留白是正常状态，不是错误）
    #   axle_count 轴数：列车总轴数（Điều 15 整车总质量表按轴数分档 / 中国《认定标准》轴数映射）；
    #     留白 ⇒ 调用方回落到 `axle_config` 的 `TR-0N` 数字
    axle_count: int | None = None
    #   wheelbase_m 首末轴中心距（m）：Điều 15「轴距每短 1m 减 2t」的输入（≤7 / >7m 分档）
    wheelbase_m: float | None = None
    #   saddle_to_first_axle_m 牵引销中心 → 半挂第一轴中心（m）：3.2–4.5 / 4.5–6.5 / >6.5m 分档
    saddle_to_first_axle_m: float | None = None
    #   registered_payload_ton **核定载质量（t）= 超载闸唯一真源**；留白 ⇒ 调用方回落 `max_load_ton`
    registered_payload_ton: float | None = None

    @property
    def floor_area_m2(self) -> float | None:
        """地板面积 = 长 × 宽（用于平板车/长件面积约束）。"""
        if self.length_m and self.width_m:
            return self.length_m * self.width_m
        return None

    @property
    def effective_volume_m3(self) -> float | None:
        """有效容积：厢式车用 volume_capacity_m3；平板车用 面积×堆高×效率。"""
        if self.volume_capacity_m3:
            return self.volume_capacity_m3
        area = self.floor_area_m2
        if area and self.max_cargo_height_m:
            return area * self.max_cargo_height_m
        return None


class VehicleRegistryError(ValueError):
    pass


def _resolve_csv_path() -> Path:
    env_override = os.getenv("VEHICLE_REGISTRY_CSV_PATH")
    if env_override:
        return Path(env_override)
    # 桌面版：资源根下的车辆型号库.csv（Electron 通过 OSRM_RESOURCE_DIR 指向用户数据目录）
    resource_csv = vehicle_csv_path()
    if resource_csv.exists():
        return resource_csv
    # Docker 镜像内：backend/Dockerfile 已 COPY 车辆型号库.csv 到 /app/
    docker_candidate = Path("/app/车辆型号库.csv")
    if docker_candidate.exists():
        return docker_candidate
    # 原生运行：backend/app/services/vehicle_registry.py -> parents[3] == OSRM++/
    # 车辆型号库是正算/反算共用的车辆主数据，不属于"反算专属"，单独放在 车辆型号库/
    # 目录（不在 公式反算文件/ 里，那个目录只放反算相关的技能文档和样本数据）。
    return Path(__file__).resolve().parents[3] / "车辆型号库" / "车辆型号库.csv"


def _parse_float(value: str) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def _parse_int(value: str) -> int | None:
    value = (value or "").strip()
    return int(float(value)) if value else None


#: 费率口径合法集（专家 §3.3 / §5.1：常规件 per_km；大件 per_trip（含底价）；模块车 per_trip + per_axle_day）
RATE_MODELS: tuple[str, ...] = ("per_km", "per_trip", "per_axle_day")

_COUPLABLE_TRUE = frozenset({"1", "yes", "y", "true"})
_COUPLABLE_FALSE = frozenset({"0", "no", "n", "false"})


def _parse_couplable(raw: str | None):
    """`couplable`（可否拼轴）：yes/no → True/False，留白 → None。

    未识别的值**原样返回**（不在这里抛异常），由 `_validate()` 统一报错 —— 与 axle_config 同一套路。
    """
    v = (raw or "").strip().lower()
    if not v:
        return None
    if v in _COUPLABLE_TRUE:
        return True
    if v in _COUPLABLE_FALSE:
        return False
    return v


def _parse_rate_model(raw: str | None) -> str | None:
    """`rate_model`（费率口径）：统一小写；留白 → None；非法值原样返回，由 `_validate()` 报错。"""
    return (raw or "").strip().lower() or None


def _parse_optional_float(raw: str | None):
    """v016 T-B 的可空数值列（`wheelbase_m` / `saddle_to_first_axle_m` / `registered_payload_ton`）。

    * **留白（空/空白/缺列）→ `None`**：这 4 列是可空列，「没有数据」是正常状态，绝不是错误
      （旧格式 CSV 没有这些列，`.get()` 给 `None` 也必须能读）；
    * 数字 → `float`；
    * 坏值 → **原样返回字符串**，交给 `_validate()` 统一报错（与 `_parse_couplable` /
      `_parse_axle_config` 同一套路：解析层不抛难以定位的异常，报错文案要点名车型 + 列 + 原值）。
    """
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return text


def _parse_optional_int(raw: str | None):
    """`axle_count`：留白 → `None`；整数 → `int`；非整数（如 `6.5`）或坏值 → 原样返回，由 `_validate()` 报错。"""
    value = _parse_optional_float(raw)
    if value is None or isinstance(value, str):
        return value
    return int(value) if float(value).is_integer() else (raw or "").strip()


def _validate(models: list["VehicleModel"]) -> None:
    seen_ids: set[str] = set()
    categories_present: set[str] = set()
    for m in models:
        if m.model_id in seen_ids:
            raise VehicleRegistryError(f"车辆型号库存在重复的 model_id: {m.model_id}")
        seen_ids.add(m.model_id)
        if m.category not in VEHICLE_CATEGORIES:
            raise VehicleRegistryError(
                f"车型「{m.model_id}」的 category「{m.category}」不在合法枚举内: {VEHICLE_CATEGORIES}"
            )
        categories_present.add(m.category)
        # 🆕 2026-09-23：标准车型代码格式校验（空值允许留白）
        if m.axle_config and not _AXLE_CONFIG_RE.match(m.axle_config):
            raise VehicleRegistryError(
                f"车型「{m.model_id}」的 axle_config「{m.axle_config}」格式非法："
                f"应为 TR-02 或 TR-0N-X（X ∈ C 中置轴 / A 铰接 / R 载货 / F 全挂）"
            )
        # 🆕 2026-09-29（v015.8 T6）：rate_model / couplable 校验（空值允许留白）
        if m.rate_model and m.rate_model not in RATE_MODELS:
            raise VehicleRegistryError(
                f"车型「{m.model_id}」的 rate_model「{m.rate_model}」非法："
                f"应为 {' / '.join(RATE_MODELS)}（可留白）"
            )
        if m.couplable is not None and not isinstance(m.couplable, bool):
            raise VehicleRegistryError(
                f"车型「{m.model_id}」的 couplable「{m.couplable}」非法：应为 yes / no（可留白）"
            )
        # 🆕 2026-09-29（v016 T-B）：4 个新列的**容错**校验 ——
        #   留白（`None`）永远是合法状态（planner 各自回落：axle_count → axle_config 的 TR-0N；
        #   registered_payload_ton → max_load_ton；轴距留白 ⇒ 只按中国口径算并标注「越侧待补轴距」），
        #   只有「填了但填坏 / 填成非正数」才报错，且必须点名车型 + 列 + 原值。
        for column, value in (("axle_count", m.axle_count),
                              ("wheelbase_m", m.wheelbase_m),
                              ("saddle_to_first_axle_m", m.saddle_to_first_axle_m),
                              ("registered_payload_ton", m.registered_payload_ton)):
            if value is None:
                continue                              # ✅ 留白合法 —— 绝不因空值报错
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise VehicleRegistryError(
                    f"车型「{m.model_id}」的 {column}「{value}」非法：应为正数或留白"
                )
            if value != value or value in (float("inf"), float("-inf")) or value <= 0:
                raise VehicleRegistryError(
                    f"车型「{m.model_id}」的 {column} 必须 > 0（或留白）：{value}"
                )

    missing_categories = set(VEHICLE_CATEGORIES) - categories_present
    if missing_categories:
        raise VehicleRegistryError(
            f"以下车辆大类在车辆型号库里一个型号都没有，拼货自动匹配会永远选不到: {missing_categories}"
        )


#: 标准车型代码**全集**（《公路货运车辆超限超载认定标准》14 种组合）——
#  与 `desktop/renderer/js/vehicles3d.js` 的 `TYPES` 键逐字一致（跨源由
#  `backend/tests/test_axle_config.py::test_csv_codes_exist_in_vehicles3d_types` 锁住）。
#  为什么不用「格式级」正则 `^TR-0[2-6](-[CARF])?$`：它会放行标准里**并不存在**的组合
#  （TR-05-R / TR-06-R / TR-03-F / TR-0N 无后缀），手改 CSV 写错也没人拦。
AXLE_CONFIG_CODES: tuple[str, ...] = (
    "TR-02",
    "TR-03-R", "TR-03-A", "TR-03-C",
    "TR-04-R", "TR-04-A", "TR-04-C", "TR-04-F",
    "TR-05-A", "TR-05-C", "TR-05-F",
    "TR-06-A", "TR-06-C", "TR-06-F",
)
#: 由全集**派生**（单一来源，避免枚举与正则漂移）
_AXLE_CONFIG_RE = re.compile("^(?:" + "|".join(re.escape(c) for c in AXLE_CONFIG_CODES) + ")$")


def _parse_axle_config(raw: str | None) -> str | None:
    """解析标准车型代码：`TR-02`（2 轴载货）或 `TR-0N-X`（X ∈ C 中置轴 / A 铰接 / R 载货 / F 全挂）。

    空值返回 None（允许留白：中置轴/全挂暂无对应车型库条目）；格式非法则原样返回，
    由 `_validate()` 统一报错——避免在解析层抛出难以定位的异常。
    """
    v = (raw or "").strip().upper()
    return v or None


def _load_registry(csv_path: Path) -> list[VehicleModel]:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"车辆型号库 CSV 不存在: {csv_path}（原生运行检查相对路径，"
            f"容器内检查 VEHICLE_REGISTRY_CSV_PATH 环境变量和挂载）"
        )
    models = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            models.append(
                VehicleModel(
                    category=row["category"].strip(),
                    model_id=row["model_id"].strip(),
                    display_name=row["display_name"].strip(),
                    max_load_ton=float(row["max_load_ton"]),
                    volume_capacity_m3=_parse_float(row["volume_capacity_m3"]),
                    length_m=_parse_float(row["length_m"]),
                    width_m=_parse_float(row["width_m"]),
                    height_m=_parse_float(row["height_m"]),
                    max_cargo_height_m=_parse_float(row.get("max_cargo_height_m")),
                    loading_efficiency=float(row.get("loading_efficiency") or 0.90),
                    curb_weight_ton=_parse_float(row.get("curb_weight_ton")),
                    base_rate_vnd_per_km=float(row["base_rate_vnd_per_km"]),
                    fuel_l_per_100km=float(row["fuel_l_per_100km"]),
                    fuel_penalty=float(row["fuel_penalty"] or 0),
                    fixed_surcharge_vnd=float(row["fixed_surcharge_vnd"] or 0),
                    toll_rate_vnd_per_km=float(row["toll_rate_vnd_per_km"] or 0),
                    osrm_profile=row["osrm_profile"].strip(),
                    suitable_cargo_types=tuple(
                        t.strip() for t in row["suitable_cargo_types"].split(";") if t.strip()
                    ),
                    notes=row["notes"].strip(),
                    axle_config=_parse_axle_config(row.get("axle_config")),
                    # 🆕 2026-09-29（v015.8 T6）：大件配车 7 列（`.get` 保证旧格式 CSV 也能读）
                    deck_height_m=_parse_float(row.get("deck_height_m")),
                    axle_lines=_parse_int(row.get("axle_lines")),
                    axle_load_per_line_t=_parse_float(row.get("axle_load_per_line_t")),
                    deck_width_extendable_m=_parse_float(row.get("deck_width_extendable_m")),
                    couplable=_parse_couplable(row.get("couplable")),
                    min_turn_radius_m=_parse_float(row.get("min_turn_radius_m")),
                    rate_model=_parse_rate_model(row.get("rate_model")),
                    # 🆕 2026-09-29（v016 T-B）：4 个新列（`.get` 保证 27 列旧格式 CSV 也能读）
                    axle_count=_parse_optional_int(row.get("axle_count")),
                    wheelbase_m=_parse_optional_float(row.get("wheelbase_m")),
                    saddle_to_first_axle_m=_parse_optional_float(row.get("saddle_to_first_axle_m")),
                    registered_payload_ton=_parse_optional_float(row.get("registered_payload_ton")),
                )
            )
    _validate(models)
    return models


_CSV_PATH = _resolve_csv_path()
try:
    VEHICLE_MODELS: list[VehicleModel] = _load_registry(_CSV_PATH)
except FileNotFoundError:
    import logging
    logging.getLogger(__name__).warning("车辆型号库CSV不存在，使用空列表降级")
    VEHICLE_MODELS = []
VEHICLE_MODEL_INDEX: dict[str, VehicleModel] = {m.model_id: m for m in VEHICLE_MODELS}


def reload_registry() -> list[VehicleModel]:
    """🆕 v009：重新解析 CSV 路径并热重载车型库（改完费率不用重启后端）。

    必须**就地**刷新 `VEHICLE_MODELS` / `VEHICLE_MODEL_INDEX`：`cost_engine.py` 等模块用
    `from ... import VEHICLE_MODELS` 直接持有列表对象，重新赋值全局变量会让它们继续看旧库。

    解析失败（文件缺失/列缺失/校验不过）→ **保留旧缓存**并抛出可读异常 ——
    一次坏写入绝不能把车型库清空（那会让所有报价 500）。
    """
    global _CSV_PATH
    csv_path = _resolve_csv_path()
    try:
        models = _load_registry(csv_path)
    except FileNotFoundError as exc:
        raise VehicleRegistryError(f"车辆型号库重载失败（已保留旧缓存）：{exc}") from exc
    except (KeyError, ValueError) as exc:
        raise VehicleRegistryError(f"车辆型号库重载失败（已保留旧缓存）：{csv_path.name} 解析异常：{exc}") from exc
    _CSV_PATH = csv_path
    VEHICLE_MODELS[:] = models
    VEHICLE_MODEL_INDEX.clear()
    VEHICLE_MODEL_INDEX.update({m.model_id: m for m in models})
    return models


def get_model(model_id: str) -> VehicleModel | None:
    return VEHICLE_MODEL_INDEX.get(model_id)


def profile_for_model(model_id: str | None) -> str | None:
    """🆕 v015.4：车型 → OSRM profile（车辆型号库.csv 的 `osrm_profile` 列，如 truck / driving）。

    这是「地图路线按车型」的**唯一取值口**：型号库里 39 款车声明 truck、3 个小厢货声明 driving
    （v015.8 起共 42 款）。
    未指定车型 / 车型库里没有该 model_id / 该列为空 → 返回 None，
    调用方（api/route.py）据此走全局默认 profile（保持 v015.4 之前的零回归行为）。
    """
    if not model_id:
        return None
    model = VEHICLE_MODEL_INDEX.get(model_id)
    if model is None:
        return None
    profile = (model.osrm_profile or "").strip().lower()
    return profile or None


def models_by_category() -> dict[str, list[VehicleModel]]:
    result: dict[str, list[VehicleModel]] = {c: [] for c in VEHICLE_CATEGORIES}
    for m in VEHICLE_MODELS:
        result[m.category].append(m)
    return result
