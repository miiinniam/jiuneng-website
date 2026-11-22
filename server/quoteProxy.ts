/**
 * 报价功能（features/quote）后端代理 —— 浏览器与 OSRM++ 引擎之间的唯一通道
 * ──────────────────────────────────────────────────────────────────────────
 * 契约见 `features/quote/CONTRACT.md` §3。只有三条硬规矩，改动前先读：
 *
 *  1. **引擎地址只在服务端**：浏览器只打 `/api/quote/*`，响应里不得出现引擎域名/密钥。
 *  2. **公开口径由服务端重建**：`POST /api/quote/route`（无口令）只回白名单字段
 *     （里程/时长/车数/车型 + 参考价区间），`breakdown` / `cost_*` / `margin` / `profit`
 *     一个都不许出门。内部版（`x-quote-key`）才回引擎原样 QuoteResponse。
 *     自动配车 `POST /api/quote/fit` 同一套：无口令只回 8 字段对客白名单（`buildPublicFit`），
 *     口令通过才回配车明细（`buildInternalFit`，仍断掉成本单价口径）。
 *  3. **对客 message 必须是中文**：英文 reason 只允许出现在 `reason` 字段里；
 *     引擎原始报错（可能含车型库/公式/堆栈）只截断进 `console.error`，绝不拼进响应。
 *
 * 其它约定：
 *  · 超时默认 75s（Render 免费层冷启动实测 30–60s），路线计算对「毫秒级 502/断连」
 *    做冷启动退避重试（与 `server/osrmQuote.ts` 同一套判据，见 COLD_START_WAITS）。
 *  · `OSRM_API_BASE` 未配置 → 一律 `{ ok:false, reason:'engine_not_configured' }`，
 *    不许由服务端或前端自行估数。
 *  · `QUOTE_INTERNAL_KEY` 未配置 → 内部端点 503 `internal_disabled`（fail-closed）。
 */
import { Router, Request, Response } from 'express';
import { createQuoteAiHandler } from './quoteAi';
import { geocodeFallback } from './geocodeFallback';
import crypto from 'crypto';
import { engineApiBase, engineKey } from './env.ts';

/* ────────────────────────────── 时间预算 ────────────────────────────── */

/** 引擎调用默认预算：冷启动（免费层休眠唤醒 30–60s）也在这个窗口内。 */
const ENGINE_TIMEOUT_MS = 75_000;
/** 页面首屏依赖的轻量参考数据：等太久比「暂时没有」更伤，冷启动由 /route 的长预算兜住。 */
const REFERENCE_TIMEOUT_MS = 20_000;
/** 地址搜索同理：失败一律 200 + 空数组，不值得让用户盯着转圈。 */
const GEOCODE_TIMEOUT_MS = 12_000;
/** 判定「快速失败」的阈值：快于它的 5xx/断连按「实例未唤醒」处理，值得退避重试。 */
const FAST_FAIL_MS = 3_000;
/** 冷启动退避：4+8+16+24 = 累计 52s，加 5 次尝试仍在 75s 预算内（同 osrmQuote.ts）。 */
const COLD_START_WAITS = [4_000, 8_000, 16_000, 24_000];
/** Node 定时器延迟是 32 位有符号存储，超过它会回绕成极小值（立刻超时）。 */
const MAX_TIMER_MS = 2_147_483_647;

/** 参考价区间取整到 10 万 VND（与 `server/osrmQuote.ts` 完全一致，不要另设步长）。 */
const PRICE_STEP_VND = 100_000;

/* ────────────────────────────── 缓存 ────────────────────────────── */

type CacheEntry<T> = { at: number; value: T };

/**
 * 小型 TTL 缓存 + 单飞合并。
 * · 只缓存**成功**结果：失败不入缓存，否则一次瞬时 502 会让参考数据冻住十分钟；
 * · 单飞：同一 key 并发只打一次引擎（页面打开会同时请求 reference 与 route）。
 */
const cacheStore = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

async function cached<T>(key: string, ttlMs: number, load: () => Promise<T | null>): Promise<T | null> {
  const hit = cacheStore.get(key) as CacheEntry<T> | undefined;
  if (hit && Date.now() - hit.at < ttlMs) return hit.value;
  const pending = inflight.get(key) as Promise<T | null> | undefined;
  if (pending) return pending;
  const task = (async () => {
    const value = await load();
    if (value !== null) cacheStore.set(key, { at: Date.now(), value });
    return value;
  })();
  inflight.set(key, task);
  try {
    return await task;
  } finally {
    inflight.delete(key);
  }
}

const VEHICLE_TTL_MS = 10 * 60_000;
const RATE_TTL_MS = 5 * 60_000;
/** 第三方汇率（USD/VND）每小时更新一次即可，失败不缓存。 */
const FX_TTL_MS = 60 * 60_000;

/* ────────────────────────────── 引擎调用 ────────────────────────────── */

/** 已归一化的失败：`reason` 给分支判断，`message` 是可直接展示的中文。 */
export type QuoteFailure = { reason: string; message: string; status: number };

/**
 * 引擎调用结果。
 * ⚠️ 故意**不做** `{ok:true}|{ok:false}` 联合：本项目 tsconfig 未开 strictNullChecks，
 *    TS 5.8 在这种配置下不收窄布尔字面量判别式（`if (!r.ok)` 之后仍报 `failure` 不存在），
 *    于是所有分支都得写 `=== false`。用单一形状 + 可选字段，读起来一致、也不会被类型绊住。
 */
type EngineResult = { ok: boolean; data?: unknown; failure?: QuoteFailure };

type EngineInit = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  timeoutMs?: number;
  /** 冷启动退避重试（只给 /route/cost 这类「客户在等结果」的调用开）。 */
  coldStartRetry?: boolean;
};

const fail = (reason: string, message: string, status: number): EngineResult => ({
  ok: false,
  failure: { reason, message, status },
});

/** 引擎非 2xx 的对外中文文案（原始报文只进日志）。 */
function messageForEngineStatus(status: number): string {
  // 400/422 都是「输入不被接受」（未知货类、缺车型、缺体积…）→ 让客户改参数，别说成引擎故障
  if (status === 400 || status === 422) return '测算条件不被接受，请检查货物类型、车型与重量后重试。';
  if (status === 429) return '测算请求过于频繁，请稍后再试。';
  if (status === 401 || status === 403) return '测算服务暂不可用（鉴权未通过），请联系项目经理。';
  return '测算服务暂时不可用，请稍后再试或直接走正式询价。';
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 在剩余预算内等待（退避不能把总预算吃穿，否则「重试」变成「必然超时」）。 */
async function sleepWithin(ms: number, deadline: number): Promise<void> {
  const left = deadline - Date.now();
  if (left <= 0) return;
  await sleep(Math.min(ms, left));
}

/**
 * 调用引擎并归一化结果。**永不抛异常**（网络/解析错误都变成 EngineErr），
 * 这样各个路由只需要处理一种形状，也不会因为漏 catch 把 Express 进程带崩。
 */
async function callEngine(pathAndQuery: string, init: EngineInit = {}): Promise<EngineResult> {
  const base = engineApiBase();
  if (!base) {
    return fail('engine_not_configured', '报价引擎尚未配置，暂时无法出价，请直接联系我们。', 503);
  }
  const url = `${base}${pathAndQuery.startsWith('/') ? '' : '/'}${pathAndQuery}`;
  const method = init.method ?? 'GET';
  const budget = Math.min(init.timeoutMs ?? ENGINE_TIMEOUT_MS, MAX_TIMER_MS);
  const deadline = Date.now() + budget;
  const waits = init.coldStartRetry ? COLD_START_WAITS : [];

  for (let attempt = 0; attempt <= waits.length; attempt += 1) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      return fail('engine_timeout', '测算引擎响应超时，请稍后再试。', 504);
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), remaining);
    const startedAt = Date.now();
    try {
      const res = await fetch(url, {
        method,
        headers: {
          Accept: 'application/json',
          ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(engineKey() ? { 'X-API-Key': engineKey() } : {}),
          'User-Agent': 'jiuneng-website-quote-proxy',
        },
        ...(init.body !== undefined ? { body: JSON.stringify(init.body) } : {}),
        signal: ctrl.signal,
      });
      if (res.ok) {
        const text = await res.text();
        try {
          return { ok: true, data: text.trim() ? JSON.parse(text) : null };
        } catch {
          console.error(`[quote-proxy] ${method} ${pathAndQuery} 响应不是合法 JSON：${text.slice(0, 200)}`);
          return fail('engine_error', '测算服务返回的数据格式异常，请稍后再试。', 502);
        }
      }
      const detail = await res.text().catch(() => '');
      console.error(
        `[quote-proxy] ${method} ${pathAndQuery} status=${res.status} ${String(detail).slice(0, 300)}`,
      );
      const fastFail = res.status >= 500 && Date.now() - startedAt < FAST_FAIL_MS && attempt < waits.length;
      if (fastFail) {
        console.warn(`[quote-proxy] 引擎快速返回 ${res.status}（疑似实例未唤醒），第 ${attempt + 1} 次重试`);
        await sleepWithin(waits[attempt], deadline);
        continue;
      }
      // 422/400 是「条件不被接受」，502 语义不对，用 422 让调用方区分「改参数」与「等一会」
      const status = res.status === 422 || res.status === 400 ? 422 : res.status === 429 ? 429 : 502;
      return fail('engine_error', messageForEngineStatus(res.status), status);
    } catch (error) {
      const aborted = (error as { name?: string })?.name === 'AbortError';
      // 本段是**业务预算**到点：如实报超时，不重试
      if (aborted) return fail('engine_timeout', '测算引擎响应超时，请稍后再试。', 504);
      const fastFail = Date.now() - startedAt < FAST_FAIL_MS && attempt < waits.length;
      if (fastFail) {
        console.warn(`[quote-proxy] 引擎快速失败（疑似实例未唤醒），第 ${attempt + 1} 次重试：`, error);
        await sleepWithin(waits[attempt], deadline);
        continue;
      }
      console.error(`[quote-proxy] ${method} ${pathAndQuery} 连接失败：`, error);
      return fail('engine_unreachable', '测算引擎连接失败，请稍后再试或直接联系我们。', 502);
    } finally {
      clearTimeout(timer);
    }
  }
  return fail('engine_unreachable', '测算引擎连接失败，请稍后再试或直接联系我们。', 502);
}

