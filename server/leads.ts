/**
 * 留资线索与「分项解锁」令牌（契约 §3.3 / §3.4）
 * ────────────────────────────────────────────────────────────
 * 为什么要令牌而不是登录：报关分项是**对外含服务口径**的数字，公开区间可以给，逐项明细要换联系方式。
 * 令牌必须满足三条（缺一条就等于没闸门）：
 *  1. 绑 leadId —— 甲客户的令牌不能拿来解锁乙客户的参数；
 *  2. 绑参数指纹 —— 拿到令牌后改 vehicle_count 再打一次必须失效（否则「一次留资，随便改参数」）；
 *  3. 有过期时间 —— 默认 30 分钟（LEAD_TTL_MIN）。
 * 令牌 = base64url(JSON{l,p,e}) + '.' + base64url(HMAC-SHA256(secret, `l.p.e`))，无状态、可多实例。
 *
 * 其它约束：
 *  - 线索落库是 JSONL 追加（`LEADS_DIR/leads.jsonl`），**令牌绝不入库**；落库失败只 warn，
 *    不能让「磁盘/权限问题」把客户的留资变成 500（线索已经到手，宁可丢明细也别丢线索）。
 *  - 同一来源每小时超过 LEAD_RATE_PER_HOUR 直接拒绝（`rate_limited`），防止被刷出大量假线索。
 *  - 缺字段回 `missing_field`，节流回 `rate_limited`（路由层分别映射 400/429）。
 */
import { createHash, createHmac, randomUUID, timingSafeEqual } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { v7 } from './env.ts';

export type LeadErrorCode = 'missing_field' | 'rate_limited';

export class LeadError extends Error {
  code: LeadErrorCode;
  field?: string;

  constructor(code: LeadErrorCode, message: string, field?: string) {
    super(message);
    this.name = 'LeadError';
    this.code = code;
    if (field) this.field = field;
  }
}

export type CreateLeadInput = {
  company?: unknown;
  contact?: unknown;
  reach?: unknown;
  params?: unknown;
  /** 调用方来源标识（路由传真实 IP）；缺省归到 'unknown' 桶。 */
  ip?: string;
};

export type CreatedLead = { leadId: string; token: string; expiresAt: string };

export type ParsedToken = { leadId: string; paramsHash: string; expiresAtMs: number };

export type RedeemOptions = { leadId?: unknown; now?: number };

/* ── 同 IP 节流（内存滑动窗口：单实例足够；多实例各自计数，属可接受的降级） ── */
const rateHits = new Map<string, number[]>();
const RATE_WINDOW_MS = 60 * 60 * 1000;

function rateLimited(ip: string, limit: number, now: number): boolean {
  const bucket = (rateHits.get(ip) ?? []).filter((t) => now - t < RATE_WINDOW_MS);
  if (bucket.length >= limit) {
    rateHits.set(ip, bucket);
    return true;
  }
  bucket.push(now);
  rateHits.set(ip, bucket);
  // 防 map 膨胀：只保留近窗口内有命中的来源
  if (rateHits.size > 5_000) {
    for (const [k, v] of rateHits) {
      if (!v.length || now - v[v.length - 1] > RATE_WINDOW_MS) rateHits.delete(k);
    }
  }
  return false;
}

/* ── 参数指纹：稳定序列化（键排序，递归）→ sha1 hex ── */

