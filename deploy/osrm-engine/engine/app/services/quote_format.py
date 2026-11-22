"""报价单金额工具（v010 抽出共用）。

从 `quote_docx_builder` 原样抽出，供 `quote_docx_builder`（旧版式）与 `quote_template`（v010 双语版式）
共用 —— 避免 `quote_template` 反向 import `quote_docx_builder` 造成循环导入。
两个函数的实现与行为**未做任何改动**，既有测试（`tests/test_quote_export.py` 里的 `_fmt_vnd` /
`_vnd_uppercase` 断言）继续有效。
"""


# ── 🆕 v023（② 口岸费「两端开关」）：scope 四值 = 唯一派生出口 ──────────────
# 命名与两端业务的对应：china_side（中国端）= 出口端 ⇒ export_only；
#                        vietnam_side（越南端）= 进口端 ⇒ import_only。
SCOPE_NONE = "none"
SCOPE_EXPORT_ONLY = "export_only"
SCOPE_IMPORT_ONLY = "import_only"
SCOPE_BOTH = "both"
SCOPE_VALUES = (SCOPE_NONE, SCOPE_EXPORT_ONLY, SCOPE_IMPORT_ONLY, SCOPE_BOTH)


# ── 🆕 v024 T3：普货口径（`estimate_mode="general_cargo"`）文案的**唯一定义处** ──────────
#   谁需要：① `/route/cost` 响应自证（`api/route.py::_estimate_meta`）
#           ② 报价单渲染器（`quote_docx_builder` 在 payload 漏传时兜底印同一句）
#   ⇒ 页面与单据必须**共用一个字符串**，两边各拼一套必然漂移（本项目 v023 先例：响应侧与
#     导出侧各自手写同一条口岸费规则，只修一边 ⇒ 另一边照旧判三行）。
#
#   ⚠️ 措辞不许写成「满载计价」这类会让人以为是称重算的说法 —— 会与本句「未按货物重量计费」自相矛盾。
ESTIMATE_BASIS_GENERAL_CARGO = "按「车型全包公里费率 × 里程 × N 车」估算，未按货物重量计费"
#   吊装费按**整票吨位**算、且不在 VEHICLE_SCALING_ITEMS 里 ⇒ 普货票（不填货物信息）**计不了**吊装费。
#   这是「缺项」，必须写明，不许静默少一项让人以为已经含在内。
HEAVY_LIFT_SKIPPED_NOTE = "未提供货物重量 ⇒ 吊装费未计"


def estimate_basis_of(estimate_mode: str | None) -> str | None:
    """普货口径句：`general_cargo` ⇒ 冻结文案；其余（含缺省 `normal`）⇒ None（老响应逐字节不变）。"""
    return ESTIMATE_BASIS_GENERAL_CARGO if estimate_mode == "general_cargo" else None


#   🆕 v024 T3（@aiosrm 裁定）：越文口径句 —— 这份 docx 通篇中越双语（条款走 `_bi`、大写金额走越文、
#   账户双语），只有这一句决定客户「知道自己是按车型公里费率估的、没含吊装费」。
#   越南客户读不到这句 ⇒ 单据是残的；`oversize_note` 单语不算先例（那是手工录入的内部说明，
#   不是定价依据）。
#   ⚠️ 契约字段 `estimate_basis`（响应 + 导出请求）**不动**，仍是那条中文冻结串（门禁逐字断言、
#   老响应逐字节不变）；越文只在**渲染器侧**取，仍是**唯一定义处**（不新造第二定义）。
ESTIMATE_BASIS_GENERAL_CARGO_VI = (
    "Tính theo「đơn giá trọn gói theo km của loại xe × số km × số xe」, "
    "không tính theo trọng lượng hàng hóa"
)
HEAVY_LIFT_SKIPPED_NOTE_VI = "Chưa có trọng lượng hàng hóa ⇒ chưa tính phí cẩu (nâng hạ)"


def estimate_basis_vi_of(estimate_mode: str | None) -> str | None:
    """普货口径句的**越文**（渲染器专用）：`general_cargo` ⇒ 冻结越文；其余 ⇒ None。"""
    return ESTIMATE_BASIS_GENERAL_CARGO_VI if estimate_mode == "general_cargo" else None


def estimate_notes_vi_of(notes) -> list[str]:
    """已知缺项中文说明 ⇒ 越文对照；**认不出的原样不译**（不许把中文当越文印出去）。"""
    table = {HEAVY_LIFT_SKIPPED_NOTE: HEAVY_LIFT_SKIPPED_NOTE_VI}
    out = []
    for n in (notes or []):
        txt = str(n).strip()
        if txt in table:
            out.append(table[txt])
    return out


