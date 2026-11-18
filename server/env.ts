/**
 * 环境变量归一入口（v7 工具层唯一读取点）
 * ────────────────────────────────────────────────────────────
 * 规矩：
 *  1. **非法值必须留痕**——`numEnv` 在回落默认时打 `console.warn` 并把被拒原值写进日志，
 *     否则运维改了环境变量却看不出没生效（引擎侧的 OSRM_QUOTE_TIMEOUT_MS 已踩过这个坑）。
 *  2. 一律**调用时才读**（函数而非常量）：测试与本地切换环境变量不需要重启进程，
 *     也避免模块求值期把未加载的 .env 定格下来。
 *  3. `BORDER_MARKUP` 是**对外系数**，未配置时必须回 `null`（fail-closed：宁可不出价，
 *     也不泄漏成本或乱报价）。空字符串与「没写」等价。
 */

/** 数值 env 归一：缺失/空串回落默认；非有限、≤0、越界 → 告警 + 回落默认。 */
export function numEnv(name: string, fallback: number, opts: { min?: number; max?: number } = {}): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') return fallback;
  const value = Number(raw);
  const min = opts.min ?? Number.NEGATIVE_INFINITY;
  const max = opts.max ?? Number.POSITIVE_INFINITY;
  if (!Number.isFinite(value) || value <= 0 || value < min || value > max) {
    console.warn(`[env] ${name}=${JSON.stringify(raw)} 非法（要求 ${min}..${max} 的正数），回落默认 ${fallback}`);
    return fallback;
  }
  return value;
}

/** 整数 env 归一：在 numEnv 之上向下取整。 */
export function intEnv(name: string, fallback: number, opts: { min?: number; max?: number } = {}): number {
  return Math.floor(numEnv(name, fallback, opts));
}

/** 字符串 env：缺失回落默认，存在则 trim（保留「显式填空」这个语义差异）。 */
export function strEnv(name: string, fallback = ''): string {
  const raw = process.env[name];
  return raw === undefined ? fallback : raw.trim();
}

/** 布尔 env：1/true/yes/on 视为真（大小写不敏感）。 */
export function boolEnv(name: string, fallback = false): boolean {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') return fallback;
  return /^(1|true|yes|on)$/i.test(raw.trim());
}

/**
 * 引擎根地址（不含 `/api/v1`）。
 * 口径与 `server/osrmQuote.ts` 的 `engineBase()` 一致：可填根地址，也可填完整前缀
 * （漏写 `/api/v1` 会静默 404，所以这里容错补上）。
 * ⚠️ osrmQuote.ts 里那两个函数**没有导出**（本代理无权改那个文件），所以这里复刻同一口径；
 *    两处**共享同一个环境变量名**，不存在第二套配置。
 */
export function engineApiBase(): string {
  const raw = strEnv('OSRM_API_BASE').replace(/\/+$/, '');
  if (!raw) return '';
  return /\/api\/v1$/.test(raw) ? raw : `${raw}/api/v1`;
}

/** 引擎根地址（`/health` 挂在根路径上）。 */
export function engineRootBase(): string {
  return engineApiBase().replace(/\/api\/v1$/, '');
}

/** 引擎请求头里的密钥（值取自 OSRM_ENGINE_KEY，与网关的 ENGINE_API_KEY 必须一致）。 */
export function engineKey(): string {
  return strEnv('OSRM_ENGINE_KEY');
}

/** 工具层调用引擎的等待上限（默认 20s，可用 OSRM_TOOLS_TIMEOUT_MS 覆盖并夹到 1s..60s）。 */
export function toolsTimeoutMs(): number {
  return Math.min(intEnv('OSRM_TOOLS_TIMEOUT_MS', 20_000, { min: 1_000, max: 60_000 }), 2_147_483_647);
}

export const v7 = {
  /** 报关费对外系数；**未配置 → null**（fail-closed）。 */
  borderMarkup: (): number | null => (strEnv('BORDER_MARKUP') === '' ? null : numEnv('BORDER_MARKUP', 1.5, { min: 1, max: 10 })),
  /** 区间半宽（0.10 = 系数后 ±10%）。 */
  borderRangePct: (): number => numEnv('BORDER_RANGE_PCT', 0.1, { min: 0.01, max: 0.5 }),
  /** 留资令牌有效期（分钟）。 */
  leadTtlMin: (): number => intEnv('LEAD_TTL_MIN', 30, { min: 1, max: 1440 }),
  /** 同一来源每小时最多建多少条线索。 */
  leadRatePerHour: (): number => intEnv('LEAD_RATE_PER_HOUR', 5, { min: 1, max: 100 }),
  /** 令牌签名密钥。默认值只用于本地；线上必须显式配（见 .env.example）。 */
  detailSecret: (): string => strEnv('DETAIL_TOKEN_SECRET', 'dev-only-secret'),
  /** 线索落库目录（JSONL）。 */
  leadsDir: (): string => strEnv('LEADS_DIR', './data'),
  /** 可选：线索转发 webhook（转发失败只 warn，不回滚线索）。 */
  leadsWebhook: (): string => strEnv('LEADS_WEBHOOK_URL'),
  engineApiBase,
  engineRootBase,
  engineKey,
  toolsTimeoutMs,
};
