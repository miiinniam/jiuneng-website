// features/quote/src/api.ts
// 报价功能唯一数据出口。浏览器只打本站 /api/quote/*（同源），
// 不许直连引擎后端，也不许出现引擎域名 —— 见 CONTRACT.md §3 / §5 / §11。
//
// 约定：
// · 内部接口（模板 / 批量 / DDP / 口岸费用 / 内部报价）自动带 x-quote-key 请求头，
//   口令存在 sessionStorage['jn-quote-key']，页面只在 401 时决定怎么提示。
// · 一律 90s 超时（AbortController）；失败统一抛 QuoteApiError，message 必为中文。

import type {
  BatchRowInput,
  BatchRowResult,
  BorderCostParams,
  BorderCostResult,
  CargoTypeRate,
  DDPFullParams,
  DDPFullResult,
  QuoteFormState,
  QuoteRequest,
  QuoteResponse,
  RouteGeometry,
  TemplateOut,
  VehicleModelsByCategory,
} from './engine/types';

export type QuoteScope = 'public' | 'internal';

/* ────────────────────────── 类型（契约 §3.1 / §5） ────────────────────────── */

/**
 * 公开报价结果（服务端按白名单重建）。
 * 注意：公开口径**没有** breakdown / cost_* / margin 之类的成本字段，
 * 缺失是正常的，不要在这里做必填校验。
 */
export interface PublicQuoteResult {
  ok: true;
  scope: 'public';
  distance_km: number;
  duration_h: number;
  vehicle_count: number;
  vehicle: { id: string; name: string; max_load_ton: number | null } | null;
  /** 引擎没给售价时为 null（线上实测如此）——界面必须能渲染"暂不给区间" */
  price_low_vnd: number | null;
  price_high_vnd: number | null;
  timing: { loading_hours: number; rest_hours: number; total_duration_h: number };
  geometry: RouteGeometry | null;
}

/** 地址搜索结果（GET /api/quote/geocode） */
export interface GeoResult {
  label: string;
  lat: number;
  lng: number;
  kind?: 'city' | 'address';
}

/** GET /api/quote/reference 整包 */
export interface ReferenceBundle {
  vehicle_models: VehicleModelsByCategory;
  cargo_types: Record<string, CargoTypeRate>;
  fuel_price: { price_vnd: number; source: string };
  exchange_rate: { usd_vnd: number; cny_vnd: number; updated_at: string } | null;
}

/* ────────────────────────── AI 聊天类型 ──────────────────────────
 * 与 legacy lib/chatTypes.ts 同形（只搬类型，字段名不改），放在这里是因为
 * B 代理只交付 api.ts，D 代理的 ChatPanel 从本文件 import。
 */

export interface ChatAction {
  label: string;
  icon?: string;
  tool: string;
  payload: Record<string, unknown>;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool_status';
  content: string;
  toolName?: string;
  toolStatus?: 'running' | 'done';
  toolResult?: Record<string, unknown>;
  actions?: ChatAction[];
}

export interface SSEEvent {
  event: string; // "text" | "tool_start" | "tool_done" | "form_patch" | "quote_result" | "error" | "done"
  data: {
    content?: string;
    name?: string;
    params?: Record<string, unknown>;
    result?: Record<string, unknown>;
    message?: string;
    usage?: Record<string, unknown>;
    /** form_patch：要写进表单的补丁（camelCase，键同 QuoteFormSnapshot） */
    patch?: Record<string, unknown>;
    /** form_patch：哪个工具改的（set_route / set_cargo / …），仅用于日志 */
    reason?: string;
  };
}

/**
 * 一件货的表单快照行（与 `server/tools/quoteTools.ts` 的 QuoteFormItem 同形）。
 * 服务端 `sanitizeQuoteForm()` 逐键校验类型，多给的键会被丢弃，所以这里不塞别的字段。
 */
