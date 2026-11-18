/**
 * 留资线索与明细令牌（契约 §3.3 / §3.4 的服务端闸门）
 * ────────────────────────────────────────────────────────────
 * 断言都是「必须为真」的口径，不用 truthy 糊过去：
 *  - 令牌绑定 leadId + 参数指纹 + 过期时间；任一不符都必须回 null（路由映射 403 token_mismatch）。
 *  - 结构上不是本站令牌的串（例如 curl 手填的 "y"）必须 readToken 回 null → 路由映射 403 lead_required。
 *  - 同一 IP 超过 LEAD_RATE_PER_HOUR → createLead 抛 LeadError(code='rate_limited')。
 *
 * 跑法：node --test server/leads.test.ts   （Node 24 原生类型剥离，无需 tsx）
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createLead, redeemToken, readToken, LeadError, __resetForTest } from './leads.ts';

const TMP_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'jiuneng-leads-'));
process.env.LEADS_DIR = TMP_DIR;
process.env.DETAIL_TOKEN_SECRET = 'test-secret-do-not-use-in-prod';
delete process.env.LEADS_WEBHOOK_URL;

const base = { company: 'ABC 贸易', contact: '张三', reach: '13800000000', params: { vehicle_count: 1 } };

test('创建线索返回 leadId（uuid）与可解析令牌', async () => {
  __resetForTest();
  const r = await createLead({ ...base, ip: '10.0.0.1' });
  assert.match(r.leadId, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  assert.ok(r.token.length > 20, `token 太短：${r.token}`);
  const exp = Date.parse(r.expiresAt);
  assert.ok(Number.isFinite(exp), `expiresAt 不是合法时间：${r.expiresAt}`);
  assert.ok(exp > Date.now(), 'expiresAt 必须在未来');
  const parsed = readToken(r.token);
  assert.ok(parsed, 'readToken 应能解析本站令牌');
  assert.equal(parsed!.leadId, r.leadId);
});

test('令牌绑定参数指纹：改参数后令牌失效', async () => {
  __resetForTest();
  const r = await createLead({ ...base, ip: '10.0.0.2' });
  assert.equal(redeemToken(r.token, { vehicle_count: 2 }), null);
  assert.equal(redeemToken(r.token, { vehicle_count: 1 })?.leadId, r.leadId);
});

test('令牌绑定 leadId：换 leadId 后令牌失效', async () => {
  __resetForTest();
  const r = await createLead({ ...base, ip: '10.0.0.3' });
  assert.equal(redeemToken(r.token, { vehicle_count: 1 }, { leadId: 'other-lead' }), null);
  assert.notEqual(redeemToken(r.token, { vehicle_count: 1 }, { leadId: r.leadId }), null);
});

test('过期令牌失效', async () => {
  __resetForTest();
  const r = await createLead({ ...base, ip: '10.0.0.4' });
  const later = Date.now() + 31 * 60 * 1000; // 默认 TTL 30 分钟
  assert.equal(redeemToken(r.token, { vehicle_count: 1 }, { now: later }), null);
  assert.notEqual(redeemToken(r.token, { vehicle_count: 1 }, { now: Date.now() }), null);
});

test('非本站令牌结构：readToken / redeemToken 都回 null（路由据此回 lead_required）', async () => {
  __resetForTest();
  assert.equal(readToken('y'), null);
  assert.equal(readToken(''), null);
  assert.equal(readToken(undefined), null);
  assert.equal(readToken(12345), null);
  assert.equal(readToken('a.b.c'), null);
  assert.equal(redeemToken('y', { vehicle_count: 1 }), null);
});

test('同一 IP 超过 LEAD_RATE_PER_HOUR 后拒绝', async () => {
  __resetForTest();
  process.env.LEAD_RATE_PER_HOUR = '2';
  const mk = () => createLead({ ...base, ip: '1.1.1.1' });
  await mk();
  await mk();
  await assert.rejects(mk(), (error: unknown) => {
    assert.ok(error instanceof LeadError, '必须是 LeadError');
    assert.equal((error as LeadError).code, 'rate_limited');
    assert.match((error as Error).message, /rate_limited/);
    return true;
  });
  // 另一个 IP 不受影响
  await createLead({ ...base, ip: '2.2.2.2' });
  delete process.env.LEAD_RATE_PER_HOUR;
});

test('缺字段抛 missing_field（公司/联系人/联系方式）', async () => {
  __resetForTest();
  for (const broken of [
    { ...base, company: '   ' },
    { ...base, contact: '' },
    { ...base, reach: undefined },
  ]) {
    await assert.rejects(
      createLead({ ...broken, ip: '9.9.9.9' } as never),
      (error: unknown) => (error as LeadError).code === 'missing_field',
    );
  }
});

test('线索落库到 LEADS_DIR/leads.jsonl（每单一行，令牌不入库）', async () => {
  __resetForTest();
  const file = path.join(TMP_DIR, 'leads.jsonl');
  const before = fs.existsSync(file) ? fs.readFileSync(file, 'utf-8').trim().split('\n').length : 0;
  const r = await createLead({ ...base, ip: '10.0.0.9' });
  const lines = fs.readFileSync(file, 'utf-8').trim().split('\n');
  assert.equal(lines.length, before + 1);
  const row = JSON.parse(lines[lines.length - 1]);
  assert.equal(row.leadId, r.leadId);
  assert.equal(row.company, base.company);
  assert.equal(row.token, undefined, '令牌不得写进落库记录');
});
