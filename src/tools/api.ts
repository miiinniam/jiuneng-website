/**
 * 工具舱统一 API 封装（线路 / 报关 / 留资 / 车辆匹配）。
 *
 * 规矩（契约 §2–§3）：
 *  1. 浏览器只打本站 `/api/*`，永不直连引擎或网关。
 *  2. 所有失败都归一成 `ApiError`：`reason` 保留服务端原值（内部排查用），
 *     `message` 是客户可读中文。**英文 reason 不许出现在界面上**。
 *  3. 超时 75s：引擎冷启动实测 42.5s，服务端预算也是 75s，前端不能比它短。
 *  4. 报关 `available:false` 是**预期状态**（未配置对外系数时 fail-closed），不是错误，
 *     因此在返回值里表达，不抛异常。
 */

import { getTools } from '../content';
import type { Lang } from '../shell/i18n';

export const REQUEST_TIMEOUT_MS = 75_000;

/* 当前语言（LangProvider 挂载/切换时写入），让非组件层错误文案跟着走 */
let apiLang: Lang = 'zh';
export function setApiLang(lang: Lang) {
  apiLang = lang;
}

export class ApiError extends Error {
  readonly reason: string;
  readonly status: number;

  constructor(reason: string, message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.reason = reason;
    this.status = status;
  }
}

/* ── 服务端 reason → 客户可读中文 ─────────────────────────────── */

const REASON_TEXT: Record<string, string> = {
  // 线路测算（server/osrmQuote.ts）
  unknown_origin: '所选起点不在可测算城市清单内，请从清单中选择。',
  unknown_destination: '所选终点不在可测算城市清单内，请从清单中选择。',
  bad_weight: '货重需为大于 0 的数值（单位 kg）。',
  need_volume: '拼车测算需要填写货物总体积（m³）；若无法给出体积，请改选整车或走正式询价。',
  bad_vehicle: '整车测算需要在可选车型中指定一种。',
  not_configured: '测算引擎尚未接入，暂时无法在线测算，请联系项目经理。',
  engine_not_configured: '测算引擎尚未接入，暂时无法在线测算，请联系项目经理。',
  engine_timeout: '测算引擎响应超时（首次唤醒可能需 30–60 秒），请稍后重试；也可直接提交询价。',
  engine_unreachable: '测算引擎暂时不可达，请稍后重试；也可直接提交询价。',
  engine_error: '测算引擎返回异常，本次未能得出结论，请稍后重试或提交询价。',
  server_error: '测算服务暂时不可用，请稍后重试或提交询价。',
  no_route: '两地之间未找到可用的陆运线路，请联系项目经理确认。',
  // 留资与明细
  missing_field: '请把公司、联系人、联系方式三项填写完整。',
  rate_limited: '提交过于频繁，请稍后再试；也可以直接联系项目经理。',
  lead_required: '查看分项明细需要先留下公司与联系人信息。',
  token_mismatch: '明细凭证已失效或与当前参数不符，请重新提交参数后再查看。',
  // 车辆匹配
  bad_request: '参数不完整或格式不正确，请检查后重试。',
  invalid_input: '参数不完整或格式不正确，请检查后重试。',
  empty_cargo: '请至少填写一行货物明细（长、宽、重）。',
  // 通用
  timeout: '请求超时（75 秒），请稍后重试。',
  network: '网络异常，未能连上服务器，请检查网络后重试。',
  bad_response: '服务器返回格式异常，请稍后重试。',
};

export function reasonText(reason: string, lang: Lang = apiLang): string {
  if (lang !== 'zh') {
    const t = getTools(lang).api as Record<string, string>;
    if (t[reason]) return t[reason];
    if (/^status_5\d\d$/.test(reason)) return t.status5xx;
    if (/^status_4\d\d$/.test(reason)) return t.status4xx;
    if (/^status_/.test(reason)) return t.statusOther;
    return t.fallback;
  }
  if (REASON_TEXT[reason]) return REASON_TEXT[reason];
  if (/^status_5\d\d$/.test(reason)) return '测算引擎暂时不可用，请稍后重试；也可直接提交询价。';
  if (/^status_4\d\d$/.test(reason)) return '本次请求未被受理，请检查填写内容后重试。';
  if (/^status_/.test(reason)) return '服务端返回异常状态，请稍后重试。';
  return '请求未能完成，请稍后重试；也可以直接提交询价，由项目经理核算。';
}

