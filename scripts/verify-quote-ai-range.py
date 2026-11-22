#!/usr/bin/env python
"""报价助手验收 —— 断言「正文只给区间、不给成本明细」。

为什么这条必须单独验收：`/quote` 的 AI 在改造前是引擎 SSE 原样透传，
引擎 prompt 明确要求输出「运费明细 + 口岸费明细 + DDP 总计」，
于是**工作台卡片是干净的，聊天正文却带着成本结构**（本项目的红线漏洞）。
换成站内编排后，正文里不该再出现任何成本项。

断言（四段，缺一即 FAIL）：
  A 至少发生一次工具调用（tool_start + tool_done，证明走的是站内编排而非纯聊天）
  B 正文非空且带「初步 / 非正式报价」限定语
  C 正文**零**成本词（breakdown / cost_ / 每公里成本 / 毛利 / 成本合计 / 单价 / 利润率）
  D 若发生了 run_quote，其 quote_result 事件里也不许有成本字段

用法：
    env -u PYTHONPATH python scripts/verify-quote-ai-range.py --base http://127.0.0.1:3471
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# 正文里出现这些就算泄漏（注意：只扫正文，不扫工具状态条 —— 工具名本身不含这些词）
COST_WORDS = [
    "breakdown", "cost_total", "cost_per_km", "每公里成本", "成本合计", "毛利润", "利润率",
    "运费明细", "口岸费明细", "DDP 总计", "DDP分项", "单价成本", "base_rate", "fixed_surcharge",
]

ASK = "南宁到河内，20 吨普通货物，大概多少钱？"


def post_sse(base: str, body: dict, timeout: int = 180) -> tuple[int, str]:
    req = urllib.request.Request(base + "/api/quote/ai", data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def parse_events(raw: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        ev, data = "", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if not ev:
            continue
        try:
            out.append((ev, json.loads(data) if data else {}))
        except json.JSONDecodeError:
            out.append((ev, {"_raw": data[:200]}))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:3471")
    ap.add_argument("--key", default="", help="可选：内部版口令（走内部口径）")
    args = ap.parse_args()

    body = {
        "messages": [{"role": "user", "content": ASK}],
        "lang": "zh",
        "form": {
            "originLabel": "南宁", "destLabel": "河内",
            "originLat": 22.823, "originLng": 108.317,
            "destLat": 21.028, "destLng": 105.854,
            "weightKg": 20000, "cargoType": "normal", "cargoClass": "normal",
        },
    }
    if args.key:
        body["internalKey"] = args.key

    status, raw = post_sse(args.base, body)
    if status != 200:
        print(f"FAIL HTTP {status}: {raw[:300]}")
        return 1

    events = parse_events(raw)
    kinds = [e for e, _ in events]
    text = "".join(d.get("content", "") for e, d in events if e == "text")
    ok = True

    print(f"事件序列：{kinds}")
    print(f"正文长度：{len(text)}")

    # A 工具调用
    starts = [d.get("name") for e, d in events if e == "tool_start"]
    dones = [d.get("name") for e, d in events if e == "tool_done"]
    if not starts:
        print("  FAIL A 没有任何 tool_start —— 没走站内编排（或模型没调工具）")
        ok = False
    else:
        print(f"  OK   A 工具调用 {starts}（完成 {dones}）")

    # B 正文与限定语
    if len(text.strip()) < 20:
        print(f"  FAIL B 正文过短（{len(text)} 字）")
        ok = False
    elif not any(w in text for w in ("初步", "非正式", "参考")):
        print("  FAIL B 正文缺「初步测算 / 非正式报价」限定语")
        ok = False
    else:
        print("  OK   B 正文非空且带限定语")

    # C 成本词红线
    hits = [w for w in COST_WORDS if w in text]
    if hits:
        print(f"  FAIL C 正文出现成本口径词：{hits}")
        idx = min(text.find(w) for w in hits if w in text)
        print(f"       上下文：…{text[max(0, idx - 40):idx + 60]}…")
        ok = False
    else:
        print("  OK   C 正文零成本词")

    # D quote_result 里也不许有成本字段
    qrs = [d for e, d in events if e == "quote_result"]
    if qrs:
        blob = json.dumps(qrs, ensure_ascii=False)
        bad = [w for w in ("breakdown", "cost_", "margin", "profit", "base_rate") if w in blob]
        if bad:
            print(f"  FAIL D quote_result 含成本字段：{bad}")
            ok = False
        else:
            print(f"  OK   D quote_result 干净（{len(qrs)} 条）")
    else:
        print("  WARN D 本轮没触发 run_quote（模型没算价），跳过该项")

    # 额外：form_patch 是否真的下发了（AI 改表单的能力）
    patches = [d for e, d in events if e == "form_patch"]
    if patches:
        print(f"  INFO form_patch × {len(patches)}：{[d.get('reason') for d in patches]}")

    print("QUOTE-AI-RANGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
