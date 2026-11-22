#!/usr/bin/env python
"""P1 公开配车端点 `POST /api/quote/fit` 验收（静态白名单 + 12 条真案例）。

(A) 白名单静态检查（不需要服务在跑）：
    读 `server/quoteProxy.ts`，定位 `function buildPublicFit` 的函数体
    （找不到则退化为包含 `'/fit'` 的路由段），断言新增的对客响应构造里
    不出现成本 / 算法内部字段：
      breakdown · count_doctrine · axle_lines · base_rate · fixed_surcharge · margin · profit
    任一命中 ⇒ 打印命中行号并 FAIL。这是「成本不出门」红线的机器守卫。

(B) 真案例比对（服务在跑时才做）：
    对 BASE_URL（默认 http://127.0.0.1:3000，可用环境变量 BASE_URL 覆盖）
    逐条 POST /api/quote/fit，断言：
      1. HTTP 200 且 ok=true                        （期望 ok=false 的坏请求两条除外）
      2. picks 长度 ≤ 3                              （选择不过载：1 主选 + 折叠候选）
      3. 每条 pick 有 model_id / name / vehicle_count
      4. 响应 JSON 文本里不含禁止词（同 A，另加 '"items"' —— 明细不外漏）
    并按引擎金标案例核对车数（期望值来源：引擎侧 test_a5_blade_trailers /
    test_oversize / test_golden_cargo_fixture，代理不许自己改口径）：
      30m 塔筒=1 · 60m 叶片=1 · 80m 叶片=0（超库上限，如实报 0，不许伪造车）
      · 1.4m 宽钢板×2 ≥1 · 100t 轴线货 ≥1 · 10m 普货=1 · 可解体件 200/ok
      · 13.5m 设备需许可（permit_tier 非空） · 空清单与缺重量行 = bad_request
      · 6m 木箱×3 ≥1 · 距离 1200km 不改配车

    服务没起时 (B) 打印 SKIP 并提示「先用 npm run dev 起服务」，不算 FAIL；
    最终结果只按 (A) 判定（退出码 0）。

用法：
    env -u PYTHONPATH python scripts/verify-quote-fit.py
    BASE_URL=http://127.0.0.1:3300 env -u PYTHONPATH python scripts/verify-quote-fit.py

退出码：0 全部通过；1 有失败。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

# ── 口径常量（与 docs/ai-inquiry/07-官网接头勘察与改造计划.md §3 P1 对齐） ──
FORBIDDEN = ['breakdown', 'count_doctrine', 'axle_lines',
             'base_rate', 'fixed_surcharge', 'margin', 'profit']
FORBIDDEN_RESP = FORBIDDEN + ['"items"']

HERE = pathlib.Path(__file__).resolve().parent
PROXY_FILE = HERE.parent / 'server' / 'quoteProxy.ts'
PROXY_HINT = 'server/quoteProxy.ts'

DEFAULT_BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
CASE_TIMEOUT = float(os.environ.get('FIT_TIMEOUT', '120'))   # 引擎冷启动 30–60s，留足预算


def item(name: str, length_m: float, width_m: float, height_m: float,
         weight_kg: float, count: int = 1, stackable: bool = False,
         divisible: bool | None = None) -> dict:
    """按 P1 入参白名单造一条货物行（不塞引擎专属键）。"""
    row = {
        'name': name, 'length_m': length_m, 'width_m': width_m, 'height_m': height_m,
        'weight_kg': weight_kg, 'count': count, 'stackable': stackable,
    }
    if divisible is not None:
        row['divisible'] = divisible
    return row


# 12 条真案例：body 即原样 POST 的请求体；expect 是期望口径。
# 尺寸未在案例描述里给出的（1.4m 宽钢板 / 6m 木箱）按业务常识补成一张标准平板货，
# 期望只要求「配得出车」，补的尺寸不参与判据。
CASES = [
    dict(n=1, label='30m 塔筒 25t 3.0×3.0',
         body={'items': [item('30m 塔筒', 30, 3.0, 3.0, 25000)],
               'cargo_type': 'normal', 'allow_oversized': True},
         expect={'total': 1}),
    dict(n=2, label='60m 叶片 12t 3.2×3.2',
         body={'items': [item('60m 叶片', 60, 3.2, 3.2, 12000)],
               'cargo_type': 'oversized', 'allow_oversized': True},
         expect={'total': 1}),
    dict(n=3, label='80m 叶片 12t 3.2×3.2（超库上限）',
         body={'items': [item('80m 叶片', 80, 3.2, 3.2, 12000)],
               'cargo_type': 'oversized', 'allow_oversized': True},
         expect={'total': 0}),
    dict(n=4, label='1.4m 宽钢板 12t ×2（并排）',
         body={'items': [item('1.4m 宽钢板', 6, 1.4, 0.2, 12000, count=2)],
               'cargo_type': 'normal'},
         expect={'total_min': 1}),
    dict(n=5, label='100t 轴线车货 20m 3.0×3.0',
         body={'items': [item('100t 轴线车货', 20, 3.0, 3.0, 100000)],
               'cargo_type': 'heavy_equipment', 'allow_oversized': True},
         expect={'total_min': 1}),
    dict(n=6, label='10m 普货 8t 2.2×2.0',
         body={'items': [item('普货', 10, 2.2, 2.0, 8000)],
               'cargo_type': 'normal'},
         expect={'total': 1}),
    dict(n=7, label='30m 塔筒 25t（可解体）',
         body={'items': [item('30m 塔筒', 30, 3.0, 3.0, 25000, divisible=True)],
               'cargo_type': 'normal', 'allow_oversized': True},
         expect={'http_ok': True}),
    dict(n=8, label='13.5m 设备 35t 3.2×3.2（需许可）',
         body={'items': [item('13.5m 设备', 13.5, 3.2, 3.2, 35000)],
               'cargo_type': 'heavy_equipment', 'allow_oversized': True},
         expect={'http_ok': True, 'permit_tier': True}),
    dict(n=9, label='空 items=[]（坏请求）',
         body={'items': []},
         expect={'ok_false': True, 'reason': 'bad_request'}),
    dict(n=10, label='缺 weight_kg 的行（坏请求）',
         body={'items': [{'name': '缺重量设备', 'length_m': 6, 'width_m': 2.2, 'height_m': 2.0}]},
         expect={'ok_false': True}),
    dict(n=11, label='6m 木箱 3t ×3',
         body={'items': [item('6m 木箱', 6, 2.0, 2.0, 3000, count=3)],
               'cargo_type': 'normal'},
         expect={'total_min': 1}),
    dict(n=12, label='distance_km=1200 + 案例1',
         body={'items': [item('30m 塔筒', 30, 3.0, 3.0, 25000)],
               'cargo_type': 'normal', 'allow_oversized': True, 'distance_km': 1200},
         expect={'http_ok': True, 'same_total_as': 1}),
]


# ══════════════════════════════ (A) 静态白名单 ══════════════════════════════

def _locate_segments(text: str) -> tuple[list[tuple[str, int, str]], str]:
    """返回 [(说明, 起始偏移, 段落文本)]；找不到任何目标时列表为空。

    优先 `function buildPublicFit`（到下一个顶层 function 为止）；
    退化为包含 `'/fit'` 的路由段（从所在 `router.` 到下一个 `router.`）。
    """
    m = re.search(r'(?m)^(?:export\s+)?(?:async\s+)?function\s+buildPublicFit\s*[(<]', text)
    if m:
        tail = text[m.end():]
        nxt = re.search(r'(?m)^(?:export\s+)?(?:async\s+)?function\s+[A-Za-z_$]', tail)
        end = m.end() + nxt.start() if nxt else len(text)
        return [('buildPublicFit', m.start(), text[m.start():end])], 'buildPublicFit'

    segs: list[tuple[str, int, str]] = []
    seen: set[int] = set()
    for hit in re.finditer(r"""['"]/fit['"]""", text):
        start = max(text.rfind('router.', 0, hit.start()), 0)
        if start in seen:
            continue
        seen.add(start)
        nxt = text.find('router.', hit.end())
        end = nxt if nxt != -1 else len(text)
        segs.append(("'/fit' 路由段", start, text[start:end]))
    return segs, ("'/fit' 路由段" if segs else '')


