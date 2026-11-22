/**
 * 地址检索的**线上兜底链**。
 *
 * 为什么需要：线上引擎（Render）调公共 Nominatim 恒返空 —— OSM 对数据中心 IP 有限制/封禁。
 * 实测 `https://site.jiuneng.space/api/quote/geocode?q=` 传「南宁 / Hanoi / Pingxiang / 凭祥」
 * 全部 `{"results":[]}`，而同一条链路在本地完全正常（本地 IP 未被限）。
 * 后果不止是 AI 设不了路线：**网页表单的地址建议也一起失效**（两条路共用一个路由）。
 *
 * 顺序：引擎（Nominatim）→ 本模块（中文别名 → Photon）→ 空。
 * 坐标一律取自 OSM 数据（Photon 是 komoot 跑的 OSM 服务），**不内置手写坐标** ——
 * 手写坐标错了就是给错价，比查不到更糟。
 */

/** 中文/越南语常用地名 → 英文检索名。只放**无歧义**的（如「太原」中越同名，不放）。
 *  ⚠️ 这里必须带省份/国家限定：实测 `Pingxiang` 裸查命中的是**河北平乡县**（37.06N/115.02E），
 *  而不是广西凭祥（22.10N/106.75E）—— 坐标错了就是给错价，比查不到更糟。 */
const CN_ALIAS: Record<string, string> = {
  // 中国侧
  南宁: 'Nanning, Guangxi, China',
  凭祥: 'Pingxiang, Guangxi, China',
  友谊关: 'Friendship Pass, Guangxi, China',
  友谊关口岸: 'Friendship Pass, Guangxi, China',
  东兴: 'Dongxing, Guangxi, China',
  防城港: 'Fangchenggang, Guangxi, China',
  崇左: 'Chongzuo, Guangxi, China',
  龙州: 'Longzhou, Guangxi, China',
  大新: 'Daxin, Guangxi, China',
  靖西: 'Jingxi, Guangxi, China',
  柳州: 'Liuzhou, Guangxi, China',
  桂林: 'Guilin, Guangxi, China',
  北海: 'Beihai, Guangxi, China',
  钦州: 'Qinzhou, Guangxi, China',
  玉林: 'Yulin, Guangxi, China',
  广州: 'Guangzhou, Guangdong, China',
  深圳: 'Shenzhen, Guangdong, China',
  昆明: 'Kunming, Yunnan, China',
  文山: 'Wenshan, Yunnan, China',
  河口: 'Hekou, Yunnan, China',
  // 越南侧
  河内: 'Hanoi, Vietnam',
  海防: 'Haiphong, Vietnam',
  胡志明: 'Ho Chi Minh City, Vietnam',
  西贡: 'Ho Chi Minh City, Vietnam',
  岘港: 'Da Nang, Vietnam',
  顺化: 'Hue, Vietnam',
  谅山: 'Lang Son, Vietnam',
  同登: 'Dong Dang, Lang Son, Vietnam',
  老街: 'Lao Cai, Vietnam',
  下龙: 'Ha Long, Vietnam',
  海阳: 'Hai Duong, Vietnam',
  北宁: 'Bac Ninh, Vietnam',
  北江: 'Bac Giang, Vietnam',
  芽庄: 'Nha Trang, Vietnam',
  归仁: 'Quy Nhon, Vietnam',
  芹苴: 'Can Tho, Vietnam',
  边和: 'Bien Hoa, Vietnam',
  头顿: 'Vung Tau, Vietnam',
  广宁: 'Quang Ninh, Vietnam',
  越南太原: 'Thai Nguyen, Vietnam',
};

/**
 * 中越业务的坐标包围盒。**落在外面的结果一律丢弃**：
 * 这是最后一道闸 —— 别名再准也可能被检索服务理解歪（实测 `Pingxiang` 裸查给的是河北平乡），
 * 而给错坐标的代价是一条错误报价。宁可回空让客户手填。
 */
const CN_VN_BBOX = { latMin: 8, latMax: 24, lngMin: 100, lngMax: 112 };

export function inServiceArea(lat: number, lng: number): boolean {
  return lat >= CN_VN_BBOX.latMin && lat <= CN_VN_BBOX.latMax && lng >= CN_VN_BBOX.lngMin && lng <= CN_VN_BBOX.lngMax;
}

