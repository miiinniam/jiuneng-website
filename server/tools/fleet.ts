/**
 * 车辆匹配（契约 §3.5）
 * ────────────────────────────────────────────────────────────
 * 输入：货重/体积/货类 + 逐件尺寸（长宽高、单件重量、件数、可否叠放）。
 * 输出：推荐分组（车型 / 类别 / 需车数 / 理由 / 尺寸标记）+ 总车数 + 超限判定。
 *
 * 出参**白名单重建**（引擎回包里这些一律丢弃）：
 *  - `breakdown` / `vehicle_breakdowns`：四约束车数分解（内部口径）
 *  - `pairs[].per_truck` / `pairs[].pair_id`：共车组合的内部编排细节
 *  - `locked` / `confirm` / `count_doctrine` / `axle_lines`：桌面版的操作态与轴荷推演
 *  - 任何金额字段（选车不该带价）
 * 理由：官网只回答「用什么车、几辆、是否超限」，桌面版的配车工作台细节不外露。
 */
import { EngineError, engineJson } from './engineClient.ts';
import { specMap, type VehicleSpec } from './vehicleModels.ts';

export type FleetItem = {
  name: string;
  length_m: number;
  width_m: number;
  height_m: number;
  weight_kg: number;
  count: number;
  stackable: boolean;
};

export type FleetInput = {
  weight_kg: number;
  volume_m3?: number;
  cargo_type?: string;
  items: FleetItem[];
  /**
   * 允许超限运输配车（引擎 v016 开关）。缺省 false：
   * 超限件在库内配不出时会如实报 blocked，而不是偷偷按普通件配。
   */
  allow_oversized?: boolean;
};

export type FleetGroup = {
  model: string;
  /** 车型库 display_name —— 对客户只说库里的名字，不许模型自造；库查不到时回落 model */
  display_name: string;
  category: string;
  /** 车型库额定载重（吨）；库查不到时回落引擎值，再取不到为 0 */
  max_load_ton: number;
  vehicle_count: number;
  reason: string;
  flags: string[];
  /** 库内完整配置（车长/轴型/可伸缩宽…）；库查询失败为 null —— 拿不到就如实报，不许推测 */
  spec: VehicleSpec | null;
};

export type FleetMatch =
  | {
      ok: true;
      groups: FleetGroup[];
      total_trucks: number;
      oversize: { blocked: boolean; basis: string };
    }
  | { ok: false; reason: string; note: string };

export type ParseResult = { ok: true; value: FleetInput } | { ok: false; reason: 'bad_input'; note: string };

const MAX_ITEMS = 20;
const MAX_COUNT = 50;
const MAX_FLAG_LEN = 80;

const num = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const text = (value: unknown, fallback = ''): string => (typeof value === 'string' ? value.trim().slice(0, 120) : fallback);

