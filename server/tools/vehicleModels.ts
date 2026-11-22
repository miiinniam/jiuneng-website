/**
 * 车型库配置 —— 引擎 `/reference/vehicle-models` 的非成本字段视图。
 *
 * 为什么单独一层：
 *   `fleet.ts` 原先的 `groups[]` 只有 `model_id / category / vehicle_count / reason / flags`，
 *   模型讲车型时拿不到库里的载重、车长、轴配置 → 只能靠猜或含糊其辞（实测客户会追问「这车多长」）。
 *   这里把库内配置查出来挂到配车结果上，**车型名与参数一律来自库**，不由模型生成。
 *
 * 红线：本文件永远不许输出 `base_rate_vnd_per_km / fuel_l_per_100km / fuel_penalty /
 *      fixed_surcharge_vnd / toll_rate_vnd_per_km / notes`（成本单价与供应商备注）。
 *      引擎回包里有这 6 个键，这里**逐键白名单重建**（不是 spread 后删），类型层面也不给它们留位。
 */
import { engineJson, singleFlight } from './engineClient.ts';

export type VehicleSpec = {
  model_id: string;
  display_name: string;
  category: string;
  /** 额定载重（吨） */
  max_load_ton: number;
  /** 车厢/平板长（米） */
  length_m: number;
  width_m: number;
  height_m: number;
  /** 允许装载高度（米），无则 null */
  max_cargo_height_m: number | null;
  /** 装载效率（0–1），无则 null */
  loading_efficiency: number | null;
  /** 整备重量（吨），无则 null */
  curb_weight_ton: number | null;
  /** 平板/车厢面积（m²），无则 null */
  floor_area_m2: number | null;
  /** 有效容积（m³），无则 null */
  effective_volume_m3: number | null;
  /** 轴型（如 TR-02、6×4），无则 null */
  axle_config: string | null;
  /** 可运货类（引擎原值，如 ['normal','other']） */
  suitable_cargo_types: string[];
};

/** 缓存 TTL：车型库是静态表，5 分钟足够；引擎重启时最多滞后 5 分钟。 */
export const SPEC_TTL_MS = 5 * 60 * 1000;

let cache: { at: number; map: Map<string, VehicleSpec> } | null = null;

/** 数值归一：只收 number 与数字字符串，`Number.isFinite` 才算数；其余一律 `null`（含 bool / 对象 / 空串）。 */
function toNum(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text) return null;
    const n = Number(text);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/** 必填数值：取不到记 0（`max_load_ton / length_m / width_m / height_m` 用）。 */
function toNum0(value: unknown): number {
  return toNum(value) ?? 0;
}

/** 文本归一：只接受字符串，trim 后为空即 `null`（`axle_config` 用）。 */
function toText(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  return text ? text.slice(0, 40) : null;
}

/** 货类数组：只收非空字符串，去空去重，最多 8 个。 */
function toCargoTypes(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    if (typeof item !== 'string') continue;
    const text = item.trim().slice(0, 40);
    if (text && !out.includes(text)) out.push(text);
    if (out.length >= 8) break;
  }
  return out;
}

/**
 * 纯函数：引擎 `/reference/vehicle-models` 回包 → `model_id → VehicleSpec`。
 *
 * 回包形状是 `{ <category>: [ {…}, … ] }`（引擎侧 `models_by_category()` **会带上空类别的空数组**），
 * 所以：非数组的 value、非对象的行、缺 `model_id` 的行一律跳过；`category` 取外层键。
 *
 * 白名单逐键取值（**不 spread 引擎对象**）：成本单价与 `notes` 在这里就被丢掉，
 * 下游即便把整个 spec 透出去也带不出内部字段。
 */
export function mapCatalogue(raw: unknown): Map<string, VehicleSpec> {
  const map = new Map<string, VehicleSpec>();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return map;

  for (const [categoryKey, rows] of Object.entries(raw as Record<string, unknown>)) {
    if (!Array.isArray(rows)) continue;
    const category = typeof categoryKey === 'string' ? categoryKey.trim() : '';
    if (!category) continue;

    for (const row of rows) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) continue;
      const item = row as Record<string, unknown>;
      const modelId = typeof item.model_id === 'string' ? item.model_id.trim() : '';
      if (!modelId) continue;
      const displayName = typeof item.display_name === 'string' ? item.display_name.trim() : '';

      map.set(modelId, {
        model_id: modelId,
        display_name: displayName.slice(0, 80) || modelId,
        category,
        max_load_ton: toNum0(item.max_load_ton),
        length_m: toNum0(item.length_m),
        width_m: toNum0(item.width_m),
        height_m: toNum0(item.height_m),
        max_cargo_height_m: toNum(item.max_cargo_height_m),
        loading_efficiency: toNum(item.loading_efficiency),
        curb_weight_ton: toNum(item.curb_weight_ton),
        floor_area_m2: toNum(item.floor_area_m2),
        effective_volume_m3: toNum(item.effective_volume_m3),
        axle_config: toText(item.axle_config),
        suitable_cargo_types: toCargoTypes(item.suitable_cargo_types),
      });
    }
  }
  return map;
}

/** 拉库并映射。失败只 warn 一行（引擎内部报文只进服务端日志），返回空 Map。 */
async function fetchSpecs(): Promise<Map<string, VehicleSpec>> {
  try {
    const raw = await engineJson<unknown>('/reference/vehicle-models');
    return mapCatalogue(raw);
  } catch (error) {
    const code = (error as { code?: string })?.code ?? 'unknown';
    console.warn('[vehicleModels] 车型库拉取失败，本轮按「查不到」回落：', code, (error as Error)?.message ?? error);
    return new Map<string, VehicleSpec>();
  }
}

/** 取全库配置（按 model_id 索引）。失败返回空 Map —— 调用方一律按「查不到 = null」处理，不许编。 */
export async function specMap(): Promise<Map<string, VehicleSpec>> {
  if (cache && Date.now() - cache.at < SPEC_TTL_MS) return cache.map;
  // 并发合并：同一时刻只打一次引擎（价格不缓存、配置缓存，两者语义不同）
  return singleFlight('vehicle-models', async () => {
    // 进到临界区再判一次：等锁期间可能有别的请求已经把缓存填好了
    if (cache && Date.now() - cache.at < SPEC_TTL_MS) return cache.map;
    const at = Date.now();
    const map = await fetchSpecs();
    // 失败也写进缓存（值为空 Map）：引擎宕机时不要每个请求都去撞一遍超时。
    // 代价是引擎恢复后最多滞后一个 TTL（5 分钟）——与「引擎重启最多滞后 5 分钟」同一口径。
    cache = { at, map };
    return map;
  });
}

/** 测试用：清空缓存。 */
export function resetSpecCache(): void {
  cache = null;
}
