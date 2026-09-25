/**
 * 工具层探针：直接调 agentChat 的工具函数，检查 OSRM++ 返回里带的价格/内部字段有没有被剥掉。
 *
 * 关键设计：**先断言"工具真的成功了"再做泄漏检查**——
 * 否则一旦参数契约变了（历史上就发生过：老版本传 cargo_weight_ton，现在是 weight_kg），
 * 工具会返回参数错误、payload 里没数据，泄漏检查会「因为没东西可泄漏」而假通过。
 *
 * 用法（引擎需在跑）：
 *   OSRM_API_BASE=http://127.0.0.1:18000 npx tsx scripts/probe-tools.ts
 */
import { queryRouteCost, lookupServiceInfo } from '../server/agentChat';

const FORBIDDEN = [
  'breakdown',
  'profit_vnd',
  'margin_rate',
  'border_fees',
  'cost_total',
  'cost_distance',
  'geometry',
  'timing',
  'osrm_profile',
];

async function main() {
  const route = await queryRouteCost({
    origin: '南宁',
    destination: '河内',
    border: '友谊关口岸',
    weight_kg: 25000,
    volume_m3: 60,
    mode: 'consolidated',
  });

  const payload = route.payload as Record<string, unknown>;
  console.log('=== query_route_cost payload ===');
  console.log(JSON.stringify(payload, null, 2).slice(0, 800));

  const fails: string[] = [];

  // 1) 非空转：工具必须真的算出东西
  const distance = Number(payload.distance_km ?? payload.distance);
  const count = Number(payload.vehicle_count ?? payload.trucks);
  if (!Number.isFinite(distance) || distance <= 0) {
    fails.push(`工具没给出里程（payload.distance_km=${JSON.stringify(payload.distance_km)}）——参数契约可能已变，后续泄漏检查会假通过`);
  }
  if (!Number.isFinite(count) || count <= 0) {
    fails.push(`工具没给出车数（payload.vehicle_count=${JSON.stringify(payload.vehicle_count)}）`);
  }

  // 2) 泄漏检查：内部字段不得出现在对客 payload 里
  console.log('\n=== 泄漏断言 ===');
  const raw = JSON.stringify(route.payload);
  for (const bad of FORBIDDEN) {
    const hit = raw.includes(bad);
    if (hit) fails.push(`内部字段泄漏：${bad}`);
    console.log(`  ${hit ? '✗ 泄漏' : '✓ 未出现'}  ${bad}`);
  }

  // 3) 站内资料工具仍可用
  const info = lookupServiceInfo('documents', 'zh');
  const p = info.payload as Record<string, unknown>;
  const docs = Array.isArray(p.documents) ? p.documents.length : 0;
  console.log(`\n=== lookup_service_info(documents) : ${docs} 条 ===`);
  if (docs === 0) fails.push('lookup_service_info(documents) 返回 0 条——站内资料未接到工具');

  const contact = lookupServiceInfo('contact', 'vi');
  const email = String((contact.payload as Record<string, unknown>).email ?? '');
  console.log(`=== lookup_service_info(contact, vi) email: ${email} ===`);
  if (!email.includes('jiuneng')) fails.push(`联系邮箱看起来不对：${email}`);

  console.log(fails.length ? `\n✗ ${fails.length} 项失败：\n  - ${fails.join('\n  - ')}` : '\n全部通过 ✅');
  process.exit(fails.length ? 1 : 0);
}

main().catch((e) => {
  console.error('probe failed:', e);
  process.exit(1);
});