/* ────────────────────────────── 参考数据 ────────────────────────────── */

type VehicleModel = {
  model_id?: unknown;
  display_name?: unknown;
  max_load_ton?: unknown;
  [key: string]: unknown;
};
type VehicleModelsByCategory = Record<string, VehicleModel[]>;

/** 车型库（按类别分组，引擎原样）+ 按 model_id 索引（route 重建公开车型信息用）。 */
async function vehicleCatalogue(): Promise<VehicleModelsByCategory | null> {
  return cached('vehicle-models', VEHICLE_TTL_MS, async () => {
    const r = await callEngine('/reference/vehicle-models', { timeoutMs: REFERENCE_TIMEOUT_MS });
    if (!r.ok) return null;
    const data = r.data;
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    return data as VehicleModelsByCategory;
  });
}

async function vehicleIndex(): Promise<Map<string, VehicleModel>> {
  const catalogue = await vehicleCatalogue();
  const index = new Map<string, VehicleModel>();
  if (!catalogue) return index;
  for (const models of Object.values(catalogue)) {
    if (!Array.isArray(models)) continue;
    for (const model of models) {
      const id = typeof model?.model_id === 'string' ? model.model_id : '';
      if (id) index.set(id, model);
    }
  }
  return index;
}

async function cargoTypeRates(): Promise<Record<string, unknown> | null> {
  return cached('cargo-types', RATE_TTL_MS, async () => {
    const r = await callEngine('/reference/cargo-types', { timeoutMs: REFERENCE_TIMEOUT_MS });
    if (!r.ok || !r.data || typeof r.data !== 'object') return null;
    return r.data as Record<string, unknown>;
  });
}

async function fuelPriceInfo(): Promise<{ price_vnd: number; source: string } | null> {
  return cached('fuel-price', RATE_TTL_MS, async () => {
    const r = await callEngine('/reference/fuel-price', { timeoutMs: REFERENCE_TIMEOUT_MS });
    if (!r.ok || !r.data || typeof r.data !== 'object') return null;
    const raw = r.data as { price_vnd?: unknown; source?: unknown };
    const price = typeof raw.price_vnd === 'number' && Number.isFinite(raw.price_vnd) ? raw.price_vnd : null;
    if (price === null) return null;
    return { price_vnd: price, source: typeof raw.source === 'string' ? raw.source : 'engine' };
  });
}

/** 引擎汇率：`vnd_per_rmb`（VND / 1 CNY）+ 更新时间。 */
async function engineExchangeRate(): Promise<{ vnd_per_rmb: number; updated: string } | null> {
  return cached('exchange-rate', RATE_TTL_MS, async () => {
    const r = await callEngine('/reference/exchange-rate', { timeoutMs: REFERENCE_TIMEOUT_MS });
    if (!r.ok || !r.data || typeof r.data !== 'object') return null;
    const raw = r.data as { vnd_per_rmb?: unknown; updated?: unknown };
    const rate = typeof raw.vnd_per_rmb === 'number' && Number.isFinite(raw.vnd_per_rmb) && raw.vnd_per_rmb > 0
      ? raw.vnd_per_rmb
      : null;
    if (rate === null) return null;
    return { vnd_per_rmb: rate, updated: typeof raw.updated === 'string' ? raw.updated : '' };
  });
}

/**
 * USD→VND 汇率。
 * 为什么另找：引擎只提供 `vnd_per_rmb`（引擎侧 `exchange_rate.py` 用 exchangerate-api 的 CNY base），
 * 没有美元口径。契约 §3.1 要求 `exchange_rate.usd_vnd`，所以这里走同一个公开数据源取一次，
 * 失败就回 null —— **绝不**用固定数字顶替（猜汇率比不给汇率更糟）。
 */
async function usdVndRate(): Promise<number | null> {
  return cached('usd-vnd', FX_TTL_MS, async () => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 3_000);
    try {
      const res = await fetch('https://api.exchangerate-api.com/v4/latest/USD', {
        signal: ctrl.signal,
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) return null;
      const raw = (await res.json()) as { rates?: { VND?: unknown } };
      const vnd = raw?.rates?.VND;
      return typeof vnd === 'number' && Number.isFinite(vnd) && vnd > 0 ? vnd : null;
    } catch (error) {
      console.warn('[quote-proxy] USD/VND 汇率不可用（usd_vnd 将为 null）：', (error as Error)?.message ?? error);
      return null;
    } finally {
      clearTimeout(timer);
    }
  });
}

/* ────────────────────────────── 小工具 ────────────────────────────── */

const isFiniteNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

const roundTo = (v: number, step: number) => Math.round(v / step) * step;

/** 保留 1 位小数（里程/时长这类展示值，不暴露引擎的浮点长尾巴）。 */
const round1 = (v: number) => Math.round(v * 10) / 10;

const toNumberOr = (v: unknown, fallback: number): number => {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return fallback;
};

const toBool = (v: unknown): boolean => v === true || v === 'true' || v === 1;

/** 只保留含中日韩字符的引擎文案（英文 detail 不许进对客 message）。 */
function hasCjk(text: string): boolean {
  return /[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff]/.test(text);
}

/** 请求体不是对象（null/数组/字符串）时统一当空对象，避免各处重复判断。 */
function bodyOf(req: Request): Record<string, unknown> {
  const body = req.body;
  return body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string, unknown>) : {};
}

/** 客户可读的中文参数错误。 */
const badRequest = (message: string): QuoteFailure => ({ reason: 'bad_request', message, status: 400 });

/**
 * 引擎未配置时的统一失败。
 * ⚠️ 必须在**参数归一之前**拦：否则「车型自动匹配」会先失败成「请选择车型」，
 *    把「引擎没配」误报成「客户没填」——排障方向会被带歪。
 */
const notConfigured = (): QuoteFailure => ({
  reason: 'engine_not_configured',
  message: '报价引擎尚未配置，暂时无法出价，请直接联系我们。',
  status: 503,
});

const engineConfigured = (): boolean => Boolean(engineApiBase());

const sendFailure = (res: Response, failure: QuoteFailure): void => {
  res.status(failure.status).json({ ok: false, reason: failure.reason, message: failure.message });
};

/* ────────────────────────────── 内部口令 ────────────────────────────── */

function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a, 'utf8');
  const right = Buffer.from(b, 'utf8');
  if (left.length !== right.length) return false;
  try {
    return crypto.timingSafeEqual(left, right);
  } catch {
    return false;
  }
}