export interface ChatFormItem {
  id?: string;
  name?: string;
  lengthM?: number;
  widthM?: number;
  heightM?: number;
  weightKg?: number;
  count?: number;
  stackable?: boolean;
  divisible?: boolean;
}

/**
 * 当前报价表单的快照（camelCase，与 `server/tools/quoteTools.ts` 的 QuoteFormSnapshot 对齐）。
 * 只有这些键会进服务端白名单；`weightKg` 一律折成 **公斤**（服务端直接当 `weight_kg` 送引擎，
 * 不做单位换算），配对的 `weightUnit` 因此恒为 `'kg'`。
 * 不传 = AI 看不到表单（与改造前的行为完全一致）。
 */
export interface ChatFormSnapshot {
  originLabel?: string;
  destLabel?: string;
  originLat?: number;
  originLng?: number;
  destLat?: number;
  destLng?: number;
  cargoClass?: string;
  cargoType?: string;
  weightKg?: number;
  weightUnit?: string;
  items?: ChatFormItem[];
  vehicleModelId?: string;
  needLoading?: boolean;
  needUnloading?: boolean;
  needCrane?: boolean;
  /** 公开版表单目前没有这个开关，服务端白名单里有，暂不填 */
  allowOversized?: boolean;
}

/** POST /api/quote/ai 请求体 */
export interface ChatPayload {
  messages: ChatMessage[];
  /** 旧上下文（引擎透传时代用）。新后端改读 `form`，这里保留只为不改调用方签名 */
  context?: Record<string, unknown>;
  /** 当前表单快照（服务端 `body.form`）——不传时后端按空表单处理 */
  form?: ChatFormSnapshot;
  /** 回复语言：服务端 `parseLang(body.lang)` 决定工具状态行与回复语言 */
  lang?: 'zh' | 'vi' | 'en';
}

/** `aiChat` 的两个可选增量回调（都不传 ⇒ 行为与改造前一致）。 */
export interface AiChatHandlers {
  /** 服务端 `form_patch`：AI 改表单（单向下行，永不回流给模型） */
  onFormPatch?: (patch: Record<string, unknown>, reason: string) => void;
  /** 服务端 `quote_result`：确定性测算结果（公开口径，只有区间，无成本字段） */
  onQuoteResult?: (result: Record<string, unknown>) => void;
}

/* ────────────────────────── 错误 ────────────────────────── */

/**
 * 所有报价接口的失败形态。`message` 一定是中文可展示文案，
 * `reason` / `status` 只用于日志与分支判断（例如 401 让页面弹口令框）。
 */
export class QuoteApiError extends Error {
  reason: string;
  status: number;

  constructor(message: string, reason = 'unknown', status = 0) {
    super(message);
    this.name = 'QuoteApiError';
    this.reason = reason;
    this.status = status;
  }
}

/** reason → 中文文案。服务端若是引擎原样透传（含英文 message），这里统一兜中文。 */
import { apiErrors } from './i18n/apiErrors';
import { detectLang } from '../../../src/shell/i18n';

const REASON_MESSAGES: Record<string, string> = {
  unauthorized: '内部口令不正确或已过期，请重新输入',
  internal_disabled: '内部版暂未开启（服务端未配置口令），请稍后再试',
  engine_not_configured: '报价引擎尚未配置，暂时无法出价，请直接联系我们',
  engine_timeout: '报价引擎响应超时，请稍后重试',
  engine_error: '报价引擎返回异常，请稍后重试',
  engine_unreachable: '报价引擎连接失败，请稍后重试',
  bad_request: '报价参数不正确，请检查起终点与货物信息',
  route_not_found: '没有找到可用路线，请检查起终点或换一个地址',
  no_route: '没有找到可用路线，请检查起终点或换一个地址',
  ai_unavailable: 'AI 助手暂时不可用，请稍后再试',
  network: '网络连接失败，请检查网络后重试',
  timeout: '请求超时，请稍后重试',
  bad_response: '服务返回的数据格式不正确，请稍后重试',
  unknown: '请求失败，请稍后重试',
};

