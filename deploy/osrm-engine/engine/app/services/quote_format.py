"""报价单金额工具（v010 抽出共用）。

从 `quote_docx_builder` 原样抽出，供 `quote_docx_builder`（旧版式）与 `quote_template`（v010 双语版式）
共用 —— 避免 `quote_template` 反向 import `quote_docx_builder` 造成循环导入。
两个函数的实现与行为**未做任何改动**，既有测试（`tests/test_quote_export.py` 里的 `_fmt_vnd` /
`_vnd_uppercase` 断言）继续有效。
"""


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
