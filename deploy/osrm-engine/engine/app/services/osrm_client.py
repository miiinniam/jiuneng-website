"""OSRM Route API 封装（DEVELOPMENT_GOALS.md §5.2）。

对接 start.ps1 启动的本地 osrm-routed（默认 http://localhost:5001）。
内置 httpx 传输层重试（连接错误/5xx 自动重试 2 次）。
OSRM 不可用时降级为 Haversine 直线距离 × 1.3（§10.2 降级方案）。
"""

import asyncio
import math
from urllib.parse import urlparse
import os
from dataclasses import dataclass, field

import httpx

from app.config import settings

# OSRM 降级系数：越南公路网实际距离 ≈ 直线距离 × 1.3（经验值）
ROAD_FACTOR = 1.3
# 降级时假设平均车速 60 km/h
FALLBACK_SPEED_KMH = 60.0

# 🆕 v008b：单次 OSRM 请求的**硬上限**（秒）。httpx 的 timeout 是逐读操作的，
# 服务端细水长流时可能永不触发 → 请求无限挂起（实测打包版后端会挂 >60s，用户侧=一直转）。
# 可用环境变量 OSRM_HARD_TIMEOUT_S 覆盖（现场网络差时可调大）。
HARD_TIMEOUT_S = float(os.environ.get("OSRM_HARD_TIMEOUT_S", "25"))

# 传输层重试：对幂等 GET 请求安全，自动应对 OSRM 偶发抖动
_transport = httpx.AsyncHTTPTransport(retries=2)


class OSRMError(RuntimeError):
    pass


class ProfileUnsupported(OSRMError):
    """🆕 v015.4：服务端不认识/未编译请求的 profile —— 车型选路的**重试信号**。

    与普通 OSRMError 区分：这种情况换成默认 profile 重试是有意义的（服务端只是在
    那条 profile 路径上没有路网图）；而超时/连不上服务器时换 profile 重试没意义
    （只会白等一个硬超时 HARD_TIMEOUT_S），必须直接走直线降级。
    """


class OSRMServerError(OSRMError):
    """🆕 v015.4：服务端**有响应但报错**（5xx / code != Ok）—— 同样值得换 profile 重试。

    服务端还在线，重试一次默认 profile 的成本很低；但如果是超时/连不上（服务端不在线），
    换 profile 重试只会白等一个硬超时，所以必须区分开。
    """


# OSRM 明确表示「profile 不可用」的错误码 / HTTP 状态（自建 osrm-routed 未编译该 profile）
PROFILE_ERROR_CODES = {"InvalidUrl", "InvalidProfile", "InvalidService", "InvalidOptions"}
PROFILE_ERROR_STATUS = {400, 404, 405, 501}

# 🆕 v015.4：降级文案的固定短语 —— 用户必须一眼看到「没有做限高限重校验」，
#   否则会默认这条路线已经按车型避开了限高/限重/限行路段（那是错的）。
PROFILE_NOTE_FLAG = "未按车型限高限重校验"


def available_profiles() -> set[str]:
    """本机 OSRM 实际编译/提供的 profile 清单（settings.osrm_available_profiles，逗号分隔）。

    默认只声明 driving —— 公共 demo 对任意 profile 字串都返回 200 且结果与 driving 逐位相同
    （实测见 config.py 注释），光看 HTTP 状态无法判断车型 profile 是否真的生效。
    """
    return {p.strip().lower() for p in str(settings.osrm_available_profiles).split(",") if p.strip()}


def _note_unavailable(requested: str, used: str, detail: str) -> str:
    return (f"所选车型路线 profile「{requested}」在本机 OSRM 上不可用或报错（{detail}），"
            f"已回退「{used}」重算：{PROFILE_NOTE_FLAG}")


def _note_demo_ignores_profile(requested: str, base: str) -> str:
    """声明里有该 profile，但服务端是公共 demo（只编译 driving）——必须如实说未生效。"""
    return (
        f"所选车型路线 profile「{requested}」在公共 demo OSRM（{HOSTS_WITHOUT_PROFILE_SUPPORT[0]}）上"
        f"并不存在——官方只提供「{base}」路网，对任意 profile 字串都静默按「{base}」返回；"
        f"已按「{base}」口径出价：未按车型限高限重校验"
    )


def _note_not_declared(requested: str, used: str) -> str:
    return (f"所选车型路线 profile「{requested}」不在本机 OSRM 路网清单内"
            f"（OSRM_AVAILABLE_PROFILES={settings.osrm_available_profiles}；"
            f"自建 truck 路网并声明后才会按车型限高限重选路）—— "
            f"服务端会静默按「{used}」返回路线，已按「{used}」口径出价：{PROFILE_NOTE_FLAG}")