function messageForReason(reason: string, status: number): string {
  const lang = detectLang();
  if (lang !== 'zh') {
    const e = apiErrors(lang);
    const hit = e.reason[reason];
    if (hit) return hit;
    if (status === 401) return e.reason.unauthorized;
    if (status === 503) return e.reason.internal_disabled;
    if (status === 504) return e.reason.engine_timeout;
    if (status >= 500) return e.server;
    if (status >= 400) return e.rejected;
    return e.reason.unknown;
  }
  const known = REASON_MESSAGES[reason];
  if (known) return known;
  if (status === 401) return REASON_MESSAGES.unauthorized;
  if (status === 503) return REASON_MESSAGES.internal_disabled;
  if (status === 504) return REASON_MESSAGES.engine_timeout;
  if (status >= 500) return '服务暂时不可用，请稍后重试';
  if (status >= 400) return '请求未被接受，请检查填写内容后重试';
  return REASON_MESSAGES.unknown;
}

/* ────────────────────────── 内部口令 ────────────────────────── */

const KEY_STORAGE = 'jn-quote-key';
/** sessionStorage 被禁用（隐私模式 / 无 window）时的内存兜底 */
let memoryKey: string | null = null;

function storage(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return null;
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function setInternalKey(key: string | null): void {
  const cleaned = key === null ? null : key.trim() || null;
  memoryKey = cleaned;
  const store = storage();
  if (!store) return;
  try {
    if (cleaned === null) store.removeItem(KEY_STORAGE);
    else store.setItem(KEY_STORAGE, cleaned);
  } catch {
    /* 写入失败就只留内存值 */
  }
}

export function getInternalKey(): string | null {
  const store = storage();
  if (!store) return memoryKey;
  try {
    const v = store.getItem(KEY_STORAGE);
    if (v !== null && v !== '') return v;
  } catch {
    /* fallthrough */
  }
  return memoryKey;
}

export function hasInternalKey(): boolean {
  return getInternalKey() !== null;
}

/* ────────────────────────── 请求基建 ────────────────────────── */

const TIMEOUT_MS = 90_000;
const BASE = '/api/quote';

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** true = 带 x-quote-key（内部接口） */
  internal?: boolean;
  /** 调用方显式指定的口令（覆盖 sessionStorage 里的值）；空串视为不给 */
  internalKey?: string;
  signal?: AbortSignal;
  /** 允许空响应体（DELETE 等） */
  allowEmpty?: boolean;
};

function isAbortError(e: unknown): boolean {
  return (
    typeof e === 'object' &&
    e !== null &&
    ((e as { name?: string }).name === 'AbortError' || (e as { code?: number }).code === 20)
  );
}

/** 组合“90s 超时”与调用方传入的取消信号（不用 AbortSignal.any，兼容性更稳） */
function makeSignal(external?: AbortSignal): {
  signal: AbortSignal;
  timedOut: () => boolean;
  cleanup: () => void;
} {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, TIMEOUT_MS);
  const onAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener('abort', onAbort);
  }
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    cleanup: () => {
      clearTimeout(timer);
      external?.removeEventListener('abort', onAbort);
    },
  };
}

/**
 * 请求头组装。口令来源优先级：`internalKey`（显式传入）> sessionStorage。
 * 两个都没有就不带 x-quote-key —— 服务端按公开口径处理，这正是公开版期望。
 */
function buildHeaders(
  body: unknown,
  internal: boolean,
  internalKey?: string,
): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const raw = internalKey ?? (internal ? getInternalKey() : null);
  const key = raw && raw.trim() ? raw.trim() : null;
  if (key) headers['x-quote-key'] = key;
  return headers;
}

type Envelope = { ok?: boolean; reason?: string; message?: string } & Record<string, unknown>;

