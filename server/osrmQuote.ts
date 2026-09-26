/**
 * OSRM++ 测算出口（官网唯一出口）
 * ────────────────────────────────────────────────────────────
 * 合规与安全约束（勿绕过）：
 *  1. 浏览器永远拿不到 OSRM++ 引擎地址——只能经由本站服务端转发（`POST /api/osrm-quote` 与对话工具共用本模块）。
 *  2. 出参走白名单重建：**绝不**回传 `breakdown` / `profit_vnd` / `margin_rate` / `border_fees` /
 *     `cost_*` / `geometry` 等内部成本与利润字段（官网只对外，不含成本结构）。
 *  3. 对客口径：只给「里程 / 预计行驶时长 / 车数 / 车型 + 参考价区间」，区间由引擎售价 ±10% 取整得出，
 *     并统一标注「初步测算，非正式报价」。**不是**报价，不得表述为报价或时效承诺。
 *  4. 引擎侧需配 `OSRM_ENGINE_KEY`（本站以 `X-API-Key` 发送）；未配 `OSRM_API_BASE` 时如实回「未接入」，
 *     不得由模型或前端自行估算任何数字。
 */

// 测算调用预算见下方 quoteTimeoutMs()（默认 75s，可用 OSRM_QUOTE_TIMEOUT_MS 覆盖）。
// ⚠️ 声明必须放在 MAX_TIMER_MS/归一函数**之后**：const 有 TDZ，前移会在模块求值期直接抛错。

/* ── 起点/终点/口岸白名单（不透传任意地址，避免依赖地理编码 + 参数可控） ── */

export type Place = { zh: string; vi: string; en: string; lat: number; lng: number; kind: 'cn' | 'vn' | 'border' };

export const PLACES: Record<string, Place> = {
  shanghai: { zh: '上海', vi: 'Thượng Hải', en: 'Shanghai', lat: 31.2304, lng: 121.4737, kind: 'cn' },
  ningbo: { zh: '宁波', vi: 'Ninh Ba', en: 'Ningbo', lat: 29.8683, lng: 121.544, kind: 'cn' },
  shenzhen: { zh: '深圳', vi: 'Thâm Quyến', en: 'Shenzhen', lat: 22.5431, lng: 114.0579, kind: 'cn' },
  guangzhou: { zh: '广州', vi: 'Quảng Châu', en: 'Guangzhou', lat: 23.1291, lng: 113.2644, kind: 'cn' },
  qingdao: { zh: '青岛', vi: 'Thanh Đảo', en: 'Qingdao', lat: 36.0671, lng: 120.3826, kind: 'cn' },
  tianjin: { zh: '天津', vi: 'Thiên Tân', en: 'Tianjin', lat: 39.0842, lng: 117.2009, kind: 'cn' },
  yiwu: { zh: '义乌', vi: 'Nghĩa Ô', en: 'Yiwu', lat: 29.3068, lng: 120.0754, kind: 'cn' },
  nanning: { zh: '南宁', vi: 'Nam Ninh', en: 'Nanning', lat: 22.817, lng: 108.3665, kind: 'cn' },
  pingxiang: { zh: '凭祥', vi: 'Bằng Tường', en: 'Pingxiang', lat: 22.0949, lng: 106.7573, kind: 'cn' },
  youyiguan: { zh: '友谊关口岸', vi: 'Cửa khẩu Hữu Nghị', en: 'Friendship Pass (Youyiguan)', lat: 21.9755, lng: 106.7089, kind: 'border' },
  dongxing: { zh: '东兴口岸', vi: 'Cửa khẩu Đông Hưng', en: 'Dongxing Port', lat: 21.5397, lng: 107.9708, kind: 'border' },
  hekou: { zh: '河口口岸', vi: 'Cửa khẩu Hà Khẩu', en: 'Hekou Port', lat: 22.507, lng: 103.957, kind: 'border' },
  hanoi: { zh: '河内', vi: 'Hà Nội', en: 'Hanoi', lat: 21.0278, lng: 105.8342, kind: 'vn' },
  bacninh: { zh: '北宁', vi: 'Bắc Ninh', en: 'Bac Ninh', lat: 21.1861, lng: 106.0763, kind: 'vn' },
  haiphong: { zh: '海防', vi: 'Hải Phòng', en: 'Haiphong', lat: 20.8449, lng: 106.6881, kind: 'vn' },
  danang: { zh: '岘港', vi: 'Đà Nẵng', en: 'Da Nang', lat: 16.0544, lng: 108.2022, kind: 'vn' },
  'ho chi minh': { zh: '胡志明', vi: 'TP. Hồ Chí Minh', en: 'Ho Chi Minh City', lat: 10.8231, lng: 106.6297, kind: 'vn' },
};

