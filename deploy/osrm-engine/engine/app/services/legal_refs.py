"""v016 法规条号**唯一真源**（中越两侧：超限/超载/许可/轴荷/总重）。

为什么要这个模块：`fleet_planner` 的许可文案里散落着 **TT46/2015/TT-BGTVT** 的条号，
而 TT46 已被 **TT39/2024/TT-BGTVT（2025-01-01 生效）** 废止、再被 **TT12/2025/TT-BXD
（2025-07-01 生效）** 取代，并经 **TT19/2026/TT-BXD** 修订 ⇒ 合并本 **26/VBHN-BXD**。
旧条号在新法里**没有一一对应**（Điều 11 khoản 4 甚至不存在），所以：

  ① 条号只在本文件里写死（键 + 条号 + 链接 + 生效日期 + 一行摘要）；
  ② 其它模块（`fleet_planner` 的 `PERMIT_PITFALLS` / `_single_required` / `_line_block` /
     `DIM_POLICY` 注释）**只引用本文件的键**，不再自己写条号；
  ③ 失效→现行的迁移关系放 `MIGRATION_FROM_TT46`，便于评审时逐条比对。

⚠️ 上线前必须由越南侧法务/持证调度按 **26/VBHN-BXD 合并本**复核（设计稿 §10/§12 待办）：
   · Điều 8 khoản 3 的「≥2 个单原」口径（本版 vs 专家口径有分歧 ⇒ 串联共车只挂在开关 ON 上）；
   · TT19/2026/TT-BXD 对 TT12/2025 各条的具体修改；
   · 「勘验/加固/护送费用由申请人承担」的现行条文号（旧 TT46 Điều 20 khoản 3 已失效）。
   软件只**标注**许可与红线，不给法律结论背书。
"""
from __future__ import annotations

#: 越南现行法规链（单一真源，文案里统一用它，不再出现 TT46/2015 条号）
VN_CURRENT_CODE = "TT12/2025/TT-BXD"
VN_CURRENT_EFFECTIVE = "2025-07-01"
VN_AMENDED_BY = "TT19/2026/TT-BXD"
VN_CONSOLIDATED = "26/VBHN-BXD"
VN_SUPERSESSION = (
    "TT46/2015/TT-BGTVT（已失效）→ TT39/2024/TT-BGTVT（2025-01-01 生效，废止 TT46）"
    f"→ {VN_CURRENT_CODE}（{VN_CURRENT_EFFECTIVE} 生效）→ 经 {VN_AMENDED_BY} 修订"
    f" ⇒ 合并本 {VN_CONSOLIDATED}"
)

#: 中国侧：超限（可许可）与超载（无许可路径）两套依据
CN_OVERSIZE_REGULATION = "《超限运输车辆行驶公路管理规定》（交通运输部令 2016 年第 62 号，2021 年第 12 号修正）"
CN_LIMIT_STANDARD = "《公路货运车辆超限超载认定标准》附件4（14 种标准车型总质量限值）"
CN_TRAFFIC_LAW_OVERLOAD = "《中华人民共和国道路交通安全法》第四十八条（严禁超载）/ 第九十二条（罚款）"

_LV = "https://luatvietnam.vn/giao-thong/thong-tu-12-2025-tt-bxd-quy-dinh-tai-trong-kho-gioi-han-va-luu-hanh-xe-qua-tai-tren-duong-bo-404405-d1.html"
_CB = "https://congbao.chinhphu.vn/van-ban/thong-tu-so-12-2025-tt-bxd-45475/57515.htm"
_CB19 = "https://congbao.chinhphu.vn/van-ban/thong-tu-so-19-2026-tt-bxd-469519.htm"
_CB_VBHN = "https://moc.gov.vn/vn/tin-tuc/1196/94433/"