function throwFromEnvelope(env: Envelope, status: number): never {
  const reason = typeof env.reason === 'string' && env.reason ? env.reason : 'engine_error';
  const message =
    typeof env.message === 'string' && env.message.trim() ? env.message : messageForReason(reason, status);
  throw new QuoteApiError(message, reason, status);
}

/** 统一请求：拼 URL、带头、90s 超时、非 2xx / ok:false 归一成 QuoteApiError */
async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, internal = false, internalKey, signal, allowEmpty = false } = opts;
  const guard = makeSignal(signal);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: buildHeaders(body, internal, internalKey),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: guard.signal,
      credentials: 'same-origin',
      cache: 'no-store',
    });
  } catch (e) {
    if (guard.timedOut()) {
      throw new QuoteApiError(REASON_MESSAGES.timeout, 'timeout', 0);
    }
    if (isAbortError(e)) throw e; // 调用方主动取消：原样抛，页面按 AbortError 忽略
    throw new QuoteApiError(REASON_MESSAGES.network, 'network', 0);
  } finally {
    guard.cleanup();
  }

  let text = '';
  try {
    text = await res.text();
  } catch (e) {
    if (isAbortError(e)) throw e;
    throw new QuoteApiError(REASON_MESSAGES.network, 'network', res.status);
  }

  let parsed: unknown = null;
  if (text.trim()) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = null;
    }
  }

  const env = (parsed && typeof parsed === 'object' ? parsed : null) as Envelope | null;

  if (!res.ok) {
    if (env) throwFromEnvelope(env, res.status);
    throw new QuoteApiError(messageForReason(`http_${res.status}`, res.status), `http_${res.status}`, res.status);
  }

  if (env && env.ok === false) throwFromEnvelope(env, res.status);

  if (env === null) {
    if (allowEmpty) return undefined as T;
    throw new QuoteApiError(REASON_MESSAGES.bad_response, 'bad_response', res.status);
  }

  return env as T;
}

/* ────────────────────────── 公开接口 ────────────────────────── */

/** GET /api/quote/reference —— 车型库 / 货物类型费率 / 油价 / 汇率 */
export function fetchReference(): Promise<ReferenceBundle> {
  return request<ReferenceBundle>('/reference');
}

/**
 * GET /api/quote/geocode?q= —— 地址搜索。
 * 服务端失败也返回 200 + { results: [] }，所以空结果不是错误。
 */
export async function geocode(q: string): Promise<GeoResult[]> {
  const query = q.trim();
  if (!query) return [];
  const env = await request<{ results?: GeoResult[] }>(`/geocode?q=${encodeURIComponent(query)}`);
  return Array.isArray(env.results) ? env.results : [];
}

/**
 * POST /api/quote/route
 * · scope='public'   → PublicQuoteResult（无成本字段，属正常）
 * · scope='internal' → QuoteResponse（引擎原样，服务端包在 { ok:true, scope:'internal', quote } 里）
 */
export async function quoteRoute(
  req: QuoteRequest,
  scope: QuoteScope,
): Promise<PublicQuoteResult | QuoteResponse> {
  const env = await request<Envelope>('/route', {
    method: 'POST',
    body: req,
    internal: scope === 'internal',
  });

  if (scope === 'public') {
    return env as unknown as PublicQuoteResult;
  }
  const quote = (env as { quote?: unknown }).quote;
  if (quote && typeof quote === 'object') return quote as QuoteResponse;
  return env as unknown as QuoteResponse;
}

/** 区分公开结果 / 内部结果（C/D 用来收窄联合类型） */
export function isPublicQuoteResult(
  r: PublicQuoteResult | QuoteResponse | null | undefined,
): r is PublicQuoteResult {
  return !!r && (r as { scope?: string }).scope === 'public';
}

