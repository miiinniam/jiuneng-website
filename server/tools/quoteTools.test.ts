/**
 * 报价工具层单测 —— 守三条线：
 *  ① 工具只「校验 + 算补丁」，补丁以 form_patch 下行，不许偷偷改别的键；
 *  ② 地址检索失败时**不许**下发半个补丁（猜错的坐标等于给错价）；
 *  ③ run_quote 的结果里不许出现 breakdown / cost_ / margin / profit（客户看得见的红线）。
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { createQuoteExecutor, QUOTE_TOOLS, type QuoteFormSnapshot } from './quoteTools.ts';
import type { SseEvent, ToolResult } from '../agentChat.ts';

const BASE_FORM: QuoteFormSnapshot = {
  originLabel: '南宁',
  destLabel: '河内',
  originLat: 22.823,
  originLng: 108.317,
  destLat: 21.028,
  destLng: 105.854,
  weightKg: 20000,
  cargoType: 'normal',
};

/** 公开测算结果的真实形状（buildPublicQuote 的白名单出参） */
const PUBLIC_RESULT = {
  ok: true,
  scope: 'public',
  distance_km: 386.8,
  duration_h: 5.7,
  total_trucks: 1,
  needs_split: false,
  split_note: null,
  picks: [{ model_id: 'flatbed_13m', name: '普通平板 13米', max_load_ton: 30, vehicle_count: 1 }],
  note: '引擎按逐件口径配车：1 个车型方案，共 1 车。',
};

function makeExec(form: QuoteFormSnapshot = BASE_FORM, over: Partial<Parameters<typeof createQuoteExecutor>[0]> = {}) {
  return createQuoteExecutor({
    form,
    geocode: async (q: string) =>
      q === '南宁'
        ? { label: '南宁', lat: 22.823, lng: 108.317 }
        : q === '河内'
          ? { label: '河内 Hà Nội', lat: 21.028, lng: 105.854 }
          : null,
    runQuote: async () => PUBLIC_RESULT,
    ...over,
  });
}

const patchesOf = (r: ToolResult): Record<string, unknown>[] =>
  (r.events ?? [])
    .filter((e: SseEvent) => e.event === 'form_patch')
    .map((e) => (e as { data: { patch: Record<string, unknown> } }).data.patch);

test('read_form：已填齐时 missing 为空、ready=true', async () => {
  const r = await makeExec()('read_form', {}, 'zh');
  assert.equal(r.ok, true);
  assert.deepEqual(r.payload.missing, []);
  assert.equal(r.payload.ready, true);
  assert.equal(r.events, undefined, '读操作不许下发补丁');
});

test('read_form：缺重量时把「总重量」列进 missing', async () => {
  const r = await makeExec({ ...BASE_FORM, weightKg: 0 })('read_form', {}, 'zh');
  assert.equal(r.payload.ready, false);
  assert.deepEqual(r.payload.missing, ['总重量']);
});

test('set_route：地名解析成功 ⇒ 下发 form_patch（含坐标与展示名）', async () => {
  const r = await makeExec()('set_route', { origin: '南宁', destination: '河内' }, 'zh');
  assert.equal(r.ok, true);
  const patches = patchesOf(r);
  assert.equal(patches.length, 1);
  assert.equal(patches[0].originLat, 22.823);
  assert.equal(patches[0].originLabel, '南宁');
  assert.equal(patches[0].destLat, 21.028);
  assert.equal(patches[0].destLabel, '河内 Hà Nội');
});

test('set_route：地名检索不到 ⇒ ok=false 且**不下发任何补丁**（不猜坐标）', async () => {
  const r = await makeExec()('set_route', { origin: '火星基地' }, 'zh');
  assert.equal(r.ok, false);
  assert.equal(patchesOf(r).length, 0, '检索失败时不许下发半个补丁');
  assert.match(r.summary, /检索不到|补充省份/);
});

test('set_cargo：明细整表替换（不是追加），且单位统一成公斤', async () => {
  const r = await makeExec()(
    'set_cargo',
    {
      weight_kg: 25000,
      cargo_type: 'oversized',
      items: [{ name: '塔筒节', length_m: 30, width_m: 3, height_m: 3, weight_kg: 25000, count: 1 }],
    },
    'zh',
  );
  assert.equal(r.ok, true);
  const p = patchesOf(r)[0];
  assert.equal(p.weightKg, 25000);
  assert.equal(p.weightUnit, 'kg');
  assert.equal(p.cargoType, 'oversized');
  const items = p.items as Array<Record<string, unknown>>;
  assert.equal(items.length, 1, '整表替换：只应有本次传入的 1 行');
  assert.equal(items[0].lengthM, 30);
  assert.equal(items[0].weightKg, 25000);
  assert.equal(items[0].count, 1);
});

