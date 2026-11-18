/**
 * 报关与口岸费用：公开区间 + 留资后的分项明细（契约 §3.2 / §3.4）
 * ────────────────────────────────────────────────────────────
 * 合规红线（改代码前先读）：
 *  1. 引擎的成本参数（报关 ¥1500/车、越南清关 ¥2500/车、口岸 ¥300/800、滞留 300万/400万 VND/天、
 *     吊装 500/800/1000 ¥/吨…）**绝不允许出现在任何响应体、日志正文或错误文案里**。
 *     所以出参一律**白名单重建**：只有 `{label_zh, amount, unit}` 三个键，键名用中文业务名。
 *  2. `BORDER_MARKUP` 未配置 ⇒ `available:false`（fail-closed）。宁可不出价，也不乱报价。
 *  3. 汇率拿不到 ⇒ `ddp`/`vietnam` 为 `null`，**不许猜**（猜汇率等于乱报价）。
 *  4. 区间与分项用**同一份引擎回包**算：区间 = 成本 × 系数 × (1 ± 半宽)，取整 RMB 10 / VND 10 万；
 *     分项 = 成本 × 系数（逐项取整），合计 = 各项之和（两套口径不一致会被客户抓住）。
 */
import { v7 } from '../env.ts';
import { EngineError, engineJson } from './engineClient.ts';

export type CustomsInput = {
  vehicle_count: number;
  domestic_transport_rmb: number;
  container_count: number;
  container_type: string | null;
  detention_days: number;
  heavy_lift_tons: number;
};

export type CustomsSideItem = { label_zh: string; amount: number; unit: 'RMB' | 'VND' };

export type CustomsRange =
  | { available: false; note: string }
  | {
      available: true;
      china: { min_rmb: number; max_rmb: number };
      /** 汇率缺失时为 null（见文件头第 3 条）。 */
      vietnam: { min_vnd: number; max_vnd: number } | null;
      ddp: { min_vnd: number; max_vnd: number; rate: number } | null;
      disclosure: 'indicative_only';
      detail_requires_lead: true;
    };

export type CustomsDetail = {
  china_side: CustomsSideItem[];
  vietnam_side: CustomsSideItem[];
  china_total_rmb: number;
  vietnam_total_vnd: number;
  notes: string[];
};

export type CustomsErrorCode = 'markup_missing' | 'rate_unavailable' | 'engine_not_configured' | 'engine_timeout' | 'engine_unreachable' | 'engine_error';

export class CustomsError extends Error {
  code: CustomsErrorCode;
  status?: number;

  constructor(code: CustomsErrorCode, message: string, status?: number) {
    super(message);
    this.name = 'CustomsError';
    this.code = code;
    if (status !== undefined) this.status = status;
  }
}

/** 引擎费用 key → 中文业务名。**只认白名单**：未知键直接丢弃（不透传英文键、不猜中文名）。 */
const LABELS: Record<string, string> = {
  customs_declaration: '报关费',
  yard_fee: '口岸费',
  unloading: '装卸费',
  transloading: '换装费',
  domestic_transport: '境内运输费',
  customs_clearance: '清关费',
  inspection: '查验费',
  detention: '滞留费',
  heavy_lift: '吊装费',
  port_charge: '港杂费',
  trucking_to_site: '提货送厂',
};

const DISCLOSURE_NOTE = '金额为对外含服务口径，非成本；正式报价以项目经理复核为准';

const RMB_STEP_RANGE = 10;
const RMB_STEP_DETAIL = 10;
const VND_STEP_RANGE = 100_000;
const VND_STEP_DETAIL = 10_000;

const roundTo = (value: number, step: number): number => Math.round(value / step) * step;

/* ── 入参归一（query 与 body 共用；Express 的 query 值一律是 string|string[]） ── */

function pick(raw: unknown, key: string): unknown {
  if (!raw || typeof raw !== 'object') return undefined;
  const value = (raw as Record<string, unknown>)[key];
  return Array.isArray(value) ? value[0] : value;
}

