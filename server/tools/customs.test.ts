/**
 * 报关区间与分项（契约 §3.2 / §3.4）
 * ────────────────────────────────────────────────────────────
 * 钉住四件事：
 *  1. fail-closed：BORDER_MARKUP 未配置 → available:false，且**一次都不打引擎**（不泄漏也不乱报价）。
 *  2. 区间算法：cost × markup × (1 ± rangePct)，RMB 取整 10、VND 取整 10 万。
 *  3. 分项白名单重建：每项只有 label_zh|amount|unit 三个键，响应里不许出现引擎英文键或成本字段。
 *  4. 汇率拿不到 → ddp/vietnam 为 null，**不许猜**。
 *
 * 跑法：node --test server/tools/customs.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseCustomsInput, publicRange, detail, CustomsError } from './customs.ts';

process.env.OSRM_API_BASE = 'http://engine.test';
process.env.OSRM_ENGINE_KEY = 'k1';
process.env.BORDER_MARKUP = '1.5';
process.env.BORDER_RANGE_PCT = '0.10';

const FEES = {
  china_side: { items: { customs_declaration: 1500, yard_fee: 300, unloading: 800, transloading: 1000 }, subtotal: 3600 },
  vietnam_side: { items: { customs_clearance: 2500, yard_fee: 800 }, subtotal: 3300 },
  china_total: 3600,
  vietnam_total: 3300,
  ddp_total: 6900,
};

type Stub = { calls: string[]; restore: () => void };

/** 假引擎：按路径回不同 payload（不联网）。 */
function stubEngine(opts: { fees?: unknown; rate?: unknown; feesStatus?: number; rateFails?: boolean } = {}): Stub {
  const calls: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    calls.push(url);
    if (url.includes('/border/fees-only')) {
      const status = opts.feesStatus ?? 200;
      return new Response(JSON.stringify(opts.fees ?? FEES), { status });
    }
    if (url.includes('/reference/exchange-rate')) {
      if (opts.rateFails) throw new Error('rate_down');
      return new Response(JSON.stringify(opts.rate ?? { vnd_per_rmb: 3870, source: 'api', updated: '2026-11-18' }), { status: 200 });
    }
    return new Response('{"detail":"not found"}', { status: 404 });
  }) as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = original; } };
}

test('BORDER_MARKUP 未配置 → available:false 且不打引擎（fail-closed）', async () => {
  process.env.BORDER_MARKUP = '';
  const stub = stubEngine();
  try {
    const out = await publicRange(parseCustomsInput({ vehicle_count: 1 }));
    assert.deepEqual(out, { available: false, note: '线上暂不提供报关费测算，请联系项目经理' });
    assert.equal(stub.calls.length, 0, '未配置系数时必须一次都不打引擎');
  } finally {
    stub.restore();
    process.env.BORDER_MARKUP = '1.5';
  }
});

test('区间算法：成本 × 系数 ± 区间，RMB 取整 10 / VND 取整 10 万', async () => {
  const stub = stubEngine();
  try {
    const out = await publicRange(parseCustomsInput({ vehicle_count: 1 }));
    assert.equal(out.available, true);
    if (!out.available) return;
    // 3600 × 1.5 = 5400 → ±10% = 4860 / 5940
    assert.equal(out.china.min_rmb, 4860);
    assert.equal(out.china.max_rmb, 5940);
    // 3300 × 1.5 × 3870 = 19,156,500 → ±10%，取整 10 万
    assert.equal(out.vietnam!.min_vnd, 17_200_000);
    assert.equal(out.vietnam!.max_vnd, 21_100_000);
    assert.equal(out.ddp!.rate, 3870);
    assert.equal(out.ddp!.min_vnd, 36_000_000);
    assert.equal(out.ddp!.max_vnd, 44_100_000);
    assert.equal(out.disclosure, 'indicative_only');
    assert.equal(out.detail_requires_lead, true);
    for (const edge of [out.china.min_rmb, out.china.max_rmb]) assert.equal(edge % 10, 0);
    for (const edge of [out.vietnam!.min_vnd, out.vietnam!.max_vnd, out.ddp!.min_vnd, out.ddp!.max_vnd]) {
      assert.equal(edge % 100_000, 0);
    }
  } finally {
    stub.restore();
  }
});

test('拿不到汇率 → ddp 与 vietnam 为 null，中国端照旧（不许猜汇率）', async () => {
  const stub = stubEngine({ rateFails: true });
  try {
    const out = await publicRange(parseCustomsInput({ vehicle_count: 1 }));
    assert.equal(out.available, true);
    if (!out.available) return;
    assert.equal(out.ddp, null);
    assert.equal(out.vietnam, null);
    assert.equal(out.china.min_rmb, 4860);
  } finally {
    stub.restore();
  }
});

