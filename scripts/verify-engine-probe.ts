/**
 * probeEngine 验收：可达 / 死端口 / 挂起超时 / 未配置 四分支 + 三种 OSRM_API_BASE 写法等价。
 *
 * 断言一律钉住**取值**（不是「有 reason 就算过」）——否则把 osrmQuote.ts 里的错误分类
 * 整体反转（abort→unreachable、其余→timeout）后脚本依然全过，等于没有验收。
 *
 * 用法：npx tsx scripts/verify-engine-probe.ts   （需引擎已在 127.0.0.1:18000，见 DEVELOPMENT.md §14.7）
 */
import { probeEngine } from '../server/osrmQuote';

const fails: string[] = [];
const LIVE_BASE = 'http://127.0.0.1:18000';

/** 抓 console.warn 调用的探测包装（断言「必须告警」/「不得告警」两向都要）。 */
async function probeCatchingWarn(ms: number, base = LIVE_BASE) {
  const caught: string[] = [];
  const orig = console.warn;
  console.warn = ((...args: unknown[]) => { caught.push(args.map(String).join(' ')); }) as typeof console.warn;
  process.env.OSRM_API_BASE = base;
  try {
    return { result: await probeEngine(ms), warns: caught };
  } finally {
    console.warn = orig;
  }
}

/* ── 可达分支 ── */
process.env.OSRM_API_BASE = LIVE_BASE;
const live = await probeEngine(5000);
console.log('live  :', JSON.stringify(live));

if (!live.ok && live.reason === 'unreachable') {
  console.error('⚠️ 127.0.0.1:18000 上没有引擎：先按 DEVELOPMENT.md 的说明起引擎，以下失败是环境问题而非 probeEngine 缺陷。');
}
if (!live.ok) fails.push(`引擎在 18000 应判可达，实际 ${JSON.stringify(live)}`);
if (live.ms <= 0) fails.push(`live.ms 应为正数，实际 ${live.ms}`);

/* ── base 写法等价：根地址 / 根地址带尾斜杠 / 完整前缀都要命中 /health ── */
for (const form of [LIVE_BASE, `${LIVE_BASE}/`, `${LIVE_BASE}/api/v1`]) {
  process.env.OSRM_API_BASE = form;
  const r = await probeEngine(5000);
  console.log('base  :', `${form.padEnd(34)} → ${JSON.stringify(r)}`);
  if (r.ok !== true) fails.push(`OSRM_API_BASE=${JSON.stringify(form)} 应判可达，实际 ${JSON.stringify(r)}`);
}

/* ── 死端口分支（钉住 reason 取值） ── */
process.env.OSRM_API_BASE = 'http://127.0.0.1:19999';   // 没人监听
const dead = await probeEngine(1200);
console.log('dead  :', JSON.stringify(dead));
if (dead.ok || dead.reason !== 'unreachable') fails.push(`死端口应 reason=unreachable，实际 ${JSON.stringify(dead)}`);

/* ── 未配置分支 ── */
process.env.OSRM_API_BASE = '';
const none = await probeEngine(500);
console.log('none  :', JSON.stringify(none));
if (none.reason !== 'not_configured') fails.push(`未配置应 reason=not_configured，实际 ${JSON.stringify(none)}`);
if (none.ok !== false) fails.push(`未配置应 ok=false，实际 ${JSON.stringify(none)}`);
if (none.ms !== 0) fails.push(`未配置应 ms=0（不发起任何请求），实际 ${JSON.stringify(none)}`);

/* ── 挂起分支：连得上但不应答，必须判 timeout 且预算真的生效 ── */
const { createServer } = await import('node:http');
const hang = createServer(() => { /* 收到请求也不回，模拟卡死/唤醒中的引擎 */ });
await new Promise<void>((r) => hang.listen(18123, '127.0.0.1', r));
process.env.OSRM_API_BASE = 'http://127.0.0.1:18123';
const t0 = Date.now();
const hung = await probeEngine(400);
const wall = Date.now() - t0;
hang.close();
console.log('hung  :', JSON.stringify(hung), `wall=${wall}ms`);
if (hung.reason !== 'timeout') fails.push(`挂起服务应判 timeout，实际 ${JSON.stringify(hung)}`);
if (wall > 1500) fails.push(`超时预算未生效：400ms 预算实耗 ${wall}ms`);
if (hung.ok !== false) fails.push(`挂起服务不得判 ok，实际 ${JSON.stringify(hung)}`);

process.env.OSRM_API_BASE = LIVE_BASE;   // 收尾复原，避免影响后续复用本进程的断言

/* ── 上界夹紧：**直调**覆盖 osrmQuote.ts 里那条零覆盖分支 ──────────────── */
// 仓库内的调用方（server.ts）传的是 positiveEnvMs 归一后的值 ⇒ `> 2³¹−1` 那一支在仓库内**不可达**。
// 若不夹：Node 定时器把 2³² 按 32 位有符号回绕成 ~1ms → abort 立刻触发 → **活引擎**被误报
// {ok:false, reason:'timeout'}（运维会去追一个不存在的引擎故障）。这里直调 2³² 把它钉住。
const huge = await probeCatchingWarn(4_294_967_296);
console.log('clamp :', JSON.stringify(huge.result), `warns=${JSON.stringify(huge.warns)}`);
if (huge.result.ok !== true || huge.result.reason !== undefined) {
  fails.push(`2³² 的探测预算未被夹紧：活引擎被误报 ${JSON.stringify(huge.result)}`
    + '（Node 定时器把 2³² 回绕成 ~1ms → abort 在引擎回包前就触发）');
} else {
  console.log('   ✓ 2³² 被夹到 2147483647 后活引擎仍如实报 ok=true（未回绕成立刻 abort）');
}
if (!huge.warns.some((w) => w.includes('超过上限') && w.includes('4294967296'))) {
  fails.push(`2³² 被夹紧时必须 console.warn 出被拒原值与「超过上限」，实际 ${JSON.stringify(huge.warns)}`);
} else {
  console.log('   ✓ 夹紧告警含被拒原值 4294967296 与「超过上限」');
}

/* ── 反向用例：合法预算**不得**有任何告警（否则「有 warn 就算过」会被别处的告警蒙混）── */
const normal = await probeCatchingWarn(5000);
if (normal.result.ok !== true) fails.push(`合法预算 5000ms 应判可达，实际 ${JSON.stringify(normal.result)}`);
if (normal.warns.length !== 0) fails.push(`合法预算 5000ms 不该产生任何告警，实际 ${JSON.stringify(normal.warns)}`);
else console.log('   ✓ 合法预算 5000ms 无任何告警（告警断言不是「有 warn 就算过」）');

console.log(fails.length ? `✗ ${fails.join(' | ')}` : '✓ probeEngine 四分支 + 三种 base 写法均正确');
process.exit(fails.length ? 1 : 0);