function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'number') return Number.isFinite(value) ? JSON.stringify(value) : 'null';
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`;
  }
  return JSON.stringify(String(value));
}

export function paramsFingerprint(params: unknown): string {
  return createHash('sha1').update(stableStringify(params ?? {})).digest('hex');
}

/* ── 令牌编解码 ── */

const b64url = (buf: Buffer | string): string => Buffer.from(buf).toString('base64url');

function sign(payloadKey: string, secret: string): string {
  return createHmac('sha256', secret).update(payloadKey).digest('base64url');
}

/**
 * 只做**结构**解析：判断这串到底是不是本站令牌。
 * 路由据此区分 `lead_required`（根本不是令牌 / 没给）与 `token_mismatch`（是本站令牌但校验不过）。
 */
export function readToken(token: unknown): ParsedToken | null {
  if (typeof token !== 'string') return null;
  const trimmed = token.trim();
  if (!trimmed || trimmed.length > 512) return null;
  const parts = trimmed.split('.');
  if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
  let payload: unknown;
  try {
    payload = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8'));
  } catch {
    return null;
  }
  if (!payload || typeof payload !== 'object') return null;
  const raw = payload as Record<string, unknown>;
  const leadId = typeof raw.l === 'string' ? raw.l : '';
  const paramsHash = typeof raw.p === 'string' ? raw.p : '';
  const expiresAtMs = typeof raw.e === 'number' ? raw.e : NaN;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(leadId)) return null;
  if (!/^[0-9a-f]{40}$/.test(paramsHash)) return null;
  if (!Number.isFinite(expiresAtMs) || expiresAtMs <= 0) return null;
  return { leadId, paramsHash, expiresAtMs };
}

function makeToken(leadId: string, paramsHash: string, expiresAtMs: number): string {
  const payload = b64url(JSON.stringify({ l: leadId, p: paramsHash, e: expiresAtMs }));
  return `${payload}.${sign(`${leadId}.${paramsHash}.${expiresAtMs}`, v7.detailSecret())}`;
}

/**
 * 校验令牌：结构 → 签名 → leadId（若调用方给了）→ 过期 → 参数指纹。
 * 任一不过都回 `null`（路由统一映射 403 token_mismatch，不区分是哪一条不过：不给探测面）。
 */
export function redeemToken(token: unknown, params: unknown, opts: RedeemOptions = {}): ParsedToken | null {
  const parsed = readToken(token);
  if (!parsed) return null;
  const parts = String(token).trim().split('.');
  const expected = Buffer.from(sign(`${parsed.leadId}.${parsed.paramsHash}.${parsed.expiresAtMs}`, v7.detailSecret()));
  const actual = Buffer.from(parts[1]);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;
  if (opts.leadId !== undefined && String(opts.leadId) !== parsed.leadId) return null;
  if ((opts.now ?? Date.now()) > parsed.expiresAtMs) return null;
  if (paramsFingerprint(params) !== parsed.paramsHash) return null;
  return parsed;
}

/* ── 落库与转发 ── */

type StoredLead = {
  leadId: string;
  createdAt: string;
  expiresAt: string;
  company: string;
  contact: string;
  reach: string;
  params: unknown;
  ip: string;
};

async function persist(row: StoredLead): Promise<void> {
  try {
    const dir = path.resolve(process.cwd(), v7.leadsDir());
    await fs.promises.mkdir(dir, { recursive: true });
    await fs.promises.appendFile(path.join(dir, 'leads.jsonl'), `${JSON.stringify(row)}\n`, 'utf8');
  } catch (error) {
    console.warn('[leads] 落库失败（线索仍然返回给调用方）：', error);
  }
}

/** 可选转发：失败只 warn（线索已在本地落库，不回滚、不重试刷屏）。 */
function forward(row: StoredLead): void {
  const hook = v7.leadsWebhook();
  if (!hook) return;
  void (async () => {
    try {
      const res = await fetch(hook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'User-Agent': 'jiuneng-website-leads' },
        body: JSON.stringify(row),
      });
      if (!res.ok) console.warn(`[leads] webhook 转发失败 status=${res.status}（线索已本地落库）`);
    } catch (error) {
      console.warn('[leads] webhook 转发异常（线索已本地落库）：', error);
    }
  })();
}

/* ── 对外：建线索 ── */

function requireText(value: unknown, field: string, maxLen = 120): string {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) throw new LeadError('missing_field', `missing_field: ${field}`, field);
  if (text.length > maxLen) throw new LeadError('missing_field', `missing_field: ${field}（超长）`, field);
  return text;
}

export async function createLead(input: CreateLeadInput): Promise<CreatedLead> {
  const now = Date.now();
  const ip = String(input.ip ?? '').trim() || 'unknown';
  if (rateLimited(ip, v7.leadRatePerHour(), now)) {
    throw new LeadError('rate_limited', `rate_limited: 同一来源每小时最多 ${v7.leadRatePerHour()} 条，请稍后再试`);
  }

  const company = requireText(input.company, 'company');
  const contact = requireText(input.contact, 'contact', 60);
  const reach = requireText(input.reach, 'reach', 120);

  const leadId = randomUUID();
  const expiresAtMs = now + v7.leadTtlMin() * 60 * 1000;
  const paramsHash = paramsFingerprint(input.params);
  const expiresAt = new Date(expiresAtMs).toISOString();

  const row: StoredLead = {
    leadId,
    createdAt: new Date(now).toISOString(),
    expiresAt,
    company,
    contact,
    reach,
    params: input.params ?? {},
    ip,
  };
  await persist(row);
  forward(row);

  return { leadId, token: makeToken(leadId, paramsHash, expiresAtMs), expiresAt };
}

/** 测试专用：清空节流窗口（不改任何持久化文件）。 */
export function __resetForTest(): void {
  rateHits.clear();
}
