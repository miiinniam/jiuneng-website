"""地理编码服务（DEVELOPMENT_GOALS.md §5.3）。

当前直接调用公共 Nominatim API，支持中文/越南语/英文地址搜索。
Nominatim 的使用政策要求带上有区分度的 User-Agent，且不要高频调用
（<= 1 req/s）；后续如果调用量上来了，再按文档 §5.3 换成自建的
Photon/Nominatim 实例。

2026-07-16: 纯异步实现 + 手写 TTL 缓存（24h 按天分桶），
消除 lru_cache + 同步 httpx 阻塞事件循环的问题。
"""

import asyncio
import json
import time
from dataclasses import dataclass

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "OSRM-plus-plus/0.1 (jiuneng-international internal logistics tool)"

# ── 异步 TTL 缓存 ──
# 按天分桶（query + limit + date），每天自然刷新，无需手动驱逐。
# Nominatim 公共实例严格限制 1 req/s，缓存命中可避免重复查询。
CACHE_TTL_SECONDS = 86400  # 24h
CACHE_MAXSIZE = 2000

_cache: dict[str, tuple[float, str]] = {}  # key → (expires_at, json_str)
_cache_lock = asyncio.Lock()


class GeocoderError(RuntimeError):
    pass


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    display_name: str
    # 🆕 v008：所属国家/性质 —— "CN" / "VN" / "BORDER"（边境口岸，本身不属于某一国）
    #   用途：判定运输范围（境内 vs 跨境），见 app/api/route.py 的 _route_scope()
    country: str = ""


# 🆕 v008：运输范围判定的兜底依据 —— 坐标落在哪国的粗略包围盒。
#   注：中越边境带（约 lat 21–23.5、lng 102–110）两国包围盒重叠 → 返回 ""（判不准），
#   这种情况下由本地地名表给出的 country 决定；都判不出则按跨境保守处理。
_VN_BBOX = (8.0, 23.5, 102.0, 110.0)     # lat_min, lat_max, lng_min, lng_max
_CN_BBOX = (18.0, 54.0, 73.0, 135.5)


def bbox_country(lat: float, lng: float) -> str:
    """按坐标粗略判断国家；落在两国包围盒重叠带或都不在 → 返回空串（判不准）。"""
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return ""
    in_vn = _VN_BBOX[0] <= la <= _VN_BBOX[1] and _VN_BBOX[2] <= ln <= _VN_BBOX[3]
    in_cn = _CN_BBOX[0] <= la <= _CN_BBOX[1] and _CN_BBOX[2] <= ln <= _CN_BBOX[3]
    if in_vn and in_cn:
        return ""     # 边境带：判不准，交给本地地名表
    if in_vn:
        return "VN"
    if in_cn:
        return "CN"
    return ""


def country_of(name: str) -> str:
    """按地名反查国家（走本地表别名匹配）；查不到 → ""。"""
    if not name or not str(name).strip():
        return ""
    hits = _local_lookup(str(name))
    return hits[0].country if hits else ""


def _make_cache_key(query: str, limit: int) -> str:
    """按天分桶：同一天同一 query+limit 命中缓存。"""
    bucket = time.strftime("%Y%m%d")  # "20260716"
    return f"{bucket}|{query.strip()}|{limit}"


def _evict_if_needed(now: float) -> None:
    """容量保护：删除最早过期的条目。注意调用方必须持有 _cache_lock。"""
    if len(_cache) <= CACHE_MAXSIZE:
        return
    expired = [(k, exp) for k, (exp, _) in _cache.items() if now >= exp]
    if expired:
        expired.sort(key=lambda x: x[1])
        overflow = len(_cache) - CACHE_MAXSIZE
        for k, _ in expired[: min(overflow, len(expired))]:
            del _cache[k]