function toFinite(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

const clamp = (n: number, min: number, max: number): number => Math.min(Math.max(n, min), max);
const clampInt = (n: number, min: number, max: number): number => clamp(Math.trunc(n), min, max);

export function parseCustomsInput(raw: unknown): CustomsInput {
  const vehicle = toFinite(pick(raw, 'vehicle_count'));
  const domestic = toFinite(pick(raw, 'domestic_transport_rmb'));
  const containers = toFinite(pick(raw, 'container_count'));
  const detention = toFinite(pick(raw, 'detention_days'));
  const heavy = toFinite(pick(raw, 'heavy_lift_tons'));
  const rawType = pick(raw, 'container_type');
  const typeText = typeof rawType === 'string' ? rawType.trim() : '';
  return {
    // 车数 <1 无意义（引擎侧 ge=1）→ 默认 1；上限 99 防止被拿来刷超长计算
    vehicle_count: vehicle === null ? 1 : clampInt(vehicle, 1, 99),
    domestic_transport_rmb: domestic === null ? 0 : Math.round(clamp(domestic, 0, 10_000_000) * 100) / 100,
    container_count: containers === null ? 0 : clampInt(containers, 0, 99),
    // 柜型只收窄到字母数字（引擎侧按配置表查，未知值自然不加费）
    container_type: /^[A-Za-z0-9_ -]{1,16}$/.test(typeText) ? typeText : null,
    detention_days: detention === null ? 0 : clampInt(detention, 0, 30),
    heavy_lift_tons: heavy === null ? 0 : Math.round(clamp(heavy, 0, 200) * 100) / 100,
  };
}

/* ── 引擎回包（只在本模块内使用，绝不外传） ── */

type EngineSide = { items?: Record<string, unknown>; subtotal?: unknown };
type EngineFees = { china_side?: EngineSide; vietnam_side?: EngineSide; china_total?: unknown; vietnam_total?: unknown };

type SideFees = { items: Record<string, number>; total: number };

function readSide(side: EngineSide | undefined, fallbackTotal: unknown): SideFees {
  const items: Record<string, number> = {};
  const raw = side?.items && typeof side.items === 'object' ? side.items : {};
  for (const [key, value] of Object.entries(raw)) {
    const n = toFinite(value);
    if (n !== null && n > 0) items[key] = n;
  }
  const total = toFinite(side?.subtotal) ?? toFinite(fallbackTotal) ?? Object.values(items).reduce((s, v) => s + v, 0);
  return { items, total };
}

async function feesOnly(input: CustomsInput): Promise<{ china: SideFees; vietnam: SideFees }> {
  const query = new URLSearchParams({
    vehicle_count: String(input.vehicle_count),
    domestic_transport_rmb: String(input.domestic_transport_rmb),
    container_count: String(input.container_count),
    detention_days: String(input.detention_days),
    heavy_lift_tons: String(input.heavy_lift_tons),
  });
  if (input.container_type) query.set('container_type', input.container_type);
  const raw = await engineJson<EngineFees>(`/border/fees-only?${query.toString()}`);
  return {
    china: readSide(raw.china_side, raw.china_total),
    vietnam: readSide(raw.vietnam_side, raw.vietnam_total),
  };
}

/** 汇率（VND / RMB）。拿不到回 null —— 绝不回落到写死的数字。 */
async function exchangeRate(): Promise<number | null> {
  try {
    const raw = await engineJson<{ vnd_per_rmb?: unknown }>('/reference/exchange-rate', { timeoutMs: Math.min(v7.toolsTimeoutMs(), 10_000) });
    const rate = toFinite(raw?.vnd_per_rmb);
    return rate !== null && rate > 0 ? rate : null;
  } catch (error) {
    console.warn('[customs] 汇率不可用（ddp 将为 null）：', (error as Error)?.message ?? error);
    return null;
  }
}

function mapEngineError(error: unknown): never {
  if (error instanceof EngineError) throw new CustomsError(error.code, error.message, error.status);
  throw new CustomsError('engine_error', String((error as Error)?.message ?? error));
}

/* ── 对外：公开区间 ── */

export async function publicRange(input: CustomsInput): Promise<CustomsRange> {
  const markup = v7.borderMarkup();
  if (markup === null) {
    // 未配置对外系数：不打引擎、不出数字（fail-closed）
    return { available: false, note: '线上暂不提供报关费测算，请联系项目经理' };
  }

  let fees: { china: SideFees; vietnam: SideFees };
  try {
    fees = await feesOnly(input);
  } catch (error) {
    console.warn('[customs] 区间测算失败：', (error as Error)?.message ?? error);
    return { available: false, note: '测算引擎暂时不可用，请联系项目经理' };
  }

  const pct = v7.borderRangePct();
  const chinaMid = fees.china.total * markup;
  const vietnamMidRmb = fees.vietnam.total * markup;
  const china = {
    min_rmb: roundTo(chinaMid * (1 - pct), RMB_STEP_RANGE),
    max_rmb: roundTo(chinaMid * (1 + pct), RMB_STEP_RANGE),
  };

  const rate = await exchangeRate();
  if (rate === null) {
    // 不许猜汇率：VND 侧与 DDP 一律 null，中国端照旧
    return {
      available: true,
      china,
      vietnam: null,
      ddp: null,
      disclosure: 'indicative_only',
      detail_requires_lead: true,
    };
  }

  const vietnamMidVnd = vietnamMidRmb * rate;
  const ddpMidVnd = (chinaMid + vietnamMidRmb) * rate;
  return {
    available: true,
    china,
    vietnam: {
      min_vnd: roundTo(vietnamMidVnd * (1 - pct), VND_STEP_RANGE),
      max_vnd: roundTo(vietnamMidVnd * (1 + pct), VND_STEP_RANGE),
    },
    ddp: {
      min_vnd: roundTo(ddpMidVnd * (1 - pct), VND_STEP_RANGE),
      max_vnd: roundTo(ddpMidVnd * (1 + pct), VND_STEP_RANGE),
      rate,
    },
    disclosure: 'indicative_only',
    detail_requires_lead: true,
  };
}

/* ── 对外：分项明细（调用方必须先过留资令牌校验） ── */

function rebuildSide(items: Record<string, number>, markup: number, unit: 'RMB' | 'VND', rate: number | null): { rows: CustomsSideItem[]; total: number } {
  const rows: CustomsSideItem[] = [];
  for (const [key, cost] of Object.entries(items)) {
    const label = LABELS[key];
    if (!label) continue; // 白名单外：丢弃，不透传英文键
    const sell = cost * markup;
    const amount = unit === 'RMB'
      ? roundTo(sell, RMB_STEP_DETAIL)
      : roundTo(sell * (rate ?? 0), VND_STEP_DETAIL);
    if (!Number.isFinite(amount) || amount <= 0) continue;
    rows.push({ label_zh: label, amount, unit });
  }
  const total = rows.reduce((sum, row) => sum + row.amount, 0);
  return { rows, total };
}

export async function detail(input: CustomsInput): Promise<CustomsDetail> {
  const markup = v7.borderMarkup();
  if (markup === null) throw new CustomsError('markup_missing', '报关费测算未开放');

  let fees: { china: SideFees; vietnam: SideFees };
  try {
    fees = await feesOnly(input);
  } catch (error) {
    mapEngineError(error);
  }

  const rate = await exchangeRate();
  if (rate === null) {
    // 越南端分项必须是 VND：没有汇率就**不返回半截数据**（宁可不给明细）
    throw new CustomsError('rate_unavailable', '汇率暂时不可用，分项明细稍后再试');
  }

  const china = rebuildSide(fees.china.items, markup, 'RMB', rate);
  const vietnam = rebuildSide(fees.vietnam.items, markup, 'VND', rate);
  return {
    china_side: china.rows,
    vietnam_side: vietnam.rows,
    china_total_rmb: china.total,
    vietnam_total_vnd: vietnam.total,
    notes: [DISCLOSURE_NOTE, `越南端按 1 RMB ≈ ${Math.round(rate)} VND 折算`],
  };
}

export const __internals = { LABELS, DISCLOSURE_NOTE };