/** 入参校验：非法一律回 bad_input（不打引擎、不猜尺寸），缺省值按业务常识补。 */
export function parseFleetInput(raw: unknown): ParseResult {
  const body = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const rawItems = body.items;
  if (!Array.isArray(rawItems) || rawItems.length === 0) {
    return { ok: false, reason: 'bad_input', note: '请至少填写一行货物（尺寸 + 单件重量 + 件数）' };
  }
  if (rawItems.length > MAX_ITEMS) {
    return { ok: false, reason: 'bad_input', note: `货物行数超过上限（${MAX_ITEMS} 行），请拆单后再匹配` };
  }

  const items: FleetItem[] = [];
  for (let i = 0; i < rawItems.length; i++) {
    const row = (rawItems[i] && typeof rawItems[i] === 'object' ? rawItems[i] : {}) as Record<string, unknown>;
    const weight = num(row.weight_kg);
    if (weight === null || weight <= 0) {
      return { ok: false, reason: 'bad_input', note: `第 ${i + 1} 行：单件重量需为大于 0 的数值（kg）` };
    }
    const rawCount = row.count === undefined || row.count === null || row.count === '' ? 1 : num(row.count);
    if (rawCount === null || !Number.isInteger(rawCount) || rawCount < 1 || rawCount > MAX_COUNT) {
      return { ok: false, reason: 'bad_input', note: `第 ${i + 1} 行：件数需为 1–${MAX_COUNT} 的整数` };
    }
    const length = row.length_m === undefined || row.length_m === null || row.length_m === '' ? 0 : num(row.length_m);
    const width = row.width_m === undefined || row.width_m === null || row.width_m === '' ? 0 : num(row.width_m);
    const height = row.height_m === undefined || row.height_m === null || row.height_m === '' ? 0 : num(row.height_m);
    for (const [label, value] of [['长度', length], ['宽度', width], ['高度', height]] as const) {
      if (value === null || value < 0) {
        return { ok: false, reason: 'bad_input', note: `第 ${i + 1} 行：${label}需为不小于 0 的数值（米，可留空）` };
      }
    }
    items.push({
      name: text(row.name, `货物 ${i + 1}`) || `货物 ${i + 1}`,
      length_m: length as number,
      width_m: width as number,
      height_m: height as number,
      weight_kg: weight,
      count: rawCount,
      stackable: row.stackable === true || row.stackable === 'true',
    });
  }

  const declared = num(body.weight_kg);
  const totalWeight = declared !== null && declared > 0
    ? declared
    : items.reduce((sum, item) => sum + item.weight_kg * item.count, 0);
  const volume = num(body.volume_m3);
  const cargoType = text(body.cargo_type);

  const value: FleetInput = { weight_kg: totalWeight, items };
  if (volume !== null && volume > 0) value.volume_m3 = volume;
  if (cargoType) value.cargo_type = cargoType;
  if (typeof body.allow_oversized === 'boolean') value.allow_oversized = body.allow_oversized;
  return { ok: true, value };
}

type EngineGroup = Record<string, unknown>;
type EngineFit = { groups?: unknown; total_trucks?: unknown; oversize?: unknown };

function sanitizeFlags(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const value of raw) {
    if (typeof value !== 'string') continue;
    const flag = value.trim().slice(0, MAX_FLAG_LEN);
    if (flag && !out.includes(flag)) out.push(flag);
    if (out.length >= 8) break;
  }
  return out;
}

const toInt = (value: unknown, fallback = 0): number => {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
};

/**
 * 车型族（引擎的 category 是**英文枚举**：small_box|flatbed|high_side|container|cold_chain|special）。
 * 契约 §3.5 要求对客出中文类别，所以这里做一次白名单翻译；未知值一律「其他」——
 * 绝不把引擎的英文枚举透给客户，也不猜具体车型（具体车型看 model）。
 */
const CATEGORY_ZH: Record<string, string> = {
  small_box: '厢式货车',
  flatbed: '平板车',
  high_side: '高栏车',
  container: '集装箱车',
  cold_chain: '冷链车',
  special: '特种车',
};

function categoryLabel(raw: unknown): string {
  const code = typeof raw === 'string' ? raw.trim() : '';
  if (CATEGORY_ZH[code]) return CATEGORY_ZH[code];
  // 引擎旧版本可能直接回中文：只接受中文串，其余归「其他」
  if (/^[\u4e00-\u9fa5]{1,8}$/.test(code)) return code;
  return '其他';
}

/**
 * 引擎的 reason 把**内部配车口径**接在同一句里
 * （例：「… 2 辆装完；主因 体积；车数口径 件守恒下限 2 / 四约束估算 2 取大（GVM 档 0，比价口径 rate_only）」）。
 * 对客只保留第一句，并剥掉含内部措辞的括号，绝不外露「口径 / GVM / 四约束 / rate_only / 轴荷」这类词。
 */
const INTERNAL_MARK = /口径|GVM|四约束|rate_only|件守恒|比价|轴荷|doctrine/;

function customerReason(raw: unknown, vehicleCount: number): string {
  const rawText = text(raw);
  const fallback = `按载重与尺寸匹配，需 ${vehicleCount} 辆`;
  if (!rawText) return fallback;
  const first = rawText.split('；')[0].trim();
  const cleaned = first
    .replace(/（[^）]*）/g, (m) => (INTERNAL_MARK.test(m) ? '' : m))
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned || fallback;
}

