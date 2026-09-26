"""AIOSRM++ 正式 docx 报价单生成器。

版式：信头 → 标题 → 基本信息 → 一、运输项目概况 →
二、费用明细（（一）运输费用 / （二）进出口费用）→ 三、费用总计 →
四、报价说明 → 签署区。

客户版（role=customer）：运输费=售价（VND），进出口费折算 VND 展示（RMB 参考），
费用总计 = 运输费 + 进出口费 = 客户总报价。绝不出现成本/利润。
内部版（role=internal）在运输费后附成本/利润小结。
"""
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


# ── 金额工具：已抽到 quote_format.py（v010 起与 quote_template 共用）──────
# 此处 re-export，既有 `from app.services.quote_docx_builder import _fmt_vnd` 调用与测试不受影响。
from app.services.quote_format import _fmt_vnd, _vnd_uppercase  # noqa: E402,F401


def _set_font(run, size=10.5, bold=False, cn="宋体"):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), cn)


def _shade(cell, color="D9D9D9"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def _add_letterhead(doc, profile):
    name = profile.get("cn_name", "")
    vi = profile.get("vi_name", "")
    addr = profile.get("address_cn", "")
    phone = profile.get("phone", "")
    email = profile.get("email", "")
    tax = profile.get("tax_id", "")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(name)
    _set_font(r, size=18, bold=True, cn="黑体")
    if vi:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p2.add_run(vi), size=10, cn="宋体")
    line = []
    if addr:
        line.append(addr)
    if phone:
        line.append("电话：" + phone)
    if email:
        line.append("邮箱：" + email)
    if tax:
        line.append("MST：" + tax)
    if line:
        p3 = doc.add_paragraph()
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p3.add_run("　".join(line)), size=9, cn="宋体")
    p4 = doc.add_paragraph()
    pPr = p4._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_title(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p.add_run("运输服务报价单"), size=16, bold=True, cn="黑体")
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p2.add_run("BÁO GIÁ VẬN CHUYỂN"), size=12, bold=True, cn="宋体")


def _add_basic_info(doc, payload, quote_no):
    from datetime import datetime
    tab = doc.add_table(rows=4, cols=2)
    tab.style = "Table Grid"
    rows = [
        ("报价单号", quote_no),
        ("报价日期", datetime.now().strftime("%Y年%m月%d日")),
        ("有效期限", f"{payload.validity_days} 天"),
        ("致", payload.customer_name),
    ]
    for i, (k, v) in enumerate(rows):
        tab.rows[i].cells[0].text = k
        tab.rows[i].cells[1].text = v
        _set_font(tab.rows[i].cells[0].paragraphs[0].runs[0], 10.5, bold=True)
        if k == "致":
            for run in tab.rows[i].cells[1].paragraphs[0].runs:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def _add_route_overview(doc, payload, profile):
    doc.add_paragraph("一、运输项目概况")
    cargos = payload.cargo or []
    tab = doc.add_table(rows=1 + len(cargos), cols=5)
    tab.style = "Table Grid"
    headers = ["货物名称", "数量", "重量(吨)", "尺寸(cm)", "备注"]
    for j, h in enumerate(headers):
        tab.rows[0].cells[j].text = h
        _shade(tab.rows[0].cells[j])
        _set_font(tab.rows[0].cells[j].paragraphs[0].runs[0], 10.5, bold=True)
    for i, c in enumerate(cargos, start=1):
        cell = tab.rows[i].cells
        cell[0].text = c.name
        cell[1].text = f"{c.qty}"
        cell[2].text = f"{c.weight_ton:.1f}"
        dims = [str(int(v)) if v else "—" for v in (c.l_cm, c.w_cm, c.h_cm)]
        cell[3].text = "×".join(dims)
        cell[4].text = "单件"
    kv = doc.add_table(rows=4, cols=2)
    kv.style = "Table Grid"
    info = [
        ("运输方式", f"{payload.vehicle_model_name} × {payload.vehicle_count} 车"),
        ("运输路线", payload.route_name),
        ("运输距离", f"{payload.distance_km} km" if payload.distance_km else "—"),
        ("预计时效", f"{payload.duration_h} h" if payload.duration_h else "—"),
    ]
    for i, (k, v) in enumerate(info):
        kv.rows[i].cells[0].text = k
        kv.rows[i].cells[1].text = v
        _set_font(kv.rows[i].cells[0].paragraphs[0].runs[0], 10.5, bold=True)


