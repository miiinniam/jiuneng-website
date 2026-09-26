"""Pydantic 请求/响应模型，字段对应 DEVELOPMENT_GOALS.md §8.2 的示例。

注：地理编码服务（地址 -> 经纬度）不在本阶段范围内，起点/终点直接传经纬度；
address 只是可选的展示字段，不会被后端解析。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str | None = None


class RouteInput(BaseModel):
    origin: LatLng
    destination: LatLng
    waypoints: list[LatLng] = Field(default_factory=list)
    border: LatLng | None = None  # 🆕 边境口岸（用于把路线拆成 中国段/越南段）


class CargoItemInput(BaseModel):
    """🆕 单件货物明细（可选）——用于长件/面积约束精确计算车辆数。

    不填则回退到 Level 1（仅重量+总体积判断）。
    stackable=False 表示不可堆叠（如变压器/设备），按地板面积计。
    """
    name: str = ""
    count: int = Field(default=1, ge=1)
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    height_m: float | None = None
    weight_kg: float | None = None
    stackable: bool = True


class CargoInput(BaseModel):
    weight_kg: float = Field(gt=0)
    volume_m3: float | None = None
    type: str = "normal"
    value_vnd: float | None = None  # 用于保险费计算
    items: list[CargoItemInput] = Field(default_factory=list)  # 🆕 单件明细


class VehicleInput(BaseModel):
    loading_mode: Literal["consolidated", "full_truck"]
    vehicle_model_id: str | None = None  # full_truck 必填，consolidated 忽略
    # 🆕 v015.4：显式指定 OSRM 路线 profile（如 "truck"）。给了就以它为准，
    # 否则按 vehicle_model_id 去车辆型号库取 osrm_profile 列；都没有 → 全局默认 driving。
    osrm_profile: str | None = None
    empty_return: bool = False
    need_loading: bool = False
    avoid_restricted_zones: bool = False
    avoid_construction_zones: bool = False
    via_mountain_road: bool = False
    via_port: bool = False

    @model_validator(mode="after")
    def _check_model_id_required_for_full_truck(self) -> "VehicleInput":
        if self.loading_mode == "full_truck" and not self.vehicle_model_id:
            raise ValueError("整车模式（full_truck）必须指定 vehicle_model_id")
        return self


class CostParamsInput(BaseModel):
    fuel_price_vnd: float | None = None
    wage_hourly_vnd: float | None = None
    toll_rate_vnd_per_km: float | None = None
    misc_cost_vnd: float = 0.0
    force_vehicle_count: int | None = None  # 覆盖四约束估算车数（装车实际值）
    # 🆕 大件/超限：单件重量 > 车型载重时默认拒绝报价（该车型装不下这一件）。
    # 用户显式确认「按拆分为多辆普通车计算」时传 true，才按四约束车数拆车出价。
    allow_oversized_split: bool = False


class BorderFeesOverride(BaseModel):
    """逐项覆盖：只传被改的项，值为本次报价的总金额(RMB)。

    派生项（吊装/滞箱/检验/港口费）未改时不传；每车固定费未改也不传 → 保持自动计算。
    """
    china_side: dict[str, float] = Field(default_factory=dict)
    vietnam_side: dict[str, float] = Field(default_factory=dict)


class PricingInput(BaseModel):
    """🆕 手动定价：本次毛利率 + 口岸费逐项覆盖（None=用默认/自动）。

    - margin_rate：毛利率覆盖（0–0.95，小数）。None=用 settings.margin_rate。
    - border_fees_override：口岸费逐项覆盖（RMB 总额）。None=按 fixed_fees 固定费率自动计算。
    """
    margin_rate: float | None = Field(default=None, ge=0, le=0.95,
                                      description="毛利率覆盖（0–0.95），None=用默认")
    border_fees_override: BorderFeesOverride | None = Field(default=None,
                                                            description="口岸费逐项覆盖(RMB)，None=自动计算")


class QuoteRequest(BaseModel):
    route: RouteInput
    cargo: CargoInput
    vehicle: VehicleInput
    cost_params: CostParamsInput = Field(default_factory=CostParamsInput)
    pricing: PricingInput = Field(default_factory=PricingInput)  # 🆕 手动定价

    @model_validator(mode="after")
    def _check_volume_required_for_consolidated(self) -> "QuoteRequest":
        # 跨字段校验（vehicle.loading_mode 决定 cargo.volume_m3 是否必填），
        # Pydantic v2 只能在最外层模型上做
        if self.vehicle.loading_mode == "consolidated" and self.cargo.volume_m3 is None:
            raise ValueError("拼货模式（consolidated）必须填写 cargo.volume_m3")
        return self


class LegOutput(BaseModel):
    """一段子路线（如 中国段 or 越南段）。"""
    distance_km: float
    duration_h: float


class RouteOutput(BaseModel):
    distance_km: float
    duration_h: float  # OSRM 原始行驶时间（未经速度惩罚调整）
    adjusted_duration_h: float  # 经速度惩罚系数调整后的实际预计行驶时间
    geometry: dict
    china_leg: LegOutput | None = None   # 🆕 中国段（发车地 → 口岸）；**仅跨境**有值
    vietnam_leg: LegOutput | None = None  # 🆕 越南段（口岸 → 目的地）；**仅跨境**有值
    # 🆕 v008：运输范围 —— domestic_cn / domestic_vn / cross_border / unknown
    #   （境内运输时前端据此：不分段着色、不显示口岸、口岸费区标注「不涉及进出口」）
    scope: str | None = None
    # 🆕 v009：当期价格系数（周期性需求调价）—— 只乘运输费，默认 1.0（无命中期间）
    price_factor: float = 1.0
    price_factor_note: str | None = None      # 冻结文案：当期价格系数 ×1.15（2026-10旺季，需求 +50%，λ=0.30）
    # 乘系数前的运输费小计（距离成本+固定调度费+路桥+附加，已 ×车辆数）；不含装卸费/保险费/杂费
    transport_subtotal_vnd: float | None = None
    # 🆕 v015.4：地图路线按车型 —— profile 兑现情况（诚实降级标注，前端地图/导出件必须显示）
    #   profile_requested: 车型要求的 OSRM profile（None = 未指定车型，走全局默认）
    #   profile_used:      实际采用的路网口径（未兑现时＝回退的默认 profile）
    #   profile_honored:   False ⇒ **未按车型限高限重校验**，同时 profile_note 给出中文原因
    profile_requested: str | None = None
    profile_used: str | None = None
    profile_honored: bool = True
    profile_note: str | None = None


class TimingOutput(BaseModel):
    speed_factor: float
    adjusted_duration_h: float
    rest_hours: float
    loading_hours: float
    total_duration_h: float


class BreakdownOutput(BaseModel):
    cost_distance: float
    cost_time: float
    cost_fuel: float
    cost_loading: float
    cost_insurance: float
    cost_toll: float
    cost_misc: float
    cost_body_surcharge: float
    cost_restricted_zone: float
    cost_construction_zone: float
    cost_mountain_road: float
    cost_port: float
    cost_fixed: float
    cost_total: float
    cost_per_km: float
    cost_per_ton_km: float | None
    capacity_ratio: float
    matched_vehicle_model_id: str
    matched_vehicle_model_name: str
    vehicle_count: int = 1
    cost_per_vehicle: float | None = None


class BorderFeeSide(BaseModel):
    items: dict = Field(default_factory=dict)      # {费用名: RMB}
    subtotal_rmb: float = 0


class BorderFeesOut(BaseModel):
    china_side: BorderFeeSide = Field(default_factory=BorderFeeSide)
    vietnam_side: BorderFeeSide = Field(default_factory=BorderFeeSide)
    total_rmb: float = 0
    total_vnd: float = 0
    exchange_rate: float | None = None
    manual: bool = False                   # 🆕 True=手动设定进出口费（单行）
    manual_total_rmb: float | None = None  # 🆕 手动设定合计(RMB)


class QuoteResponse(BaseModel):
    route: RouteOutput
    timing: TimingOutput
    breakdown: BreakdownOutput
    suggestions: list[dict]  # [{"code": str, "params": dict}, ...]
    route_fallback: bool = False  # True 表示路线为降级估算（非 OSRM 实测）
    vehicle_count: int = 1
    price_vnd: float = 0          # 售价 = 成本 × (1 + margin_rate)
    profit_vnd: float = 0         # 利润 = 成本 × margin_rate
    margin_rate: float = 0        # 毛利率
    border_fees: BorderFeesOut | None = None   # 进出口口岸费（中国段+越南段，RMB+VND）
    # 🆕 v015.4：路线 profile 兑现情况的**镜像字段**（与 route.* 同值）。
    #   前端地图面板 / 导出件任取一处即可，避免漏读导致「以为做过限高限重校验」。
    profile_requested: str | None = None
    profile_used: str | None = None
    profile_honored: bool = True
    profile_note: str | None = None


class TemplateCreate(BaseModel):
    name: str
    config: dict


class TemplateUpdate(BaseModel):
    name: str


class TemplateOut(BaseModel):
    id: str
    name: str
    config: dict
    created_at: datetime


class BatchRowInput(BaseModel):
    """对应批量导入 Excel 里的一行。"""

    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    weight_kg: float = Field(gt=0)
    volume_m3: float | None = None
    cargo_type: str = "normal"
    loading_mode: Literal["consolidated", "full_truck"]  # 替代旧 vehicle_type+body_type
    vehicle_model_id: str | None = None
    empty_return: bool = False
    need_loading: bool = False
    avoid_restricted_zones: bool = False
    avoid_construction_zones: bool = False
    via_mountain_road: bool = False
    via_port: bool = False
    cargo_items: list[dict] = Field(default_factory=list)  # 🆕 单件明细（长件/面积约束）
    cargo_value_vnd: float | None = None
    fuel_price_vnd: float | None = None
    wage_hourly_vnd: float | None = None
    toll_rate_vnd_per_km: float | None = None
    misc_cost_vnd: float = 0.0

    @model_validator(mode="after")
    def _check_conditional_fields(self) -> "BatchRowInput":
        if self.loading_mode == "full_truck" and not self.vehicle_model_id:
            raise ValueError("整车模式（full_truck）必须指定 vehicle_model_id")
        if self.loading_mode == "consolidated" and self.volume_m3 is None:
            raise ValueError("拼货模式（consolidated）必须填写 volume_m3")
        return self


class BatchRequest(BaseModel):
    rows: list[dict]


class BatchRowResult(BaseModel):
    row_index: int
    success: bool
    error: str | None = None
    quote: QuoteResponse | None = None


class BatchResponse(BaseModel):
    results: list[BatchRowResult]


# ── AI 分析 API 模型 ──

class AIPredictionSample(BaseModel):
    """单个预测偏差样本，供 AI 分析。"""
    vehicle_model_id: str
    dest: str = ""
    distance_km: float
    actual_vnd: float
    predicted_vnd: float
    error_pct: float
    notes: str = ""


class AIAnalysisRequest(BaseModel):
    """AI 分析请求。"""
    predictions: list[AIPredictionSample]
    context: str | None = None


class AIAnalysisResponse(BaseModel):
    """AI 分析响应。"""
    deviation_analysis: dict | None = None
    route_features: dict | None = None
    optimization_suggestions: dict | None = None


class AIRouteClassifyRequest(BaseModel):
    """路线特征分类请求。"""
    destinations: list[str]


class AIRouteClassifyResponse(BaseModel):
    """路线特征分类响应。"""
    route_features: dict


class AIExtractQuoteRequest(BaseModel):
    """报价提取请求。"""
    raw_text: str


class AIExtractQuoteResponse(BaseModel):
    """报价提取响应。"""
    extracted: dict


class AIStatusResponse(BaseModel):
    """AI 服务状态。"""
    status: str
    model: str
    message: str


# ── AI 配置（设置弹窗保存 DeepSeek Key） ──

class AIConfigRequest(BaseModel):
    """设置 AI 配置（DeepSeek API Key / model / base_url）。"""
    api_key: str = ""
    model: str | None = None
    base_url: str | None = None


class AIConfigResponse(BaseModel):
    """当前 AI 配置状态（Key 掩码显示）。"""
    has_key: bool
    masked_key: str = ""
    model: str = ""
    base_url: str = ""


# ── AI 对话聊天 API 模型 ──

class AIChatMessage(BaseModel):
    """单条聊天消息。"""
    role: str  # "user" | "assistant"
    content: str


class AIChatRequest(BaseModel):
    """AI 对话请求。"""
    messages: list[AIChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    # 🆕 v006：界面状态快照（前端 getAppState() 产物，可空；仅用于让 AI 知道界面现状）
    app_state: dict | None = None


class ActionAuditRequest(BaseModel):
    """🆕 v006：前端动作审计（由 renderer 执行后回报，仅审计用）。"""
    action: str
    args: dict = Field(default_factory=dict)
    ok: bool = True
    role: str = "internal"
    note: str = ""


# ── 报价单导出模型 ──

class CargoItemOut(BaseModel):
    name: str = "货物"
    qty: int = 1
    weight_ton: float = 0
    l_cm: float | None = None
    w_cm: float | None = None
    h_cm: float | None = None


class FeeItemOut(BaseModel):
    name: str
    unit: str = "趟"
    qty: float = 1
    unit_price_vnd: float = 0
    amount_vnd: float = 0


class QuoteExportRequest(BaseModel):
    role: Literal["customer", "internal"] = "customer"
    customer_name: str = "【请填写客户名称】"
    route_name: str = "—"
    distance_km: float | None = None
    duration_h: float | None = None
    vehicle_model_name: str = "—"
    vehicle_count: int = 1
    cargo: list[CargoItemOut] = Field(default_factory=list)
    fee_items: list[FeeItemOut] = Field(default_factory=list)
    price_vnd: float = 0
    profit_vnd: float = 0
    cost_total: float = 0
    breakdown: dict = Field(default_factory=dict)
    validity_days: int = 30
    border_fees: BorderFeesOut | None = None
    # 🆕 大件/超限：专线趟价（手工录入，未走成本模型，实报实销）
    manual_oversize_fee_vnd: float = 0
    oversize_note: str = ""


class BorderFeesSaveRequest(BaseModel):
    """把当前口岸费保存为默认（写回 fixed_fees.json）。

    每车固定费项按 vehicle_count 折算成 per_vehicle 费率；派生项（吊装/滞箱等）不写入。
    """
    vehicle_count: int = Field(default=1, ge=1)
    china_side: dict[str, float] = Field(default_factory=dict)
    vietnam_side: dict[str, float] = Field(default_factory=dict)


# ── 🆕 v009 费率与价格（公式价格反算 + 周期性需求调价） ──
# 请求模型刻意「宽松」（字段全可选），字段级校验放在服务层 → 非法字段返回 **400**
# 而不是 FastAPI 默认的 422（契约 §2 #3 要求 400 + {detail: "..."}）。

class RatesSampleCreateRequest(BaseModel):
    """新增一条反算样本（必填 6 项：日期/起点/终点/车型ID/总价/计价口径）。"""
    date: str | None = None
    origin: str | None = None
    destination: str | None = None
    vehicle_model_id: str | None = None
    total_vnd: float | None = None
    loading_mode: str | None = None
    distance_km: float | None = None
    weight_ton: float | None = None
    cargo_type: str | None = None
    source: str | None = None
    note: str | None = None


class RatesSampleImportRequest(BaseModel):
    """导入 CSV（UTF-8/GBK 自动识别；不支持 .xlsx）。"""
    filename: str = ""
    content: str = ""


class RatesFitRequest(BaseModel):
    """反算拟合请求：model_ids 为空 = 全部有样本的车型。"""
    model_ids: list[str] | None = None


class RatesAnchorCheck(BaseModel):
    """护栏 P5：市场锚点核对（标杆路线 + 你熟悉的报价）。

    实算口径与真实报价链路一致（距离成本+固定调度费+路桥+附加，×车辆数）。
    `distance_km`/`osrm_km`/`weight_ton`/`cargo_type` 都是可选的补充信息：
    里程优先取样本里同起终点路线的中位数；车辆数默认按单车运输价计。
    """
    route: str = ""
    quoted_vnd: float | None = None
    note: str | None = None
    distance_km: float | None = None
    osrm_km: float | None = None
    weight_ton: float | None = None
    cargo_type: str | None = None


class RatesApplyItem(BaseModel):
    model_id: str
    base_rate_vnd_per_km: float
    fixed_surcharge_vnd: float
    anchor_check: RatesAnchorCheck | None = None


class RatesApplyRequest(BaseModel):
    items: list[RatesApplyItem] = Field(default_factory=list)
    note: str | None = None
    force: bool = False   # 跳过 P5 强行应用（同样留痕）


class RatesPeriodCreateRequest(BaseModel):
    """需求期间（起止日自由，例如 2026-09-15 ~ 2026-10-15）。"""
    name: str | None = None
    start: str | None = None
    end: str | None = None
    trips: float | None = None
    baseline_trips: float | None = None
    note: str | None = None


class RatesSettingsRequest(BaseModel):
    """弹性设置（部分更新也接受；`lambda` 是 Python 关键字 → 用别名字段）。"""
    model_config = ConfigDict(populate_by_name=True)

    lambda_: float | None = Field(default=None, alias="lambda")
    min_factor: float | None = None
    max_factor: float | None = None
    baseline_months: int | None = None


# ── 🆕 v011 车型库后台（`/api/v1/vehicles`）──
# 角色门禁字段 `role` 沿用 `QuoteExportRequest.role` 的同一枚举（internal / customer），
# 缺省 internal（与 `ActionAuditRequest.role` 一致）。见 `api/vehicles.py` 模块头。


class VehicleUpsertRequest(BaseModel):
    """车型库新增 / 改参请求：**扁平可编辑列**（键名即 CSV 表头）。

    `model_config = extra="allow"` 是故意为之：列白名单的唯一权威是写盘层
    `vehicle_store._check_keys()`（未知列 → 400「不可编辑字段：…」），
    在 schema 里再抄一份白名单迟早漂移。
    """

    model_config = ConfigDict(extra="allow")

    role: Literal["customer", "internal"] = "internal"     # 门禁声明，不写进车辆库


class VehicleImportRequest(BaseModel):
    """车型库 CSV 导入请求（先全量校验、再写盘；任何一行非法 → 一个字节都不写）。

    `mode` 用 `str` 而非 `Literal`：`vehicle_store.import_csv()` 才是枚举权威
    （非法值抛中文 `VehicleStoreError` → 400 原样给前端）。
    """

    filename: str = ""
    content: str = ""
    mode: str = "merge"                                    # merge / replace（由数据层校验）
    role: Literal["customer", "internal"] = "internal"     # 门禁声明，不写进车辆库


# ── 🆕 v013 装箱单（`POST /api/v1/packing-list`）──
# 单位/坐标口径与前端 3D、`services/packer.py` 完全一致（**勿另立**）：
#   x/y/z = 车厢坐标 cm，原点 = 前壁左下角；x 沿车长（前壁→车门）、y 高度、z 宽度；y==0 即落地。
# 字段名是**已对接前端的前端契约**（`desktop/renderer`），改名会直接打断前端导出，勿动。
# `role` 契约值是 `client` / `internal`：`client` 版正文严禁出现 成本/利润/毛利
# （沿用报价单既有铁律）；这里额外容忍报价单侧的 `customer` 别名 → 同样按客户版处理。


class PackingJobInfo(BaseModel):
    """抬头：起点 / 终点 / 口岸 / 日期（都容许缺省，缺省写「—」）。"""

    origin: str = ""
    destination: str = ""
    border_crossing: str = ""
    date: str = ""


class PackingPlacement(BaseModel):
    """单件摆放：坐标与占用尺寸都是 cm（x=车长 / y=高 / z=宽，原点=前壁左下角）。"""

    cargoId: str = ""
    name: str = ""
    x: float = 0
    y: float = 0
    z: float = 0
    dx: float = 0
    dy: float = 0
    dz: float = 0
    weight: float = 0
    stackable: bool = True


class PackingUnplaced(BaseModel):
    cargoId: str = ""
    name: str = ""
    reason: str = ""


class PackingTruckInfo(BaseModel):
    """车厢规格：L/W/H 单位 cm，maxWeight 单位 kg。"""

    L: float = 0
    W: float = 0
    H: float = 0
    maxWeight: float = 0
    type: str = ""            # flatbed / lowbed / box / container（未知或空 → 货车）


class PackingTruck(BaseModel):
    """一辆车：规格 + 该车摆放清单 + 未装配件 + 该车 3D 截图（base64，可缺省）。"""

    index: int = 0
    model_name: str = ""
    loading_rate: float | None = None      # 0~1；缺省 → 由 placements 体积 / 车厢容积算
    truck: PackingTruckInfo = Field(default_factory=PackingTruckInfo)
    placements: list[PackingPlacement] = Field(default_factory=list)
    unplaced: list[PackingUnplaced] = Field(default_factory=list)
    snapshot_png: str | None = None        # `data:image/png;base64,…` 或纯 base64 均可


class PackingListRequest(BaseModel):
    job: PackingJobInfo = Field(default_factory=PackingJobInfo)
    role: Literal["client", "customer", "internal"] = "client"
    # 空列表是**已定行为**：端点返回 400（不是空单页）—— 见 `api/packing.py` 与测试。
    trucks: list[PackingTruck] = Field(default_factory=list)