/**
 * 内部端点鉴权。返回 null = 通过；否则是应当直接回给客户端的失败。
 * 顺序很重要：**先判「有没有配口令」** —— 没配时无论 key 对错都该说「未开启」，
 * 说「口令错」会让运维去查一个根本不存在的口令。
 */
function requireInternalKey(req: Request): QuoteFailure | null {
  const configured = (process.env.QUOTE_INTERNAL_KEY || '').trim();
  if (!configured) {
    return { reason: 'internal_disabled', message: '内部版暂未开启（服务端未配置口令），请联系管理员。', status: 503 };
  }
  const given = String(req.get('x-quote-key') ?? '').trim();
  if (!given || !safeEqual(given, configured)) {
    return { reason: 'unauthorized', message: '内部口令不正确或已过期，请重新输入。', status: 401 };
  }
  return null;
}

/* ────────────────────────────── 请求归一 ────────────────────────────── */

/** 常见货物类型别名 → 引擎口径（引擎只认 `normal / cold_chain / hazardous / ...`）。 */
const CARGO_TYPE_ALIASES: Record<string, string> = {
  general: 'normal',
  'general cargo': 'normal',
  general_cargo: 'normal',
  general_goods: 'normal',
  common: 'normal',
  cargo: 'normal',
  goods: 'normal',
  standard: 'normal',
  normal_cargo: 'normal',
  普通: 'normal',
  普货: 'normal',
  普通货物: 'normal',
  通用: 'normal',
  杂货: 'normal',
};

type NormalizedRequest = {
  request: Record<string, unknown>;
  /** 服务端为「可选字段」补的默认值，只进日志（客户没填不该判错，但必须可追溯）。 */
  notes: string[];
};

/**
 * 把契约里的 QuoteRequest 归一成引擎能接受的形状。
 * 只有两种情况会「改」客户输入，都是契约本身声明为可选的字段：
 *  1. `cargo.type`：`general` 之类的通用写法引擎不认（会 400 `"general"`），映射到 `normal`；
 *  2. `vehicle.vehicle_model_id`：契约 §4 标为可选，但引擎对 `full_truck` 强制要求（422）。
 *     此时按货重从车型库挑最小的够载车型，结果会被回写到响应的 `vehicle` 字段里，
 *     客户能看到实际用的是哪台车 —— 不静默、不猜价。
 */
async function normalizeRequest(raw: Record<string, unknown>): Promise<{ value: NormalizedRequest } | { failure: QuoteFailure }> {
  const notes: string[] = [];
  const route = (raw.route && typeof raw.route === 'object' ? raw.route : {}) as Record<string, unknown>;
  const cargo = (raw.cargo && typeof raw.cargo === 'object' ? raw.cargo : {}) as Record<string, unknown>;
  const vehicle = (raw.vehicle && typeof raw.vehicle === 'object' ? raw.vehicle : {}) as Record<string, unknown>;
  const costParams = (raw.cost_params && typeof raw.cost_params === 'object' ? raw.cost_params : {}) as Record<string, unknown>;

  const point = (p: unknown): { lat: number; lng: number } | null => {
    if (!p || typeof p !== 'object') return null;
    const o = p as Record<string, unknown>;
    const lat = toNumberOr(o.lat, NaN);
    const lng = toNumberOr(o.lng, NaN);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return { lat, lng };
  };

  const origin = point(route.origin);
  const destination = point(route.destination);
  if (!origin) return { failure: badRequest('起点坐标无效，请重新选择起运地。') };
  if (!destination) return { failure: badRequest('终点坐标无效，请重新选择目的地。') };

  const rawWaypoints = Array.isArray(route.waypoints) ? route.waypoints : [];
  const waypoints = rawWaypoints.map(point).filter((p): p is { lat: number; lng: number } => p !== null);
  if (waypoints.length !== rawWaypoints.length) {
    return { failure: badRequest('途经点坐标无效，请重新选择途经地。') };
  }

  const weightKg = toNumberOr(cargo.weight_kg, NaN);
  if (!Number.isFinite(weightKg) || weightKg <= 0) {
    return { failure: badRequest('货物重量需为大于 0 的数值（单位 kg）。') };
  }

  const rawType = typeof cargo.type === 'string' ? cargo.type.trim().toLowerCase() : '';
  const type = rawType ? CARGO_TYPE_ALIASES[rawType] ?? rawType : 'normal';
  if (type !== rawType) notes.push(`cargo.type ${rawType} → ${type}`);

  const volumeRaw = toNumberOr(cargo.volume_m3, NaN);
  const volumeM3 = Number.isFinite(volumeRaw) && volumeRaw > 0 ? volumeRaw : null;

  const loadingMode = vehicle.loading_mode === 'full_truck' ? 'full_truck' : 'consolidated';
  let vehicleModelId = typeof vehicle.vehicle_model_id === 'string' ? vehicle.vehicle_model_id.trim() : '';

  if (loadingMode === 'full_truck' && !vehicleModelId) {
    const index = await vehicleIndex();
    if (index.size === 0) {
      // 车型库拿不到就不要瞎填：如实让客户选车型（比出一个没有车型依据的价更负责）
      return { failure: badRequest('车型库暂时取不到，请稍后重试或手动选择车型。') };
    }
    const weightTon = weightKg / 1000;
    const candidates = [...index.values()]
      .map((m) => ({
        id: typeof m.model_id === 'string' ? m.model_id : '',
        load: toNumberOr(m.max_load_ton, 0),
      }))
      .filter((m) => m.id && m.load > 0)
      .sort((a, b) => a.load - b.load);
    const fitting = candidates.find((m) => m.load >= weightTon) ?? candidates[candidates.length - 1];
    if (!fitting) return { failure: badRequest('请选择车型（整车测算需要明确车型）。') };
    vehicleModelId = fitting.id;
    notes.push(`vehicle_model_id 缺省 → 自动匹配 ${fitting.id}（${fitting.load}t，载重 ${weightTon}t）`);
  }

  if (loadingMode === 'consolidated' && volumeM3 === null) {
    // 引擎口径：拼车按体积+重量计费，缺体积会 422 —— 提前拦，给可读原因
    return { failure: badRequest('拼车测算需要填写货物总体积（m³）；若无法给出体积，请改选整车。') };
  }

  const request: Record<string, unknown> = {
    route: { origin, destination, waypoints },
    cargo: {
      weight_kg: weightKg,
      type,
      ...(volumeM3 !== null ? { volume_m3: volumeM3 } : {}),
      ...(isFiniteNumber(cargo.value_vnd) ? { value_vnd: cargo.value_vnd } : {}),
      ...(Array.isArray(cargo.items) ? { items: cargo.items } : {}),
    },
    vehicle: {
      loading_mode: loadingMode,
      ...(vehicleModelId ? { vehicle_model_id: vehicleModelId } : {}),
      empty_return: toBool(vehicle.empty_return),
      need_loading: toBool(vehicle.need_loading),
      avoid_restricted_zones: toBool(vehicle.avoid_restricted_zones),
      avoid_construction_zones: toBool(vehicle.avoid_construction_zones),
      via_mountain_road: toBool(vehicle.via_mountain_road),
    },
    cost_params: {
      ...(isFiniteNumber(costParams.fuel_price_vnd) ? { fuel_price_vnd: costParams.fuel_price_vnd } : {}),
      ...(isFiniteNumber(costParams.wage_hourly_vnd) ? { wage_hourly_vnd: costParams.wage_hourly_vnd } : {}),
      ...(isFiniteNumber(costParams.toll_rate_vnd_per_km) ? { toll_rate_vnd_per_km: costParams.toll_rate_vnd_per_km } : {}),
      misc_cost_vnd: toNumberOr(costParams.misc_cost_vnd, 0),
    },
  };

  return { value: { request, notes } };
}

/* ────────────────────────────── 公开口径重建 ────────────────────────────── */

/**
 * 把引擎 QuoteResponse 压成对客白名单。
 * ⚠️ 这里就是「成本不出门」的唯一闸门：`breakdown`（含 cost_x / margin / profit 各键）整个不读。
 * 参考价区间沿用 `server/osrmQuote.ts` 的口径：引擎**售价** `price_vnd` × 0.9 ~ × 1.1，
 * 取整到 10 万 VND。引擎不提供 `price_vnd` 时**不出一分钱**（null），
 * 绝不拿 cost_total 顶替 —— 那等于把成本泄漏给客户。
 */
