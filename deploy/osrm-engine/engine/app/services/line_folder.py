"""v015.8 形态折算器 —— 大件「分瓣 / 分段 + 摆放择优」一层（纯函数、无 IO）。

为什么要这一层：v015.7 只会拿「用户输入的整件」去比对车型载货空间，用户那批 9 类里有三类
（座环 4.98m / 底环 5.5m / 定子机座 7.8m）宽度直接判死；而工程上环/盘类静止件本来就是
「分瓣运输、现场组焊」（水轮机安装规范原文，专家 §1.1 / 附录 A-7）。本模块把**一行货**折算成
**若干单件**，每件再交给 `fleet_planner` 跑既有的 `_dim_verdict` / `车辆数分解`。

铁律（与设计稿 §2① 一致）：
  ① **不碰** `费用计算公式.车辆数分解()`（INV-2 计价同源）：本层只算「尺寸/重量/件数」，不算钱。
  ② 公式以《运输专家意见-v015.8》§1.2 为准（本模块的回归用例逐条锁死该表的实测值）：
       W_piece = W_total / n × κ（环向分瓣 κ=1.05；纵向分段 κ=1.03）
       L' = D·sin(π/n)      W' = R − r_i·cos(π/n)      H' = h
       校验：0 ≤ d_i < D（内径须小于外径）—— 不成立时 W' 会算出负/零宽 ⇒ 点名拒绝，不折算
       守恒：W_piece×n ∈ [W_total, 1.15×W_total]
       单调：**每向 ≤ 原件最大边**（h≤D 时即「单件三向 ≤ 原件三向」；h>D 时卧放把轴向 h 落在车长向，
             是「轴向沿车长」的摆放语义，不是越折越大 —— 见「输入口径」与 side 摆放注释）
  ③ 确定性：同输入同输出（斜置搜索走固定角度网格，不用随机 ⇒ 可复算、可审计）。
  ④ 判定树（专家 §1.1）：压力容器/转动体/精密件 ⇒ **原则整体**（分瓣=改设计）；
     环/盘类 ⇒ 按尺寸分瓣；长杆类 ⇒ 纵向分段（但分段=改设计，需制造厂书面确认 ⇒ 不自动）。

摆放三选（专家 §1.2b，本模块与其实测表逐条对齐）：
  · 平放 flat ：碟平躺 —— 沿长 = 弦长 L'，跨宽 = 径向包络 W'，高 = 轴向 h
  · 卧放 side ：轴横放 —— 轴向 H' 沿车长，弦长 L' 跨车宽，径向包络 W' 为高
      （定子机座 h=6.1m 立不起来，只能卧放；专家表里「6.10×3.90×1.39」= 沿长×跨宽×高）
  · 斜置 oblique：在瓣本体平面内旋 φ 求 min(最大边)（对**环形扇区**取真实包围盒，不是矩形近似 ——
      定子机座分 4 瓣旋 45° 得 3.9×3.9，总高 3.9+0.9 = 4.8m，与专家「❌」结论同源）
  择优：先在两向达标者里挑「宽 ≤ 2.5（免超宽）」的，再比总高；斜置只在前两者都不达标时启用
  （斜置要专门工装与绑扎，工程上是最后手段 —— 这也是专家表里底环/顶盖=平放、定子机座=卧放的原因）。

输入口径（「已分瓣件」护栏，M1 审核 P2-5）：
  本层只认两种几何输入 —— ①整件平放 L≈W≈D；②半瓣件 L=D、W≈R=D/2。
  已是分瓣件（split_n>1）但口径不符者（如把「卧放单件」6.10×5.52×1.85 直接录入 —— 轴向被录进长向）：
  auto **不自动降階重算**（否则会把轴向当成外径 ⇒ 低估件重、少报车数），点名要求改输整件口径；
  显式 shape=nK 保持数据透传 / 按已有几何处理（口径由显式调用方担责）。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.services import legal_refs as legal   # 🆕 v016：法规条号唯一真源（不再自写条号）

# ── 策略常量（可调、可审计；与 fleet_planner.DIM_POLICY 同族）────────────────
SPLIT_POLICY: dict = {
    "kappa": 1.05,                 # 环向分瓣附加率（把合法兰/工艺余量/加强件）——专家 §1.2a 0.03~0.08 取 0.05
    "kappa_segment": 1.03,         # 纵向分段附加率（现场接头材料）——专家 §1.2a 0.02~0.05 取 0.03
    "n_candidates": (2, 4, 6, 8),  # 形态搜索的瓣数阶梯（专家 §1.3 SPLIT_POLICY.default_n_by_shape.ring）
    "placement_order": ("flat", "side", "oblique"),   # 平放 → 卧放 → 斜置
    "width_plain_m": 2.5,          # ≤2.5m 免超宽（择优第一优先，专家 §1.2b）
    "width_haul_m": 4.5,           # 大件可运上限（与 fleet_planner.DIM_POLICY["width_haul_m"] 同值）
    "total_height_max_m": 4.5,     # 总高上限（货高 + 台面）——专家 §1.2b 校核口径
    "deck_height_m": 0.9,          # 台面高（专家 §1.2b：「3.9×3.9，则总高 4.8」= 3.9 + 0.9 的口径）
    "oblique_step_deg": 0.5,       # 斜置搜索步长（固定网格 ⇒ 确定性）
    "suggest_n_max": 32,           # 「最小可行 n」建议的几何搜索上限（建议不等于实际折算）
}

_PLACEMENT_CN = {"flat": "平放", "side": "卧放", "oblique": "斜置", "given": "按给定", "segment": "纵向分段"}

# 判定树关键词（专家 §1.1 的三类；**按序匹配**：integral 最优先，避免「主轴」被长杆类抢走）
_INTEGRAL_KEYWORDS = ("转轮", "主轴", "转轴", "转子", "球阀", "阀", "压力容器", "泵", "主变", "精密", "轴承")
_BEAM_KEYWORDS = ("大梁", "梁", "桁架", "长轴", "杆", "臂", "柱", "轨")
_RING_KEYWORDS = ("顶盖", "座环", "底环", "机座", "环", "盖", "盘", "肘管", "里衬", "法兰", "筒", "罩")

_FORM_RE = re.compile(r"分\s*(\d+)\s*(?:瓣|段)")

_INTEGRAL_HINT = "结构原则整体（转动体/压力容器/精密件）：分瓣=改设计，不接受折算（专家 §1.1①）"
_NO_GEOM_HINT = ("缺内径：环/盘件分瓣要按 L'=D·sin(π/n)、W'=R−r_i·cos(π/n) 算弦长与径向包络，"
                 "需要 D/d_i/h 或厂家分瓣图 ⇒ 无法折算瓣数（不猜）")
_BEAM_HINT = ("长杆类纵向分段=改设计（箱形梁接头设计），需制造厂书面确认 ⇒ 暂不自动分段"
              "（可显式选「分2段」重算）")


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Placement:
    """一种摆放：给出沿长/跨宽/高与是否达标（宽 ≤4.5 且 总高 ≤4.5）。"""
    placement: str            # flat | side | oblique
    L_m: float
    W_m: float
    H_m: float
    width_m: float            # 跨车宽方向尺寸（= W_m）
    height_total_m: float     # 总高 = 货高 + 台面
    fits: bool
    note: str


@dataclass(frozen=True)
class FormCandidate:
    """一种形态折算结果（n=1 即「整体/现状」）。"""
    split_n: int
    form: str                 # 整体 / 分2瓣 / 分2段
    placement: str            # given | flat | side | oblique | segment
    L_m: float
    W_m: float
    H_m: float
    w_t: float                # 单件重量（含附加率 κ）
    count: int                # 折算后件数 = n × 原行件数（折算前口径）
    fits_policy: bool         # 两向达标（宽/总高）—— 终审仍在车型层（_dim_verdict）
    placements: tuple[Placement, ...]
    verdict_hint: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class FoldResult:
    name: str
    line_id: str
    shape_class: str          # integral | ring | beam | unknown
    requested: str            # auto | integral | nK（K≥2；前端给 2/4/6/8 档）
    candidates: tuple[FormCandidate, ...]   # 递增：整体 → 2 → 4 → 6 → 8
    feasible: bool            # 至少一个候选两向达标
    min_feasible_n: int | None
    whole_weight_t: float     # 折算前「整件」重量（半瓣件按 ×给定瓣数 归一）
    hint: str                 # 不能折算 / 全都不可行时的一句话（点名文案直接引用）


# ── 判定树 ──────────────────────────────────────────────────────────────────

def classify_shape(name: str) -> str:
    """按专家 §1.1 判定树给货行分类：integral（原则整体）/ ring（按尺寸分瓣）/ beam（纵向分段）。

    为什么用关键词表而不是尺寸启发式：分瓣与否是**结构属性**（制造厂能否分、现场能否组焊），
    与尺寸无关 —— 扎拉 500MW 转轮 Φ6.23m/90.8t 整体运输即反例（专家 §1.1）。判不准的返
    "unknown"：auto 下不自动折算（保守，不猜货名）—— **例外**：带内径的未知件按环件处理
    （只有环/盘类才填内径 ⇒ 内径即最强分类信号；见 _foldable 与 fold_line 的 auto 分支）；
    缺内径的未知件只接受显式请求。
    """
    text = str(name or "")
    for kw in _INTEGRAL_KEYWORDS:
        if kw in text:
            return "integral"
    for kw in _BEAM_KEYWORDS:
        if kw in text:
            return "beam"
    for kw in _RING_KEYWORDS:
        if kw in text:
            return "ring"
    return "unknown"


# ── 输入归一化 ──────────────────────────────────────────────────────────────

def _r2(x: float) -> float:
    """统一到 0.01m（专家表精度；避免导出/对照表出现 3.8890872965260113 这种假精度）。"""
    return round(float(x), 2)


def _parse_given_n(line: dict) -> int:
    """给定形态的瓣数：显式 `split_n` 优先，其次 `form`（"分2瓣"/"分4瓣"）。

    为什么不从名字里认「1/2顶盖」：名字是自由文本，猜形态会静默改语义（不猜原则）——
    形态由调用方显式传入（T8 前端行内开关走这条参数）。
    """
    raw = line.get("split_n")
    if raw is not None and str(raw).strip() != "":
        try:
            n = int(float(raw))
            if n >= 1:
                return n
        except (TypeError, ValueError):
            pass
    m = _FORM_RE.search(str(line.get("form") or ""))
    return max(1, int(m.group(1))) if m else 1


def _num_or(dims: dict, key: str, alt) -> float:
    """取 `dims_m[key]`：键缺失 / 值为 None 或空串 ⇒ 回落 `alt`，再兜底 0.0。

    P2-3：`dims_m` 的键存在但值为 None 与「键缺失」同义（按缺失处理，不猜）——
    旧实现 `float(dims.get("L", ...))` 在直接调用路径上会 float(None) 抛 TypeError。
    """
    v = dims.get(key)
    if v is None or v == "":
        v = alt
    if v is None or v == "":
        return 0.0
    return float(v)


def _norm_line(line: dict) -> dict:
    """兼容两种拼写：设计契约 `dims_m{L,W,H}` + `w_total_t`；planner item `length_m/…/weight_kg`。

    `dims_m` 键存在但值为 None ⇒ 按缺失回落（P2-3）。另算出 `inner_d_invalid`（P2-2）：
    给了内径但不是 `0 ≤ d_i < D`（D = 平面外径口径 max(L,W)）⇒ 折算层点名拒绝（不折算）。
    """
    dims = line.get("dims_m") or {}
    L = _num_or(dims, "L", line.get("length_m"))
    W = _num_or(dims, "W", line.get("width_m"))
    H = _num_or(dims, "H", line.get("height_m"))
    w_raw = line.get("w_total_t")
    if w_raw not in (None, ""):
        w = float(w_raw)
    else:
        w = float(line.get("weight_kg") or 0.0) / 1000.0
    inner = line.get("inner_d_m")
    inner_v = float(inner) if inner not in (None, "") else None
    D_flat = max(L, W)
    return {
        "line_id": str(line.get("line_id") or ""),
        "name": str(line.get("name") or ""),
        "L": L, "W": W, "H": H,
        "w_piece_t": w,
        "count": max(1, int(line.get("count") or 1)),
        "n_given": _parse_given_n(line),
        "inner_d_m": inner_v,
        "inner_d_invalid": (inner_v is not None and not (0.0 <= inner_v < D_flat)),
        "shape_class": (str(line["shape_class"]).strip().lower() if line.get("shape_class") else None),
    }


def _norm_shape(shape) -> str:
    """形态串归一：auto | integral（整体 / n1）| nK（K≥2）。

    宽进口径（M1 审核 P2-7，文档=实现）：前端只提供 2/4/6/8 四档，但内部**接受任意 n≥2**
    （不设上限 —— 前端日后改档位不用动本层）；非法串点名报错，不静默按 auto 跑。
    """
    s = str(shape or "auto").strip().lower()
    if s in ("", "auto"):
        return "auto"
    if s in ("integral", "整体"):
        return "integral"
    m = re.fullmatch(r"n(\d+)", s) or _FORM_RE.fullmatch(str(shape or "").strip())
    if m:
        n = int(m.group(1))
        if n == 1:
            return "integral"          # 「n1」等同于不变形态（前端开关的稳妥写法）
        if n >= 2:
            return f"n{n}"
    raise ValueError(
        f"未知形态 shape={shape!r}（合法：auto | integral | n1 | nK（K≥2：前端提供 2/4/6/8 四档，"
        f"内部宽进接受 n≥2）| 「分N瓣」/「分N段」中文标签）")


def _foldable(L: dict, cls: str) -> bool:
    """能不能算折算：整体类不能；环/盘/未知件要有内径（有内径 ⇒ 必是环/盘类，按环件处理）；
    长杆类纵向分段不需要内径。"""
    if cls == "integral":
        return False
    if L["inner_d_m"] is not None:
        return True
    return cls == "beam"


def _given_geometry_mismatch(L: dict, cls: str) -> bool:
    """已分瓣件（n_given>1）的输入口径校验（M1 审核 P2-5）：True ⇒ 不自动降階、点名要求改输口径。

    本层只认两种几何输入（见模块 docstring「输入口径」）：
      ① 整件平放 L≈W（=外径 D）；
      ② 切片/半瓣件 L=外径 D、径向包络 W ≤ R=D/2（n=2 时 W≈R）。
    反例：定子机座 4 瓣按卧放单件录入 6.10×5.52×1.85 —— 轴向 6.10 在长向、径向包络 5.52 在宽向，
    两个口径都不满足；若照旧按 max(L,W) 取外径会「把轴向当外径」降階重算（误得 2 瓣 6.10×3.05×1.85）。
    长杆类（beam）走纵向分段口径，不适用本校验。
    """
    if cls == "beam" or L["n_given"] <= 1:
        return False
    l, w = L["L"], L["W"]
    if l <= 0.0:
        return False                       # 无平面尺寸：谈不上口径（交给缺数据/阶梯分支的现状处理）
    if abs(l - w) <= max(0.05 * l, 0.15):                    # 整件平放框：L≈W≈D
        return False
    if 0.0 < w <= l / 2.0 + max(0.05 * (l / 2.0), 0.15):     # 半瓣/切片：W=径向包络 ≤ R
        return False
    return True


# ── 几何：瓣本体与三种摆放 ──────────────────────────────────────────────────

def ring_piece_dims(*, D: float, d_i: float, h: float, n: int) -> tuple[float, float, float]:
    """专家 §1.2b：等分 n 瓣的环/盘件「瓣本体」外包络 (弦长 L', 径向包络 W', 轴向高 H')。

        L' = D·sin(π/n)（n=2 时 = D）      W' = R − r_i·cos(π/n)（n=2 时 = R）      H' = h
    n=1（整件）返回 (D, D, h)：整环的外包络就是外径方框。

    校验（M1 审核 P2-2）：`0 ≤ d_i < D` —— 内径 ≥ 外径时 W' 会算成负/零宽
    （例：D5.5/d6.0/n8 ⇒ W' = 2.75 − 3.0·cos22.5° = −0.02），直接调用必须点名报错；
    折算层在 `fold_line` 先拦（见 `inner_d_invalid`），保证负数尺寸不流入下游。
    """
    if not (0.0 <= d_i < D):
        raise ValueError(
            f"内径须小于外径且不为负（0 ≤ d_i < D）：D={D:g}、d_i={d_i:g} —— 请核对环/盘件内外径输入")
    if n <= 1:
        return (_r2(D), _r2(D), _r2(h))
    Lp = D * math.sin(math.pi / n)
    Rp, ri = D / 2.0, d_i / 2.0
    Wp = Rp - ri * math.cos(math.pi / n)
    return (_r2(Lp), _r2(Wp), _r2(h))


def _sector_bbox(*, D: float, d_i: float, n: int, phi_rad: float) -> tuple[float, float]:
    """环形扇区（等分 n 瓣、外径 D、内径 d_i）在平面内旋 φ 后的**真实**包围盒 (bx, by)。

    为什么按扇区几何而不是「把 L'×W' 矩形旋转」：专家 §1.2b 的「旋 45° 得 3.9×3.9」正是扇区
    的真实包围盒（定子机座分 4 瓣，90° 扇区旋 45° ⇒ 包围盒 = R×R = 3.9×3.9）。矩形近似会得到
    5.21×5.21，与专家结论对不上。
    """
    R, r = D / 2.0, d_i / 2.0
    a0, a1 = phi_rad - math.pi / n, phi_rad + math.pi / n
    xs, ys = [], []
    for ang, rad in ((a0, R), (a1, R), (a0, r), (a1, r)):
        xs.append(rad * math.cos(ang))
        ys.append(rad * math.sin(ang))
    for ang in (0.0, math.pi / 2, -math.pi / 2, math.pi):   # 极值点（若落在扇区角域内）
        if a0 - 1e-12 <= ang <= a1 + 1e-12:
            xs.append(R * math.cos(ang))
            ys.append(R * math.sin(ang))
    return (max(xs) - min(xs), max(ys) - min(ys))


def _oblique_dims(*, D: float, d_i: float, n: int) -> tuple[float, float]:
    """斜置：平面内旋 φ 求 min(最大边)，返回 (跨宽, 高) = (大边, 小边)。

    固定步长网格（SPLIT_POLICY["oblique_step_deg"]）⇒ 确定性；tie 用角度序打破 ⇒ 同输入同输出。
    """
    step = float(SPLIT_POLICY["oblique_step_deg"])
    steps = max(2, int(round(90.0 / step)))
    best = None
    for i in range(steps + 1):
        phi_deg = i * step
        bx, by = _sector_bbox(D=D, d_i=d_i, n=n, phi_rad=math.radians(phi_deg))
        big, small = max(bx, by), min(bx, by)
        key = (round(big, 6), round(small, 6), phi_deg)
        if best is None or key < best[0]:
            best = (key, big, small)
    return (_r2(best[1]), _r2(best[2]))


def _mk_placement(placement: str, Lm: float, Wm: float, Hm: float) -> Placement:
    deck = float(SPLIT_POLICY["deck_height_m"])
    width, height = _r2(Wm), _r2(Hm)
    total_h = _r2(height + deck)
    fits = (width <= SPLIT_POLICY["width_haul_m"] + 1e-9
            and total_h <= SPLIT_POLICY["total_height_max_m"] + 1e-9)
    why = "达标" if fits else (
        f"宽 {width:.2f}m > {SPLIT_POLICY['width_haul_m']:g}m" if width > SPLIT_POLICY["width_haul_m"] + 1e-9
        else f"总高 {total_h:.2f}m > {SPLIT_POLICY['total_height_max_m']:g}m")
    return Placement(placement=placement, L_m=_r2(Lm), W_m=width, H_m=height,
                     width_m=width, height_total_m=total_h, fits=fits,
                     note=f"{_PLACEMENT_CN[placement]}：宽 {width:.2f}m、总高 {total_h:.2f}m（{why}）")


def _place_candidates(*, D: float, d_i: float, h: float, n: int) -> list[Placement]:
    """专家 §1.2b 摆放三选：平放 / 卧放 / 斜置（全部评估，供择优与可解释）。"""
    Lp, Wp, Hp = ring_piece_dims(D=D, d_i=d_i, h=h, n=n)
    bw, bh = _oblique_dims(D=D, d_i=d_i, n=n)
    return [
        _mk_placement("flat", Lp, Wp, Hp),    # 碟平躺：宽 = 径向包络 W'，高 = 轴向 h
        _mk_placement("side", Hp, Lp, Wp),    # 轴横放：轴向 H' 沿车长，弦长 L' 跨宽，径向包络 W' 为高
        _mk_placement("oblique", Hp, bw, bh),  # 斜置：轴向沿车长，旋转后包围盒大边跨宽、小边作高
    ]


def _choose_placement(placements: list[Placement]) -> Placement | None:
    """择优：先满足「宽 ≤ 2.5（免超宽）」，再比总高；斜置仅当前两者都不达标时启用。

    为什么斜置是最后手段：斜置要专门工装与绑扎，工程上不首选 —— 这条口径与专家 §1.2b 实测表
    逐条一致（底环/顶盖 = 平放；定子机座 6/8 瓣 = 卧放；4 瓣连斜置都过不去）。
    """
    pool = [p for p in placements if p.placement in ("flat", "side") and p.fits]
    if pool:
        tier = [p for p in pool if p.width_m <= SPLIT_POLICY["width_plain_m"] + 1e-9] or pool
        return min(tier, key=lambda p: (p.height_total_m, p.width_m,
                                        SPLIT_POLICY["placement_order"].index(p.placement)))
    return next((p for p in placements if p.placement == "oblique" and p.fits), None)


def _verdict_hint(Lm: float, Wm: float, Hm: float) -> tuple[str, ...]:
    """专家 §1.3 piece 契约：逐向点出许可档（前端零改动也能显示）。"""
    out: list[str] = []
    deck = float(SPLIT_POLICY["deck_height_m"])
    if Wm > 2.5 + 1e-9:
        out.append(f"宽{Wm:.2f}>2.5 超宽（需许可）")
    if Wm > 3.5 + 1e-9:
        # 🆕 v016：条号改引唯一真源（旧条号已由 TT39/2024 → TT12/2025/TT-BXD 取代；
        #   失效说明与迁移表见 legal_refs.py，任何模块都不许再自写旧条号）
        out.append(f"宽{Wm:.2f}>3.5 需护送（越 {legal.VN_CURRENT_CODE} 许可条件）")
    if Wm > 3.75 + 1e-9:
        out.append(f"宽{Wm:.2f}>3.75 需勘路")
    if Hm + deck > 4.2 + 1e-9:
        out.append(f"总高{Hm + deck:.2f}m>4.2 需许可/勘路")
    if Lm > 20.0 + 1e-9:
        out.append(f"长{Lm:.2f}m>20 需许可（越）/ 组合长需联动")
    return tuple(out)


# ── 候选形态 ────────────────────────────────────────────────────────────────

def _given_candidate(L: dict) -> FormCandidate:
    """现状形态（用户输什么进什么）：不折算、不重算，只做达标提示。"""
    n_g = L["n_given"]
    fits = (L["W"] <= SPLIT_POLICY["width_haul_m"] + 1e-9
            and L["H"] + SPLIT_POLICY["deck_height_m"] <= SPLIT_POLICY["total_height_max_m"] + 1e-9)
    return FormCandidate(
        split_n=n_g, form=("整体" if n_g <= 1 else f"分{n_g}瓣"), placement="given",
        L_m=_r2(L["L"]), W_m=_r2(L["W"]), H_m=_r2(L["H"]),
        w_t=L["w_piece_t"], count=L["count"], fits_policy=fits, placements=(),
        verdict_hint=_verdict_hint(_r2(L["L"]), _r2(L["W"]), _r2(L["H"])),
        note="用户给定形态：原样进车型层（本层不改尺寸/重量/件数）",
    )


def _fold_ring_candidate(L: dict, n: int) -> FormCandidate:
    """环/盘件折算：n == 给定瓣数时透传（用户数据最权威），否则套 §1.2b 公式。"""
    D = max(L["L"], L["W"])      # 平面外径：整件平放 L=W=D；半瓣件 L=D、W≈R
    d_i, h = L["inner_d_m"], L["H"]
    placements = _place_candidates(D=D, d_i=d_i, h=h, n=n)
    chosen = _choose_placement(placements)
    deck = float(SPLIT_POLICY["deck_height_m"])
    if n == L["n_given"]:
        Lm, Wm, Hm = _r2(L["L"]), _r2(L["W"]), _r2(L["H"])
        w_t, placement = L["w_piece_t"], "given"
        fits = (Wm <= SPLIT_POLICY["width_haul_m"] + 1e-9 and Hm + deck <= SPLIT_POLICY["total_height_max_m"] + 1e-9)
    else:
        w_t = L["w_piece_t"] * L["n_given"] / n * float(SPLIT_POLICY["kappa"])
        if chosen is not None:
            Lm, Wm, Hm, placement, fits = chosen.L_m, chosen.W_m, chosen.H_m, chosen.placement, True
        else:
            # 三选一都不达标：对外仍给「卧放」包络（环件唯一现实摆法），与专家 §1.2b 表同口径
            side = next(p for p in placements if p.placement == "side")
            Lm, Wm, Hm, placement, fits = side.L_m, side.W_m, side.H_m, "side", False
    return FormCandidate(
        split_n=n, form=f"分{n}瓣", placement=placement,
        L_m=_r2(Lm), W_m=_r2(Wm), H_m=_r2(Hm), w_t=w_t,
        count=L["count"] * n // L["n_given"], fits_policy=fits,
        placements=tuple(placements), verdict_hint=_verdict_hint(_r2(Lm), _r2(Wm), _r2(Hm)),
        note=("给定瓣数：数据透传" if placement == "given" else
              f"按 W_total/n×κ 折算（κ={SPLIT_POLICY['kappa']}）；摆放择优 = {_PLACEMENT_CN[placement]}"),
    )


def _fold_beam_candidate(L: dict, n: int) -> FormCandidate:
    """长杆类纵向分段：只切长度（挠度/预拱度由现场接头控制），κ 取纵向分段口径 1.03。"""
    deck = float(SPLIT_POLICY["deck_height_m"])
    Lm, Wm, Hm = _r2(L["L"] / n), _r2(L["W"]), _r2(L["H"])
    fits = (Wm <= SPLIT_POLICY["width_haul_m"] + 1e-9 and Hm + deck <= SPLIT_POLICY["total_height_max_m"] + 1e-9)
    return FormCandidate(
        split_n=n, form=f"分{n}段", placement="segment",
        L_m=Lm, W_m=Wm, H_m=Hm,
        w_t=L["w_piece_t"] * L["n_given"] / n * float(SPLIT_POLICY["kappa_segment"]),
        count=L["count"] * n // L["n_given"], fits_policy=fits, placements=(),
        verdict_hint=_verdict_hint(Lm, Wm, Hm),
        note=f"纵向分段（κ={SPLIT_POLICY['kappa_segment']}，现场接头材料）：需制造厂确认分段方案",
    )


def _fold_candidate(L: dict, cls: str, n: int) -> FormCandidate:
    return _fold_beam_candidate(L, n) if cls == "beam" else _fold_ring_candidate(L, n)


def _min_feasible_n(*, D: float, d_i: float, h: float) -> int | None:
    """「最小可行 n」建议：在偶数阶梯上做几何外推（只看宽/总高，不给车型下结论）。

    为什么只搜偶数：分瓣面/把合法兰要对称布置，工程上都是 2/4/6/8… 等分。
    """
    n_max = int(SPLIT_POLICY["suggest_n_max"])
    for n in range(2, n_max + 1, 2):
        if _choose_placement(_place_candidates(D=D, d_i=d_i, h=h, n=n)) is not None:
            return n
    return None


def _block_note(cands: list[FormCandidate]) -> str:
    """把「卡在哪一向」说清楚（供点名文案引用）：平放总高 7.00m>4.5m、卧放宽 5.52m>4.5m …"""
    wmax = float(SPLIT_POLICY["width_haul_m"])
    hmax = float(SPLIT_POLICY["total_height_max_m"])
    parts: list[str] = []
    for c in cands:
        if c.placements:
            for p in c.placements:
                if p.fits:
                    continue
                if p.width_m > wmax + 1e-9:
                    parts.append(f"{_PLACEMENT_CN[p.placement]}宽{p.width_m:.2f}m>{wmax:g}m")
                else:
                    parts.append(f"{_PLACEMENT_CN[p.placement]}总高{p.height_total_m:.2f}m>{hmax:g}m")
        elif c.W_m > wmax + 1e-9:
            parts.append(f"宽{c.W_m:.2f}m>{wmax:g}m")
        elif c.H_m + SPLIT_POLICY["deck_height_m"] > hmax + 1e-9:
            parts.append(f"总高{c.H_m + SPLIT_POLICY['deck_height_m']:.2f}m>{hmax:g}m")
    seen, uniq = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return "、".join(uniq) or "形态不可行"


def _failure_hint(*, L: dict, cls: str, requested: str, cands: list[FormCandidate],
                  min_n: int | None) -> str:
    """形态层失败时的「一句话出路」（点名文案/前端出路按钮直接引用）。"""
    if cls == "integral":
        return _INTEGRAL_HINT
    blocked = _block_note(cands)
    if min_n is not None:
        tail = f" ⇒ 最小可行 {min_n} 瓣 或特批/专询"
    else:
        tail = " ⇒ 该件任何分瓣数都过不了宽/总高，需特批/专项评估、改设计或水运"
    if requested == "integral":
        return f"整体形态不可行（{blocked}）{tail}"
    if requested.startswith("n"):
        return f"所请求形态（分{requested[1:]}瓣）不可行（{blocked}）{tail}"
    return f"形态搜索：整体/2/4/6/8 瓣均不可行（{blocked}）{tail}"


def _inner_d_invalid_hint(L: dict) -> str:
    """内径校验失败的点名文案（P2-2）：拒绝折算（不算负数尺寸），说清校验口径。"""
    d_i, D = L["inner_d_m"], max(L["L"], L["W"])
    head = (f"内径数据有误（内径 {d_i:.2f}m 为负）" if d_i < 0.0
            else f"内径数据有误（内径 {d_i:.2f}m ≥ 外径 {D:.2f}m）")
    return (f"{head}：内径须小于外径（0 ≤ d_i < D）—— 否则径向包络 W'=R−r_i·cos(π/n) 会算出负/零宽，"
            f"下游会静默当成“达标”。⇒ 拒绝折算（不猜）：请核对环/盘件内外径后重新输入。")


def _split_input_hint(L: dict) -> str:
    """已分瓣件「输入口径不符」的点名文案（P2-5）：不自动降階重算，给输入口径说明。"""
    return (f"该件已按 {L['n_given']} 瓣录入（{L['L']:.2f}×{L['W']:.2f}×{L['H']:.2f}），"
            f"但尺寸口径与本层输入约定不符：本层只认「整件平放 L≈W≈D」或「半瓣件 L=D、W≈R=D/2」两种口径 —— "
            f"当前 L={L['L']:.2f}m、W={L['W']:.2f}m 更像是「卧放的单瓣件」（轴向尺寸可能被录进了长向）。"
            f"⇒ 不自动降階重算（避免把轴向当成外径）：请改输整件外径/内径/轴向高，"
            f"或显式指定 shape=nK 按已有几何处理。")


# ── 主入口 ──────────────────────────────────────────────────────────────────

def fold_line(line: dict, *, shape: str = "auto") -> FoldResult:
    """一行货 → 若干候选形态（递增 n；第一条永远是「现状」）。

    shape：
      auto      —— 判定树允许且参数齐备时，试 整体 ⇒ 2 ⇒ 4 ⇒ 6 ⇒ 8 瓣（调用方取最小可行者）
      integral  —— 只要现状（后端不变形态；v015.7 行为的逃生口）
      nK（K≥2） —— 只要该瓣数（前端提供 2/4/6/8 四档；内部**宽进**接受任意 K≥2），
                   不可行就如实报，不偷偷回退
    """
    L = _norm_line(line)
    cls = L["shape_class"] or classify_shape(L["name"])
    requested = _norm_shape(shape)
    cands: list[FormCandidate] = [_given_candidate(L)]
    hint = ""
    foldable = _foldable(L, cls)
    bad_inner = bool(L["inner_d_invalid"])        # P2-2：内径须小于外径（0 ≤ d_i < D）
    mismatch = _given_geometry_mismatch(L, cls)    # P2-5：已分瓣件输入口径护栏（只拦 auto 的自动阶梯）

    if requested == "auto":
        if cls == "integral":
            hint = _INTEGRAL_HINT
        elif not foldable:
            hint = _NO_GEOM_HINT
        elif cls == "beam":
            hint = _BEAM_HINT
        elif bad_inner:
            hint = _inner_d_invalid_hint(L)
        elif mismatch:
            hint = _split_input_hint(L)
        else:
            cands += [_fold_ring_candidate(L, n) for n in SPLIT_POLICY["n_candidates"] if n != L["n_given"]]
    elif requested == "integral":
        if cls == "integral":
            hint = _INTEGRAL_HINT
        elif not foldable:
            hint = _NO_GEOM_HINT
    else:                                   # nK：只要这一种
        n = int(requested[1:])
        if cls == "integral":
            hint = _INTEGRAL_HINT
        elif not foldable:
            hint = _NO_GEOM_HINT
        elif bad_inner:
            # P2-2：显式请求也不算出负数尺寸 —— 点名拒绝（数据透传只适用于合法几何）
            hint = _inner_d_invalid_hint(L)
        else:
            # P2-5：显式路径 = 数据透传 / 按已有几何处理（不套自动阶梯护栏；口径由显式调用方担责）
            cands = [_fold_candidate(L, cls, n)]

    min_n = None
    if foldable and cls == "ring" and L["inner_d_m"] is not None and not bad_inner and not mismatch:
        min_n = _min_feasible_n(D=max(L["L"], L["W"]), d_i=L["inner_d_m"], h=L["H"])

    feasible = any(c.fits_policy for c in cands)
    if not hint and not feasible:
        hint = _failure_hint(L=L, cls=cls, requested=requested, cands=cands, min_n=min_n)

    return FoldResult(
        name=L["name"], line_id=L["line_id"], shape_class=cls, requested=requested,
        candidates=tuple(cands), feasible=feasible, min_feasible_n=min_n,
        whole_weight_t=L["w_piece_t"] * L["n_given"], hint=hint,
    )