def _note_service_down(requested: str, used: str) -> str:
    return (f"OSRM 服务不可用，路线为直线估算；所选车型 profile「{requested}」未生效"
            f"（按「{used}」口径估算）：{PROFILE_NOTE_FLAG}")


@dataclass
class RouteLeg:
    """一段子路线（两个相邻 waypoint 之间）。"""
    distance_m: float
    duration_s: float


@dataclass
class RouteResult:
    distance_m: float
    duration_s: float
    geometry: dict
    fallback: bool = False  # True 表示使用降级估算，非 OSRM 实测路线
    legs: list[RouteLeg] = field(default_factory=list)  # 途经点切分的子段（如 中国段/越南段）
    # 🆕 v015.4：地图路线按车型 —— profile 兑现情况（诚实降级标注）
    profile_requested: str | None = None  # 车型要求的 profile（None = 调用方未指定车型）
    profile_used: str | None = None       # 实际采用的路网口径（未兑现时＝回退的默认 profile）
    profile_honored: bool = True          # False ⇒ **未按车型限高限重校验**，见 profile_note
    profile_note: str | None = None       # 中文降级说明（profile_honored=False 时必有值）


#: 官方公共 demo OSRM：**只编译了 driving**，对任意 profile 字串都返回 200 且结果与 driving
#  逐位相同（2026-09-23 实测：/route/v1/truck/ 与 /route/v1/foo/ 都返 200，distance 完全相同）。
#  因此在这类服务端上「声明了 truck」必然是假的 —— 判定兑现时不能只看声明，还要看服务端有没有能力
#  提供该路网，否则就是我们自己假报「已按车型限高限重校验」。
HOSTS_WITHOUT_PROFILE_SUPPORT: tuple[str, ...] = ("router.project-osrm.org",)


def host_supports_profiles(base_url: str) -> bool:
    """该 OSRM 服务端**是否有能力**按不同 profile 出路网（公共 demo 只有 driving）。"""
    host = urlparse(base_url or "").netloc.lower()
    return not any(h in host for h in HOSTS_WITHOUT_PROFILE_SUPPORT)