export type GeoHit = { label: string; lat: number; lng: number };

const PHOTON_URL = 'https://photon.komoot.io/api/';
const PHOTON_TIMEOUT_MS = 8000;
const CACHE_TTL_MS = 10 * 60 * 1000;
const CACHE_MAX = 300;

const cache = new Map<string, { at: number; hits: GeoHit[] }>();

/** 去掉「省 / 市 / 县 / 区」等后缀与首尾空白，让「南宁市」与「南宁」命中同一别名。 */
export function normalizePlace(raw: string): string {
  return raw
    .trim()
    .replace(/[（(].*?[)）]/g, '')
    .replace(/\s+/g, '')
    .replace(/(省|市|县|区|镇|口岸)$/u, '')
    .trim();
}

/** 地名 → 英文检索名；没有别名就原样返回（Photon 也认英文/越南文原名）。 */
export function searchTermOf(raw: string): string {
  const key = normalizePlace(raw);
  return CN_ALIAS[key] ?? CN_ALIAS[raw.trim()] ?? raw.trim();
}

type PhotonFeature = {
  geometry?: { coordinates?: unknown };
  properties?: Record<string, unknown>;
};

/** Photon 回包 → 检索结果。label 尽量保留用户输入的写法，方便客户在建议列表里认出来。 */
export function mapPhoton(query: string, payload: unknown, limit = 6): GeoHit[] {
  const feats = (payload as { features?: unknown })?.features;
  if (!Array.isArray(feats)) return [];
  const hasCN = /[\u4e00-\u9fa5]/.test(query);
  const hits: GeoHit[] = [];
  for (const raw of feats) {
    const f = (raw && typeof raw === 'object' ? raw : {}) as PhotonFeature;
    const coords = f.geometry?.coordinates;
    if (!Array.isArray(coords) || coords.length < 2) continue;
    const lng = Number(coords[0]);
    const lat = Number(coords[1]);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
    // 最后一道闸：不在中越范围内的一律丢（实测裸查 Pingxiang 会返回河北平乡县）
    if (!inServiceArea(lat, lng)) continue;
    const p = f.properties ?? {};
    const name = typeof p.name === 'string' ? p.name : '';
    const state = typeof p.state === 'string' ? p.state : '';
    const country = typeof p.country === 'string' ? p.country : '';
    const tail = [name, state, country].filter((s) => s && s.length > 0);
    if (!tail.length) continue;
    // 中文查询时把用户原词放最前：建议列表里客户认的是自己要找的地方
    const label = hasCN ? `${query.trim()}（${tail.join(', ')}）` : tail.join(', ');
    hits.push({ label: label.slice(0, 120), lat, lng });
    if (hits.length >= limit) break;
  }
  return hits;
}

/**
 * 兜底检索。**永不抛错**：地址查不到不是错误（契约 §3.1 要求回空数组，前端让用户手填）。
 */
export async function geocodeFallback(
  q: string,
  limit = 6,
  fetchImpl: typeof fetch = fetch,
): Promise<GeoHit[]> {
  const query = q.trim();
  if (!query || query.length > 120) return [];

  const key = `${normalizePlace(query)}|${limit}`;
  const now = Date.now();
  const cached = cache.get(key);
  if (cached && now - cached.at < CACHE_TTL_MS) return cached.hits;

  const term = searchTermOf(query);
  const url = `${PHOTON_URL}?q=${encodeURIComponent(term)}&limit=${limit}&lang=en`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), PHOTON_TIMEOUT_MS);
  try {
    const res = await fetchImpl(url, {
      headers: {
        // Nominatim/Photon 都要求可辨识 UA；共用同一个标识便于对方限流时识别我们
        'User-Agent': 'OSRM-plus-plus/0.1 (jiuneng-international logistics tool)',
        Accept: 'application/json',
      },
      signal: ctrl.signal,
    });
    if (!res.ok) return [];
    const hits = mapPhoton(query, await res.json(), limit);
    if (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value as string);
    cache.set(key, { at: now, hits });
    return hits;
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

/** 仅供测试：清缓存。 */
export function resetGeocodeCache(): void {
  cache.clear();
}