# ── 本地坐标兜底 ──
# 本机网络对公共 Nominatim 受限（getaddrinfo failed）时，常见中越城市/口岸离线 geocode。
# 用「别名列表子串匹配查询」：查询里出现任一别名即命中。
_LOCAL_COORDS: list[tuple[list[str], float, float, str, str]] = [
    # 边境口岸
    (["友谊关", "友谊口岸", "凭祥", "huu nghi", "huu nghi quan", "hữu nghị", "pingxiang"], 21.9711, 106.7108, "友谊关口岸（凭祥/谅山）", "BORDER"),
    (["东兴", "芒街", "đông hưng", "móng cái", "mong cai", "dongxing"], 21.5478, 107.9718, "东兴/芒街口岸", "BORDER"),
    (["河口", "老街", "hekou", "lào cai", "lao cai"], 22.507, 103.959, "河口/老街口岸", "BORDER"),
    # 越南城市
    (["河内", "hanoi", "hà nội", "ha noi"], 21.0285, 105.8542, "河内 Hà Nội", "VN"),
    (["海防", "hải phòng", "hai phong", "haiphong"], 20.8449, 106.6881, "海防 Hải Phòng", "VN"),
    (["北宁", "bắc ninh", "bac ninh"], 21.1860, 106.0763, "北宁 Bắc Ninh", "VN"),
    (["北江", "bắc giang", "bac giang"], 21.2750, 106.1940, "北江 Bắc Giang", "VN"),
    (["谅山", "lạng sơn", "lang son"], 21.8533, 106.7610, "谅山 Lạng Sơn", "VN"),
    (["下龙", "下龍", "hạ long", "ha long"], 20.9599, 107.0425, "下龙 Hạ Long", "VN"),
    (["顺化", "順化", "hue", "huế", "thành phố huế", "thua thien hue", "thừa thiên huế"], 16.4637, 107.5909, "顺化 Huế", "VN"),
    (["岘港", "峴港", "đà nẵng", "da nang", "danang"], 16.0544, 108.2022, "岘港 Đà Nẵng", "VN"),
    (["胡志明", "西贡", "hồ chí minh", "ho chi minh", "saigon", "tphcm"], 10.8231, 106.6297, "胡志明市 TP. Hồ Chí Minh", "VN"),
    # 中国城市
    (["上海", "shanghai", "shang hai"], 31.2304, 121.4737, "上海", "CN"),
    (["北京", "beijing", "pékin"], 39.9042, 116.4074, "北京", "CN"),
    (["广州", "guangzhou", "canton"], 23.1291, 113.2644, "广州", "CN"),
    (["深圳", "shenzhen"], 22.5431, 114.0579, "深圳", "CN"),
    (["东莞", "dongguan"], 23.0207, 113.7518, "东莞", "CN"),
    (["佛山", "foshan"], 23.0215, 113.1214, "佛山", "CN"),
    (["杭州", "hangzhou"], 30.2741, 120.1551, "杭州", "CN"),
    (["苏州", "suzhou"], 31.2989, 120.5853, "苏州", "CN"),
    (["南宁", "nanning"], 22.8170, 108.3665, "南宁", "CN"),
    (["崇左", "chongzuo"], 22.3766, 107.3640, "崇左", "CN"),
    (["昆明", "kunming"], 24.8801, 102.8329, "昆明", "CN"),
    (["太原", "thái nguyên", "thai nguyen"], 21.5942, 105.8482, "太原 Thái Nguyên", "VN"),
    (["永福", "vĩnh phúc", "vinh phuc", "vinh yen", "vĩnh yên"], 21.3092, 105.5965, "永福 Vĩnh Phúc", "VN"),
    (["宁平", "ninh bình", "ninh binh"], 20.2506, 105.9745, "宁平 Ninh Bình", "VN"),
    (["清化", "thanh hóa", "thanh hoa"], 19.8075, 105.7764, "清化 Thanh Hóa", "VN"),
    (["荣市", "vinh", "nghệ an", "nghe an"], 18.6735, 105.6922, "荣市 Vinh (Nghệ An)", "VN"),
    (["河静", "hà tĩnh", "ha tinh"], 18.3430, 105.9058, "河静 Hà Tĩnh", "VN"),
    (["广治", "quảng trị", "quang tri", "dong ha", "đông hà"], 16.8122, 107.1006, "广治 Quảng Trị", "VN"),
    (["广南", "quảng nam", "quang nam", "hoi an", "hội an"], 15.8799, 108.3261, "广南 Quảng Nam", "VN"),
    (["归仁", "quy nhơn", "quy nhon", "bình định", "binh dinh"], 13.7830, 109.2196, "归仁/平定 Bình Định", "VN"),
    (["芽庄", "nha trang", "khánh hòa", "khanh hoa"], 12.2388, 109.1967, "芽庄 Nha Trang", "VN"),
    (["平阳", "bình dương", "binh duong", "thu dau mot", "thủ dầu một"], 10.9798, 106.6518, "平阳 Bình Dương", "VN"),
    (["同奈", "đồng nai", "dong nai", "bien hoa", "biên hòa"], 10.9574, 106.8427, "同奈 Đồng Nai", "VN"),
    (["头顿", "vũng tàu", "vung tau", "bà rịa", "ba ria"], 10.3410, 107.0844, "头顿 Vũng Tàu", "VN"),
    (["芹苴", "cần thơ", "can tho"], 10.0342, 105.7855, "芹苴 Cần Thơ", "VN"),
    (["安江", "an giang", "long xuyen", "long xuyên"], 10.3757, 105.4179, "安江 An Giang", "VN"),
    (["无锡", "wuxi"], 31.4912, 120.3119, "无锡", "CN"),
    (["常州", "changzhou"], 31.8107, 119.9741, "常州", "CN"),
    (["宁波", "ningbo"], 29.8683, 121.5440, "宁波", "CN"),
    (["温州", "wenzhou"], 27.9939, 120.6994, "温州", "CN"),
    (["嘉兴", "jiaxing"], 30.7461, 120.7555, "嘉兴", "CN"),
    (["绍兴", "shaoxing"], 30.0303, 120.5802, "绍兴", "CN"),
    (["台州", "taizhou"], 28.6564, 121.4207, "台州", "CN"),
    (["中山", "zhongshan"], 22.5176, 113.3928, "中山", "CN"),
    (["珠海", "zhuhai"], 22.2707, 113.5767, "珠海", "CN"),
    (["惠州", "huizhou"], 23.1115, 114.4152, "惠州", "CN"),
    (["江门", "jiangmen"], 22.5789, 113.0815, "江门", "CN"),
    (["肇庆", "zhaoqing"], 23.0472, 112.4651, "肇庆", "CN"),
    (["汕头", "shantou"], 23.3535, 116.6820, "汕头", "CN"),
    (["泉州", "quanzhou"], 24.8741, 118.6757, "泉州", "CN"),
    (["厦门", "xiamen", "amoy"], 24.4798, 118.0894, "厦门", "CN"),
    (["福州", "fuzhou"], 26.0745, 119.2965, "福州", "CN"),
    (["青岛", "qingdao"], 36.0671, 120.3826, "青岛", "CN"),
    (["天津", "tianjin"], 39.0842, 117.2010, "天津", "CN"),
    (["大连", "dalian"], 38.9140, 121.6147, "大连", "CN"),
    (["沈阳", "shenyang"], 41.8057, 123.4315, "沈阳", "CN"),
    (["成都", "chengdu"], 30.5728, 104.0668, "成都", "CN"),
    (["重庆", "chongqing", "chungking"], 29.5630, 106.5516, "重庆", "CN"),
    (["长沙", "changsha"], 28.2282, 112.9388, "长沙", "CN"),
    (["武汉", "wuhan"], 30.5928, 114.3055, "武汉", "CN"),
    (["郑州", "zhengzhou"], 34.7466, 113.6254, "郑州", "CN"),
    (["西安", "xian", "xi'an"], 34.3416, 108.9398, "西安", "CN"),
    (["合肥", "hefei"], 31.8206, 117.2272, "合肥", "CN"),
    (["南昌", "nanchang"], 28.6820, 115.8582, "南昌", "CN"),
    (["贵阳", "guiyang"], 26.6470, 106.6302, "贵阳", "CN"),
]