test('set_cargo：非法行（缺长/宽/重）被丢弃；全非法则 ok=false', async () => {
  const r = await makeExec()('set_cargo', { items: [{ name: '没尺寸' }] }, 'zh');
  assert.equal(r.ok, false);
  assert.equal(patchesOf(r).length, 0);
});

test('set_vehicle：库外车型 ⇒ 拒绝（车型名只能来自车型库）', async () => {
  // specMap 走真实引擎，测试环境不可达 ⇒ 空 Map ⇒ 任何 id 都算库外
  const r = await makeExec()('set_vehicle', { model_id: 'not_a_real_truck' }, 'zh');
  assert.equal(r.ok, false);
  assert.equal(patchesOf(r).length, 0);
});

test('set_conditions：只改四个开关，不许改运输模式', async () => {
  const r = await makeExec()('set_conditions', { need_loading: true, allow_oversized: true }, 'zh');
  assert.equal(r.ok, true);
  const p = patchesOf(r)[0];
  assert.deepEqual(Object.keys(p).sort(), ['allowOversized', 'needLoading']);
  assert.equal('loadingMode' in p, false, '公开版固定整车，工具不许改运输模式');
});

test('run_quote：表单缺重量 ⇒ 不跑引擎，ok=false 并点明缺什么', async () => {
  let called = false;
  const exec = makeExec({ ...BASE_FORM, weightKg: 0 }, {
    runQuote: async () => {
      called = true;
      return PUBLIC_RESULT;
    },
  });
  const r = await exec('run_quote', {}, 'zh');
  assert.equal(r.ok, false);
  assert.equal(called, false, '缺项时不该打引擎');
  assert.deepEqual(r.payload.missing, ['总重量']);
});

test('run_quote：成功 ⇒ 下发 quote_result，且结果里没有成本字段（红线）', async () => {
  const r = await makeExec()('run_quote', {}, 'zh');
  assert.equal(r.ok, true);
  const qr = (r.events ?? []).filter((e: SseEvent) => e.event === 'quote_result');
  assert.equal(qr.length, 1, '必须下发 quote_result 给前端渲染');
  const json = JSON.stringify(qr[0]);
  for (const forbidden of ['breakdown', 'cost_', 'margin', 'profit', 'base_rate', 'fixed_surcharge']) {
    assert.equal(json.includes(forbidden), false, `测算结果泄漏了内部字段 ${forbidden}`);
  }
  // 反向自证：结果里确实有客户该看到的数字，否则上面那组断言是空转
  assert.ok(json.includes('386.8'), '里程没进结果，红线断言等于空转');
  assert.match(r.summary, /里程约 386\.8 公里/);
});

test('run_quote：引擎不可用 ⇒ ok=false 且不下发 quote_result', async () => {
  const exec = makeExec(BASE_FORM, { runQuote: async () => null });
  const r = await exec('run_quote', {}, 'zh');
  assert.equal(r.ok, false);
  assert.equal((r.events ?? []).length, 0);
  assert.match(r.summary, /不可用|正式询价/);
});

test('工具声明齐全且都带 description（模型靠它决定调不调）', () => {
  const names = QUOTE_TOOLS.map((t) => (t as { name: string }).name);
  assert.deepEqual(names.sort(), [
    'match_vehicles', 'read_form', 'run_quote', 'set_cargo',
    'set_conditions', 'set_route', 'set_vehicle',
  ]);
  for (const t of QUOTE_TOOLS) {
    const tool = t as { name: string; description: string };
    assert.ok(tool.description.length > 20, `${tool.name} 的描述太短，模型会误用`);
  }
  // 金额口径必须写进 run_quote 的描述里，否则模型会自己补明细
  const runQuote = QUOTE_TOOLS.find((t) => (t as { name: string }).name === 'run_quote') as { description: string };
  assert.match(runQuote.description, /区间/);
  assert.match(runQuote.description, /不得改写/);
});