#: 条号真源：键 → {code, article, effective, url, summary}
LEGAL_REFS: dict[str, dict] = {
    # ── 越南：现行 TT12/2025/TT-BXD ─────────────────────────────────────────
    "vn.d10k1": {
        "code": VN_CURRENT_CODE, "article": "Điều 10 khoản 1", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "超限货定义：长 >20.0m、宽 >2.5m、总高 >4.2m（集装箱 4.35m）—— 承接旧 TT46 Điều 9 的数值，条号变更",
    },
    "vn.d10k2": {
        "code": VN_CURRENT_CODE, "article": "Điều 10 khoản 2", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "超重货（hàng siêu trọng）= 装载后**整车总质量 > 48t**（旧口径 32t 单件断点已无法规依据）",
    },
    "vn.d8k2d": {
        "code": VN_CURRENT_CODE, "article": "Điều 8 khoản 2 điểm d", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "超设计/核定载质量 ⇒ 不得上路（**超载红线**：中越两侧均无许可路径）",
    },
    "vn.d8k3": {
        "code": VN_CURRENT_CODE, "article": "Điều 8 khoản 3", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "装载 ≥2 个单原的条件：a) 总质量/轴荷不超 Điều 14/15；b) 堆高按 Điều 16；"
                   "c) 纵向 ≤20.0m 且不超车厢；d) 全宽 ≤2.5m —— 承接旧 TT46 Điều 11 khoản 4（旧条文号不存在）",
    },
    "vn.d8k4": {
        "code": VN_CURRENT_CODE, "article": "Điều 8 khoản 4", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "加固（gia cường）程序 —— **费用归属条文号待核实**（配合 Nghị định 165/2024/NĐ-CP，不写进客户件）",
    },
    "vn.d12k2d": {
        "code": VN_CURRENT_CODE, "article": "Điều 12 khoản 2 điểm d", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "超重货（整车总质量 >48t）只准载 1 个单原（Chỉ được chở 01 đơn nguyên hàng siêu trọng）"
                   "—— 承接旧 TT46 Điều 14 khoản 2 điểm c，**门槛 32t → 48t（整车总重口径）**",
    },
    "vn.d14": {
        "code": VN_CURRENT_CODE, "article": "Điều 14", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "轴荷/拼轴上限：单轴 ≤10t；双联轴按轴距 ≤11/16/18t；三联轴 ≤21t（轴距 ≤1.3m）/24t"
                   "—— 承接旧 TT46 Điều 16；项目 8t/轴线口径仍偏保守可用",
    },
    "vn.d15": {
        "code": VN_CURRENT_CODE, "article": "Điều 15", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "整车总质量表：单车 2/3/4 轴 16/24/30t、≥5 轴 32t（轴距 ≤7m）/34t（>7m）；"
                   "半挂列车 3/4/5 轴 26/34/38（牵销-首轴 3.2–4.5m）或 42（>4.5m）/≥6 轴 40/44/48t；"
                   "全挂列车 ≤45t；**轴距每短 1m 减 2t**（需 `wheelbase_m` / `saddle_to_first_axle_m` 列）",
    },
    "vn.d16": {
        "code": VN_CURRENT_CODE, "article": "Điều 16", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "堆货高按设计载质量分档：≤4.2 / 3.5 / 2.8m（与货物的堆高标记同源）",
    },
    "vn.d22k1dd": {
        "code": VN_CURRENT_CODE, "article": "Điều 22 khoản 1 điểm đ", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "许可前置：须声明铁路/内河/航空/海运不适用或需联运（即「无其他运输方式」）"
                   "—— 承接旧 TT46 Điều 20 khoản 1",
    },
    "vn.d22k3a": {
        "code": VN_CURRENT_CODE, "article": "Điều 22 khoản 3 điểm a", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "超核定载质量 ⇒ **一律不发超限许可证**（超载在越南同样无许可路径）",
    },
    "vn.d22k4": {
        "code": VN_CURRENT_CODE, "article": "Điều 22 khoản 4", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "许可证有效期 ≤90 天（已改建路段）/ ≤30 天（未改建或需护送/加固）",
    },
    "vn.d24": {
        "code": VN_CURRENT_CODE, "article": "Điều 24", "effective": VN_CURRENT_EFFECTIVE,
        "url": _LV,
        "summary": "超限许可由 Sở Xây dựng 按线路签发（许可主体）",
    },
    "vn.vbhn26": {
        "code": VN_CONSOLIDATED, "article": "合并本（全篇）", "effective": "2026-06-02", "url": _CB_VBHN,
        "summary": "TT12/2025/TT-BXD 经 TT19/2026/TT-BXD 修订后的合并文本 —— **上线前按它逐条复核**",
    },
    # ── 中国侧 ──────────────────────────────────────────────────────────────
    "cn.limit_standard": {
        "code": CN_LIMIT_STANDARD, "article": "附件4 表（14 种标准车型）", "effective": "2016-09-21",
        "url": "https://jtj.quanzhou.gov.cn/ztzl/sjgkfbwj/202512/P020251205613898625295.pdf",
        "summary": "车货总质量限值：二轴 18t；三轴 25/27t；四轴 31/36t；五轴 43t；六轴及以上 49t（驱动轴单轴 46t）",
    },
    "cn.oversize_rule": {
        "code": CN_OVERSIZE_REGULATION, "article": "第三条 / 第十条 / 第十七条", "effective": "2021-08-26",
        "url": "https://www.hengqin.gov.cn/lab/flfg/bmgz/content/post_3642535.html",
        "summary": "超限阈值（高 >4m / 宽 >2.55m / 长 >18.1m）；"
                   "第十七条列**不予许可**情形（轴荷超限/桥涵承载不足）⇒ 软件永不放行",
    },
    "cn.overload_law": {
        "code": CN_TRAFFIC_LAW_OVERLOAD, "article": "第四十八条 / 第九十二条", "effective": "2021-04-29",
        "url": "https://jtgl.beijing.gov.cn/jgj/jgxx/flfg/fl/205308/index.html",
        "summary": "严禁超载（超行驶证核定载质量）；超载无许可路径 —— 本版「允许超限运输配车」开关一字不放",
    },
}

