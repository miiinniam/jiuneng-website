import json

from app.services._paths import data_dir

_PROFILE_FILE = data_dir() / "company_info.json"

_DEFAULT_PROFILE = {
    "cn_name": "玖能国际",
    "vi_name": "JIUNENG International Co., Ltd.",
    "address_cn": "河内纸桥郡维新街82号5层R03",
    "address_vi": "No. 82, Duy Tan Street, Cau Giay, Hanoi",
    "phone": "0983 580 808",
    "email": "quoctejiuneng@gmail.com",
    "tax_id": "0202235124",
    # 🆕 v010：报价单「收款账户」区块（改这里或 data/company_info.json，不动代码）
    # ⚠️ 户名以越南营业执照为准：印章与营业执照上的公司名写法需一致，见实施记录「户名写法待核」。
    "bank_holder_cn": "玖能国际有限责任公司",
    "bank_holder_vi": "CÔNG TY TNHH QUỐC TẾ JIU NENG",
    "bank_name_cn": "越南科技商业股份银行（Techcombank）东都分行",
    "bank_name_vi": "Ngân hàng TMCP Kỹ Thương Việt Nam (Techcombank) – Chi nhánh Đông Đô",
    "bank_account_vnd": "68219696",
    "bank_account_usd": "19040201120015",
    "bank_swift": "VTCBVNVX",
    # ⚠️ 付款条件的**具体条款**在正式合同中约定（用户 2026-09-21 指示），
    #    报价单只保留这句中性说明；配空字符串则整段不显示（只留收款账户）。
    "payment_terms_cn": "付款方式在正式合同中约定。",
    "payment_terms_vi": "Phương thức thanh toán được thỏa thuận trong hợp đồng chính thức.",
    # 🆕 手写签名开关（用户 2026-09-21：「就只保留公司签章，后面再改」）
    #    false = 只盖公章（默认）；true = 手签 + 公章一起上（需 resources/company_sign.png 在位）
    "signature_enabled": False,
}


def get_profile() -> dict:
    """读取公司信头配置；缺失/出错时返回内置默认（玖能国际）。"""
    try:
        data = json.loads(_PROFILE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULT_PROFILE)
    return {**_DEFAULT_PROFILE, **data}