test('分项白名单重建：每项只有 label_zh|amount|unit，且不含引擎英文键', async () => {
  const stub = stubEngine();
  try {
    const out = await detail(parseCustomsInput({ vehicle_count: 1 }));
    assert.ok(out.china_side.length >= 4);
    for (const row of [...out.china_side, ...out.vietnam_side]) {
      assert.deepEqual(Object.keys(row).sort(), ['amount', 'label_zh', 'unit']);
    }
    const labels = [...out.china_side, ...out.vietnam_side].map((r) => r.label_zh);
    for (const need of ['报关费', '口岸费', '装卸费', '清关费']) assert.ok(labels.includes(need), `缺中文名 ${need}`);
    assert.ok(out.china_side.every((r) => r.unit === 'RMB'));
    assert.ok(out.vietnam_side.every((r) => r.unit === 'VND'));
    // 金额口径：报关费 1500 × 1.5 = 2250；清关费 2500 × 1.5 × 3870 ≈ 14,510,000
    assert.equal(out.china_side.find((r) => r.label_zh === '报关费')!.amount, 2250);
    assert.equal(out.vietnam_side.find((r) => r.label_zh === '清关费')!.amount, 14_510_000);
    // 合计 = 各项之和（不许两套口径）
    assert.equal(out.china_total_rmb, out.china_side.reduce((s, r) => s + r.amount, 0));
    assert.equal(out.vietnam_total_vnd, out.vietnam_side.reduce((s, r) => s + r.amount, 0));
    assert.ok(out.notes.length >= 1 && out.notes[0].includes('非成本'));
    const json = JSON.stringify(out);
    for (const forbidden of ['customs_declaration', 'yard_fee', 'unloading', 'transloading', 'customs_clearance', 'breakdown', 'profit', 'cost_', 'margin']) {
      assert.ok(!json.includes(forbidden), `响应体泄漏了内部字段 ${forbidden}`);
    }
  } finally {
    stub.restore();
  }
});

test('分项里未知的引擎费用键直接丢弃（不猜测中文名）', async () => {
  const stub = stubEngine({ fees: { ...FEES, china_side: { items: { customs_declaration: 1500, weird_internal_item: 999 }, subtotal: 2499 } } });
  try {
    const out = await detail(parseCustomsInput({ vehicle_count: 1 }));
    assert.equal(out.china_side.length, 1);
    assert.equal(out.china_side[0].label_zh, '报关费');
    assert.ok(!JSON.stringify(out).includes('weird_internal_item'));
  } finally {
    stub.restore();
  }
});

test('引擎不可达 → available:false（可读文案，不含内部细节）', async () => {
  const stub = stubEngine({ feesStatus: 502 });
  try {
    const out = await publicRange(parseCustomsInput({ vehicle_count: 1 }));
    assert.equal(out.available, false);
    assert.match((out as { note: string }).note, /暂时不可用/);
  } finally {
    stub.restore();
  }
});

test('汇率缺失时分项明确报 rate_unavailable，不返回半截数据', async () => {
  const stub = stubEngine({ rateFails: true });
  try {
    await assert.rejects(detail(parseCustomsInput({ vehicle_count: 1 })), (error: unknown) => {
      assert.ok(error instanceof CustomsError);
      assert.equal((error as CustomsError).code, 'rate_unavailable');
      return true;
    });
  } finally {
    stub.restore();
  }
});

test('入参归一：字符串数字可解析，越界夹到合法区间，container_type 收窄', () => {
  assert.deepEqual(parseCustomsInput({ vehicle_count: '3' }), {
    vehicle_count: 3, domestic_transport_rmb: 0, container_count: 0, container_type: null, detention_days: 0, heavy_lift_tons: 0,
  });
  assert.equal(parseCustomsInput({}).vehicle_count, 1);
  assert.equal(parseCustomsInput({ vehicle_count: 0 }).vehicle_count, 1);
  assert.equal(parseCustomsInput({ vehicle_count: 'abc' }).vehicle_count, 1);
  assert.equal(parseCustomsInput({ vehicle_count: 5000 }).vehicle_count, 99);
  assert.equal(parseCustomsInput({ detention_days: -3 }).detention_days, 0);
  assert.equal(parseCustomsInput({ container_type: '  40HQ  ' }).container_type, '40HQ');
  assert.equal(parseCustomsInput({ container_type: '' }).container_type, null);
  assert.equal(parseCustomsInput({ domestic_transport_rmb: '1200.5' }).domestic_transport_rmb, 1200.5);
});

test('区间查询把入参原样传给引擎（车数/境内运输费/滞留天数各一份）', async () => {
  const stub = stubEngine();
  try {
    await publicRange(parseCustomsInput({ vehicle_count: 2, domestic_transport_rmb: 900, detention_days: 1, container_count: 2, container_type: '40HQ', heavy_lift_tons: 3 }));
    const feesCall = stub.calls.find((u) => u.includes('/border/fees-only'));
    assert.ok(feesCall, '必须打过 fees-only');
    const q = new URL(feesCall!).searchParams;
    assert.equal(q.get('vehicle_count'), '2');
    assert.equal(q.get('domestic_transport_rmb'), '900');
    assert.equal(q.get('detention_days'), '1');
    assert.equal(q.get('container_count'), '2');
    assert.equal(q.get('container_type'), '40HQ');
    assert.equal(q.get('heavy_lift_tons'), '3');
  } finally {
    stub.restore();
  }
});