/* ────────────────────────── 自动配车（公开） ──────────────────────────
 * POST /api/quote/fit —— 「货物 → 引擎自动配车」的公开入口。
 * 契约与服务端同一份：入参 items（每件货的长宽高/重量/件数/可叠可拆），
 * 出参 picks（每个候选车型 + 需要几台 + 是否超限 + 超限许可档位/办理工作日）。
 *
 * 注意：返回里**没有**成本 / 费率 / breakdown —— 公开口径只回答「用什么车、几台」，
 * 不给钱。缺失是正常的，不要在这里做必填校验，也不要往界面塞价格。
 */

/** 一件货的尺寸与重量（单位：米 / 千克）。height_m 缺省时引擎按平放估高度。 */
export interface FitCargoItem {
  name?: string;
  length_m: number;
  width_m: number;
  height_m?: number;
  weight_kg: number;
  count?: number;
  stackable?: boolean;
  divisible?: boolean;
}

/** 单个候选车型的配车结果 */
export interface FitPick {
  model_id: string;
  name: string;
  max_load_ton: number | null;
  vehicle_count: number;
  oversize: boolean;
  /** 超限许可档位（越南口径），不超限为 null */
  permit_tier: '一类' | '二类' | '三类' | null;
  /** 许可办理所需本地工作日；不超限为 null */
  permit_workdays_local: number | null;
  permit_note: string | null;
}

/** 自动配车公开结果 —— 无成本字段，属正常 */
export interface PublicFitResult {
  ok: true;
  scope: 'public';
  total_trucks: number;
  needs_split: boolean;
  split_note: string | null;
  picks: FitPick[];
  note: string;
}

/** POST /api/quote/fit 请求体 */
export interface FitRequest {
  items: FitCargoItem[];
  cargo_type?: string;
  distance_km?: number;
  allow_oversized?: boolean;
}

/* ── 内部版配车明细（契约 08 §C）──────────────────────────────
 * 只有带合法 x-quote-key 的请求才返回这些字段；公开版**永久不返回**（成本与桌面
 * 工作台口径红线）。字段值内部形状由引擎决定（如 breakdown 的键是中文：
 * 车数/重量/体积/长度/面积/主因…），所以类型只声明「键值对」，前端按键渲染，
 * 不在此处翻译业务含义。
 */

/** 内部版单个车型组的配车明细（15 个字段与契约逐字对齐） */
export interface InternalFitGroup {
  model_id: string;
  display_name: string;
  category: string;
  /** 吨 */
  max_load_ton: number;
  vehicle_count: number;
  /** 运输单元数（拼货/多车合计口径） */
  transport_units: number;
  reason: string;
  /** 尺寸约束命中项（如「长度超限」），引擎原文 */
  dim_flags: string[];
  /** 许可相关提示（含中国/越南档位与工作日），引擎原文 */
  permit_flags: string[];
  oversize_released: boolean;
  /** 车数三重口径：floor / four_const / packer 等，键名由引擎给 */
  count_doctrine: Record<string, unknown>;
  /** 轴荷线；不涉及大件时为 null */
  axle_lines: Record<string, unknown> | null;
  /** 四约束分解：车数/重量/体积/长度/面积/主因（+ 不可分等引擎附加键） */
  breakdown: Record<string, unknown>;
  /** 共车组合：每条含 per_truck / trucks / reason，具体键以引擎为准 */
  pairs: Array<Record<string, unknown>>;
}

/** POST /api/quote/fit 内部版响应 */
export interface InternalFit {
  ok: true;
  scope: 'internal';
  total_trucks: number;
  needs_split: boolean;
  split_note: string;
  note: string;
  groups: InternalFitGroup[];
}

/**
 * POST /api/quote/fit —— 按货物自动配车。
 *
 * · 不带 internalKey（公开版 /quote）→ 8 字段公开口径，**与内部版上线前逐字段一致**；
 * · 带 internalKey（内部版 /quote/internal）→ 内部明细口径（分解 / 轴荷线 / 共车组合）。
 *
 * 失败沿用统一口径：request() 内部已把非 2xx / ok:false 归一成 QuoteApiError，
 * reason 走 messageForReason 出中文文案，所以这里不再包装、不新造错误类型。
 */
