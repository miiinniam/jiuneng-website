#!/usr/bin/env python
"""内部版配车明细验收 —— 断言「公开版不给、内部版才给」。

为什么要两支对照：只看内部版有没有 breakdown 是**没有判别力**的断言 ——
公开版也给了它同样满足。所以每个案例都跑两遍（无 key / 带 key），
公开版必须干净、内部版必须齐全，两者一起才算过。

用法（站点需带 QUOTE_INTERNAL_KEY 启动）：
    QUOTE_INTERNAL_KEY=dev-internal python scripts/verify-quote-internal-fit.py \
        --base http://127.0.0.1:3471 --key dev-internal

退出码：0 全绿 / 1 有用例失败 / 2 参数不全（不算通过）
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

# 公开版顶层白名单（server/quoteProxy.ts buildPublicFit）
PUBLIC_TOP = {"ok", "scope", "total_trucks", "needs_split", "split_note", "picks", "note"}
PUBLIC_PICK = {"model_id", "name", "max_load_ton", "vehicle_count", "oversize",
               "permit_tier", "permit_workdays_local", "permit_note"}

# 内部版顶层（契约 §C + divisibility）
INTERNAL_TOP = {"ok", "scope", "total_trucks", "needs_split", "split_note", "note", "groups",
                "divisibility"}
INTERNAL_GROUP = {"model_id", "display_name", "category", "max_load_ton", "vehicle_count",
                  "transport_units", "reason", "dim_flags", "permit_flags", "oversize_released",
                  "count_doctrine", "axle_lines", "breakdown", "pairs"}

# 公开版出现这些词即红线（内部成本/桌面工作台口径）
LEAK_WORDS = ["breakdown", "count_doctrine", "axle_lines", "divisibility", "transport_units",
              "base_rate", "fixed_surcharge", "toll_rate", "margin", "profit",
              "vehicle_breakdowns", "pairs"]

CASES = [
    # 30 m 塔筒：走三类许可，最典型的内部明细来源
    {"name": "30m 塔筒", "items": [{"name": "塔筒节", "length_m": 30, "width_m": 3,
                                   "height_m": 3, "weight_kg": 25000, "count": 1,
                                   "stackable": False}], "divisible": False},
    # 可解体件：触发 A6 拆件建议（divisibility 非 null）
    {"name": "48m 可解体罐体", "items": [{"name": "罐体段", "length_m": 48, "width_m": 4.2,
                                         "height_m": 4.3, "weight_kg": 40000, "count": 1,
                                         "stackable": False, "divisible": True}],
     "divisible": True},
]


def post(base: str, path: str, body: dict, key: str | None, timeout: int = 90) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("x-quote-key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:3471")
    ap.add_argument("--key", required=True, help="站点的 QUOTE_INTERNAL_KEY（内部版口令）")
    args = ap.parse_args()
    if not args.key.strip():
        print("KEY: MISSING —— 必须给 --key（空口令不算通过）")
        return 2

    ok = True
    for case in CASES:
        body = {"items": case["items"], "allow_oversized": True}
        print(f"══ {case['name']} ══")

        # ① 公开版：字段集必须严格等于白名单，且无内部词
        status, pub = post(args.base, "/api/quote/fit", body, None)
        if status != 200 or not pub.get("ok"):
            print(f"  FAIL 公开版 HTTP {status} {str(pub)[:160]}")
            ok = False
            continue
        extra = set(pub.keys()) - PUBLIC_TOP
        missing = PUBLIC_TOP - set(pub.keys())
        if extra or missing:
            print(f"  FAIL 公开版顶层字段越界 extra={sorted(extra)} missing={sorted(missing)}")
            ok = False
        else:
            print(f"  OK   公开版顶层 = 白名单 7 项")

        bad_pick = set()
        for pick in pub.get("picks") or []:
            bad_pick |= set(pick.keys()) - PUBLIC_PICK
        if bad_pick:
            print(f"  FAIL 公开版 pick 越界 {sorted(bad_pick)}")
            ok = False
        else:
            print(f"  OK   公开版 pick 字段干净（{len(pub.get('picks') or [])} 个方案）")

        raw_text = json.dumps(pub, ensure_ascii=False)
        hits = [w for w in LEAK_WORDS if w in raw_text]
        if hits:
            print(f"  FAIL 公开响应出现内部词 {hits}")
            ok = False
        else:
            print("  OK   公开响应零内部词")

        # ② 内部版：字段必须齐全
        status, ins = post(args.base, "/api/quote/fit", body, args.key)
        if status != 200 or not ins.get("ok"):
            print(f"  FAIL 内部版 HTTP {status} {str(ins)[:200]}")
            ok = False
            continue
        if ins.get("scope") != "internal":
            print(f"  FAIL 内部版 scope={ins.get('scope')!r}，期望 'internal'")
            ok = False
        missing_top = INTERNAL_TOP - set(ins.keys())
        if missing_top:
            print(f"  FAIL 内部版顶层缺 {sorted(missing_top)}")
            ok = False
        else:
            print("  OK   内部版顶层 8 项齐全（含 divisibility）")

        groups = ins.get("groups") or []
        if not groups:
            print("  WARN 内部版 groups 为空（配不出车），跳过组字段断言")
        else:
            missing_g = INTERNAL_GROUP - set(groups[0].keys())
            if missing_g:
                print(f"  FAIL 内部版组字段缺 {sorted(missing_g)}")
                ok = False
            else:
                print(f"  OK   内部版组字段 14 项齐全（{len(groups)} 组）")
            # 明细必须真有内容，不能是空 dict 糊过去
            if not groups[0].get("breakdown"):
                print("  FAIL breakdown 为空 dict —— 内部版等于没给明细")
                ok = False
            else:
                print(f"  OK   breakdown 有内容 {list(groups[0]['breakdown'])[:6]}")

        # ③ divisibility 与案例预期一致（可解体件必须给建议）
        div = ins.get("divisibility")
        if case["divisible"]:
            if not div:
                print("  FAIL 可解体件 divisibility 为 null（A6 建议没出门）")
                ok = False
            else:
                print(f"  OK   可解体件给了建议 {list(div)[:5]}")
        else:
            print(f"  OK   非可解体件 divisibility={div!r}")

    print("INTERNAL-FIT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
