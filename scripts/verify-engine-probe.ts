/** probeEngine 三分支验收：可达 / 死端口 / 未配置。用法：npx tsx scripts/verify-engine-probe.ts */
import { probeEngine } from '../server/osrmQuote';

const fails: string[] = [];

process.env.OSRM_API_BASE = 'http://127.0.0.1:18000';
const live = await probeEngine(5000);
console.log('live  :', JSON.stringify(live));

process.env.OSRM_API_BASE = 'http://127.0.0.1:19999';   // 没人监听
const dead = await probeEngine(1200);
console.log('dead  :', JSON.stringify(dead));

process.env.OSRM_API_BASE = '';
const none = await probeEngine(500);
console.log('none  :', JSON.stringify(none));

if (!live.ok) fails.push(`引擎在 18000 应判可达，实际 ${JSON.stringify(live)}`);
if (live.ms <= 0) fails.push(`live.ms 应为正数，实际 ${live.ms}`);
if (dead.ok || !dead.reason) fails.push(`死端口应判失败且带 reason，实际 ${JSON.stringify(dead)}`);
if (none.reason !== 'not_configured') fails.push(`未配置应 reason=not_configured，实际 ${JSON.stringify(none)}`);

console.log(fails.length ? `✗ ${fails.join(' | ')}` : '✓ probeEngine 三分支正确');
process.exit(fails.length ? 1 : 0);