function buildPublicQuote(
  raw: Record<string, unknown>,
  index: Map<string, VehicleModel>,
): Record<string, unknown> {
  const route = (raw.route && typeof raw.route === 'object' ? raw.route : {}) as Record<string, unknown>;
  const timing = (raw.timing && typeof raw.timing === 'object' ? raw.timing : {}) as Record<string, unknown>;
  const breakdown = (raw.breakdown && typeof raw.breakdown === 'object' ? raw.breakdown : {}) as Record<string, unknown>;

  const matchedId = typeof breakdown.matched_vehicle_model_id === 'string' ? breakdown.matched_vehicle_model_id : '';
  const matchedName = typeof breakdown.matched_vehicle_model_name === 'string' ? breakdown.matched_vehicle_model_name : '';
  const model = matchedId ? index.get(matchedId) : undefined;
  const vehicle = matchedId
    ? {
        id: matchedId,
        name: matchedName || (typeof model?.display_name === 'string' ? model.display_name : matchedId),
        max_load_ton: isFiniteNumber(model?.max_load_ton) ? model.max_load_ton : null,
      }
    : null;

  const sell = isFiniteNumber(raw.price_vnd) && raw.price_vnd > 0 ? raw.price_vnd : null;
  const priceLow = sell === null ? null : roundTo(sell * 0.9, PRICE_STEP_VND);
  const priceHigh = sell === null ? null : roundTo(sell * 1.1, PRICE_STEP_VND);

  const distance = isFiniteNumber(route.distance_km) ? route.distance_km : null;
  const duration = isFiniteNumber(route.adjusted_duration_h)
    ? route.adjusted_duration_h
    : isFiniteNumber(route.duration_h)
      ? route.duration_h
      : null;

  return {
    ok: true,
    scope: 'public',
    distance_km: distance === null ? null : round1(distance),
    duration_h: duration === null ? null : round1(duration),
    vehicle_count: Math.max(1, Math.trunc(toNumberOr(raw.vehicle_count ?? breakdown.vehicle_count, 1))),
    vehicle,
    price_low_vnd: priceLow,
    price_high_vnd: priceHigh,
    timing: {
      loading_hours: round1(toNumberOr(timing.loading_hours, 0)),
      rest_hours: round1(toNumberOr(timing.rest_hours, 0)),
      total_duration_h: round1(toNumberOr(timing.total_duration_h, duration ?? 0)),
    },
    geometry: route.geometry && typeof route.geometry === 'object' ? route.geometry : null,
  };
}

/* ────────────────────────────── 自动配车公开口径 ────────────────────────────── */

/**
 * 引擎 `permit_flags` 里唯一对客的许可口径：`中国许可：二类（省内 5 个工作日 / 跨省 10 个工作日）…`。
 * 为什么只解析这一句、而不是整条数组外传：同一数组里还混着越南侧/出口侧的内部判据与收费口径，
 * 整条给客户等于把规则表送出去。只取「等级 + 省内工作日」，匹配不到就三个字段全 null —— 不猜许可等级。
 */
const PERMIT_FLAG_RE = /中国许可：(一类|二类|三类)（省内\s*(\d+)\s*个工作日/;

type PermitInfo = {
  permit_tier: '一类' | '二类' | '三类' | null;
  permit_workdays_local: number | null;
  permit_note: string | null;
};

function permitFromFlags(flags: unknown): PermitInfo {
  const none: PermitInfo = { permit_tier: null, permit_workdays_local: null, permit_note: null };
  if (!Array.isArray(flags)) return none;
  for (const flag of flags) {
    if (typeof flag !== 'string') continue;
    const matched = flag.match(PERMIT_FLAG_RE);
    if (!matched) continue;
    const workdays = Number(matched[2]);
    return {
      permit_tier: matched[1] as '一类' | '二类' | '三类',
      permit_workdays_local: Number.isFinite(workdays) ? workdays : null,
      // 全文给客户（含跨省天数），但截断：引擎文案尾部可能跟内部备注
      permit_note: flag.slice(0, 200),
    };
  }
  return none;
}

/** 对客车型方案：字段与 `features/quote` 前端类型一一对应，多一个都不加。 */
type PublicFitPick = {
  model_id: string;
  name: string;
  max_load_ton: number | null;
  vehicle_count: number;
  oversize: boolean;
  permit_tier: '一类' | '二类' | '三类' | null;
  permit_workdays_local: number | null;
  permit_note: string | null;
};

/**
 * 把引擎 FitVehiclesResponse 压成对客白名单。
 * ⚠️ 与 `buildPublicQuote` 同一个闸门原则：`groups` 里的 `breakdown` / `count_doctrine` /
 *    `axle_lines` / `pairs` / `items`（以及任何含 cost|rate|price|margin|profit 的键）**一个都不读**，
 *    只按下面显式列出的键重新组装。要加字段先确认它不是成本或规则口径。
 * 排序必须稳定可复现（车数降序、同数按 model_id 升序）：客户刷新两次不能看到两套方案。
 */
function buildPublicFit(
  raw: Record<string, unknown>,
  index: Map<string, VehicleModel>,
): Record<string, unknown> {
  const groups = Array.isArray(raw.groups) ? raw.groups : [];

  const picks = groups
    .map((entry) => (entry && typeof entry === 'object' ? entry : {}) as Record<string, unknown>)
    .map((group): PublicFitPick | null => {
      const modelId = typeof group.model_id === 'string' ? group.model_id.trim() : '';
      if (!modelId) return null; // 没有车型号，对客没法说明是哪个方案
      const model = index.get(modelId);

      const groupName = typeof group.display_name === 'string' ? group.display_name.trim() : '';
      const indexNameRaw = model?.display_name;
      const indexName = typeof indexNameRaw === 'string' ? indexNameRaw : '';

      const groupLoadRaw = group.max_load_ton;
      const indexLoadRaw = model?.max_load_ton;
      const groupLoad = isFiniteNumber(groupLoadRaw) ? groupLoadRaw : null;
      const indexLoad = isFiniteNumber(indexLoadRaw) ? indexLoadRaw : null;

      return {
        model_id: modelId,
        name: groupName || indexName || modelId,
        max_load_ton: groupLoad !== null ? groupLoad : indexLoad,
        vehicle_count: Math.max(1, Math.trunc(toNumberOr(group.vehicle_count, 1))),
        oversize: Boolean(group.oversize_released),
        ...permitFromFlags(group.permit_flags),
      };
    })
    .filter((pick): pick is PublicFitPick => pick !== null)
    .sort(
      (a, b) =>
        b.vehicle_count - a.vehicle_count ||
        (a.model_id < b.model_id ? -1 : a.model_id > b.model_id ? 1 : 0),
    )
    .slice(0, 3);

  const totalTrucks = isFiniteNumber(raw.total_trucks) ? raw.total_trucks : 0;
  const needsSplit = Boolean(raw.needs_split);
  const splitNote = needsSplit && typeof raw.split_hint === 'string' ? raw.split_hint.slice(0, 300) : null;

  return {
    ok: true,
    scope: 'public',
    total_trucks: totalTrucks,
    needs_split: needsSplit,
    split_note: splitNote,
    picks,
    // 0 车时必须说清「不是没算，是配不出来」，否则客户会以为页面卡住了；
    // 另有一个缝：total>0 但 groups 全被过滤（无 model_id / 脏数据）时，不能对客说「0 个方案，共 N 车」
    note:
      picks.length > 0
        ? `引擎按逐件口径配车：${picks.length} 个车型方案，共 ${totalTrucks} 车。`
        : totalTrucks > 0
          ? `已算出 ${totalTrucks} 车，但车型方案明细不完整，请走正式询价复核。`
          : '当前尺寸/重量在库内配不出可行车型，请补充货物明细或走正式询价。',
  };
}

/* ────────────────────────────── 自动配车内部口径 ────────────────────────────── */

/**
 * 内部版（`x-quote-key` 通过）组的字段集 —— 共 15 个，与契约 C 节一一对应：
 * 契约类型列了 14 个（model_id / display_name / category / max_load_ton / vehicle_count /
 * transport_units / reason / dim_flags / permit_flags / oversize_released / count_doctrine /
 * axle_lines / breakdown / pairs），引擎 `_group_out` 里另有 `pair_total_width_m`
 * （共车组合总宽，非成本口径），凑齐 15，也一并显式带出。
 * ⚠️ 引擎组里的 `items`（逐行明细 + 逐行 axle_lines）与 `locked`（桌面版逐行锁定态）**不带**：
 *    前者是行级工作态、后者是操作态，契约 C 没有它们，内部版只到「组」这一层。
 * 成本/单价键（base_rate / fixed_surcharge / toll_rate / fuel_l_per / margin / profit / notes）
 * 连内部版也不出门 —— 想看成本走 `/route` 的内部原样口径。
 */
