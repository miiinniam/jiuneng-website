/**
 * 引擎调用薄壳（工具层唯一出口）
 * ────────────────────────────────────────────────────────────
 * 只做三件事，**不做业务计算**（算法在 customs.ts / fleet.ts / osrmQuote.ts）：
 *  1. 地址与密钥只从 `server/env.ts` 取（浏览器永远拿不到引擎地址）；
 *  2. 每次调用自带超时（AbortController）→ 网关/引擎慢不会把站点请求挂死；
 *  3. 失败统一成 `EngineError`：客户只看到「暂时不可用」，引擎内部报文只进服务端日志。
 *
 * ⚠️ 非 2xx 响应体里可能出现引擎内部措辞（费用公式/车型库/堆栈），**只截断进 console.error**，
 *    绝不拼进返回给客户端的 note。
 */
import { engineApiBase, engineKey, toolsTimeoutMs } from '../env.ts';

export type EngineCode = 'engine_not_configured' | 'engine_timeout' | 'engine_unreachable' | 'engine_error';

export class EngineError extends Error {
  code: EngineCode;
  status?: number;

  constructor(code: EngineCode, message: string, status?: number) {
    super(message);
    this.name = 'EngineError';
    this.code = code;
    if (status !== undefined) this.status = status;
  }
}

export type EngineInit = { method?: 'GET' | 'POST'; body?: unknown; timeoutMs?: number };

/** 引擎绝对地址（路径以 `/` 开头）；未配置 `OSRM_API_BASE` 时抛 engine_not_configured。 */
export function engineUrl(pathAndQuery: string): string {
  const base = engineApiBase();
  if (!base) throw new EngineError('engine_not_configured', '测算引擎未接入（未配置 OSRM_API_BASE）');
  return `${base}${pathAndQuery.startsWith('/') ? '' : '/'}${pathAndQuery}`;
}

/** 调引擎并解析 JSON；失败抛 EngineError（调用方按 code 映射对客文案）。 */
export async function engineJson<T>(pathAndQuery: string, init: EngineInit = {}): Promise<T> {
  const url = engineUrl(pathAndQuery);
  const budget = init.timeoutMs ?? toolsTimeoutMs();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), budget);
  const key = engineKey();
  let res: Response;
  try {
    res = await fetch(url, {
      method: init.method ?? 'GET',
      headers: {
        ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(key ? { 'X-API-Key': key } : {}),
        'User-Agent': 'jiuneng-website-tools',
      },
      ...(init.body !== undefined ? { body: JSON.stringify(init.body) } : {}),
      signal: ctrl.signal,
    });
  } catch (error) {
    const aborted = (error as { name?: string })?.name === 'AbortError';
    console.warn(`[engine] ${init.method ?? 'GET'} ${pathAndQuery} 失败：${aborted ? 'timeout' : String((error as Error)?.message ?? error)}`);
    throw new EngineError(
      aborted ? 'engine_timeout' : 'engine_unreachable',
      aborted ? '测算引擎响应超时' : '测算引擎连接失败',
    );
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    let clue = '';
    try {
      clue = (await res.text()).slice(0, 300);
    } catch { /* 非文本响应，忽略 */ }
    console.error(`[engine] ${init.method ?? 'GET'} ${pathAndQuery} status=${res.status} ${clue}`);
    throw new EngineError('engine_error', `测算引擎返回 ${res.status}`, res.status);
  }

  try {
    return (await res.json()) as T;
  } catch {
    console.error(`[engine] ${init.method ?? 'GET'} ${pathAndQuery} 响应不是合法 JSON`);
    throw new EngineError('engine_error', '测算引擎响应格式异常', res.status);
  }
}

/**
 * 在途合并（single-flight）：同一个 key 的并发请求只打一次上游。
 * 用途：/api/quote-route 被前端连点或同一票并发打进来时，不要按倍数烧引擎配额。
 * ⚠️ **不做结果缓存**（价格不许缓存）：Promise 一 settle 就从表里删掉，下一次请求照旧打引擎。
 */
const inflight = new Map<string, Promise<unknown>>();

export function singleFlight<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const task = (async () => run())().finally(() => {
    inflight.delete(key);
  });
  inflight.set(key, task);
  return task as Promise<T>;
}

/** 测试/运维用：当前在途请求数（不出现在任何 HTTP 响应里）。 */
export function inflightCount(): number {
  return inflight.size;
}
