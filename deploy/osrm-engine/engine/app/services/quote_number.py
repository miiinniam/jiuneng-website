import json
from datetime import datetime

from app.services._paths import data_dir

_COUNTER_FILE = data_dir() / "quote_counter.json"


def next_number() -> str:
    """生成报价单号 JN-BG-YYYYMMDD-NN，同日递增。"""
    today = datetime.now().strftime("%Y%m%d")
    data = {}
    try:
        data = json.loads(_COUNTER_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    seq = data.get(today, 0) + 1
    data[today] = seq
    _COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COUNTER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"JN-BG-{today}-{seq:02d}"