/** 客户/模型可能写各种别名，这里做归一；匹配不到就如实拒绝（不猜坐标）。 */
const PLACE_ALIASES: Record<string, string> = {
  '胡志明市': 'ho chi minh', '西贡': 'ho chi minh', 'hcmc': 'ho chi minh', 'saigon': 'ho chi minh', 'hồ chí minh': 'ho chi minh',
  'hà nội': 'hanoi', 'ha noi': 'hanoi', '河內': 'hanoi',
  '海防市': 'haiphong', 'hai phong': 'haiphong',
  '岘港市': 'danang', 'đà nẵng': 'danang',
  '北宁市': 'bacninh', 'bắc ninh': 'bacninh',
  '深圳市': 'shenzhen', '广州市': 'guangzhou', '上海市': 'shanghai', '宁波市': 'ningbo',
  '青岛市': 'qingdao', '天津市': 'tianjin', '义乌市': 'yiwu', '南宁市': 'nanning', '凭祥市': 'pingxiang',
  '友谊关': 'youyiguan', '友誼關': 'youyiguan', 'youyi': 'youyiguan', 'hữu nghị': 'youyiguan', 'cửa khẩu hữu nghị': 'youyiguan',
  '东兴': 'dongxing', 'đông hưng': 'dongxing', '河口': 'hekou', 'hà khẩu': 'hekou',
};

export function resolvePlace(input: unknown): string | null {
  const raw = String(input ?? '').trim().toLowerCase();
  if (!raw) return null;
  if (PLACES[raw]) return raw;
  if (PLACE_ALIASES[raw] && PLACES[PLACE_ALIASES[raw]]) return PLACE_ALIASES[raw];
  for (const [id, p] of Object.entries(PLACES)) {
    if ([p.zh, p.vi, p.en].some((label) => label.toLowerCase() === raw)) return id;
  }
  return null;
}

/* ── 官网可选车型（**不带**引擎的完整车型库；只放常用 6 种，避免下发内部车型库） ── */

export const VEHICLES: Record<string, { max_load_ton: number; zh: string; vi: string; en: string }> = {
  flatbed_13m: { max_load_ton: 26, zh: '普通平板 13 米', vi: 'Sàn phẳng 13 m', en: 'Flatbed 13 m' },
  flatbed_low_17m5: { max_load_ton: 38, zh: '低平板 17.5 米', vi: 'Sàn thấp 17,5 m', en: 'Low-bed 17.5 m' },
  flatbed_low_13m: { max_load_ton: 28, zh: '低平板 13 米', vi: 'Sàn thấp 13 m', en: 'Low-bed 13 m' },
  flatbed_12m5: { max_load_ton: 22, zh: '普通平板 12.5 米', vi: 'Sàn phẳng 12,5 m', en: 'Flatbed 12.5 m' },
  small_box_10t: { max_load_ton: 10, zh: '10 吨厢式货车', vi: 'Xe thùng 10 tấn', en: '10 t box truck' },
  small_box_5t: { max_load_ton: 5, zh: '5 吨厢式货车', vi: 'Xe thùng 5 tấn', en: '5 t box truck' },
};

/* ── 出入参类型 ── */

export type CalcRequest = {
  origin: unknown;
  destination: unknown;
  border?: unknown;
  weight_kg: unknown;
  volume_m3?: unknown;
  mode?: unknown;            // consolidated（拼车，默认）| full_truck（整车，须给车型）
  vehicle_model_id?: unknown;
};

export type CalcResult =
  | {
      ok: true;
      origin: { id: string; label: string };
      destination: { id: string; label: string };
      border: { id: string; label: string } | null;
      mode: 'consolidated' | 'full_truck';
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
    }
  | { ok: false; reason: string; note: string; status?: number };