class OSRMClient:
    def __init__(self, base_url: str | None = None, *, enable_fallback: bool = True,
                 profile: str | None = None):
        self.base_url = base_url or settings.osrm_base_url
        self.enable_fallback = enable_fallback
        # 🆕 v015.4：车型要求的 profile（如车辆型号库的 osrm_profile=truck）。
        #   None = 调用方没有按车型选路 → 完全走全局默认 profile（v015.4 之前的零回归行为）。
        self.requested_profile = (profile or "").strip().lower() or None

    @staticmethod
    def _haversine_distance_m(
        lng1: float, lat1: float, lng2: float, lat2: float
    ) -> float:
        """Haversine 公式：两点间球面直线距离（米）。

        用于 OSRM 降级时估算总里程和行驶时间。详见 DEVELOPMENT_GOALS.md §10.2。
        """
        R = 6_371_000  # 地球平均半径 (m)
        φ1, φ2 = math.radians(lat1), math.radians(lat2)
        Δφ = math.radians(lat2 - lat1)
        Δλ = math.radians(lng2 - lng1)
        a = (
            math.sin(Δφ / 2) ** 2
            + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _fallback_route(
        coordinates: list[tuple[float, float]],
        *,
        requested: str | None = None,
        used: str | None = None,
        honored: bool = True,
        note: str | None = None,
    ) -> RouteResult:
        """降级估算：累计所有路段的 Haversine 直线距离，乘以道路曲折系数。

        行驶时间按 60 km/h 估算。距离和时间都是近似值，仅供 OSRM 不可用时的
        临时兜底——最终报价精度会受影响，API 响应中显式标注 fallback=true。
        🆕 v015.4：把车型 profile 的兑现情况一并带出（honored=False + 中文 note），
        否则用户会以为这条估算路线已经按车型限高限重校过。
        """
        total_straight = sum(
            OSRMClient._haversine_distance_m(c1[0], c1[1], c2[0], c2[1])
            for c1, c2 in zip(coordinates, coordinates[1:])
        )
        distance_m = total_straight * ROAD_FACTOR
        duration_s = (distance_m / 1000) / FALLBACK_SPEED_KMH * 3600
        return RouteResult(
            distance_m=distance_m,
            duration_s=duration_s,
            geometry={"type": "LineString", "coordinates": []},
            fallback=True,
            profile_requested=requested,
            profile_used=used,
            profile_honored=honored,
            profile_note=note,
        )

    @staticmethod
    def _route_from(
        route: dict,
        *,
        requested: str | None,
        used: str | None,
        honored: bool,
        note: str | None,
    ) -> RouteResult:
        legs = [
            RouteLeg(distance_m=lg["distance"], duration_s=lg["duration"])
            for lg in route.get("legs", [])
        ]
        return RouteResult(
            distance_m=route["distance"],
            duration_s=route["duration"],
            geometry=route["geometry"],
            legs=legs,
            profile_requested=requested,
            profile_used=used,
            profile_honored=honored,
            profile_note=note,
        )

    @staticmethod
    def _profile_error(profile: str, status: int, code: str, message: str) -> OSRMError:
        """HTTP 状态 / OSRM 错误码 → 该归为「profile 不可用」还是普通故障。

        只有「profile 不可用」才值得换默认 profile 重试；其余（超时、5xx、连不上）
        换 profile 也一样失败，白等一个硬超时。
        """
        detail = f"HTTP {status}" + (f" {code}" if code else "") + (f" - {message}" if message else "")
        if code in PROFILE_ERROR_CODES or (status in PROFILE_ERROR_STATUS and code != "Ok"):
            return ProfileUnsupported(f"OSRM profile「{profile}」不可用（{detail}）")
        if status >= 500 or code:
            # 服务端在线但报错（5xx / NoRoute 等）→ 换默认 profile 重试仍有意义
            return OSRMServerError(f"OSRM 请求失败: {code or status} - {message}")
        return OSRMError(f"OSRM 请求失败: {code or status} - {message}")

    async def _request(
        self,
        coordinates: list[tuple[float, float]],
        profile: str | None,
        alternatives: bool,
    ) -> list[dict]:
        """coordinates: [(lng, lat), ...]，至少两个点（起点+终点，可含途经点）。"""
        if len(coordinates) < 2:
            raise ValueError("至少需要起点和终点两个坐标")

        profile = profile or settings.osrm_profile
        coords_str = ";".join(f"{lng},{lat}" for lng, lat in coordinates)
        url = f"{self.base_url}/route/v1/{profile}/{coords_str}"

        async with httpx.AsyncClient(timeout=10.0, transport=_transport) as client:
            try:
                # 🆕 v008b：**硬超时**兜底。httpx 的 timeout 是「每个读操作」的超时，
                #   若服务端细水长流地回数据（公共 demo OSRM 实测如此），读超时可能永不触发
                #   → 请求无限挂起（用户侧表现为「点了计算一直转」）。
                #   asyncio.wait_for 给整个请求一个绝对上限，超时按 OSRMError 处理 → 走既有降级路径。
                response = await asyncio.wait_for(
                    client.get(
                        url,
                        params={
                            "alternatives": "true" if alternatives else "false",
                            "steps": "false",
                            "overview": "full",
                            "geometries": "geojson",
                        },
                    ),
                    timeout=HARD_TIMEOUT_S,
                )
            except asyncio.TimeoutError as exc:
                raise OSRMError(
                    f"OSRM 请求超时（>{HARD_TIMEOUT_S}s，{self.base_url}）—— 已按降级估算处理；"
                    "公共 demo 服务器不稳，建议把 OSRM_BASE_URL 指向自建 OSRM"
                ) from exc
            except httpx.HTTPError as exc:
                raise OSRMError(f"无法连接 OSRM 服务 ({self.base_url}): {exc}") from exc

        if response.status_code >= 400:
            code, message = "", ""
            try:
                err = response.json()
                code = str(err.get("code") or "")
                message = str(err.get("message") or "")
            except Exception:  # noqa: BLE001 —— 非 JSON 错误体（网关页等）
                message = (getattr(response, "text", "") or "")[:120]
            raise self._profile_error(profile, response.status_code, code, message)

        try:
            data = response.json()
        except ValueError as exc:   # 200 但响应体不是 JSON（被网关/端口占位页顶替）
            raise OSRMError(f"OSRM 返回非 JSON 响应（HTTP {response.status_code}）") from exc

        if data.get("code") != "Ok":
            raise self._profile_error(profile, response.status_code,
                                      str(data.get("code") or ""), str(data.get("message") or ""))

        return data["routes"]

    def _requested(self, profile: str | None) -> str | None:
        """本次请求「车型要求的 profile」：显式入参优先，其次构造时传入的车型 profile。"""
        explicit = (profile or "").strip().lower()
        return explicit or self.requested_profile or None

    async def _fetch_profiled(
        self,
        coordinates: list[tuple[float, float]],
        requested: str | None,
        alternatives: bool,
    ) -> tuple[list[dict] | None, str, bool, str | None, OSRMError | None]:
        """按「车型 profile」取路线，返回 (routes|None, used_profile, honored, note, error)。

        v015.4 规则（⚠️ 绝不能让用户以为做过限高限重校验）：
          ① 未指定车型 / 就是全局默认 profile → 按默认请求（与 v015.4 之前一字不差）
          ② 指定了车型 profile → **一定先按它请求**（服务端有该路网图就兑现，这才是需求）
             - 服务端报 profile 不可用（4xx）/ 报错（5xx、NoRoute）→ 回退默认 profile 重算，
               honored=False + 中文说明（服务端在线，重试成本低）
             - 服务端 200 但本机未声明该 profile（公共 demo 会**静默忽略**）→ honored=False + 说明
             - 超时/连不上 → 不重试（不白等第二个硬超时），honored=False + 说明，走直线降级
          ③ routes=None 表示 OSRM 这条路走不通 → 由调用方决定是否直线降级（fallback 开关）
        """
        base = (settings.osrm_profile or "driving").strip().lower()
        if requested is None or requested == base:
            # 未按车型选路 → 与 v015.4 之前**一字不差**：请求默认 profile，失败交调用方降级
            try:
                routes = await self._request(coordinates, requested or base, alternatives)
            except OSRMError as exc:
                return None, requested or base, True, None, exc
            return routes, requested or base, True, None, None

        try:
            routes = await self._request(coordinates, requested, alternatives)
        except (ProfileUnsupported, OSRMServerError) as exc:
            # 服务端对车型 profile 不可用/报错（没有该路网、5xx、NoRoute）→ 换默认 profile 重试一次
            # —— 这才是需求里的「回退 driving」；服务端在线时重试成本很低。
            try:
                routes = await self._request(coordinates, base, alternatives)
            except OSRMError as retry_exc:
                note = _note_unavailable(requested, base, f"{exc}；回退请求亦失败：{retry_exc}")
                return None, base, False, note, retry_exc
            return routes, base, False, _note_unavailable(requested, base, str(exc)), None
        except OSRMError as exc:
            # 超时/连不上：服务端不在线，换 profile 重试只会白等一个硬超时 HARD_TIMEOUT_S
            # → 直接交给直线降级，并如实标注车型 profile 未生效。
            return None, base, False, _note_service_down(requested, base), exc

        if requested in available_profiles():
            if host_supports_profiles(self.base_url):
                return routes, requested, True, None, None
            # ⚠️ 声明里有该 profile，但服务端是**公共 demo**（只编译 driving）→ 声明与实际矛盾，
            #   以服务端为准。否则就是「声明即信任」下的假话：2026-09-23 实测声明 truck 后，
            #   truck 与 driving 的距离/时长逐位相同（170.2966 km / 2.3351 h），标记却是 honored=True。
            return routes, base, False, _note_demo_ignores_profile(requested, base), None
        # 服务端 200 但本机没声明这条 profile：公共 demo 实测会静默按 driving 返回，
        # 结果与 driving 逐位相同 → 不能报 honored=true（那是谎报限高限重校验）。
        return routes, base, False, _note_not_declared(requested, base), None

    async def get_route(
        self,
        coordinates: list[tuple[float, float]],
        profile: str | None = None,
    ) -> RouteResult:
        requested = self._requested(profile)
        routes, used, honored, note, error = await self._fetch_profiled(
            coordinates, requested, alternatives=False
        )
        if routes is None:
            if not self.enable_fallback:
                raise error or OSRMError(f"OSRM 不可用（{self.base_url}）")
            return self._fallback_route(coordinates, requested=requested, used=used,
                                        honored=honored, note=note)
        return self._route_from(routes[0], requested=requested, used=used,
                                honored=honored, note=note)

    async def get_routes(
        self,
        coordinates: list[tuple[float, float]],
        profile: str | None = None,
    ) -> list[RouteResult]:
        """§9 Phase X 多路线对比 —— 请求 OSRM 的候选路线（数量由 OSRM 决定，通常 1-3 条）。

        注意：降级模式下多路线退化为单条估算路线（因为无法从 OSRM 获取候选路线）。
        🆕 v015.4：与 `get_route` 同一套车型 profile 口径（先按车型 profile，兑现不了则回退并标注）。
        """
        requested = self._requested(profile)
        routes, used, honored, note, error = await self._fetch_profiled(
            coordinates, requested, alternatives=True
        )
        if routes is None:
            if not self.enable_fallback:
                raise error or OSRMError(f"OSRM 不可用（{self.base_url}）")
            return [self._fallback_route(coordinates, requested=requested, used=used,
                                         honored=honored, note=note)]
        return [self._route_from(r, requested=requested, used=used, honored=honored, note=note)
                for r in routes]
