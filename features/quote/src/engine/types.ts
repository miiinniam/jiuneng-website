// 来源：OSRM++ 报价站原始代码 features/quote/legacy/frontend/src/lib/
// 移植：迁入官网 features/quote/src/engine/（2026-11-20），字段名/函数名一律不改。
// 以下正文与 legacy types.ts 逐字一致，未做任何字段重命名。

export interface LatLng {
  lat: number;
  lng: number;
  address?: string;
}

export type LoadingMode = "consolidated" | "full_truck";

export interface VehicleModel {
  model_id: string;
  display_name: string;
  max_load_ton: number;
  volume_capacity_m3: number | null;
  length_m: number | null;
  width_m: number | null;
  height_m: number | null;
  max_cargo_height_m: number | null;
  loading_efficiency: number;
  floor_area_m2: number | null;
  effective_volume_m3: number | null;
  base_rate_vnd_per_km: number;
  fuel_l_per_100km: number;
  fuel_penalty: number;
  fixed_surcharge_vnd: number;
  toll_rate_vnd_per_km: number;
  osrm_profile: string;
  suitable_cargo_types: string[];
  notes: string;
}

/** 🆕 单件货物明细（可选）——用于长件/面积约束精确计算车辆数 */
export interface CargoItem {
  id: string;            // 前端唯一 id（增删用）
  name: string;
  count: number;
  lengthM: number;       // 米
  widthM: number;
  heightM: number | null;
  weightKg: number | null;
  stackable: boolean;    // 是否可堆叠（false=按地板面积计）
  /** 🆕 可解体（设备可拆件分运）。只影响「拆件建议」，不改配车结果（引擎 A6） */
  divisible?: boolean;
}

/** 🆕 提交给后端的单件货物格式（snake_case，对应 CargoItemInput） */
export interface CargoApiItem {
  name?: string;
  count: number;
  length_m: number;
  width_m: number;
  height_m?: number;
  weight_kg?: number;
  stackable: boolean;
  /** 🆕 可解体：让引擎给出「拆件后档位/车数」建议（A6），不改变配车结果 */
  divisible?: boolean;
}

export type VehicleModelsByCategory = Record<string, VehicleModel[]>;

export interface CargoTypeRate {
  rate_multiplier: number;
  fuel_penalty: number;
}

export interface QuoteRequest {
  route: {
    origin: LatLng;
    destination: LatLng;
    waypoints: LatLng[];
  };
  cargo: {
    weight_kg: number;
    volume_m3?: number;
    type: string;
    value_vnd?: number;
    items?: CargoApiItem[];
  };
  vehicle: {
    loading_mode: LoadingMode;
    vehicle_model_id?: string;
    empty_return: boolean;
    need_loading: boolean;
    avoid_restricted_zones: boolean;
    avoid_construction_zones: boolean;
    via_mountain_road: boolean;
  };
  cost_params: {
    fuel_price_vnd?: number;
    wage_hourly_vnd?: number;
    toll_rate_vnd_per_km?: number;
    misc_cost_vnd: number;
  };
}

export interface RouteGeometry {
  type: "LineString";
  coordinates: [number, number][];
}

/** 🆕 公开版 5 类货物分类（用户口径，第 2 步选择） */
export type CargoClass = "normal" | "equipment" | "heavy" | "oversized" | "small";

/**
 * 5 类 → 引擎 `cargo_type`。
 * ⚠️ 引擎只有 6 个合法值（normal / cold_chain / hazardous / oversized / heavy_equipment / other），
 *    没有「大型机械」「小件」这两档 —— 大型机械并入 heavy_equipment、小件并入 normal。
 *    界面分类只决定字段要求与文案，**不新增引擎档位**（新增档位要动配车排序，另评估）。
 */
export const CARGO_CLASS_TO_TYPE: Record<CargoClass, string> = {
  normal: "normal",
  equipment: "heavy_equipment",
  heavy: "heavy_equipment",
  oversized: "oversized",
  small: "normal",
};

/** 🆕 自动配车推荐（与 /api/quote/fit 的 picks 同构；此处定义避免 types ← api 反向依赖） */
export interface FitRecommendation {
  model_id: string;
  name: string;
  max_load_ton: number | null;
  vehicle_count: number;
  oversize: boolean;
  permit_tier: "一类" | "二类" | "三类" | null;
  permit_workdays_local: number | null;
  permit_note: string | null;
}