#: 失效 → 现行 迁移表（v016 设计稿 §8.1）：键 = 旧 TT46/2015 引用，值 = 本文件现行键。
MIGRATION_FROM_TT46: dict[str, str] = {
    "TT46/2015 Điều 9（2.5/4.2/20m 限值）": "vn.d10k1",
    "TT46/2015 Điều 11 khoản 4（≥2 单原装载条件）": "vn.d8k3",
    "TT46/2015 Điều 14 khoản 2 điểm c（超重货只准 1 单原）": "vn.d12k2d",
    "TT46/2015 Điều 16（轴荷/拼轴）": "vn.d14",
    "TT46/2015 Điều 20 khoản 1（「无其他运输方式」声明）": "vn.d22k1dd",
    "TT46/2015 Điều 20 khoản 3（勘验/加固/护送费用归属）": "vn.d8k4",   # ⚠️ 无直接对应条
}

#: 失效说明（只在**内部/审计**通道出现，不进客户件）
SUPERSEDED_NOTE = "以下旧条文号已失效，仅作历史比对，不得用于新文案：TT46/2015/TT-BGTVT"


def ref(key: str) -> dict:
    """取一条法规记录（键不存在 ⇒ 大声报错，不静默给空）。"""
    try:
        return LEGAL_REFS[key]
    except KeyError as exc:  # noqa: PERF203 —— 键写错必须立刻暴露
        raise KeyError(f"未知法规键 {key!r}（合法键：{sorted(LEGAL_REFS)}）") from exc


def citation(key: str) -> str:
    """文案用的「法规 条号」串，如 `TT12/2025/TT-BXD Điều 12 khoản 2 điểm d`。"""
    r = ref(key)
    return f"{r['code']} {r['article']}"


def legal_basis() -> list[str]:
    """`oversize.policy.legal_basis` 用：开关的立法支点（中越两侧各一条主线 + 罚款/许可依据）。"""
    return [
        citation("vn.d10k1"),
        citation("vn.d10k2"),
        citation("vn.d12k2d"),
        citation("vn.d8k2d"),
        citation("vn.d22k3a"),
        citation("cn.oversize_rule"),
        citation("cn.overload_law"),
    ]


def rewrite_legacy(text: str) -> str:
    """把历史文本里的旧条号（TT46/2015 …）映射成现行条号串（内部注释/迁移用）。

    只做**已知映射**（`MIGRATION_FROM_TT46`）的替换；未命中不改 —— 宁可留着让人看见，
    也不许猜一个条号糊上去。
    """
    out = text
    for old, new_key in MIGRATION_FROM_TT46.items():
        out = out.replace(old, citation(new_key))
    return out
