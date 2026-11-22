// AI 回复里的经纬度识别 —— 纯函数测试（不依赖浏览器 / 网络）。
// 跑法：npx tsx --test features/quote/src/components/ai/extractCoords.test.ts

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { extractRoutePair } from './extractCoords.ts';

test('JSON 对象块：取前两个 {lat,lng} 当起终点', () => {
  const text = '已按 友谊关 → 河内 测算。{"lat": 22.0051, "lng": 106.7498} 到 {"lat": 21.0285, "lng": 105.8542}，全程约 172 km。';
  const pair = extractRoutePair(text);
  assert.ok(pair);
  assert.deepEqual(pair[0], { lat: 22.0051, lng: 106.7498 });
  assert.deepEqual(pair[1], { lat: 21.0285, lng: 105.8542 });
});

test('对象块键序颠倒、带中文冒号也认', () => {
  const text = '起点{lng：106.7498，lat：22.0051}，终点{lng: 105.8542, lat: 21.0285}';
  const pair = extractRoutePair(text);
  assert.ok(pair);
  assert.equal(pair[0].lat, 22.0051);
  assert.equal(pair[1].lng, 105.8542);
});

test('中文字段式（纬度…经度…）按出现顺序配对', () => {
  const text = '起点：纬度 22.0051、经度 106.7498\n终点：纬度 21.0285、经度 105.8542';
  const pair = extractRoutePair(text);
  assert.ok(pair);
  assert.deepEqual(pair[0], { lat: 22.0051, lng: 106.7498 });
  assert.deepEqual(pair[1], { lat: 21.0285, lng: 105.8542 });
});

test('只有一个点 → null（不拿半对去改地图）', () => {
  assert.equal(extractRoutePair('河内大概在 {lat: 21.0285, lng: 105.8542} 附近'), null);
  assert.equal(extractRoutePair('纬度 21.0285'), null);
});

test('没有坐标 / 空串 → null', () => {
  assert.equal(extractRoutePair('25 吨普货走友谊关，13 米平板车，参考价 1800 万越南盾左右。'), null);
  assert.equal(extractRoutePair(''), null);
});

test('数值越界（纬度 > 90）→ null', () => {
  const text = '{"lat": 122.0051, "lng": 106.7498} {"lat": 21.0285, "lng": 105.8542}';
  assert.equal(extractRoutePair(text), null);
});

test('起终点完全重合 → null', () => {
  const text = '{"lat": 21.0285, "lng": 105.8542} {"lat": 21.0285, "lng": 105.8542}';
  assert.equal(extractRoutePair(text), null);
});

test('0,0 视为「没填」而不是几内亚湾', () => {
  const text = '{"lat": 0, "lng": 0} {"lat": 21.0285, "lng": 105.8542}';
  assert.equal(extractRoutePair(text), null);
});