def _fee_rows(payload):
    """按 role 生成运输费用行：返回 [(项目, 单位, 数量, 单价, 金额)]。"""
    manual = float(getattr(payload, "manual_oversize_fee_vnd", 0) or 0)
    if payload.role == "customer":
        total = payload.price_vnd
        # 🆕 大件/超限手工专线价 → 项目名直说，避免看起来像普通运输费
        name = "大件/超限运输专线价（手工录入）" if manual > 0 else "运输服务费（门到门）"
        return [(name, "趟", 1, total, total)]
    bd = payload.breakdown or {}
    rows = [
        ("距离成本", "趟", 1, bd.get("cost_distance", 0), bd.get("cost_distance", 0)),
        ("油耗成本", "趟", 1, bd.get("cost_fuel", 0), bd.get("cost_fuel", 0)),
        ("路桥费", "趟", 1, bd.get("cost_toll", 0), bd.get("cost_toll", 0)),
        ("装卸费", "趟", 1, bd.get("cost_loading", 0), bd.get("cost_loading", 0)),
    ]
    if manual > 0:
        rows.append(("大件/超限专线价（手工录入·实报实销）", "趟", 1, manual, manual))
    return [r for r in rows if r[4] or r[3]]


def _transport_subtotal(payload) -> float:
    """运输费小计（VND）。客户版=售价；内部版=成本合计。"""
    if payload.role == "customer":
        return payload.price_vnd or 0
    return payload.cost_total or 0


def _add_fee_detail(doc, payload, profile):
    """（一）运输费用。"""
    doc.add_paragraph("二、费用明细")
    doc.add_paragraph("（一）运输费用")
    rows = _fee_rows(payload)
    tab = doc.add_table(rows=1 + len(rows) + 1, cols=6)
    tab.style = "Table Grid"
    headers = ["序号", "项目", "单位", "数量", "单价(VND)", "金额(VND)"]
    for j, h in enumerate(headers):
        tab.rows[0].cells[j].text = h
        _shade(tab.rows[0].cells[j])
        _set_font(tab.rows[0].cells[j].paragraphs[0].runs[0], 10.5, bold=True)
    for i, (name, unit, qty, price, amount) in enumerate(rows, start=1):
        cells = tab.rows[i].cells
        cells[0].text = str(i)
        cells[1].text = name
        cells[2].text = unit
        cells[3].text = f"{qty:g}"
        cells[4].text = _fmt_vnd(price)
        cells[5].text = _fmt_vnd(amount)
        for j in (4, 5):
            cells[j].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    total = _transport_subtotal(payload)
    last = tab.rows[1 + len(rows)]
    last.cells[0].text = ""
    last.cells[1].text = "运输费小计"
    last.cells[2].text = ""
    last.cells[3].text = ""
    last.cells[4].text = ""
    last.cells[5].text = _fmt_vnd(total)
    last.cells[5].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_font(last.cells[1].paragraphs[0].runs[0], 10.5, bold=True)
    _set_font(last.cells[5].paragraphs[0].runs[0], 10.5, bold=True)
    if payload.role == "internal":
        p = doc.add_paragraph()
        _set_font(p.add_run("成本与利润小结"), 10.5, bold=True)
        summary = doc.add_table(rows=3, cols=2)
        summary.style = "Table Grid"
        srows = [
            ("成本合计", _fmt_vnd(payload.cost_total)),
            ("售价", _fmt_vnd(payload.price_vnd)),
            ("利润", _fmt_vnd(payload.profit_vnd)),
        ]
        for i, (k, v) in enumerate(srows):
            summary.rows[i].cells[0].text = k
            summary.rows[i].cells[1].text = v
            _set_font(summary.rows[i].cells[0].paragraphs[0].runs[0], 10.5, bold=True)


_BORDER_META = {
    "customs_declaration": "中国出口报关", "yard_fee": "货场费", "unloading": "堆场卸货",
    "transloading": "装车费", "customs_clearance": "越南报关费", "inspection": "检验费",
    "detention": "滞箱费", "heavy_lift": "吊装费", "port_charge": "港口费", "trucking_to_site": "到货场运输",
}