def check_static() -> bool:
    print('══ A 白名单静态检查（%s，无需服务）══' % PROXY_HINT)
    if not PROXY_FILE.exists():
        print('  FAIL 找不到 %s —— 无法检查公开口径' % PROXY_FILE)
        return False

    text = PROXY_FILE.read_text(encoding='utf-8', errors='replace')
    segments, where = _locate_segments(text)
    if not segments:
        print("  FAIL 既没有 buildPublicFit，也没有 '/fit' 路由段 —— P1 端点尚未实现")
        print('       公开白名单无从校验（先把 P1 落进 %s 再跑本脚本）' % PROXY_HINT)
        return False

    hits: list[tuple[str, int, str]] = []
    seen: set[tuple[str, int]] = set()            # 同一行同一词只报一次（键+值会重复命中）
    for label, start, seg in segments:
        first_line = text.count('\n', 0, start) + 1
        print('  定位 %s（第 %d 行起，%d 字符）' % (label, first_line, len(seg)))
        for word in FORBIDDEN:
            for m in re.finditer(re.escape(word), seg):
                line_no = text.count('\n', 0, start + m.start()) + 1
                if (word, line_no) in seen:
                    continue
                seen.add((word, line_no))
                line_txt = text.splitlines()[line_no - 1].strip()
                hits.append((word, line_no, line_txt))

    if not hits:
        print('  OK   未出现 %d 个禁止词：%s' % (len(FORBIDDEN), ' · '.join(FORBIDDEN)))
        return True

    print('  FAIL 公开响应构造里出现 %d 处成本/算法内部字段：' % len(hits))
    for word, line_no, line_txt in hits:
        print('       第 %d 行  [%s]  %s' % (line_no, word, line_txt[:110]))
    return False