def _side_on(side) -> bool:
    """单端是否**计入**：该端明细非零、或该端小计非零 ⇒ 计入（空 / 全 0 ⇒ 不计入）。

    为什么不判「side 是否非 None」（审核师 2026-09-30 的 fail-open 教训同族）：
      ② 之后「被关一端 = None」，但**旧 payload / 手工覆盖 / 老单据重导** 会出现
      「对象在、两端明细全空」的形态 —— 若只判 `is not None` 就会判成 `both`，
      于是「只报一端」静默漂移成两端，导出的 docx 照样印口岸费行（旧版式还带 `0 VND`）。
      按「两端各自是否非零」派生，这类 payload 判 `none`，**不 fail-open**。
    """
    if side is None:
        return False
    items = getattr(side, "items", None) or {}
    try:
        if any(float(v or 0) for v in items.values()):
            return True
    except (TypeError, ValueError):
        return True                       # 明细形态异常 ⇒ 宁可当作有值（不静默吞掉客户的费用）
    for attr in ("subtotal_rmb", "subtotal", "total_rmb", "total_vnd"):
        if getattr(side, attr, None):
            return True
    return False


def border_fee_scope_of(border_fees) -> str:
    """🆕 v023：口岸费分支的**唯一派生出口**（响应体 / 报价单导出 / 两个渲染器共用）。

    返回 `"none" | "export_only" | "import_only" | "both"`：
      - `china_side`（中国端）非零 ⇒ 出口端口岸费计入；`vietnam_side`（越南端）非零 ⇒ 进口端计入；
      - 两端都不非零 / `border_fees` 为空 ⇒ `"none"`。

    ⚠️ 禁 `border_fees is not None ⇒ "both"` 的 fail-open：那是 v022 的旧口径，
      ② 之后「仅一端」会被静默判成两端。本函数是唯一实现 —— `route.build_quote_response()`
      与两份渲染器都**只许调它**，不许各写一遍同一条规则（本项目复发病 = 同口径多处各自算）。
    """
    if border_fees is None:
        return SCOPE_NONE
    china = _side_on(getattr(border_fees, "china_side", None))
    vietnam = _side_on(getattr(border_fees, "vietnam_side", None))
    if china and vietnam:
        return SCOPE_BOTH
    if china:
        return SCOPE_EXPORT_ONLY
    if vietnam:
        return SCOPE_IMPORT_ONLY
    return SCOPE_NONE


def border_fee_scope(payload) -> str:
    """报价单 payload（`QuoteExportRequest`）的 scope —— 显式字段优先，其次按端派生。

    优先级：`border_fee_scope`（显式，前端已算好的真源）
          > `border_fees_included=False`（显式「不含」）
          > 按 `border_fees` 两端各自是否非零派生。
    """
    explicit = getattr(payload, "border_fee_scope", None)
    if explicit in SCOPE_VALUES:
        return explicit
    inc = getattr(payload, "border_fees_included", None)
    if inc is not None and not inc:
        return SCOPE_NONE
    return border_fee_scope_of(getattr(payload, "border_fees", None))


def border_fees_included_of(payload) -> bool:
    """兼容旧名：本报价是否**计入任一端**口岸费（= `border_fee_scope(payload) != "none"`）。

    🆕 v022 T4 引入，🆕 v023 起降级为 `border_fee_scope()` 的布尔投影 —— 保留是因为
      老消费方与导出请求体只认这个 bool；**分支一律改用 scope**（两端粒度 bool 表达不了）。

    为什么缺省不能 fail-open 成 True（2026-09-30 审核师复算出的真缺陷）：
      前端此刻的真实发法是只发 `border_fees: q.border_fees || null`（全仓 grep 无 `border_fees_included`），
      开关关掉时该值为 null ⇒ 旧的 `getattr(..., True)` 缺省会让导出的 docx **照样印口岸费行**
      （旧版式还带 `0 VND`）—— 正是 INV-C 明文禁止的两项。
    """
    return border_fee_scope(payload) != SCOPE_NONE


def _fmt_vnd(amount) -> str:
    """千分位：9413132 -> '9,413,132'。"""
    try:
        return f"{int(round(float(amount))):,}"
    except (TypeError, ValueError):
        return "0"


def _vnd_uppercase(amount) -> str:
    """金额数字转中文大写（单位：圆）。按四位分组，正确处理整万/整亿。"""
    units = ["", "拾", "佰", "仟"]
    big = ["", "万", "亿", "兆"]
    digits = "零壹贰叁肆伍陆柒捌玖"
    try:
        n = int(round(float(amount)))
    except (TypeError, ValueError):
        n = 0
    if n == 0:
        return "零圆整"
    s = str(n)
    # 从低位每 4 位一组 → 高到低
    groups, i = [], len(s)
    while i > 0:
        groups.append(s[max(0, i - 4):i])
        i -= 4
    groups.reverse()
    out = []
    for gi, grp in enumerate(groups):
        gnum = int(grp or "0")
        if gnum == 0:  # 全零组：仅当前面有值且后面还有非零组时补"零"
            if out and any(int(g) > 0 for g in groups[gi + 1:]):
                out.append("零")
            continue
        gtxt, z, glen = "", False, len(grp)
        for i2, ch in enumerate(grp):
            pos, d = glen - 1 - i2, int(ch)
            if d == 0:
                z = True
            else:
                if z and (gtxt or out):
                    gtxt += "零"
                gtxt += digits[d] + units[pos]
                z = False
        out.append(gtxt + big[len(groups) - 1 - gi])
    txt = "".join(out).replace("零零", "零").rstrip("零")
    return txt + "圆整"