def _add_border_fees(doc, payload):
    """（二）进出口费用：中国段/越南段明细（自动或逐项覆盖后的值）。"""
    bf = getattr(payload, "border_fees", None)
    if not bf:
        return
    rate = bf.exchange_rate or 0

    china, viet = bf.china_side, bf.vietnam_side
    if not getattr(china, "items", None) and not getattr(viet, "items", None):
        return
    manual_tag = "（已手动调整）" if getattr(bf, "manual", False) else ""
    doc.add_paragraph(f"（二）进出口费用{manual_tag}")

    def _side_table(side, title):
        rows = [(_BORDER_META.get(k, k), v) for k, v in (side.items or {}).items() if v]
        if not rows:
            return
        doc.add_paragraph(title)
        tab = doc.add_table(rows=1 + len(rows) + 1, cols=3)
        tab.style = "Table Grid"
        for j, h in enumerate(("项目", "金额(VND)", "金额(RMB)")):
            tab.rows[0].cells[j].text = h
            _shade(tab.rows[0].cells[j])
            _set_font(tab.rows[0].cells[j].paragraphs[0].runs[0], 10.5, bold=True)
        for i, (n, v) in enumerate(rows, start=1):
            tab.rows[i].cells[0].text = n
            tab.rows[i].cells[1].text = _fmt_vnd(v * rate)
            tab.rows[i].cells[2].text = _fmt_vnd(v)
            tab.rows[i].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            tab.rows[i].cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        subtotal = getattr(side, "subtotal_rmb", 0) or 0
        last = tab.rows[1 + len(rows)]
        last.cells[0].text = f"{title}小计"
        last.cells[1].text = _fmt_vnd(subtotal * rate)
        last.cells[2].text = _fmt_vnd(subtotal)
        _set_font(last.cells[0].paragraphs[0].runs[0], 10.5, bold=True)
        last.cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        last.cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    _side_table(china, "中国段")
    _side_table(viet, "越南段")
    pp = doc.add_paragraph()
    _set_font(pp.add_run(
        f"进出口费小计：{_fmt_vnd(bf.total_vnd or 0)} VND（{_fmt_vnd(bf.total_rmb or 0)} RMB，"
        f"汇率 1 CNY = {rate} VND）"), 10.5, bold=True)


def _add_fee_total(doc, payload):
    """三、费用总计：运输费 + 进出口费 = 客户总报价（VND）。"""
    transport = _transport_subtotal(payload)
    bf = getattr(payload, "border_fees", None)
    border_vnd = (bf.total_vnd or 0) if bf else 0
    grand = round(transport + border_vnd)
    doc.add_paragraph("三、费用总计")
    tab = doc.add_table(rows=3, cols=2)
    tab.style = "Table Grid"
    rows = [
        ("运输费用", f"{_fmt_vnd(transport)} VND"),
        ("进出口费用", f"{_fmt_vnd(border_vnd)} VND"),
        ("客户总报价", f"{_fmt_vnd(grand)} VND"),
    ]
    for i, (k, v) in enumerate(rows):
        tab.rows[i].cells[0].text = k
        tab.rows[i].cells[1].text = v
        _set_font(tab.rows[i].cells[0].paragraphs[0].runs[0], 10.5, bold=True)
    tab.rows[2].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_font(tab.rows[2].cells[1].paragraphs[0].runs[0], 10.5, bold=True)
    pp = doc.add_paragraph()
    _set_font(pp.add_run(f"大写金额（VND）：{_vnd_uppercase(grand)}"), 10.5, bold=True)


def _add_notes(doc, payload):
    doc.add_paragraph("四、报价说明")
    notes = [
        f"1. 本报价含运输服务费及进出口服务费，有效期 {payload.validity_days} 天。",
        "2. 本报价不含越南进口关税及增值税、保险等费用。",
        "3. 付款方式：【待确认】。",
        "4. 其余批次/货物另行报价。",
        "5. 汇率：以当日银行汇率为准，仅供参考。",
    ]
    note = (getattr(payload, "oversize_note", "") or "").strip()
    if note:
        notes.append(f"{len(notes) + 1}. {note}")   # 🆕 大件/超限专线价说明
    for n in notes:
        _set_font(doc.add_paragraph().add_run(n), 10.5)


def _add_sign_off(doc, profile):
    doc.add_paragraph()
    tab = doc.add_table(rows=1, cols=2)
    lst = tab.rows[0].cells[0]
    rst = tab.rows[0].cells[1]
    _set_font(lst.paragraphs[0].add_run("报价方：【玖能国际　签章】"), 10.5)
    _set_font(rst.paragraphs[0].add_run("客户确认：【签字/盖章】"), 10.5)
    for cell in (lst, rst):
        _set_font(cell.add_paragraph().add_run("日期：　　　　年　　月　　日"), 10.5)


def build_legacy(payload, profile, quote_no) -> bytes:
    """v009 及以前的版式（单语、逐项明细）。保留以便对比/回退，新代码不要调用。"""
    doc = Document()
    _add_letterhead(doc, profile)
    _add_title(doc)
    _add_basic_info(doc, payload, quote_no)
    _add_route_overview(doc, payload, profile)
    _add_fee_detail(doc, payload, profile)
    _add_border_fees(doc, payload)
    _add_fee_total(doc, payload)
    _add_notes(doc, payload)
    _add_sign_off(doc, profile)
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()


def build(payload, profile, quote_no) -> bytes:
    """生成正式报价单 docx（v010 起 = 中越双语 / VND+RMB 双列 / 三行汇总 / 盖章位·手签位·页码）。

    委托给 `quote_template.build`；**函数签名保持不变**，因此
    `POST /api/v1/quote/export` 与前端「📄 生成正式报价单」按钮无需任何改动。
    """
    from app.services import quote_template      # 延迟导入：避免与 quote_template 循环导入
    return quote_template.build(payload, profile, quote_no)