/** 任何异常 → 客户可读中文（界面只显示这个）。 */
export function errorText(err: unknown, lang: Lang = apiLang): string {
  if (err instanceof ApiError) {
    // 服务端 note 只有中文；非中文界面一律走本地语言包
    if (lang === 'zh') return err.message;
    return reasonText(err.reason, lang);
  }
  const t = getTools(lang).api;
  if (err instanceof Error && err.name === 'AbortError') return t.timeout;
  return t.network;
}

/* ── 传输层 ─────────────────────────────────────────────────── */

function pickReason(data: unknown, status: number): string {
  const body = data as { reason?: unknown; error?: unknown } | null;
  if (body && typeof body.reason === 'string' && body.reason) return body.reason;
  if (body && typeof body.error === 'string' && body.error) return 'server_error';
  return `status_${status}`;
}

/** 服务端 `note` 通常是更具体的中文（如「第 1 行：单件重量需为大于 0」），有中文且不含内部运维措辞才用它。 */
const INTERNAL_NOTE = /OSRM_|ENGINE_|API_KEY|可引导客户|不要自行|内部成本/;

function pickMessage(data: unknown, reason: string): string {
  const body = data as { note?: unknown } | null;
  if (body && typeof body.note === 'string' && /[\u4e00-\u9fff]/.test(body.note) && !INTERNAL_NOTE.test(body.note)) {
    return body.note;
  }
  return reasonText(reason);
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

async function call<T>(path: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      ...init,
      signal: ctrl.signal,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
    });
    const data = await readJson(res);
    if (!res.ok) {
      const reason = pickReason(data, res.status);
      throw new ApiError(reason, pickMessage(data, reason), res.status);
    }
    if (data === null) throw new ApiError('bad_response', reasonText('bad_response'), res.status);
    return data as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError('timeout', REASON_TEXT.timeout, 0);
    }
    throw new ApiError('network', REASON_TEXT.network, 0);
  } finally {
    clearTimeout(timer);
  }
}

/* ── 类型（契约 §3 写死的形状） ───────────────────────────────── */

export type PlaceOption = { id: string; kind: 'cn' | 'border' | 'vn'; zh: string; vi: string; en: string };
export type VehicleOption = { id: string; max_load_ton: number; zh: string; vi: string; en: string };
export type PlacesResponse = { places: PlaceOption[]; vehicles: VehicleOption[] };

export type QuoteMode = 'consolidated' | 'full_truck';

export type QuoteRequest = {
  origin: string;
  destination: string;
  weight_kg: number;
  volume_m3: number | null;
  mode: QuoteMode;
  vehicle_model_id: string | null;
};

export type QuoteOk = {
  ok: true;
  origin: { id: string; label: string };
  destination: { id: string; label: string };
  border: { id: string; label: string } | null;
  mode: QuoteMode;
  distance_km: number | null;
  driving_h: number | null;
  vehicle_count: number | null;
  vehicle_id: string | null;
  vehicle_label: string | null;
  price_min_vnd: number | null;
  price_max_vnd: number | null;
  price_round_vnd: number;
  price_basis: 'engine_sell_price_pm10';
  profile_honored: boolean;
  suggestions: string[];
  disclosure: 'indicative_only';
};

export type QuoteFail = { ok: false; reason: string; note: string; status?: number };
export type QuoteResult = QuoteOk | QuoteFail;

export type CustomsParams = {
  vehicle_count: number;
  domestic_transport_rmb?: number;
  container_count?: number;
  container_type?: string | null;
  detention_days?: number;
  heavy_lift_tons?: number;
};