def _local_lookup(query: str) -> list[GeocodeResult]:
    """按别名子串匹配本地坐标表；命中返回该坐标，未命中返回空。"""
    q = (query or "").strip().lower()
    if not q:
        return []
    for aliases, lat, lng, name, country in _LOCAL_COORDS:
        for a in aliases:
            if a.lower() in q:
                return [GeocodeResult(lat=lat, lng=lng, display_name=name, country=country)]
    return []


async def search_address(query: str, limit: int = 5) -> list[GeocodeResult]:
    """异步地址搜索，带 24h TTL 缓存。"""
    if not query.strip():
        return []

    cache_key = _make_cache_key(query, limit)
    now = time.time()

    # 检查缓存
    async with _cache_lock:
        if cache_key in _cache:
            expires_at, raw = _cache[cache_key]
            if now < expires_at:
                items = json.loads(raw)
                return [
                    GeocodeResult(
                        lat=float(item["lat"]),
                        lng=float(item["lon"]),
                        display_name=item["display_name"],
                        country=item.get("country") or bbox_country(item["lat"], item["lon"]),
                    )
                    for item in items
                ]

    # 缓存未命中 → 先查本地坐标表（网络受限时离线命中，避免 DNS 报错）
    local = _local_lookup(query)
    if local:
        local_raw = json.dumps(
            [{"lat": str(r.lat), "lon": str(r.lng), "display_name": r.display_name, "country": r.country} for r in local],
            ensure_ascii=False,
        )
        async with _cache_lock:
            _cache[cache_key] = (now + CACHE_TTL_SECONDS, local_raw)
        return local

    # 本地未命中 → 请求 Nominatim
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "q": query.strip(),
                    "format": "json",
                    "limit": limit,
                    "accept-language": "zh,vi,en",
                    "addressdetails": 1,   # 🆕 v008：取 country_code 用于判定运输范围
                },
                headers={"User-Agent": USER_AGENT},
            )
    except httpx.HTTPError as exc:
        raise GeocoderError(f"地理编码服务请求失败: {exc}") from exc

    if response.status_code != 200:
        raise GeocoderError(f"地理编码服务返回异常状态码: {response.status_code}")

    items = response.json()
    raw = json.dumps(items, ensure_ascii=False)

    # 写入缓存
    async with _cache_lock:
        _evict_if_needed(now)
        _cache[cache_key] = (now + CACHE_TTL_SECONDS, raw)

    return [
        GeocodeResult(
            lat=float(item["lat"]),
            lng=float(item["lon"]),
            display_name=item["display_name"],
            # 🆕 v008：Nominatim 的 country_code（cn/vn）→ 大写；拿不到就按坐标包围盒兜底
            country=(str((item.get("address") or {}).get("country_code") or "").upper()
                     or bbox_country(item["lat"], item["lon"])),
        )
        for item in items
    ]
