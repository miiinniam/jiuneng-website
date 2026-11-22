import test from 'node:test';
import assert from 'node:assert/strict';

import {
  geocodeFallback,
  inServiceArea,
  mapPhoton,
  normalizePlace,
  resetGeocodeCache,
  searchTermOf,
} from './geocodeFallback.ts';

test('normalizePlace：去后缀与括号，让「南宁市」「南宁（广西）」落到同一个别名', () => {
  assert.equal(normalizePlace('南宁市'), '南宁');
  assert.equal(normalizePlace(' 河内 '), '河内');
  assert.equal(normalizePlace('凭祥（口岸）'), '凭祥');
  assert.equal(normalizePlace('南宁 市'), '南宁');
});

test('searchTermOf：中文走别名表（带省份/国家限定，防同名误命中）', () => {
  assert.equal(searchTermOf('南宁'), 'Nanning, Guangxi, China');
  assert.equal(searchTermOf('南宁市'), 'Nanning, Guangxi, China');
  assert.equal(searchTermOf('河内'), 'Hanoi, Vietnam');
  assert.equal(searchTermOf('友谊关'), 'Friendship Pass, Guangxi, China');
  // 裸写 Pingxiang 会被解析成河北平乡县 —— 限定词是硬要求
  assert.match(searchTermOf('凭祥'), /Guangxi/);
  assert.equal(searchTermOf('Hanoi'), 'Hanoi');
  assert.equal(searchTermOf('Lang Son'), 'Lang Son');
});

test('inServiceArea：中越范围外一律判否（河北平乡 / 北京北海公园都是真实误命中）', () => {
  assert.equal(inServiceArea(22.084, 106.832), true, '凭祥');
  assert.equal(inServiceArea(21.028, 105.854), true, '河内');
  assert.equal(inServiceArea(37.063, 115.025), false, '河北平乡县（裸查 Pingxiang 的真结果）');
  assert.equal(inServiceArea(39.92, 116.38), false, '北京');
  assert.equal(inServiceArea(1.35, 103.82), false, '新加坡');
});

test('mapPhoton：范围外的命中被丢弃，不给错坐标', () => {
  const payload = {
    features: [
      // 先放河北平乡（错的那个），再放广西凭祥（对的）
      { geometry: { coordinates: [115.0254894, 37.0634355] }, properties: { name: '平乡县', country: '中国' } },
      { geometry: { coordinates: [106.8324, 22.084] }, properties: { name: '凭祥市', country: '中国' } },
    ],
  };
  const hits = mapPhoton('凭祥', payload);
  assert.equal(hits.length, 1, '平乡县必须被包围盒挡掉');
  assert.equal(hits[0].lat, 22.084);
});

test('searchTermOf：歧义词不做猜测（「太原」中越同名 → 原样查，不擅自当越南太原）', () => {
  assert.equal(searchTermOf('太原'), '太原');
  assert.equal(searchTermOf('越南太原'), 'Thai Nguyen, Vietnam');
});

test('mapPhoton：中文查询时把用户原词放最前，建议列表里客户认得出', () => {
  const payload = {
    features: [
      {
        geometry: { coordinates: [108.32, 22.82] },
        properties: { name: 'Nanning', state: 'Guangxi', country: 'China' },
      },
    ],
  };
  const hits = mapPhoton('南宁', payload);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].lat, 22.82);
  assert.equal(hits[0].lng, 108.32);
  assert.match(hits[0].label, /^南宁（Nanning, Guangxi, China）$/);
});

test('mapPhoton：英文查询时不加中文前缀', () => {
  const payload = {
    features: [
      { geometry: { coordinates: [105.85, 21.03] }, properties: { name: 'Hanoi', country: 'Vietnam' } },
    ],
  };
  assert.equal(mapPhoton('Hanoi', payload)[0].label, 'Hanoi, Vietnam');
});

test('mapPhoton：畸形输入一律回空数组（不许抛）', () => {
  assert.deepEqual(mapPhoton('x', null), []);
  assert.deepEqual(mapPhoton('x', {}), []);
  assert.deepEqual(mapPhoton('x', { features: 'nope' }), []);
  assert.deepEqual(mapPhoton('x', { features: [{ geometry: { coordinates: ['a', 'b'] } }] }), []);
  // 缺 name/state/country 的要素直接丢（label 会空，前端没法展示）
  assert.deepEqual(mapPhoton('x', { features: [{ geometry: { coordinates: [1, 2] }, properties: {} }] }), []);
});

test('geocodeFallback：HTTP 非 2xx / 网络异常都回空数组，且不缓存失败', async () => {
  resetGeocodeCache();
  let calls = 0;
  const badFetch = (async () => {
    calls += 1;
    return { ok: false, json: async () => ({}) } as unknown as Response;
  }) as unknown as typeof fetch;
  assert.deepEqual(await geocodeFallback('南宁', 2, badFetch), []);
  assert.equal(calls, 1);

  const throwing = (async () => {
    calls += 1;
    throw new Error('boom');
  }) as unknown as typeof fetch;
  assert.deepEqual(await geocodeFallback('南宁', 2, throwing), []);
  assert.equal(calls, 2, '失败不得命中缓存，必须是真又打了一次');
});

test('geocodeFallback：请求带别名英文名，命中后走缓存', async () => {
  resetGeocodeCache();
  const seen: string[] = [];
  const fakeFetch = (async (url: string) => {
    seen.push(String(url));
    return {
      ok: true,
      json: async () => ({
        features: [
          { geometry: { coordinates: [108.32, 22.82] }, properties: { name: 'Nanning', country: 'China' } },
        ],
      }),
    } as unknown as Response;
  }) as unknown as typeof fetch;

  const first = await geocodeFallback('南宁', 2, fakeFetch);
  assert.equal(first.length, 1);
  assert.match(seen[0], /q=Nanning/);
  assert.match(seen[0], /photon\.komoot\.io/);

  const second = await geocodeFallback('南宁', 2, fakeFetch);
  assert.equal(second.length, 1);
  assert.equal(seen.length, 1, '第二次应命中缓存，不再打网络');
});