export function fitVehicles(req: FitRequest): Promise<PublicFitResult>;
export function fitVehicles(req: FitRequest, internalKey: string): Promise<InternalFit>;
export function fitVehicles(
  req: FitRequest,
  internalKey?: string,
): Promise<PublicFitResult | InternalFit> {
  if (internalKey === undefined) {
    return request<PublicFitResult>('/fit', { method: 'POST', body: req });
  }
  return request<InternalFit>('/fit', { method: 'POST', body: req, internalKey });
}

/* ────────────────────────── AI 助手（SSE） ────────────────────────── */

/**
 * POST /api/quote/ai —— 报价助手（站内编排）的 SSE，这里自己解析。
 *
 * 服务端事件（`server/agentChat.ts` 编排 + `server/tools/quoteTools.ts` 工具层）：
 *   event: tool_start   data: { name, params }
 *   event: tool_done    data: { name, result }
 *   event: text         data: { content }      ← 文本增量，逐段交给 onText
 *   event: form_patch   data: { patch, reason } ← AI 改表单，交给 handlers.onFormPatch
 *   event: quote_result data: { ok, scope, distance_km, … } ← 确定性测算结果，交给 handlers.onQuoteResult
 *   event: error        data: { message }      ← 抛 QuoteApiError
 *   event: done         data: { usage }        ← 正常结束
 * 每个事件都是 `event: <type>\ndata: <json>\n\n`。
 * tool_* 事件本函数不回调（契约只给了 onText），由 ChatPanel 用 context 自行呈现。
 * handlers 整体可省略：省略时 form_patch / quote_result 与其它未知事件一样被忽略。
 */
export async function aiChat(
  payload: ChatPayload,
  onText: (t: string) => void,
  signal?: AbortSignal,
  handlers?: AiChatHandlers,
): Promise<void> {
  // 流式要用可重置的看门狗：90s 无新数据就中断，长答不会因为总时长被砍。
  const controller = new AbortController();
  let timedOut = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const arm = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, TIMEOUT_MS);
  };
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', onAbort);
  }
  const cleanup = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    signal?.removeEventListener('abort', onAbort);
  };

  arm();
  try {
    let res: Response;
    try {
      res = await fetch(`${BASE}/ai`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(payload),
        signal: controller.signal,
        credentials: 'same-origin',
        cache: 'no-store',
      });
    } catch (e) {
      if (timedOut) throw new QuoteApiError(REASON_MESSAGES.timeout, 'timeout', 0);
      if (isAbortError(e)) throw e;
      throw new QuoteApiError(REASON_MESSAGES.network, 'network', 0);
    }

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      let env: Envelope | null = null;
      try {
        env = text ? (JSON.parse(text) as Envelope) : null;
      } catch {
        env = null;
      }
      if (env) throwFromEnvelope(env, res.status);
      throw new QuoteApiError(
        messageForReason(`http_${res.status}`, res.status),
        `http_${res.status}`,
        res.status,
      );
    }

    if (!res.body) {
      throw new QuoteApiError(REASON_MESSAGES.bad_response, 'bad_response', res.status);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finished = false;

    const handleBlock = (block: string) => {
      if (!block.trim()) return;
      let eventName = '';
      const dataLines: string[] = [];
      for (const rawLine of block.split('\n')) {
        const line = rawLine.replace(/\r$/, '');
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
      }
      if (dataLines.length === 0) return;

      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
      } catch {
        return; // 半截/畸形 JSON 直接丢，不打断流
      }

      const kind = eventName || (typeof data.content === 'string' ? 'text' : '');
      switch (kind) {
        case 'text': {
          const piece = typeof data.content === 'string' ? data.content : '';
          if (piece) onText(piece);
          break;
        }
        /* AI 改表单：服务端算好的补丁（camelCase，只含白名单键），单向下行 */
        case 'form_patch': {
          const onFormPatch = handlers?.onFormPatch;
          if (!onFormPatch) break;
          const rawPatch = data.patch;
          if (!rawPatch || typeof rawPatch !== 'object' || Array.isArray(rawPatch)) break;
          const reason = typeof data.reason === 'string' ? data.reason : '';
          onFormPatch(rawPatch as Record<string, unknown>, reason);
          break;
        }
        /* 确定性测算结果：data 本身就是公开测算对象（ok / scope / distance_km / …） */
        case 'quote_result': {
          handlers?.onQuoteResult?.(data);
          break;
        }
        case 'error': {
          const msg =
            typeof data.message === 'string' && data.message.trim()
              ? data.message
              : REASON_MESSAGES.ai_unavailable;
          throw new QuoteApiError(msg, 'ai_error', 200);
        }
        case 'done':
          finished = true;
          break;
        default:
          break; // tool_start / tool_done / 未知事件：忽略
      }
    };

    while (!finished) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (e) {
        if (timedOut) throw new QuoteApiError(REASON_MESSAGES.timeout, 'timeout', 0);
        if (isAbortError(e)) throw e;
        throw new QuoteApiError(REASON_MESSAGES.network, 'network', 0);
      }
      arm(); // 收到数据就续命

      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });

      let sep = buffer.indexOf('\n\n');
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        handleBlock(block);
        if (finished) break;
        sep = buffer.indexOf('\n\n');
      }
    }

    // 收尾：最后一段没有结尾空行也要处理
    if (!finished) {
      const tail = buffer.trim();
      if (tail) handleBlock(tail);
    } else {
      // 收到 done 就主动断开，别让连接挂到服务端超时
      await reader.cancel().catch(() => undefined);
    }
  } catch (e) {
    if (timedOut) throw new QuoteApiError(REASON_MESSAGES.timeout, 'timeout', 0);
    throw e;
  } finally {
    cleanup();
  }
}