export type InternalFitGroup = {
  model_id: string;
  display_name: string;
  category: string;
  max_load_ton: number;
  vehicle_count: number;
  transport_units: number;
  reason: string;
  dim_flags: string[];
  permit_flags: string[];
  oversize_released: boolean;
  count_doctrine: Record<string, unknown>;
  axle_lines: Record<string, unknown> | null;
  breakdown: Record<string, unknown>;
  pairs: Array<Record<string, unknown>>;
  pair_total_width_m: number | null;
};

export type InternalFit = {
  ok: true;
  scope: 'internal';
  total_trucks: number;
  needs_split: boolean;
  split_note: string;
  note: string;
  groups: InternalFitGroup[];
  /**
   * 可解体件（A6）拆件建议 —— 引擎 `plan.divisibility` 原样口径。
   * 引擎在「未标 `divisible`」或「本就不超限」时给 `None`，这里对应 `null`（键始终存在）。
   */
  divisibility: Record<string, unknown> | null;
};

/**
 * 嵌套对象里一旦出现这些词，就是成本/供应商备注口径，逐键断掉（与 `/reference` 的剥离同一套判据）。
 * 用**子串**匹配而不是整键相等：引擎会派生出 `fixed_surcharge_vnd` / `base_rate_vnd_per_km`
 * 这类带单位的变体。刻意不匹配裸 `cost` —— `count_doctrine.cost_caliber` 是口径标签（如
 * `rate_only`），不是金额，丢了会让内部版看不到车数口径来源。
 */
const COST_KEY_TOKENS = ['base_rate', 'fixed_surcharge', 'toll_rate', 'fuel_l_per', 'margin', 'profit', 'notes'];

function isCostKey(key: string): boolean {
  const lowered = key.toLowerCase();
  return COST_KEY_TOKENS.some((token) => lowered.includes(token));
}

/** 逐键重建一层 plain object（不是 spread、不是深拷贝）：成本键在这里断掉。 */
function plainRecord(value: unknown): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (!value || typeof value !== 'object' || Array.isArray(value)) return out;
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (isCostKey(key)) continue;
    out[key] = item;
  }
  return out;
}