function engineBase(): string {
  const raw = (process.env.OSRM_API_BASE || '').trim().replace(/\/+$/, '');
  if (!raw) return '';
  // 容错：填根地址（https://host）或完整前缀（https://host/api/v1）都能用，
  // 避免漏写 /api/v1 变成静默 404。
  return /\/api\/v1$/.test(raw) ? raw : `${raw}/api/v1`;
}

/** 引擎根地址（去掉 /api/v1 后缀）—— 引擎的 /health 挂在根路径上。 */
function engineRoot(): string {
  return engineBase().replace(/\/api\/v1$/, '');
}

/** Node 定时器延迟按 32 位有符号存储：超过它就回绕成极小值（「永不超时」变「立刻超时」）。 */
const MAX_TIMER_MS = 2_147_483_647;

/**
 * 探测预算归一：非有限值 / ≤0 → 回落默认；> 2³¹−1 → 夹到上限。
 * ⚠️ 上界这一支不是洁癖：`OSRM_PROBE_TIMEOUT_MS=4294967296`（2³²）会让 abort 定时器**立刻**触发，
 * 活引擎被误报 `{ok:false, ms:13, reason:'timeout'}`——运维会去追一个不存在的引擎故障。
 * 被拒的原始值要打进日志，否则运维永远看不出自己写的值没生效。
 * **覆盖方式**：仓库内唯一的调用方 `server.ts` 传的是 `positiveEnvMs('HEALTH_*')`（自己已经夹过上下限），
 * 所以这一支在仓库内**不可达**——它由 `scripts/verify-engine-probe.ts` 里**直调** `probeEngine(2³²)` 的
 * 用例钉住（断言夹到 2147483647 + 有告警），别把这个用例删了，否则上界回归就没人管了。
 */
function normalizeProbeBudget(timeoutMs: number, fallback = 3_000): number {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return fallback;
  if (timeoutMs > MAX_TIMER_MS) {
    console.warn(`[engine] 探测预算 ${JSON.stringify(timeoutMs)}ms 超过上限 ${MAX_TIMER_MS}ms`
      + `（Node 定时器会回绕成极小值 → 活引擎被误报 timeout），夹紧到 ${MAX_TIMER_MS}ms`);
    return MAX_TIMER_MS;
  }
  return timeoutMs;
}

/**
 * 测算调用预算（默认 75s）。
 * 为什么给这么长：引擎改为**按需唤醒**后（站点默认不再周期探查，见 server.ts 的 HEALTH_PROBE_MS），
 * Render 免费层实例休眠时首个请求要等冷启动（实测 30–60s）——预算太短会把「正在唤醒」误判成
 * 「引擎超时」，客户白等还拿不到结果。前端 fetch 未设任何超时（src/agent/App.tsx 只是 await fetch），
 * 所以这里就是端到端**唯一**的等待上限。
 * ⚠️ 归一规则与 server.ts 一致：非有限值/≤0 → 回落默认并打印被拒原值（否则运维看不出自己的值没生效）；
 *    低于下限夹紧；超过 2³¹−1 夹紧（否则 abort 定时器**立刻**触发 → 活引擎被误报 engine_timeout）。
 */
const QUOTE_TIMEOUT_DEFAULT_MS = 75_000;
const QUOTE_TIMEOUT_MIN_MS = 1_000;
function quoteTimeoutMs(): number {
  const rawStr = process.env.OSRM_QUOTE_TIMEOUT_MS;
  if (rawStr === undefined) return QUOTE_TIMEOUT_DEFAULT_MS;
  const raw = Number(rawStr);
  if (!Number.isFinite(raw) || raw <= 0) {
    console.warn(`[engine] 环境变量 OSRM_QUOTE_TIMEOUT_MS=${JSON.stringify(rawStr)} 不是有限正值，`
      + `回落到默认 ${QUOTE_TIMEOUT_DEFAULT_MS}ms`);
    return QUOTE_TIMEOUT_DEFAULT_MS;
  }
  if (raw < QUOTE_TIMEOUT_MIN_MS) {
    console.warn(`[engine] 环境变量 OSRM_QUOTE_TIMEOUT_MS=${JSON.stringify(rawStr)} 低于下限，夹紧到 ${QUOTE_TIMEOUT_MIN_MS}ms`);
    return QUOTE_TIMEOUT_MIN_MS;
  }
  if (raw > MAX_TIMER_MS) {
    console.warn(`[engine] 环境变量 OSRM_QUOTE_TIMEOUT_MS=${JSON.stringify(rawStr)} 超过上限 ${MAX_TIMER_MS}ms`
      + `（Node 定时器会回绕成极小值 → abort 立刻触发、活引擎被误报超时），夹紧到 ${MAX_TIMER_MS}ms`);
    return MAX_TIMER_MS;
  }
  return raw;
}
const TIMEOUT_MS = quoteTimeoutMs();
console.info(`[engine] 测算调用预算 ${TIMEOUT_MS}ms（冷启动等待上限；前端无独立超时）`);