export interface QuoteFormState {
  originLat: string;
  originLng: string;
  destLat: string;
  destLng: string;
  /** 地址搜索选中的地名（只用于展示，例如工作台卡片上的「友谊关 → 河内」）；
      手填坐标时为空，卡片回落到坐标。可选，不进接口。 */
  originLabel?: string;
  destLabel?: string;
  waypoints: LatLng[];
  /** 🆕 公开版第 2 步：5 类货物分类（用户口径，决定字段要求与文案） */
  cargoClass: CargoClass;
  weightKg: string;
  weightUnit: "ton" | "kg";  // 显示单位，提交时统一转 kg
  volumeM3: string;
  /** 引擎 cargo_type：由 cargoClass 派生（CARGO_CLASS_TO_TYPE）；
      内部版可直接改这个值做精调，所以它仍是独立字段 */
  cargoType: string;
  /** 货值本体。字段名沿用 legacy（`cargoValueVnd`），币种见 cargoValueCurrency */
  cargoValueVnd: string;
  /** 🆕 货值币种（公开版可选填，仅作展示/后续换算；引擎只认 value_vnd） */
  cargoValueCurrency: "RMB" | "USD" | "VND";
  items: CargoItem[];        // 🆕 单件货物明细
  loadingMode: LoadingMode;
  vehicleModelId: string;
  emptyReturn: boolean;
  needLoading: boolean;
  /** 🆕 含卸车 / 需随车吊：公开版第 4 步收集。
      ⚠️ 引擎 `/quote/route` 目前没有对应字段，这两个只进报价单备注与后续接口，**不进请求体** */
  needUnloading: boolean;
  needCrane: boolean;
  /** 🆕 自动配车推荐（第 4 步进入时静默调 /api/quote/fit；失败不影响手选） */
  fitStatus: "idle" | "loading" | "ok" | "error";
  fitPicks: FitRecommendation[];
  fitNote: string;
  fitTotalTrucks: number;
  avoidRestrictedZones: boolean;
  avoidConstructionZones: boolean;
  viaMountainRoad: boolean;
  fuelPriceVnd: string;
  wageHourlyVnd: string;
  tollRateVndPerKm: string;
  miscCostVnd: string;
}

export interface QuoteResponse {
  route: {
    distance_km: number;
    duration_h: number;
    geometry: RouteGeometry;
  };
  timing: {
    speed_factor: number;
    adjusted_duration_h: number;
    rest_hours: number;
    loading_hours: number;
    total_duration_h: number;
  };
  breakdown: {
    cost_distance: number;
    cost_time: number;
    cost_fuel: number;
    cost_loading: number;
    cost_insurance: number;
    cost_toll: number;
    cost_misc: number;
    cost_body_surcharge: number;
    cost_restricted_zone: number;
    cost_construction_zone: number;
    cost_mountain_road: number;
    cost_port: number;
    cost_fixed: number;
    cost_total: number;
    cost_per_km: number;
    cost_per_ton_km: number | null;
    capacity_ratio: number;
    matched_vehicle_model_id: string;
    matched_vehicle_model_name: string;
    vehicle_count: number;
    cost_per_vehicle: number | null;
  };
  suggestions: Suggestion[];
  vehicle_count: number;
}

export interface Suggestion {
  code: string;
  params: Record<string, string>;
}

export interface TemplateOut {
  id: string;
  name: string;
  config: QuoteFormState;
  created_at: string;
}

export interface BatchRowInput {
  origin_lat: number;
  origin_lng: number;
  dest_lat: number;
  dest_lng: number;
  weight_kg: number;
  volume_m3?: number;
  cargo_type: string;
  loading_mode: LoadingMode;
  vehicle_model_id?: string;
  empty_return: boolean;
  need_loading: boolean;
  avoid_restricted_zones: boolean;
  avoid_construction_zones: boolean;
  via_mountain_road: boolean;
  cargo_value_vnd?: number;
  fuel_price_vnd?: number;
  wage_hourly_vnd?: number;
  toll_rate_vnd_per_km?: number;
  misc_cost_vnd: number;
}

export interface BatchRowResult {
  row_index: number;
  success: boolean;
  error: string | null;
  quote: QuoteResponse | null;
}

// ── 边境/进出口费用 ──

export type TransportMode = "land" | "sea";

/** 报价模式 */
export type QuoteMode = "transport_only" | "ddp_full";

export interface BorderCostParams {
  vehicle_count: number;
  container_count: number;
  container_type: string;
  transport_mode: TransportMode;
  cargo_value_rmb: number;
  hs_code: string;
}

/** 旧版接口类型（保持兼容） */
export interface BorderCostResult {
  china_export: {
    customs_declaration: number;
    yard_fee: number;
    unloading: number;
    total: number;
  };
  border_crossing: {
    transloading: number;
    total: number;
  };
  vietnam_import: {
    customs_clearance: number;
    yard_fee: number;
    inspection?: number;
    total: number;
  };
  import_duty_rmb: number;
  vat_rmb: number;
  total_rmb: number;
  tariff_desc?: string;
  duty_source?: string;
  duty_rate?: number;
  vat_rate?: number;
}

/** 🆕 两端分开报价结果 */
export interface DDPFullItem {
  customs_declaration?: number;
  yard_fee?: number;
  unloading?: number;
  transloading?: number;
  domestic_transport?: number;
  export_tax_rebate?: number;
  customs_clearance?: number;
  inspection?: number;
  insurance?: number;
  import_duty?: number;
  vat?: number;
  detention?: number;
  heavy_lift?: number;
  port_charge?: number;
  trucking_to_site?: number;
  breakbulk_port?: number;
}

export interface DDPFullSide {
  items: DDPFullItem;
  subtotal: number;
}

export interface DDPFullResult {
  china_side: DDPFullSide;
  vietnam_side: DDPFullSide;
  china_total: number;
  vietnam_total: number;
  ddp_total: number;
  tariff_info?: {
    hs_code: string;
    desc: string;
    duty_source: string;
    duty_rate: number | null;
    vat_rate: number | null;
  } | null;
}

/** DDP 全链路参数 */
export interface DDPFullParams {
  vehicle_count: number;
  domestic_transport_rmb: number;
  cargo_value_rmb: number;
  hs_code: string;
  transport_cost_vnd: number;
  container_count: number;
  container_type: string;
  is_breakbulk: boolean;
  breakbulk_tons: number;
  detention_days: number;
  heavy_lift_tons: number;
  include_export_rebate: boolean;
}