/** 字符串数组字段：非字符串项丢掉（引擎给 null/数字都当没有），顺序与内容如实。 */
function stringListOf(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

/**
 * 把引擎 FitVehiclesResponse 转成**内部版**形状（`/quote/internal` 的配车明细）。
 * ⚠️ 与 `buildPublicFit` 相反的取舍，别互相抄：
 *   · 公开版是「白名单重建成 8 字段、最多 3 组、按车数排序」，因为对客只需要方案名与许可等级；
 *   · 内部版是「逐键显式赋值但**不裁剪**」：组数不截、顺序不动（引擎顺序即主组优先），
 *     0 车也如实写 0 —— 员工核对的就是引擎到底算了什么，静默过滤等于把证据抹掉。
 * 引擎组里 15 个字段都已存在（`app/api/reference.py` 的 `_group_out`），不需要补算。
 */
function buildInternalFit(raw: Record<string, unknown>): InternalFit {
  const rawGroups = Array.isArray(raw.groups) ? raw.groups : [];

  const groups: InternalFitGroup[] = rawGroups.map((entry) => {
    const group = (entry && typeof entry === 'object' && !Array.isArray(entry) ? entry : {}) as Record<string, unknown>;
    const vehicleCount = Math.max(0, Math.trunc(toNumberOr(group.vehicle_count, 0)));
    const axleRaw = group.axle_lines;

    // 每个键都单独写：引擎以后再往组里加字段（items/locked/per_truck…）也不会顺着漏出来
    return {
      model_id: typeof group.model_id === 'string' ? group.model_id.trim() : '',
      display_name: typeof group.display_name === 'string' ? group.display_name : '',
      category: typeof group.category === 'string' ? group.category : '',
      max_load_ton: toNumberOr(group.max_load_ton, 0),
      vehicle_count: vehicleCount,
      // 引擎口径：一次许可对一个运输单元；缺字段时按车数回落（与 `_group_out` 的取值一致）
      transport_units: Math.max(0, Math.trunc(toNumberOr(group.transport_units, vehicleCount))),
      reason: typeof group.reason === 'string' ? group.reason : '',
      dim_flags: stringListOf(group.dim_flags),
      permit_flags: stringListOf(group.permit_flags),
      oversize_released: group.oversize_released === true,
      count_doctrine: plainRecord(group.count_doctrine),
      // axle_lines 可能是 null（没有逐行轴荷推演），如实透传 null 而不是伪造空对象
      axle_lines: axleRaw && typeof axleRaw === 'object' && !Array.isArray(axleRaw)
        ? plainRecord(axleRaw)
        : null,
      breakdown: plainRecord(group.breakdown),
      // pairs 可能是空数组，元素逐个重建（`per_truck` / `pair_id` 是内部编排细节，内部版保留）
      pairs: (Array.isArray(group.pairs) ? group.pairs : []).map((pair) => plainRecord(pair)),
      pair_total_width_m: isFiniteNumber(group.pair_total_width_m) ? group.pair_total_width_m : null,
    };
  });

  const totalTrucks = Math.max(0, Math.trunc(toNumberOr(raw.total_trucks, 0)));
  const needsSplit = raw.needs_split === true;
  // 公开版只在 needs_split 时给拆单提示（免得吓到客户）；内部版不设这道闸，有 hint 就原样给
  const splitNote = typeof raw.split_hint === 'string' ? raw.split_hint : '';
  // A6 拆件建议：引擎 `plan.divisibility`（dict）或 None。重建一层而不是整块塞，成本键照样断掉；
  // 非 dict（数组/字符串等异常形状）一律 null —— 前端按「无建议」渲染，不给它猜的机会。
  const divisibilityRaw = raw.divisibility;
  const divisibility = divisibilityRaw && typeof divisibilityRaw === 'object' && !Array.isArray(divisibilityRaw)
    ? plainRecord(divisibilityRaw)
    : null;

  return {
    ok: true,
    scope: 'internal',
    total_trucks: totalTrucks,
    needs_split: needsSplit,
    split_note: splitNote,
    note:
      groups.length > 0
        ? `内部版配车明细：${groups.length} 个车型方案，共 ${totalTrucks} 车（引擎逐件口径，未做对客裁剪）。`
        : totalTrucks > 0
          ? `已算出 ${totalTrucks} 车，但引擎未给分组明细，请核对引擎日志。`
          : '引擎未配出可行车型（groups 为空），请核对货物明细或超限开关。',
    groups,
    divisibility,
  };
}

/* ────────────────────────────── 路由 ────────────────────────────── */

export function createQuoteRouter(): Router {
  const router = Router();

  /**
   * 内部端点通用前置：口令 → 引擎配置。
   * 返回 true 表示已经回过包，调用方直接 return。
   * 顺序固定：先说「没开内部版/口令错」，再说「引擎没配」——否则运维会拿错口令去查引擎。
   */
  const rejectInternal = (req: Request, res: Response): boolean => {
    const denied = requireInternalKey(req);
    if (denied) {
      sendFailure(res, denied);
      return true;
    }
    if (!engineConfigured()) {
      sendFailure(res, notConfigured());
      return true;
    }
    return false;
  };

  /* ── GET /reference：车型库 + 货类费率 + 油价 + 汇率（聚合，公开） ── */
  router.get('/reference', async (req: Request, res: Response) => {
    if (!engineConfigured()) {
      sendFailure(res, notConfigured());
      return;
    }
    const [vehicles, cargo, fuel, fx] = await Promise.all([
      vehicleCatalogue(),
      cargoTypeRates(),
      fuelPriceInfo(),
      engineExchangeRate(),
    ]);

    // 四份数据一次取齐才算「参考数据可用」：缺车型库前端连车型都选不了，如实报错更好排练错
    if (!vehicles || !cargo || !fuel) {
      res.status(502).json({
        ok: false,
        reason: 'engine_unavailable',
        message: '参考数据暂时取不到，请稍后刷新页面或直接联系我们。',
      });
      return;
    }

    let exchange: Record<string, unknown> | null = null;
    if (fx) {
      const usd = await usdVndRate();
      exchange = {
        usd_vnd: usd,
        cny_vnd: fx.vnd_per_rmb,
        updated_at: fx.updated || new Date().toISOString(),
      };
    }

    // 只回这三块白名单（引擎 reference 里的其它参数不外传）
    //
    // 车型库必须再筛一层：引擎的车型对象含 base_rate_vnd_per_km / fixed_surcharge_vnd /
    // fuel_l_per_100km / toll_rate_vnd_per_km / notes（供应商报价备注）。原来原样外传，
    // 公开接口能直接读到成本单价与供应商名 —— 与「不暴露成本」的红线冲突。
    // 公开只给客户选车需要的展示与装载参数；内部版（x-quote-key 正确）才给全量。
    const wantsFull = requireInternalKey(req) === null;
    const vehicleOut = wantsFull
      ? vehicles
      : Object.fromEntries(
          Object.entries(vehicles).map(([cat, list]) => [
            cat,
            Array.isArray(list)
              ? list.map((m) => ({
                  model_id: m.model_id,
                  display_name: m.display_name,
                  max_load_ton: m.max_load_ton,
                  volume_capacity_m3: m.volume_capacity_m3 ?? null,
                  effective_volume_m3: m.effective_volume_m3 ?? null,
                  length_m: m.length_m ?? null,
                  width_m: m.width_m ?? null,
                  height_m: m.height_m ?? null,
                  max_cargo_height_m: m.max_cargo_height_m ?? null,
                  suitable_cargo_types: Array.isArray(m.suitable_cargo_types) ? m.suitable_cargo_types : [],
                }))
              : list,
          ]),
        );

    // 货类同理：rate_multiplier 是成本口径的加价系数，公开只给键（前端自己映射中文名）
    const cargoOut = wantsFull
      ? cargo
      : Object.fromEntries(Object.keys(cargo).map((k) => [k, {}]));

    res.json({
      vehicle_models: vehicleOut,
      cargo_types: cargoOut,
      fuel_price: fuel,
      exchange_rate: exchange,
    });
  });

  /* ── GET /geocode?q=：地址检索（公开，失败一律 200 + 空数组） ── */
  router.get('/geocode', async (req: Request, res: Response) => {
    const q = String(req.query.q ?? '').trim();
    // 地址搜索失败不是错误（契约 §3.1）：任何形状的失败都回空数组，前端照常让用户手填坐标
    if (!q || q.length > 120) {
      res.json({ results: [] });
      return;
    }
    const r = await callEngine(`/geocode?q=${encodeURIComponent(q)}&limit=6`, { timeoutMs: GEOCODE_TIMEOUT_MS });
    let results: Array<{ label: string; lat: number; lng: number }> = [];
    if (r.ok && Array.isArray(r.data)) {
      results = r.data
        .map((item) => {
          const o = (item && typeof item === 'object' ? item : {}) as Record<string, unknown>;
          const label = typeof o.display_name === 'string' ? o.display_name : typeof o.label === 'string' ? o.label : '';
          const lat = toNumberOr(o.lat, NaN);
          const lng = toNumberOr(o.lng, NaN);
          if (!label || !Number.isFinite(lat) || !Number.isFinite(lng)) return null;
          return { label, lat, lng };
        })
        .filter((x): x is { label: string; lat: number; lng: number } => x !== null);
    }
    // 线上引擎调公共 Nominatim 恒返空（Render 的数据中心 IP 被 OSM 限制，实测中英越三种写法全空），
    // 而本地同一条链正常 → 引擎空就交给官网侧兜底链（中文别名 → Photon）。
    // 表单地址建议与 AI 的 set_route 共用这一处，别只在其中一条上加兜底。
    if (!results.length) {
      results = await geocodeFallback(q, 6);
      // 线上诊断用：Render 日志里能直接看出「引擎空 → 兜底命中几条」
      console.info(`[geocode] 引擎空，兜底 "${q}" → ${results.length} 条`);
    }
    res.json({ results });
  });

  /* ── POST /route：公开口径重建 / 内部引擎原样（同一路由，看头部） ── */
  router.post('/route', async (req: Request, res: Response) => {
    const wantsInternal = Boolean(String(req.get('x-quote-key') ?? '').trim());
    if (wantsInternal) {
      const denied = requireInternalKey(req);
      if (denied) {
        sendFailure(res, denied);
        return;
      }
    }
    if (!engineConfigured()) {
      sendFailure(res, notConfigured());
      return;
    }

    const normalized = await normalizeRequest(bodyOf(req));
    if ('failure' in normalized) {
      sendFailure(res, normalized.failure);
      return;
    }
    const { request, notes } = normalized.value;
    if (notes.length) console.info(`[quote-proxy] 请求补全：${notes.join('；')}`);

    const r = await callEngine('/route/cost', {
      method: 'POST',
      body: request,
      timeoutMs: ENGINE_TIMEOUT_MS,
      coldStartRetry: true,
    });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    const raw = (r.data && typeof r.data === 'object' ? r.data : {}) as Record<string, unknown>;

    if (wantsInternal) {
      // 内部版：引擎原样（含成本分项），只有在口令校验通过后才可能走到这里
      res.json({ ok: true, scope: 'internal', quote: raw });
      return;
    }

    const index = await vehicleIndex();
    res.json(buildPublicQuote(raw, index));
  });

  /* ── POST /fit：自动配车（公开 8 字段 / 内部明细，看头部） ── */
  router.post('/fit', async (req: Request, res: Response) => {
    // 内部版：带了 x-quote-key 就必须校验通过（与 /route 同一套写法）；
    // 没带头则一律走公开口径 —— 公开路径的字段集在下游 verify-quote-fit.py 里逐字段钉死。
    const wantsInternalFit = Boolean(String(req.get('x-quote-key') ?? '').trim());
    if (wantsInternalFit) {
      const denied = requireInternalKey(req);
      if (denied) {
        sendFailure(res, denied);
        return;
      }
    }
    if (!engineConfigured()) {
      sendFailure(res, notConfigured());
      return;
    }

    const body = bodyOf(req);
    const rawItems = Array.isArray(body.items) ? body.items : [];
    // 200 行上限与 /batch 同思路：引擎按「逐件」展开，没有上限时一个畸形请求就能把内存吃穿。
    // 文案沿用契约固定句式（前端按这句做提示映射），行数超限也回同一句。
    if (rawItems.length === 0 || rawItems.length > 200) {
      sendFailure(res, badRequest('请先填写货物明细（至少 1 行）。'));
      return;
    }

    const items: Record<string, unknown>[] = [];
    for (const entry of rawItems) {
      const item = (entry && typeof entry === 'object' ? entry : {}) as Record<string, unknown>;
      const lengthM = toNumberOr(item.length_m, NaN);
      const widthM = toNumberOr(item.width_m, NaN);
      const weightKg = toNumberOr(item.weight_kg, NaN);
      // 尺寸/重量是配车的唯一依据，缺一个就只能配出假方案 —— 宁可让客户回头补
      if (
        !Number.isFinite(lengthM) || lengthM <= 0 ||
        !Number.isFinite(widthM) || widthM <= 0 ||
        !Number.isFinite(weightKg) || weightKg <= 0
      ) {
        sendFailure(res, badRequest('货物明细存在无效尺寸或重量，请检查后重试。'));
        return;
      }

      // height_m 缺省按 0 处理（引擎自己回落），但服务端不替客户编一个高度：编了会直接改配车结论
      const heightM = toNumberOr(item.height_m, NaN);
      const name = typeof item.name === 'string' ? item.name.trim().slice(0, 80) : '';
      // 布尔项只在客户真的给了才转发：显式 false 会覆盖引擎默认口径（例如可拆分默认值）
      const flags: Record<string, boolean> = {};
      if (item.stackable !== undefined) flags.stackable = toBool(item.stackable);
      if (item.divisible !== undefined) flags.divisible = toBool(item.divisible);

      // 逐键重建，不 spread 原始 item —— 前端多塞的键（含成本/口令类字段）在这里就断了
      items.push({
        ...(name ? { name } : {}),
        length_m: lengthM,
        width_m: widthM,
        ...(Number.isFinite(heightM) && heightM > 0 ? { height_m: heightM } : {}),
        weight_kg: weightKg,
        count: Math.max(1, Math.trunc(toNumberOr(item.count, 1))),
        ...flags,
      });
    }

    const cargoType = typeof body.cargo_type === 'string' ? body.cargo_type.trim() : '';
    const distanceKm = toNumberOr(body.distance_km, NaN);
    const allowOversized = body.allow_oversized === undefined ? null : toBool(body.allow_oversized);

    const r = await callEngine('/reference/fit-vehicles', {
      method: 'POST',
      body: {
        items,
        ...(cargoType ? { cargo_type: cargoType } : {}),
        ...(Number.isFinite(distanceKm) && distanceKm > 0 ? { distance_km: distanceKm } : {}),
        ...(allowOversized === null ? {} : { allow_oversized: allowOversized }),
      },
      timeoutMs: ENGINE_TIMEOUT_MS,
      // 与 /route 一致：客户正盯着结果，冷启动值得退避重试
      coldStartRetry: true,
    });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }

    const raw = (r.data && typeof r.data === 'object' && !Array.isArray(r.data) ? r.data : {}) as Record<string, unknown>;

    if (wantsInternalFit) {
      // 内部版：逐键重建配车明细（组不截、顺序不动）。只有口令校验通过才可能走到这里，
      // 且不查车型库 —— 引擎组里已带 display_name / max_load_ton，内部版照引擎口径说话。
      res.json(buildInternalFit(raw));
      return;
    }

    // 车型库只用来补 display_name / max_load_ton；拿不到也不影响配车主结论（名称回落 model_id）
    const index = await vehicleIndex();
    res.json(buildPublicFit(raw, index));
  });

  /* ── POST /ai：SSE 透传（公开） ── */
  /* ── POST /ai：报价助手（站内编排；金额只给区间，表单改动走 form_patch 单向下发） ── */
  //
  // 原先这里把引擎 /ai/chat 的 SSE 原样透传：工具跑在引擎进程内（插不进自己的工具、下不发表单补丁），
  // 且引擎 prompt 要求输出 13 项运费 breakdown ⇒ 客户能在聊天正文看到成本结构。
  // 现在工具在本服务跑（server/tools/quoteTools.ts），引擎退回成纯计算后端。
  router.post('/ai', createQuoteAiHandler({
    geocode: async (q: string) => {
      const r = await callEngine(`/geocode?q=${encodeURIComponent(q)}&limit=1`, {
        timeoutMs: GEOCODE_TIMEOUT_MS,
      });
      // 引擎这个端点回的是**数组**（不是 {results:[...]}）—— 照抄本文件 /geocode 路由的读法，别猜。
      if (r.ok && Array.isArray(r.data)) {
        const first = (r.data[0] && typeof r.data[0] === 'object' ? r.data[0] : null) as Record<string, unknown> | null;
        if (first) {
          const label =
            typeof first.display_name === 'string'
              ? first.display_name
              : typeof first.label === 'string'
                ? first.label
                : '';
          const lat = toNumberOr(first.lat, NaN);
          const lng = toNumberOr(first.lng, NaN);
          if (label && Number.isFinite(lat) && Number.isFinite(lng)) {
            return { label: label.slice(0, 120), lat, lng };
          }
        }
      }
      // 线上引擎调 Nominatim 恒空（Render IP 被 OSM 限制）→ 与表单共用同一条兜底链，
      // 否则 AI 会对着「南宁」说「检索不到坐标」，而表单里明明是能搜到的。
      const hits = await geocodeFallback(q, 1);
      return hits[0] ?? null;
    },
    runQuote: async (form) => {
      // 与 /route **同一条链路**：normalizeRequest → 引擎 → buildPublicQuote（只区间口径）。
      // 另写一套计价或自己剥价 = 页面上出现第二份数字，必然对不上。
      //
      // 无明细时**不要**自己造一行「0 尺寸」的货：引擎对 length_m / width_m = 0 直接 422，
      // 而 normalizeRequest 在没有 items 时本来就会补一行（实测 HTTP 200，能出里程与区间）。
      const cargo: Record<string, unknown> = {
        weight_kg: form.weightKg,
        type: form.cargoType || 'normal',
      };
      if (form.items?.length) {
        cargo.items = form.items.map((it) => ({
          name: it.name,
          length_m: it.lengthM,
          width_m: it.widthM,
          height_m: it.heightM,
          weight_kg: it.weightKg,
          count: it.count,
          stackable: it.stackable,
          divisible: it.divisible,
        }));
      }
      const request: Record<string, unknown> = {
        route: {
          origin: { lat: form.originLat, lng: form.originLng },
          destination: { lat: form.destLat, lng: form.destLng },
        },
        cargo,
        vehicle: {
          loading_mode: 'full_truck',
          ...(form.vehicleModelId ? { vehicle_model_id: form.vehicleModelId } : {}),
        },
        ...(form.cargoClass === 'oversized' ? { allow_oversized: true } : {}),
      };
      const normalized = await normalizeRequest(request);
      if ('failure' in normalized) {
        console.warn('[quote-ai] run_quote 入参规范化失败：', normalized.failure);
        return null;
      }
      // ⚠️ normalized.value 是 { request, notes }，喂给引擎的必须是 request ——
      //    直接传整个对象会让引擎收到 {request,notes} 而 422（实测报「引擎暂时不可用」）。
      const { request: engineRequest, notes } = normalized.value;
      if (notes.length) console.info(`[quote-ai] 入参补全：${notes.join('；')}`);
      const r = await callEngine('/route/cost', {
        method: 'POST',
        body: engineRequest,
        timeoutMs: ENGINE_TIMEOUT_MS,
        // 免费层实例休眠时首个请求毫秒级断连 —— 官网表单路径同样开这个退避，AI 路径不能更差
        coldStartRetry: true,
      });
      if (!r.ok) return null;
      const raw = (r.data && typeof r.data === 'object' ? r.data : {}) as Record<string, unknown>;
      // buildPublicQuote 是公开白名单的唯一出口：breakdown / cost_* / margin / profit 一个都不读
      const index = await vehicleIndex();
      return buildPublicQuote(raw, index) as unknown as Record<string, unknown>;
    },
  }));

  /* ── 模板：公开只回空数组，内部走引擎持久化 ── */

  router.get('/templates', async (req: Request, res: Response) => {
    const hasKeyHeader = Boolean(String(req.get('x-quote-key') ?? '').trim());
    if (!hasKeyHeader) {
      // 公开版：契约 §3.1 固定空数组，前端改用 localStorage
      res.json({ templates: [] });
      return;
    }
    if (rejectInternal(req, res)) return;
    const r = await callEngine('/templates', { timeoutMs: ENGINE_TIMEOUT_MS });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    res.json({ templates: Array.isArray(r.data) ? r.data : [] });
  });

  router.post('/templates', async (req: Request, res: Response) => {
    if (rejectInternal(req, res)) return;
    const body = bodyOf(req);
    const name = typeof body.name === 'string' ? body.name.trim() : '';
    const config = body.config && typeof body.config === 'object' && !Array.isArray(body.config) ? body.config : null;
    if (!name || name.length > 80) {
      sendFailure(res, badRequest('模板名称不能为空，且不超过 80 个字符。'));
      return;
    }
    if (!config) {
      sendFailure(res, badRequest('模板内容缺失，无法保存。'));
      return;
    }
    const r = await callEngine('/templates', { method: 'POST', body: { name, config }, timeoutMs: ENGINE_TIMEOUT_MS });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    res.json(r.data);
  });

  /** 改名：契约写 PATCH，引擎只提供 PUT —— 两个动词都收，前端按契约用 PATCH 即可。 */
  const renameTemplate = async (req: Request, res: Response) => {
    if (rejectInternal(req, res)) return;
    const id = String(req.params.id ?? '').trim();
    const name = typeof bodyOf(req).name === 'string' ? String(bodyOf(req).name).trim() : '';
    if (!id || !name || name.length > 80) {
      sendFailure(res, badRequest('模板名称不能为空，且不超过 80 个字符。'));
      return;
    }
    const r = await callEngine(`/templates/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: { name },
      timeoutMs: ENGINE_TIMEOUT_MS,
    });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    res.json(r.data);
  };
  router.patch('/templates/:id', renameTemplate);
  router.put('/templates/:id', renameTemplate);

  router.delete('/templates/:id', async (req: Request, res: Response) => {
    if (rejectInternal(req, res)) return;
    const id = String(req.params.id ?? '').trim();
    if (!id) {
      sendFailure(res, badRequest('模板不存在。'));
      return;
    }
    const r = await callEngine(`/templates/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      timeoutMs: ENGINE_TIMEOUT_MS,
    });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    // 引擎回 {ok:true}；统一形状，前端静默成功即可
    res.json({ ok: true });
  });

  /* ── POST /batch：批量报价（内部） ── */
  router.post('/batch', async (req: Request, res: Response) => {
    if (rejectInternal(req, res)) return;
    const rows = bodyOf(req).rows;
    if (!Array.isArray(rows) || rows.length === 0) {
      sendFailure(res, badRequest('没有可计算的批量数据，请先导入表格。'));
      return;
    }
    if (rows.length > 500) {
      sendFailure(res, badRequest('单次批量最多支持 500 行，请拆分后重试。'));
      return;
    }
    const r = await callEngine('/batch/quote', {
      method: 'POST',
      body: { rows },
      // 批量本身要逐行打引擎，预算按行数放大，但有上限（避免请求挂到网关超时）
      timeoutMs: Math.min(MAX_TIMER_MS, ENGINE_TIMEOUT_MS + Math.min(rows.length, 100) * 1_000),
    });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    const data = (r.data && typeof r.data === 'object' ? r.data : {}) as Record<string, unknown>;
    res.json({ results: Array.isArray(data.results) ? data.results : [] });
  });

  /* ── POST /ddp：DDP 全链路非运输费用（内部） ── */
  router.post('/ddp', async (req: Request, res: Response) => {
    if (rejectInternal(req, res)) return;
    const body = bodyOf(req);
    const clampInt = (v: unknown, min: number, max: number, fallback: number): number => {
      const n = toNumberOr(v, fallback);
      return Math.min(max, Math.max(min, Math.trunc(n)));
    };
    const round2 = (v: number) => Math.round(v * 100) / 100;

    const vehicleCount = clampInt(body.vehicle_count, 1, 99, 1);
    const domestic = Math.max(0, toNumberOr(body.domestic_transport_rmb, 0));
    const containerCount = clampInt(body.container_count, 0, 99, 0);
    const containerType = typeof body.container_type === 'string' ? body.container_type.trim() : '';
    const detentionDays = clampInt(body.detention_days, 0, 30, 0);
    const heavyLiftTons = Math.max(0, toNumberOr(body.heavy_lift_tons, 0));
    const cargoValue = Math.max(0, toNumberOr(body.cargo_value_rmb, 0));
    const hsCode = typeof body.hs_code === 'string' ? body.hs_code.trim() : '';
    const transportCostVnd = Math.max(0, toNumberOr(body.transport_cost_vnd, 0));
    const isBreakbulk = toBool(body.is_breakbulk);
    const breakbulkTons = Math.max(0, toNumberOr(body.breakbulk_tons, 0));
    const includeRebate = toBool(body.include_export_rebate);

    /*
     * 为什么分两次打 `/border/china-side` + `/border/vietnam-side`，而不是一次 `/border/fees-only`：
     * fees-only 只吃「车数/境内运费/柜数/滞港/吊装」，**丢掉 hs_code 与货值** → 关税与增值税会被
     * 静默算成 0，DDP 总额偏低。两个 side 端点各自支持货值/HS/退税/换装，加起来正好合成
     * DDPFullResult（引擎 fees-only 内部的 ddp_total 本身也是 china_total + vietnam_total）。
     */
    const chinaQuery = new URLSearchParams({
      vehicle_count: String(vehicleCount),
      domestic_transport_rmb: String(round2(domestic)),
      cargo_value_rmb: String(round2(cargoValue)),
      include_rebate: String(includeRebate),
    });
    const vietnamQuery = new URLSearchParams({
      vehicle_count: String(vehicleCount),
      container_count: String(containerCount),
      is_breakbulk: String(isBreakbulk),
      breakbulk_tons: String(round2(breakbulkTons)),
      cargo_value_rmb: String(round2(cargoValue)),
      hs_code: hsCode,
      transport_cost_vnd: String(round2(transportCostVnd)),
      detention_days: String(detentionDays),
      heavy_lift_tons: String(round2(heavyLiftTons)),
    });
    if (containerType) vietnamQuery.set('container_type', containerType);

    const [china, vietnam] = await Promise.all([
      callEngine(`/border/china-side?${chinaQuery.toString()}`, { timeoutMs: ENGINE_TIMEOUT_MS }),
      callEngine(`/border/vietnam-side?${vietnamQuery.toString()}`, { timeoutMs: ENGINE_TIMEOUT_MS }),
    ]);
    if (!china.ok) {
      sendFailure(res, china.failure);
      return;
    }
    if (!vietnam.ok) {
      sendFailure(res, vietnam.failure);
      return;
    }

    const side = (data: unknown): { items: Record<string, number>; subtotal: number } => {
      const o = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
      const items: Record<string, number> = {};
      const rawItems = (o.items && typeof o.items === 'object' ? o.items : {}) as Record<string, unknown>;
      for (const [key, value] of Object.entries(rawItems)) {
        const n = toNumberOr(value, NaN);
        if (Number.isFinite(n)) items[key] = n;
      }
      const subtotal = toNumberOr(o.subtotal, Object.values(items).reduce((sum, v) => sum + v, 0));
      return { items, subtotal: round2(subtotal) };
    };

    const chinaSide = side(china.data);
    const vietnamSide = side(vietnam.data);
    res.json({
      china_side: chinaSide,
      vietnam_side: vietnamSide,
      china_total: chinaSide.subtotal,
      vietnam_total: vietnamSide.subtotal,
      ddp_total: round2(chinaSide.subtotal + vietnamSide.subtotal),
      tariff_info: null,
    });
  });

  /* ── POST /customs：口岸费用（含税，内部） ── */
  router.post('/customs', async (req: Request, res: Response) => {
    if (rejectInternal(req, res)) return;
    const body = bodyOf(req);
    const clampInt = (v: unknown, min: number, max: number, fallback: number): number => {
      const n = toNumberOr(v, fallback);
      return Math.min(max, Math.max(min, Math.trunc(n)));
    };

    const vehicleCount = clampInt(body.vehicle_count, 1, 99, 1);
    const containerCount = clampInt(body.container_count, 0, 99, 0);
    const cargoValue = Math.max(0, toNumberOr(body.cargo_value_rmb, 0));
    const containerType = typeof body.container_type === 'string' ? body.container_type.trim() : '';
    const hsCode = typeof body.hs_code === 'string' ? body.hs_code.trim() : '';

    const query = new URLSearchParams({
      vehicle_count: String(vehicleCount),
      container_count: String(containerCount),
      cargo_value_rmb: String(cargoValue),
      hs_code: hsCode,
      // 与 legacy 前端一致：海运按非散杂处理（land 也走默认 false）
      is_breakbulk: 'false',
    });
    if (containerType) query.set('container_type', containerType);

    const r = await callEngine(`/border/ddp-costs?${query.toString()}`, { timeoutMs: ENGINE_TIMEOUT_MS });
    if (!r.ok) {
      sendFailure(res, r.failure);
      return;
    }
    const raw = (r.data && typeof r.data === 'object' ? r.data : {}) as Record<string, unknown>;
    // 白名单搬运：引擎内部可能多出字段，这里只放 BorderCostResult 定义过的键
    const pick = (keys: string[]): Record<string, unknown> => {
      const out: Record<string, unknown> = {};
      for (const key of keys) if (raw[key] !== undefined) out[key] = raw[key];
      return out;
    };
    res.json({
      ...pick(['china_export', 'border_crossing', 'vietnam_import']),
      ...pick(['import_duty_rmb', 'vat_rmb', 'total_rmb']),
      ...pick(['tariff_desc', 'duty_source', 'duty_rate', 'vat_rate']),
    });
  });

  /**
   * /api/quote/* 未匹配的路径一律 JSON 404。
   * 不加这条会落到 server.ts 的 `app.get('*')` SPA 回退（回 index.html + 200），
   * 前端拿到 HTML 只能报「数据格式不正确」，看不出是自己把接口名写错了。
   */
  router.use((_req: Request, res: Response) => {
    res.status(404).json({ ok: false, reason: 'not_found', message: '接口不存在，请检查调用地址。' });
  });

  return router;
}

export default createQuoteRouter;