# ══════════════════════════════ (B) 真案例 ══════════════════════════════

def post_json(url: str, payload: dict, timeout: float) -> tuple[int, str]:
    """POST JSON，返回 (状态码, 原始响应文本)；网络失败返回 (0, 错误描述)。"""
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url, data=body, method='POST',
        headers={'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')
    except Exception as exc:                       # 连接被拒 / 超时 / DNS
        return 0, '%s: %s' % (type(exc).__name__, exc)


def server_alive(base: str) -> bool:
    try:
        with urllib.request.urlopen(base + '/api/health', timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def run_cases(base: str) -> tuple[bool, int, int]:
    """跑 12 条案例。返回 (全部通过?, 通过数, 总数)。"""
    url = base + '/api/quote/fit'
    totals: dict[int, int] = {}
    passed = 0

    for case in CASES:
        n, label, expect = case['n'], case['label'], case['expect']
        problems: list[str] = []
        overview = ''

        status, text = post_json(url, case['body'], CASE_TIMEOUT)
        if status == 0:
            problems.append('请求失败（%s）—— 服务没起或端口不对' % text)
            data = {}
        else:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                problems.append('响应不是 JSON（HTTP %d，前 80 字节：%r）' % (status, text[:80]))
                data = {}

        if data:
            ok = data.get('ok')
            picks = data.get('picks')
            total = data.get('total_trucks')
            if isinstance(total, int):
                totals[n] = total
            picks_txt = []
            if isinstance(picks, list):
                for p in picks:
                    if isinstance(p, dict):
                        picks_txt.append('%s×%s' % (p.get('name') or p.get('model_id') or '?',
                                                    p.get('vehicle_count', '?')))
                overview = 'total_trucks=%s  picks=[%s]' % (total, ', '.join(picks_txt) or '—')
            elif ok is False:
                overview = 'HTTP %d  ok=false  reason=%s' % (status, data.get('reason'))
            else:
                overview = 'total_trucks=%s  picks=(缺失)' % total

            # ① 禁止词：响应文本层面全查（含 '"items"' 明细键）
            leaks = [w for w in FORBIDDEN_RESP if w in text]
            if leaks:
                problems.append('响应含禁止词：%s' % ' · '.join(leaks))

            if expect.get('ok_false'):
                # 坏请求分支：不许 500，必须 ok=false（reason 视案例而定）
                if status >= 500:
                    problems.append('坏请求返回了 %d（不许 500）' % status)
                if ok is not False:
                    problems.append('ok=%r，期望 false' % (ok,))
                want_reason = expect.get('reason')
                if want_reason and data.get('reason') != want_reason:
                    problems.append('reason=%r，期望 %r' % (data.get('reason'), want_reason))
            else:
                # 正常分支
                if status != 200:
                    problems.append('HTTP %d（期望 200）' % status)
                if ok is not True:
                    problems.append('ok=%r（期望 true）' % (ok,))
                if not isinstance(picks, list):
                    problems.append('picks 不是数组（%r）' % (picks,))
                else:
                    if len(picks) > 3:
                        problems.append('picks=%d 条 > 3' % len(picks))
                    for idx, p in enumerate(picks, 1):
                        if not isinstance(p, dict):
                            problems.append('picks[%d] 不是对象' % idx)
                            continue
                        missing = [k for k in ('model_id', 'name', 'vehicle_count') if k not in p]
                        if missing:
                            problems.append('picks[%d] 缺字段 %s' % (idx, '/'.join(missing)))

                if 'total' in expect and total != expect['total']:
                    problems.append('total_trucks=%r，期望 %d' % (total, expect['total']))
                if 'total_min' in expect and not (isinstance(total, int) and total >= expect['total_min']):
                    problems.append('total_trucks=%r，期望 ≥%d' % (total, expect['total_min']))
                if expect.get('permit_tier'):
                    tiers = [p.get('permit_tier') for p in picks if isinstance(p, dict)] if isinstance(picks, list) else []
                    if not any(t is not None for t in tiers):
                        problems.append('picks 里没有一条 permit_tier 非 null（%s）' % (tiers or 'picks 为空'))
                if 'same_total_as' in expect:
                    ref_n = expect['same_total_as']
                    ref_total = totals.get(ref_n)
                    if ref_total is None:
                        problems.append('案例 %d 没拿到 total_trucks，无法比对距离是否改配车' % ref_n)
                    elif total != ref_total:
                        problems.append('total_trucks=%r，与案例 %d（%r）不一致 —— 距离不该改配车'
                                        % (total, ref_n, ref_total))

        good = not problems
        if good:
            passed += 1
            print('  %2d) %-28s %s  PASS' % (n, label, overview))
        else:
            print('  %2d) %-28s %s  FAIL' % (n, label, overview))
            for msg in problems:
                print('        - %s' % msg)

    return passed == len(CASES), passed, len(CASES)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    base = DEFAULT_BASE
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ('--base', '-b') and i + 1 <= len(sys.argv) - 1:
            base = sys.argv[i + 1].rstrip('/')
        elif arg.startswith('--base='):
            base = arg.split('=', 1)[1].rstrip('/')
        elif arg in ('-h', '--help'):
            print(__doc__)
            return 0
    print('BASE_URL: %s' % base)

    a_ok = check_static()

    if not server_alive(base):
        print('══ B 真案例比对（12 条）══')
        print('  SKIP 服务未启动：%s/api/health 连不上' % base)
        print('       先用 npm run dev 起服务（端口读 .env 的 PORT，本机为 3471；默认 3000），')
        print('       或 BASE_URL=http://127.0.0.1:<实际端口> 指向已启动实例后再跑。')
        print('FIT:', 'PASS' if a_ok else 'FAIL',
              '(静态 A %s；B 跳过)' % ('通过' if a_ok else '失败'))
        return 0 if a_ok else 1

    print('══ B 真案例比对（12 条 → %s/api/quote/fit）══' % base)
    b_ok, passed, total = run_cases(base)
    ok = a_ok and b_ok
    if b_ok:
        print('FIT: PASS (%d/%d)' % (passed, total))
    else:
        print('FIT: FAIL (%d fail)' % (total - passed))
        if not a_ok:
            print('     （静态白名单 A 也未通过）')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