function rebuild(raw: EngineFit, specs: Map<string, VehicleSpec>): FleetMatch {
  const rawGroups = Array.isArray(raw.groups) ? (raw.groups as EngineGroup[]) : [];
  const groups: FleetGroup[] = rawGroups.map((g) => {
    const count = toInt(g.vehicle_count, 0);
    const modelId = text(g.model_id);
    // 库优先、引擎次之、最后回落 model_id：三层都是「已有事实」，没有一层是推测
    const spec = specs.get(modelId) ?? null;
    const rawLoad = Number(g.max_load_ton);
    const loadTon = spec ? spec.max_load_ton : Number.isFinite(rawLoad) ? rawLoad : 0;
    return {
      model: modelId,
      display_name: spec?.display_name || text(g.display_name) || modelId,
      category: categoryLabel(g.category),
      max_load_ton: loadTon,
      vehicle_count: count,
      reason: customerReason(g.reason, count),
      flags: sanitizeFlags(g.dim_flags),
      spec,
    };
  });
  const oversize = (raw.oversize && typeof raw.oversize === 'object' ? raw.oversize : {}) as Record<string, unknown>;
  const unassigned = Array.isArray(oversize.unassigned) ? oversize.unassigned : [];
  const policy = (oversize.policy && typeof oversize.policy === 'object' ? oversize.policy : {}) as Record<string, unknown>;
  const hardBlocked = Array.isArray(policy.hard_blocked) ? policy.hard_blocked : [];
  return {
    ok: true,
    groups,
    total_trucks: toInt(raw.total_trucks, groups.reduce((sum, g) => sum + g.vehicle_count, 0)),
    oversize: {
      // 三条任一成立即「配不出车」：
      //  · 新引擎：oversize.unassigned / policy.hard_blocked 点名了配不上的货行；
      //  · 旧引擎（部署副本的整票 planner）没有这两个键，只在 groups 里体现 → 空 groups 就是配不上。
      //    入参已保证至少一行货，所以空 groups 不可能是「没货要配」。
      blocked: unassigned.length > 0 || hardBlocked.length > 0 || groups.length === 0,
      basis: '按单件最大尺寸判定',
    },
  };
}

const FAIL_NOTES: Record<string, string> = {
  engine_not_configured: '选车引擎未接入，请联系项目经理人工配车',
  engine_timeout: '选车引擎响应超时，可稍后重试或走正式询价',
  engine_unreachable: '选车引擎连接失败，可稍后重试或走正式询价',
  engine_error: '选车引擎暂时不可用，可稍后重试或走正式询价',
};

export async function matchFleet(input: FleetInput): Promise<FleetMatch> {
  const payload: Record<string, unknown> = {
    weight_kg: input.weight_kg,
    items: input.items.map((item) => ({
      name: item.name,
      length_m: item.length_m,
      width_m: item.width_m,
      height_m: item.height_m,
      weight_kg: item.weight_kg,
      count: item.count,
      stackable: item.stackable,
    })),
  };
  if (input.volume_m3 !== undefined) payload.volume_m3 = input.volume_m3;
  if (input.cargo_type) payload.cargo_type = input.cargo_type;
  // 超限放行：不给引擎这个键时它按默认 false 走，超限件会如实报 blocked（不回假方案）
  if (input.allow_oversized) payload.allow_oversized = true;

  try {
    const raw = await engineJson<EngineFit>('/reference/fit-vehicles', { method: 'POST', body: payload });
    // 车型库配置与配车并行取：库查询失败只让 spec 为 null，不影响配车本身
    const specs = await specMap();
    return rebuild(raw ?? {}, specs);
  } catch (error) {
    const code = error instanceof EngineError ? error.code : 'engine_error';
    console.warn('[fleet] 匹配失败：', code, (error as Error)?.message ?? error);
    return {
      ok: false,
      reason: code,
      note: FAIL_NOTES[code] ?? FAIL_NOTES.engine_error,
    };
  }
}