/* ────────────────────────── 模板（内部） ────────────────────────── */

/**
 * GET /api/quote/templates
 * 公开版服务端返回空数组（前端此时改用 localStorage，见 CONTRACT §3.1）。
 * 口令存在时自动带上 x-quote-key，所以内部版拿到真数据。
 */
export async function listTemplates(): Promise<TemplateOut[]> {
  const env = await request<{ templates?: TemplateOut[] }>('/templates', {
    internal: hasInternalKey(),
  });
  return Array.isArray(env.templates) ? env.templates : [];
}

/** POST /api/quote/templates → 200 TemplateOut */
export function saveTemplate(name: string, config: QuoteFormState): Promise<TemplateOut> {
  return request<TemplateOut>('/templates', {
    method: 'POST',
    body: { name, config },
    internal: true,
  });
}

/** DELETE /api/quote/templates/:id */
export async function deleteTemplate(id: string): Promise<void> {
  await request<void>(`/templates/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    internal: true,
    allowEmpty: true,
  });
}

/* ────────────────────────── 批量 / 边境费用（内部） ────────────────────────── */

/** POST /api/quote/batch → { results } */
export async function batchQuote(rows: BatchRowInput[]): Promise<BatchRowResult[]> {
  const env = await request<{ results?: BatchRowResult[] }>('/batch', {
    method: 'POST',
    body: { rows },
    internal: true,
  });
  return Array.isArray(env.results) ? env.results : [];
}

/** POST /api/quote/ddp → DDPFullResult */
export function ddpCosts(p: DDPFullParams): Promise<DDPFullResult> {
  return request<DDPFullResult>('/ddp', { method: 'POST', body: p, internal: true });
}

/** POST /api/quote/customs → BorderCostResult */
export function customsCosts(p: BorderCostParams): Promise<BorderCostResult> {
  return request<BorderCostResult>('/customs', { method: 'POST', body: p, internal: true });
}
