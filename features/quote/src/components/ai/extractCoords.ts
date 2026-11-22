// AI 回复里的经纬度识别 —— 纯函数，无 DOM / 无网络，可在 node 里直接测。
//
// 为什么单独抽出来：ChatPanel 只允许在「确实识别到成对的 lat/lng」时调一次
// onPickRoute，否则会拿没坐标的回复去改用户的起终点（误触）。正则与范围校验
// 放在这里，ChatPanel 只负责在一条回复结束时调一次。

import type { LatLng } from '../../engine/types';

const NUM = '-?\\d{1,3}(?:\\.\\d+)?';
/** 键可能带引号（JSON 片段）也可能不带（模型随手打字），冒号可省（`纬度 22.8`）。 */
const LAT_KEY = new RegExp(`(?:lat|latitude|纬度)\\s*"?\\s*[:：=]?\\s*"?\\s*(${NUM})`, 'gi');
const LNG_KEY = new RegExp(`(?:lng|lon|longitude|经度)\\s*"?\\s*[:：=]?\\s*"?\\s*(${NUM})`, 'gi');
/** 形如 {lat: 21.03, lng: 105.85} 的对象块（键序随意，允许带引号/中文冒号） */
const OBJECT_BLOCK = /\{[^{}]{0,240}\}/g;

function inRange(lat: number, lng: number): boolean {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (lat < -90 || lat > 90) return false;
  if (lng < -180 || lng > 180) return false;
  return true;
}

function firstMatch(text: string, re: RegExp): number | null {
  const rx = new RegExp(re.source, re.flags.replace('g', ''));
  const m = rx.exec(text);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

function allMatches(text: string, re: RegExp): number[] {
  const out: number[] = [];
  const rx = new RegExp(re.source, 'gi');
  let m: RegExpExecArray | null = rx.exec(text);
  while (m !== null) {
    const n = Number(m[1]);
    if (Number.isFinite(n)) out.push(n);
    m = rx.exec(text);
  }
  return out;
}

function toPair(lat: number, lng: number): LatLng | null {
  if (!inRange(lat, lng)) return null;
  if (lat === 0 && lng === 0) return null; // 0,0 是「没填」而不是几内亚湾
  return { lat, lng };
}

/**
 * 从一段助手中文/JSON 回复里取出「起点 + 终点」。
 * 认不出两个合法点就返回 null —— 宁可不改地图，也不要半对。
 */
export function extractRoutePair(text: string): [LatLng, LatLng] | null {
  if (!text) return null;

  // ① 先认 {lat:…, lng:…} 对象块（最可信：模型给出结构化坐标时就是这种形状）
  const fromObjects: LatLng[] = [];
  const blockRe = new RegExp(OBJECT_BLOCK.source, 'g');
  let block = blockRe.exec(text);
  while (block !== null) {
    const chunk = block[0];
    const lat = firstMatch(chunk, LAT_KEY);
    const lng = firstMatch(chunk, LNG_KEY);
    if (lat !== null && lng !== null) {
      const pair = toPair(lat, lng);
      if (pair) fromObjects.push(pair);
    }
    block = blockRe.exec(text);
  }
  if (fromObjects.length >= 2) {
    const pair: [LatLng, LatLng] = [fromObjects[0], fromObjects[1]];
    return pair[0].lat === pair[1].lat && pair[0].lng === pair[1].lng ? null : pair;
  }

  // ② 退一步：按出现顺序把「纬度…经度…」配对（表格/列表式回复）
  const lats = allMatches(text, LAT_KEY);
  const lngs = allMatches(text, LNG_KEY);
  if (lats.length >= 2 && lngs.length >= 2) {
    const candidates: LatLng[] = [];
    const n = Math.min(lats.length, lngs.length);
    for (let i = 0; i < n; i += 1) {
      const pair = toPair(lats[i], lngs[i]);
      if (pair) candidates.push(pair);
    }
    if (candidates.length >= 2) {
      const [a, b] = candidates;
      if (a.lat === b.lat && a.lng === b.lng) return null;
      return [a, b];
    }
  }

  return null;
}