export type CustomsRange =
  | { available: false; note: string }
  | {
      available: true;
      china: { min_rmb: number; max_rmb: number };
      /** 汇率拿不到时服务端给 null（不许猜汇率），前端如实显示「暂不折算」 */
      vietnam: { min_vnd: number; max_vnd: number } | null;
      ddp: { min_vnd: number; max_vnd: number; rate: number } | null;
      disclosure: 'indicative_only';
      detail_requires_lead: true;
    };

export type CustomsLine = { label_zh: string; amount: number; unit: 'RMB' | 'VND' };
export type CustomsDetail = {
  china_side: CustomsLine[];
  vietnam_side: CustomsLine[];
  china_total_rmb: number;
  vietnam_total_vnd: number;
  notes: string[];
};

export type LeadResponse = { leadId: string; token: string; expiresAt: string };

export type FleetItem = {
  name?: string;
  length_m: number;
  width_m: number;
  height_m?: number;
  weight_kg: number;
  count: number;
  stackable: boolean;
};

export type FleetRequest = {
  weight_kg: number;
  volume_m3?: number | null;
  cargo_type?: string;
  items?: FleetItem[];
};

export type FleetGroup = {
  model: string;
  category: string;
  vehicle_count: number;
  reason: string;
  flags: string[];
};

export type FleetResult =
  | {
      ok: true;
      groups: FleetGroup[];
      total_trucks: number;
      oversize: { blocked: boolean; basis: string };
    }
  | { ok: false; reason: string; note: string };

/* ── 端点 ───────────────────────────────────────────────────── */

export function fetchPlaces(): Promise<PlacesResponse> {
  return call<PlacesResponse>('/api/osrm-quote/places', { method: 'GET' });
}

/** 线路测算：成功/失败都是 200 + CalcResult 原样透传，所以不抛业务错误。 */
export function postQuoteRoute(body: QuoteRequest): Promise<QuoteResult> {
  return call<QuoteResult>('/api/quote-route', { method: 'POST', body: JSON.stringify(body) });
}

export function customsQuery(params: CustomsParams): string {
  const q = new URLSearchParams();
  q.set('vehicle_count', String(params.vehicle_count));
  const put = (key: string, value: number | string | null | undefined) => {
    if (value === null || value === undefined || value === '') return;
    q.set(key, String(value));
  };
  put('domestic_transport_rmb', params.domestic_transport_rmb);
  put('container_count', params.container_count);
  put('container_type', params.container_type);
  put('detention_days', params.detention_days);
  put('heavy_lift_tons', params.heavy_lift_tons);
  return q.toString();
}

export function fetchCustomsRange(params: CustomsParams): Promise<CustomsRange> {
  return call<CustomsRange>(`/api/customs/range?${customsQuery(params)}`, { method: 'GET' });
}

export function postLead(body: {
  company: string;
  contact: string;
  reach: string;
  params: CustomsParams;
}): Promise<LeadResponse> {
  return call<LeadResponse>('/api/lead', { method: 'POST', body: JSON.stringify(body) });
}

export function postCustomsDetail(body: {
  leadId: string;
  token: string;
  params: CustomsParams;
}): Promise<CustomsDetail> {
  return call<CustomsDetail>('/api/customs/detail', { method: 'POST', body: JSON.stringify(body) });
}

export function postFleetMatch(body: FleetRequest): Promise<FleetResult> {
  return call<FleetResult>('/api/fleet-match', { method: 'POST', body: JSON.stringify(body) });
}

/* ── 展示辅助 ───────────────────────────────────────────────── */

const INT = new Intl.NumberFormat('en-US');

/** 千分位整数；空值统一显示「—」，不要出现 NaN。 */
export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return INT.format(Math.round(value));
}

export function fmtDecimal(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return value.toFixed(digits);
}

/**
 * 引擎 suggestions 可能混入英文枚举码（如 `weight_over_limit`）。
 * 只渲染含中文的条目，避免把内部枚举词露给客户。
 */
export function chineseOnly(lines: string[] | null | undefined): string[] {
  if (!Array.isArray(lines)) return [];
  return lines.filter((line) => typeof line === 'string' && /[\u4e00-\u9fff]/.test(line));
}
