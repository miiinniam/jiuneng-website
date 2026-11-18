/**
 * 车辆匹配（契约 §3.5）
 * ────────────────────────────────────────────────────────────
 * 钉住三件事：
 *  1. 出参白名单：组对象只有 model|category|vehicle_count|reason|flags；
 *     `breakdown` / `pairs[].per_truck` / `locked` / 任何金额字段一律丢弃。
 *  2. 超限判定：引擎 `oversize.unassigned` 非空 ⇒ blocked:true。
 *  3. 失败必须是可读的 `{ok:false, reason, note}`，不把引擎内部报文透给客户。
 *
 * 跑法：node --test server/tools/fleet.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { matchFleet, parseFleetInput } from './fleet.ts';

process.env.OSRM_API_BASE = 'http://engine.test';
process.env.OSRM_ENGINE_KEY = 'k1';

const ENGINE_OK = {
  recommended: { model_id: 'flatbed_low_17m5' },
  groups: [
    {
      model_id: 'flatbed_low_17m5',
      display_name: '低平板 17.5 米',
      category: 'flatbed',
      max_load_ton: 38,
      vehicle_count: 1,
      transport_units: 1,
      reason: '超长件，需低平板',
      dim_flags: ['超长'],
      permit_flags: ['许可（一类件，最易批）'],
      count_doctrine: { caliber: 1 },
      axle_lines: { lines_max: 4 },
      oversize_released: false,
      pair_total_width_m: null,
      pairs: [{ pair_id: 'p1', line_ids: ['0'], line_names: ['风机叶片'], per_truck: 2, trucks: 1, rule_id: 'CO-1', reason: '同车', accepted: true }],
      locked: { 0: 'flatbed_low_17m5' },
      breakdown: { 车数: 1, 重量: 1, 体积: null, 长度: 1, 面积: null, 主因: '长度', 不可分: false },
    },
  ],
  total_trucks: 1,
  vehicle_breakdowns: { flatbed_low_17m5: { 车数: 1 } },
  oversize: {
    unassigned: [],
    max_piece_weight_ton: 12,
    max_piece_length_m: 42,
    cargo_type: 'normal',
    policy: { allow_oversized: false, released: [], hard_blocked: [] },
    doctrine: { one_piece_over_t: 32, axle_q_t: 48, transport_units: 1 },
  },
  message: '自动匹配完成（整票试算）',
  reason: '超长件，需低平板',
  mixed: false,
  needs_split: false,
  split_hint: null,
  engine: 'fleet_planner@v016',
  category_fallback: false,
  confirm: { total_trucks: 1, one_item_trucks: 1, multi_item_trucks: 0, lines: [], plan_confirmed: false },
  plan_confirmed: false,
};

type Stub = { calls: { url: string; body: unknown }[]; restore: () => void };

function stubEngine(opts: { body?: unknown; status?: number; throws?: boolean } = {}): Stub {
  const calls: { url: string; body: unknown }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
    if (opts.throws) throw new Error('connect ECONNREFUSED');
    return new Response(JSON.stringify(opts.body ?? ENGINE_OK), { status: opts.status ?? 200 });
  }) as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = original; } };
}

const REQ = {
  weight_kg: 18000,
  volume_m3: 40,
  cargo_type: 'normal',
  items: [{ name: '风机叶片', length_m: 42, width_m: 3.2, height_m: 3.4, weight_kg: 12000, count: 1, stackable: false }],
};

test('出参白名单：组对象只有 model|category|vehicle_count|reason|flags', async () => {
  const stub = stubEngine();
  try {
    const parsed = parseFleetInput(REQ);
    assert.ok(parsed.ok);
    if (!parsed.ok) return;
    const out = await matchFleet(parsed.value);
    assert.equal(out.ok, true);
    if (!out.ok) return;
    assert.equal(out.groups.length, 1);
    assert.deepEqual(Object.keys(out.groups[0]).sort(), ['category', 'flags', 'model', 'reason', 'vehicle_count']);
    assert.equal(out.groups[0].model, 'flatbed_low_17m5');
    assert.equal(out.groups[0].category, '平板车');
    assert.equal(out.groups[0].vehicle_count, 1);
    assert.equal(out.groups[0].reason, '超长件，需低平板');
    assert.ok(Array.isArray(out.groups[0].flags) && out.groups[0].flags.includes('超长'));
    assert.equal(out.total_trucks, 1);
    assert.deepEqual(Object.keys(out.oversize).sort(), ['basis', 'blocked']);
    assert.equal(out.oversize.blocked, false);
  } finally {
    stub.restore();
  }
});

test('丢弃 breakdown / pairs[].per_truck / locked / 金额字段', async () => {
  const stub = stubEngine();
  try {
    const parsed = parseFleetInput(REQ);
    assert.ok(parsed.ok);
    if (!parsed.ok) return;
    const out = await matchFleet(parsed.value);
    const json = JSON.stringify(out);
    // 用带引号的键名做断言：`blocked` 里就含 "locked" 子串，裸词匹配会误报
    for (const forbidden of ['"breakdown"', '"per_truck"', '"locked"', '"price', '"profit', '"margin', '"pair_id"', '"count_doctrine"', '"axle_lines"', '"vehicle_breakdowns"', '"confirm"', '"model_id"', '"dim_flags"']) {
      assert.ok(!json.includes(forbidden), `响应体泄漏了内部字段 ${forbidden}`);
    }
  } finally {
    stub.restore();
  }
});

test('超限判定：引擎 unassigned 非空 ⇒ blocked:true 且有中文依据', async () => {
  const bad = { ...ENGINE_OK, groups: [], total_trucks: 0, oversize: { ...ENGINE_OK.oversize, unassigned: [{ name: '风机叶片', reason: '单件超重' }] } };
  const stub = stubEngine({ body: bad });
  try {
    const parsed = parseFleetInput(REQ);
    assert.ok(parsed.ok);
    if (!parsed.ok) return;
    const out = await matchFleet(parsed.value);
    assert.equal(out.ok, true);
    if (!out.ok) return;
    assert.equal(out.oversize.blocked, true);
    assert.match(out.oversize.basis, /单件最大尺寸/);
    assert.equal(out.total_trucks, 0);
    assert.deepEqual(out.groups, []);
  } finally {
    stub.restore();
  }
});

test('旧版引擎（部署副本）：没有 unassigned/policy，空 groups ⇒ blocked:true 且类别译成中文', async () => {
  // 实测 deploy/osrm-engine 的整票 planner 回包：oversize 只有 unfit_reason / splittable，没有 unassigned
  const legacy = {
    recommended: null,
    groups: [],
    total_trucks: 0,
    oversize: { max_piece_length_m: 42, unfit_reason: 'piece_overlong_exceeds_all', need_special: false, splittable: true },
  };
  const stub = stubEngine({ body: legacy });
  try {
    const parsed = parseFleetInput(REQ);
    assert.ok(parsed.ok);
    if (!parsed.ok) return;
    const out = await matchFleet(parsed.value);
    assert.equal(out.ok, true);
    if (!out.ok) return;
    assert.equal(out.oversize.blocked, true, '配不出车却回 blocked:false 会误导客户');
  } finally {
    stub.restore();
  }

  const container = { ...ENGINE_OK, groups: [{ model_id: 'container_45hc', category: 'container', vehicle_count: 2, reason: '整票 …' }] };
  const stub2 = stubEngine({ body: container });
  try {
    const parsed = parseFleetInput(REQ);
    assert.ok(parsed.ok);
    if (!parsed.ok) return;
    const out = await matchFleet(parsed.value);
    assert.equal(out.ok, true);
    if (!out.ok) return;
    assert.equal(out.groups[0].category, '集装箱车', '英文枚举不得透给客户');
  } finally {
    stub2.restore();
  }
});

test('请求体只带引擎需要的字段（不透传本地附加字段）', async () => {
  const stub = stubEngine();
  try {
    const parsed = parseFleetInput(REQ);
    assert.ok(parsed.ok);
    if (!parsed.ok) return;
    await matchFleet(parsed.value);
    assert.equal(stub.calls.length, 1);
    assert.match(stub.calls[0].url, /\/reference\/fit-vehicles$/);
    const body = stub.calls[0].body as Record<string, unknown>;
    assert.deepEqual(Object.keys(body).sort(), ['cargo_type', 'items', 'volume_m3', 'weight_kg']);
    assert.deepEqual(Object.keys((body.items as Record<string, unknown>[])[0]).sort(),
      ['count', 'height_m', 'length_m', 'name', 'stackable', 'weight_kg', 'width_m']);
  } finally {
    stub.restore();
  }
});

test('引擎 5xx → ok:false engine_error；连不上 → engine_unreachable', async () => {
  const stub500 = stubEngine({ status: 500, body: { detail: 'internal traceback 费用计算公式 车辆数分解()' } });
  const parsed = parseFleetInput(REQ);
  assert.ok(parsed.ok);
  if (!parsed.ok) return;
  try {
    const out = await matchFleet(parsed.value);
    assert.equal(out.ok, false);
    if (out.ok) return;
    assert.equal(out.reason, 'engine_error');
    assert.ok(!JSON.stringify(out).includes('traceback'), '引擎内部报文不得回传');
  } finally {
    stub500.restore();
  }

  const stubDown = stubEngine({ throws: true });
  try {
    const out = await matchFleet(parsed.value);
    assert.equal(out.ok, false);
    if (out.ok) return;
    assert.equal(out.reason, 'engine_unreachable');
    assert.match(out.note, /正式询价|稍后/);
  } finally {
    stubDown.restore();
  }
});

test('入参校验：缺 items / 单件重量非法 / 数量非正整数 → bad_input（不打引擎）', async () => {
  const stub = stubEngine();
  try {
    assert.equal(parseFleetInput({}).ok, false);
    assert.equal(parseFleetInput({ items: [] }).ok, false);
    assert.equal(parseFleetInput({ items: [{ name: 'a', weight_kg: 0, count: 1 }] }).ok, false);
    assert.equal(parseFleetInput({ items: [{ name: 'a', weight_kg: 100, count: 1.5 }] }).ok, false);
    assert.equal(parseFleetInput({ items: [{ name: 'a', weight_kg: 100, count: 1, length_m: -2 }] }).ok, false);
    const bad = parseFleetInput({ items: [{ name: 'a', weight_kg: 100 }] });
    assert.ok(bad.ok, 'count 缺省应默认为 1');
    if (bad.ok) assert.equal(bad.value.items![0].count, 1);
    // 全是非法入参 ⇒ 一次引擎调用都不该发生
    parseFleetInput({});
    assert.equal(stub.calls.length, 0);
  } finally {
    stub.restore();
  }
});

test('入参缺 weight_kg 时由明细合计得出（不允许把 0 传给引擎）', () => {
  const parsed = parseFleetInput({ items: [{ name: 'a', weight_kg: 12000, count: 2 }, { name: 'b', weight_kg: 6000, count: 1 }] });
  assert.ok(parsed.ok);
  if (!parsed.ok) return;
  assert.equal(parsed.value.weight_kg, 30000);
  assert.equal(parsed.value.items!.length, 2);
});