/**
 * 轻量探测引擎是否可达。给健康检查复用，**不抛异常**，只回结果。
 * 注意：引擎在 Render 免费层会休眠，探测超时要显式小于官网业务超时（见上 TIMEOUT_MS，默认 75s）。
 */
export async function probeEngine(timeoutMs = 3_000): Promise<{ ok: boolean; ms: number; reason?: string }> {
  // 预算归一：非有限正值（NaN/0/负数/Infinity）传给 setTimeout 会变成「立刻 abort」或「永不 abort」，
  // 前者让健康检查把活引擎误报成 timeout → 一律回落到默认 3s。
  // **上界同理必须夹**：超 2³¹−1 的延迟被 Node 定时器按 32 位有符号回绕成极小值，
  // 于是「永不超时」变成「立刻超时」，活引擎被误报 `{ok:false, ms:13, reason:'timeout'}`（假告警）。
  // （注：仓库内的调用方 server.ts 传的是 positiveEnvMs 归一后的值，所以这条上界分支要靠
  //  scripts/verify-engine-probe.ts 的直调用例才覆盖得到 —— 这就是那条用例存在的理由。）
  const budget = normalizeProbeBudget(timeoutMs);
  const base = engineBase();
  if (!base) return { ok: false, ms: 0, reason: 'not_configured' };

  const started = Date.now();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), budget);
  try {
    const res = await fetch(`${engineRoot()}/health`, {
      signal: ctrl.signal,
      headers: { 'User-Agent': 'jiuneng-website-healthcheck' },
    });
    const ms = Date.now() - started;
    if (!res.ok) return { ok: false, ms, reason: `status_${res.status}` };
    return { ok: true, ms };
  } catch (error: any) {
    const ms = Date.now() - started;
    // AbortError 是超时；其余按不可达归类，便于健康检查区分展示
    return { ok: false, ms, reason: error?.name === 'AbortError' ? 'timeout' : 'unreachable' };
  } finally {
    clearTimeout(timer);
  }
}

const roundTo = (v: number, step: number) => Math.round(v / step) * step;

/** 引擎在 Render 免费层会被冷启动休眠，超时给足并区分「超时」与「不可达」。 */
export async function runQuote(req: CalcRequest): Promise<CalcResult> {
  const originId = resolvePlace(req.origin);
  const destId = resolvePlace(req.destination);
  if (!originId) return { ok: false, reason: 'unknown_origin', note: '起点不在可测算城市清单内' };
  if (!destId) return { ok: false, reason: 'unknown_destination', note: '终点不在可测算城市清单内' };
  const borderId = req.border ? resolvePlace(req.border) : null;

  const weight = Number(req.weight_kg);
  if (!Number.isFinite(weight) || weight <= 0) {
    return { ok: false, reason: 'bad_weight', note: '货重需为大于 0 的数值（单位 kg）' };
  }
  const volume = Number(req.volume_m3);
  const mode: 'consolidated' | 'full_truck' = req.mode === 'full_truck' ? 'full_truck' : 'consolidated';
  // 引擎口径：拼车按体积+重量计费，缺体积会 422 —— 在这里提前拦，给客户可读的原因
  if (mode === 'consolidated' && !(Number.isFinite(volume) && volume > 0)) {
    return { ok: false, reason: 'need_volume', note: '拼车测算需要填写货物总体积（m³）；若无法给出体积，请改选整车或走正式询价。' };
  }
  const vehicleId = typeof req.vehicle_model_id === 'string' ? req.vehicle_model_id : '';
  if (mode === 'full_truck' && !VEHICLES[vehicleId]) {
    return { ok: false, reason: 'bad_vehicle', note: '整车测算需在可选车型中指定一种' };
  }

  const base = engineBase();
  if (!base) {
    return {
      ok: false,
      reason: 'engine_not_configured',
      note: '测算引擎未接入（未配置 OSRM_API_BASE）。可引导客户走正式询价，由项目经理核算，不要自行估算里程或金额。',
    };
  }

  const body = {
    route: {
      origin: { lat: PLACES[originId].lat, lng: PLACES[originId].lng },
      destination: { lat: PLACES[destId].lat, lng: PLACES[destId].lng },
      ...(borderId ? { border: { lat: PLACES[borderId].lat, lng: PLACES[borderId].lng } } : {}),
    },
    cargo: {
      weight_kg: weight,
      ...(Number.isFinite(volume) && volume > 0 ? { volume_m3: volume } : {}),
      type: 'normal',
    },
    vehicle: {
      loading_mode: mode,
      ...(mode === 'full_truck' ? { vehicle_model_id: vehicleId } : {}),
    },
  };

  /** 单次引擎调用（含自身超时）。 */
  const attemptEngine = async (): Promise<Response> => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      return await fetch(`${base}/route/cost`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(process.env.OSRM_ENGINE_KEY ? { 'X-API-Key': process.env.OSRM_ENGINE_KEY } : {}),
        },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  };

  /* 免费层实例休眠时，Render 会**毫秒级**把第一个请求拒掉（502 或直接断连）——这不是「引擎慢」，
     而是「实例没醒」，75s 预算根本轮不到它。实测冷启动要约 **32s**（/health 200 用时 32.42s）：
     只有**再发一次**才会真正等到实例醒来。所以只对「快速失败」补一次重试；真正的慢失败
     （超时）不重试，避免把预算吃两遍。
     ⚠️ 重试必须留在**本 try 内部**：AbortError 要能被下面的 catch 映射成 engine_timeout，
     漏出去就成了 server_error（第一次改就踩了这个坑，verify-quote-timeout.py 的 B/C 段钉着）。
     验收：scripts/verify-quote-timeout.py 的 G 段（假引擎只对第一次请求回 502）。 */
  const FAST_FAIL_MS = 3_000;
  /* 2026-09-27 线上实测：Render 对休眠实例的请求是**毫秒级 502**（不是挂住等），
     而实例唤醒实测 **42.5s**（直连网关 /health → HTTP 200 用时 42.481s；Render 面板自述
     「delay requests by 50 seconds or more」）。只重试一次没用（第 2 次照样秒 502）。
     所以按「快速失败」判据退避重试，窗口要**盖过一次冷启动**：4+8+16+24 = 累计 52s，
     加 5 次尝试本身 ≈ 55s < 75s 预算。这样冷启动后的第一问也能拿到里程和参考价区间。
     真正的慢失败（超时）不重试，交给下面的 catch 映射成 engine_timeout。 */
  const COLD_START_WAITS = [4_000, 8_000, 16_000, 24_000];
  let res: Response | undefined;
  let lastEngineError: unknown = null;
  try {
    for (let attempt = 0; attempt <= COLD_START_WAITS.length; attempt++) {
      const attemptStartedAt = Date.now();
      lastEngineError = null;
      try {
        res = await attemptEngine();
        // 正常 / 非 5xx / 慢失败 → 都不再重试（慢失败交给外层 catch）
        if (res.ok || res.status < 500 || Date.now() - attemptStartedAt >= FAST_FAIL_MS) break;
        console.warn(`osrm engine fast ${res.status}（疑似免费层实例未唤醒），第 ${attempt + 1} 次尝试`);
      } catch (fastError) {
        lastEngineError = fastError;
        // ⚠️ 超时（AbortError）**绝不能重试**：那是「引擎慢」这个合法答案，不是「实例没醒」。
        // 预算比 FAST_FAIL_MS 小时（例如 OSRM_QUOTE_TIMEOUT_MS=1000）会把超时误判成快速失败，
        // 退化成一串重试 —— 实测把 1s 预算拖成 35.1s（verify-quote-timeout.py 的 C 段抓出来的）。
        const aborted = (fastError as { name?: string })?.name === 'AbortError';
        if (aborted || Date.now() - attemptStartedAt >= FAST_FAIL_MS) throw fastError;
        console.warn(`osrm engine fast failure（疑似免费层实例未唤醒），第 ${attempt + 1} 次尝试：`, fastError);
      }
      if (attempt < COLD_START_WAITS.length) {
        await new Promise((resolve) => setTimeout(resolve, COLD_START_WAITS[attempt]));
      }
    }
    if (!res) throw lastEngineError ?? new Error('engine call failed');
    if (!res.ok) {
      // 引擎用 422 + detail 说明校验失败；只映射已知情形，其余保持通用文案（不回传引擎内部信息）
      let clue = '';
      try {
        const body = (await res.json()) as { detail?: unknown };
        clue = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? '');
      } catch { /* 非 JSON 响应，忽略 */ }
      if (clue.includes('volume_m3')) {
        return { ok: false, status: res.status, reason: 'need_volume', note: '拼车测算需要填写货物总体积（m³）；若无法给出体积，请改选整车或走正式询价。' };
      }
      console.error('osrm engine error', res.status, clue.slice(0, 300));
      return {
        ok: false,
        status: res.status,
        reason: 'engine_error',
        note: '测算引擎暂时不可用，可引导客户走正式询价。',
      };
    }

    /* ⚠️ 白名单重建：只挑对客字段，内部成本/利润/口岸费用明细一律丢弃。 */
    const raw = (await res.json()) as Record<string, unknown>;
    const route = (raw.route ?? {}) as Record<string, unknown>;
    const sell = typeof raw.price_vnd === 'number' && Number.isFinite(raw.price_vnd) ? raw.price_vnd : null;
    const step = 100_000; // 取整到 10 万 VND
    // 引擎的 profile_note 只用于服务端日志（含 OSRM_AVAILABLE_PROFILES 等内部措辞，不对客展示）
    if (typeof raw.profile_note === 'string' && raw.profile_note) console.info('osrm profile:', raw.profile_note.slice(0, 200));
    const suggestionCodes = Array.isArray(raw.suggestions)
      ? raw.suggestions
          .map((s) => (s && typeof s === 'object' ? String((s as Record<string, unknown>).code ?? '') : ''))
          .filter((c) => /^[a-z_]{3,40}$/.test(c))
      : [];

    return {
      ok: true,
      origin: { id: originId, label: PLACES[originId].zh },
      destination: { id: destId, label: PLACES[destId].zh },
      border: borderId ? { id: borderId, label: PLACES[borderId].zh } : null,
      mode,
      distance_km: typeof route.distance_km === 'number' ? Math.round(route.distance_km * 10) / 10 : null,
      driving_h: typeof route.adjusted_duration_h === 'number' ? Math.round(route.adjusted_duration_h * 10) / 10 : null,
      vehicle_count: typeof raw.vehicle_count === 'number' ? raw.vehicle_count : null,
      vehicle_id: mode === 'full_truck' ? vehicleId : null,
      vehicle_label: mode === 'full_truck' ? VEHICLES[vehicleId].zh : null,
      price_min_vnd: sell !== null ? roundTo(sell * 0.9, step) : null,
      price_max_vnd: sell !== null ? roundTo(sell * 1.1, step) : null,
      price_round_vnd: step,
      price_basis: 'engine_sell_price_pm10',
      profile_honored: raw.profile_honored === true,
      suggestions: suggestionCodes,
      disclosure: 'indicative_only',
    };
  } catch (error) {
    const aborted = (error as { name?: string })?.name === 'AbortError';
    return {
      ok: false,
      reason: aborted ? 'engine_timeout' : 'engine_unreachable',
      note: aborted
        ? '测算引擎响应超时（免费层实例可能正在唤醒），可稍后重试或走正式询价。'
        : '测算引擎连接失败，可引导客户走正式询价。',
    };
  }
}
