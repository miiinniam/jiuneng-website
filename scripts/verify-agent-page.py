#!/usr/bin/env python
"""
/ai（物流 AI 智能体页）验收脚本 —— CDP 真机渲染 + 交互 + 全页截图。

为什么单独写一个：
  verify-layout.py 的探针选择器是为旧首页写的（.nav / .hero-content …），
  对 /ai 全部返回 None，只能报「无横向溢出」，等于没验证。
  本脚本用 .jx-* 类名探针，并额外做三件旧脚本不做的事：
    1. 交互链路：hero 输入框 → 询价表单预填 / 标签页切换 / 轮播翻页 / 汉堡菜单
    2. 表单 → /api/logistics-consult → 结果面板（真实网络往返，不是看 DOM 猜）
    3. 全页截图 + 200px 带亮度扫描（判断有无深色区块回归）

用法：
    NODE_ENV=production PORT=3300 node dist/server.cjs      # 先起生产服务
    python scripts/verify-agent-page.py --url http://localhost:3300/ai \\
        --widths 390 768 1440 --shot-dir shots/ai
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
]

PROBE = r"""
(() => {
  const de = document.documentElement;
  const vw = de.clientWidth;

  const overflowing = [];
  for (const el of document.querySelectorAll('.jx-page *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.left < -1) {
      // 跑马灯 / 滚动容器内部允许越界（父级 overflow:hidden）
      if (el.closest('.jx-marquee, .jx-roletabs, .jx-tabbar, .jx-carousel-view')) continue;
      overflowing.push({
        tag: el.tagName.toLowerCase(),
        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 46),
        left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width),
      });
    }
  }
  overflowing.sort((a, b) => b.right - a.right);

  const info = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {
      w: Math.round(r.width), h: Math.round(r.height),
      opacity: cs.opacity, visibility: cs.visibility, display: cs.display,
    };
  };

  const sections = [...document.querySelectorAll('main > section, footer')].map((s) => {
    const r = s.getBoundingClientRect();
    return { id: s.id || s.tagName.toLowerCase(), h: Math.round(r.height), top: Math.round(r.top + window.scrollY) };
  });

  // 内容可见性：opacity:0 的文本节点数量（无头下动画不跑会在这里暴露）
  let invisible = 0;
  for (const el of document.querySelectorAll('.jx-page h1, .jx-page h2, .jx-page h3, .jx-page p')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const cs = getComputedStyle(el);
    if (cs.opacity === '0' || cs.visibility === 'hidden') invisible += 1;
  }

  const nav = document.querySelector('.jx-nav');
  const burger = document.querySelector('.jx-burger');

  return JSON.stringify({
    viewport: vw,
    scrollWidth: de.scrollWidth,
    horizontalOverflow: de.scrollWidth > vw + 1,
    overflowing: overflowing.slice(0, 10),
    docHeight: de.scrollHeight,
    sections,
    invisibleText: invisible,
    navDisplay: nav ? getComputedStyle(nav).display : 'missing',
    burgerDisplay: burger ? getComputedStyle(burger).display : 'missing',
    h1: (document.querySelector('.jx-hero-title') || {}).textContent || '',
    firstSectionTitle: (document.querySelector('.jx-sec-title') || {}).textContent || '',
    promptPlaceholder: (document.querySelector('.jx-prompt-input') || {}).placeholder || '',
    teamCards: document.querySelectorAll('.jx-team-card').length,
    serviceSlides: document.querySelectorAll('.jx-service').length,
    appTabs: document.querySelectorAll('.jx-tab').length,
    caseCards: document.querySelectorAll('.jx-case-card').length,
    key: {
      hero: info('.jx-hero'),
      prompt: info('.jx-prompt'),
      team: info('.jx-team-card'),
      service: info('.jx-service'),
      appCard: info('.jx-app-card'),
      band: info('.jx-band'),
      consult: info('.jx-consult'),
      result: info('.jx-result'),
      cta: info('.jx-cta'),
      footer: info('.jx-footer'),
    },
  }, null, 1);
})()
"""

INTERACTIONS = r"""
(async () => {
  const out = {};
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // 1) 应用场景标签切换
  const tabs = [...document.querySelectorAll('.jx-tab')];
  out.tabCount = tabs.length;
  const before = (document.querySelector('.jx-app-content h3') || {}).textContent;
  if (tabs[2]) { tabs[2].click(); await sleep(400); }
  const after = (document.querySelector('.jx-app-content h3') || {}).textContent;
  out.appTabSwitch = { before, after, changed: before !== after };
  const activeTabs = document.querySelectorAll('.jx-tab.is-active').length;
  out.activeTabCount = activeTabs;

  // 2) 轮播翻页
  const count = document.querySelector('.jx-carousel-count');
  const beforeCount = count ? count.textContent : null;
  const track = document.querySelector('.jx-carousel-track');
  const beforeTf = track ? track.style.transform : null;
  const next = document.querySelectorAll('.jx-nav-btn')[1];
  if (next) { next.click(); await sleep(900); }
  out.carousel = {
    before: beforeCount,
    after: count ? count.textContent : null,
    transformBefore: beforeTf,
    transformAfter: track ? track.style.transform : null,
  };

  // 3) hero 提示框 → 询价表单预填
  const input = document.querySelector('.jx-prompt-input');
  const text = '越南河内项目，3 台变压器，单件 62 吨，凭祥口岸进';
  if (input) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(input, text);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(200);
    const form = document.querySelector('.jx-prompt');
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await sleep(1200);
    const details = document.querySelector('#consult .jx-consult .jx-full textarea');
    out.promptToForm = {
      textareaValue: details ? details.value : null,
      prefilled: !!(details && details.value.includes('变压器')),
      atConsult: Math.abs(window.scrollY + 76 - (document.getElementById('consult') || {}).offsetTop) < 400,
    };
  }

  // 4) 表单 → /api/logistics-consult → 结果面板
  const setVal = (el, v) => {
    const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype
      : el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const inputs = [...document.querySelectorAll('#consult .jx-consult .jx-form-grid input')];
  if (inputs[0]) setVal(inputs[0], '验收测试');
  if (inputs[3]) setVal(inputs[3], '凭祥口岸');
  if (inputs[4]) setVal(inputs[4], '河内');
  if (inputs[5]) setVal(inputs[5], '62 吨');
  const ta = document.querySelector('#consult .jx-consult .jx-full textarea');
  if (ta) setVal(ta, '验收测试：3 台变压器，单件 62 吨，凭祥口岸进，10 月装运。');

  const api = { status: null, ok: null, body: null };
  const origFetch = window.fetch;
  window.fetch = async (...args) => {
    const res = await origFetch(...args);
    try {
      const clone = res.clone();
      api.status = res.status;
      api.ok = res.ok;
      api.body = (await clone.text()).slice(0, 400);
    } catch (e) { api.body = 'read-failed'; }
    return res;
  };

  const submit = document.querySelector('#consult .jx-consult .jx-submit');
  if (submit) { submit.click(); await sleep(6000); }
  window.fetch = origFetch;

  const resultEl = document.querySelector('#consult .jx-consult .jx-result');
  out.formSubmit = {
    apiStatus: api.status,
    apiOk: api.ok,
    bodyHead: api.body,
    resultText: resultEl ? resultEl.innerText.replace(/\s+/g, ' ').slice(0, 320) : null,
    skeletonGone: !document.querySelector('.jx-skeleton'),
  };

  return JSON.stringify(out, null, 1);
})()
"""

MOBILE_MENU = r"""
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const burger = document.querySelector('.jx-burger');
  if (!burger) return JSON.stringify({ error: 'no burger' });
  const before = document.querySelector('.jx-mobile-panel').className;
  burger.click();
  await sleep(500);
  const panel = document.querySelector('.jx-mobile-panel');
  const r = panel.getBoundingClientRect();
  return JSON.stringify({
    before,
    after: panel.className,
    panelHeight: Math.round(r.height),
    links: panel.querySelectorAll('a').length,
    open: panel.className.includes('is-open') && r.height > 100,
  }, null, 1);
})()
"""

SUCCESS_FORM = r"""
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const setVal = (el, v) => {
    const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype
      : el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const inputs = [...document.querySelectorAll('#consult .jx-consult .jx-form-grid input')];
  if (inputs[0]) setVal(inputs[0], 'Mock 验收');
  const ta = document.querySelector('#consult .jx-consult .jx-full textarea');
  if (ta) setVal(ta, 'Mock 验收：3 台变压器，凭祥口岸进，河内交付。');
  document.querySelector('#consult .jx-consult .jx-submit').click();

  const out = { rendered: false, hasRoute: false, hasDocs: false, text: null };
  for (let i = 0; i < 60; i++) {
    await sleep(300);
    const el = document.querySelector('#consult .jx-consult .jx-result');
    const txt = el ? el.innerText : '';
    if (txt.includes('[MOCK]')) { out.rendered = true; }
    if (txt.includes('凭祥口岸进境')) { out.hasRoute = true; }
    if (txt.includes('Form E')) { out.hasDocs = true; }
    if (out.rendered) { out.text = txt.replace(/\s+/g, ' ').slice(0, 400); break; }
  }
  return JSON.stringify(out);
})()
"""


REVEAL_CSS = ".jx-page *{animation:none !important;transition:none !important}"


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists() or "/" not in c:
            return c
    sys.exit("找不到 Chrome，请用 --chrome 指定路径")


def band_brightness(png: Path, band: int = 200) -> list[float]:
    """按 200px 带扫描平均亮度（0-255）。无 PIL 时返回空列表。"""
    try:
        from PIL import Image
    except ImportError:
        return []
    with Image.open(png) as im:
        im = im.convert("L")
        w, h = im.size
        vals = []
        for top in range(0, h, band):
            crop = im.crop((0, top, w, min(top + band, h)))
            hist = crop.histogram()
            total = sum(hist)
            if not total:
                continue
            vals.append(sum(i * n for i, n in enumerate(hist)) / total)
        return [round(v, 1) for v in vals]


async def main_async(args) -> int:
    port = 9444
    profile = Path(tempfile.gettempdir()) / "jiuneng-agent-verify"
    chrome = args.chrome or find_chrome()
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
         f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rc = 0
    try:
        ws_url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as fh:
                    pages = [t for t in json.load(fh) if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if not ws_url:
            print("ERROR: CDP 端口未就绪")
            return 1

        try:
            import websockets
        except ImportError:
            print("ERROR: 需要 websockets —— pip install websockets")
            return 1

        async with websockets.connect(ws_url, max_size=40 * 1024 * 1024) as ws:
            counter = 0

            async def cmd(method, params=None):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == counter:
                        return msg

            async def evaluate(expr):
                res = await cmd("Runtime.evaluate",
                                {"expression": expr, "returnByValue": True, "awaitPromise": True})
                r = res.get("result", {})
                if r.get("exceptionDetails"):
                    det = r["exceptionDetails"]
                    print("  JS 异常:", det.get("text"),
                          (det.get("exception") or {}).get("description", "")[:400])
                return r.get("result", {}).get("value")

            await cmd("Page.enable")
            await cmd("Runtime.enable")

            # ── 1. 多视口几何 + 可见性 ──────────────────────────────
            for w in ([] if args.only == 'interactions' else args.widths):
                await cmd("Emulation.setDeviceMetricsOverride",
                          {"width": w, "height": 900, "deviceScaleFactor": 1, "mobile": w < 700})
                await cmd("Page.navigate", {"url": args.url})
                await asyncio.sleep(args.settle)
                raw = await evaluate(PROBE)
                print("=" * 66)
                print(f"视口 {w}px")
                print("=" * 66)
                if not raw:
                    print("  探针失败")
                    rc = 1
                    continue
                d = json.loads(raw)
                flag = "✗ 横向溢出" if d["horizontalOverflow"] else "✓ 无横向溢出"
                print(f"  scrollWidth={d['scrollWidth']} viewport={d['viewport']} → {flag}"
                      f"   页高={d['docHeight']}px")
                for o in d["overflowing"]:
                    print(f"    越界: {o['tag']}.{o['cls']} {o['left']}→{o['right']}")
                print(f"  内容不透明检查: opacity:0 的标题/段落 = {d['invisibleText']}"
                      f"  {'✓' if d['invisibleText'] == 0 else '✗ 有内容被动画藏住'}")
                print(f"  导航: .jx-nav={d['navDisplay']}  .jx-burger={d['burgerDisplay']}")
                print(f"  H1: {d['h1'][:60]}")
                print(f"  结构: 数字员工卡={d['teamCards']} 服务卡={d['serviceSlides']} "
                      f"场景标签={d['appTabs']} 案例卡={d['caseCards']}")
                print("  区块高度:")
                for s in d["sections"]:
                    print(f"    {s['id']:10s} top={s['top']:6d} h={s['h']:5d}")
                print("  关键元素:")
                for name, r in d["key"].items():
                    if r is None:
                        print(f"    {name:9s} — (缺失)")
                    else:
                        print(f"    {name:9s} {r['w']:5d}×{r['h']:<5d} opacity={r['opacity']} {r['display']}")
                if d["invisibleText"] != 0:
                    rc = 1
                if d["horizontalOverflow"]:
                    rc = 1

                # 汉堡菜单（窄视口）
                if w < 700:
                    raw_menu = await evaluate(MOBILE_MENU)
                    if raw_menu:
                        m = json.loads(raw_menu)
                        okm = m.get("open")
                        print(f"  汉堡菜单: 面板高={m.get('panelHeight')}px 链接={m.get('links')} "
                              f"{'✓ 可展开' if okm else '✗ 未展开'}")
                        if not okm:
                            rc = 1
                print()

            # ── 2. 交互链路（桌面视口） ────────────────────────────
            if args.only == 'widths':
                return rc
            await cmd("Emulation.setDeviceMetricsOverride",
                      {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await cmd("Page.navigate", {"url": args.url})
            await asyncio.sleep(args.settle)
            print("=" * 66)
            print("交互链路（1440px）")
            print("=" * 66)
            raw = await evaluate(INTERACTIONS)
            if not raw:
                print("  交互探针失败")
                rc = 1
            else:
                d = json.loads(raw)
                t = d.get("appTabSwitch", {})
                print(f"  场景标签切换: 「{t.get('before')}」→「{t.get('after')}」"
                      f"  {'✓' if t.get('changed') else '✗ 内容未切换'}"
                      f" (同时激活 {d.get('activeTabCount')} 个 tab)")
                if not t.get("changed") or d.get("activeTabCount") != 1:
                    rc = 1
                c = d.get("carousel", {})
                print(f"  轮播翻页: {c.get('before')} → {c.get('after')}"
                      f"  transform {c.get('transformBefore')} → {c.get('transformAfter')}")
                if c.get("before") == c.get("after"):
                    rc = 1
                p = d.get("promptToForm", {})
                print(f"  hero 输入 → 询价表单预填: {'✓' if p.get('prefilled') else '✗'}"
                      f"  滚动到位={p.get('atConsult')}")
                print(f"    预填值: {str(p.get('textareaValue'))[:70]}")
                if not p.get("prefilled"):
                    rc = 1
                f = d.get("formSubmit", {})
                print(f"  表单提交 → /api/logistics-consult: HTTP {f.get('apiStatus')}"
                      f" (ok={f.get('apiOk')})")
                print(f"    响应体: {str(f.get('bodyHead'))[:150]}")
                print(f"    结果面板: {str(f.get('resultText'))[:150]}")
                print(f"    loading 骨架已清除: {f.get('skeletonGone')}")

            # ── 2b. 成功路径（拦截 API，塞回契约形状的 JSON） ──────────
            # 本地无 GEMINI_API_KEY，500 只证明失败分支正确；这里用 CDP Fetch
            # 拦截把 200 + 契约 JSON 塞回去，验证成功分支的渲染。这是模拟响应。
            if args.only != 'widths':
                MOCK = {
                    "routeRecommendation": "[MOCK] 凭祥口岸进境，河内方向走公路干线",
                    "documentChecklist": ["[MOCK] Form E 原产地证", "[MOCK] 大件超限许可"],
                    "hsCodeAdvice": "[MOCK] 变压器归类方向需正式核定",
                    "riskMitigation": ["[MOCK] 桥梁限重需现场确认"],
                    "consultantStatement": "[MOCK] 以上为初步评估，非正式报价。",
                }
                await cmd("Fetch.enable", {"patterns": [
                    {"urlPattern": "*logistics-consult*", "requestStage": "Response"}]})
                await cmd("Page.navigate", {"url": args.url})
                await asyncio.sleep(args.settle)

                counter += 1
                root = counter
                # 先建立浏览器侧连接，保证 Fetch 事件已订阅
                await cmd("Runtime.evaluate", {"expression": "1+1"})
                await ws.send(json.dumps({
                    "id": root, "method": "Runtime.evaluate",
                    "params": {"expression": SUCCESS_FORM, "returnByValue": True,
                               "awaitPromise": True}}))
                fulfilled = 0
                res = None
                end = time.time() + 60
                while time.time() < end:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
                    if msg.get("method") == "Fetch.requestPaused":
                        p = msg["params"]
                        await ws.send(json.dumps({
                            "id": 90000 + fulfilled,
                            "method": "Fetch.fulfillRequest",
                            "params": {
                                "requestId": p["requestId"],
                                "responseCode": 200,
                                "responseHeaders": [{"name": "Content-Type",
                                                     "value": "application/json"}],
                                "body": base64.b64encode(
                                    json.dumps(MOCK).encode()).decode(),
                            },
                        }))
                        fulfilled += 1
                    elif msg.get("id") == root:
                        res = msg
                        break
                val = (res or {}).get("result", {}).get("result", {}).get("value")
                print("")
                print(f"  成功路径（拦截放行 {fulfilled} 个响应）")
                if val:
                    d = json.loads(val)
                    print(f"    成功分支渲染: {'✓' if d.get('rendered') else '✗'}"
                          f"  线路结论={d.get('hasRoute')} 单证清单={d.get('hasDocs')}")
                    print(f"    结果面板: {str(d.get('text'))[:230]}")
                    if not d.get("rendered"):
                        rc = 1
                else:
                    print("    成功路径探针失败（未拿到结果）")
                    rc = 1
                await cmd("Fetch.disable")


            # ── 3. 全页截图 + 亮度扫描 ─────────────────────────────
            if args.shot_dir and args.only != 'interactions':
                out_dir = Path(args.shot_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                for w, full in ((1440, True), (390, True)):
                    await cmd("Emulation.setDeviceMetricsOverride",
                              {"width": w, "height": 900, "deviceScaleFactor": 1, "mobile": w < 700})
                    await cmd("Page.navigate", {"url": args.url})
                    await asyncio.sleep(args.settle)
                    await evaluate(f"""(() => {{
                        const s = document.createElement('style');
                        s.textContent = {json.dumps(REVEAL_CSS)};
                        document.head.appendChild(s);
                        // 首屏 Hero 占 88vh，全页截图时压缩它，否则比例失真
                        const h = document.createElement('style');
                        h.textContent = '.jx-page .jx-hero{{min-height:auto !important}}';
                        document.head.appendChild(h);
                    }})()""")
                    await asyncio.sleep(0.6)
                    metrics = await cmd("Page.getLayoutMetrics")
                    cs = metrics.get("result", {}).get("cssContentSize") or metrics.get("result", {}).get("contentSize")
                    height = int(cs["height"]) if cs else 900
                    shot = await cmd("Page.captureScreenshot", {
                        "format": "png",
                        "captureBeyondViewport": True,
                        "clip": {"x": 0, "y": 0, "width": w, "height": height, "scale": 1},
                    })
                    b64 = shot.get("result", {}).get("data")
                    if not b64:
                        print(f"  截图失败 @{w}px")
                        rc = 1
                        continue
                    fp = out_dir / f"ai-full-{w}.png"
                    fp.write_bytes(base64.b64decode(b64))
                    bands = band_brightness(fp)
                    dark = [i for i, v in enumerate(bands) if v < 120]
                    print(f"\n  全页截图 @{w}px → {fp}  ({w}×{height})")
                    if bands:
                        print(f"  200px 带亮度: min={min(bands)} max={max(bands)}"
                              f"  低于 120 的带: {dark if dark else '无 ✓'}")
                    else:
                        print("  （未安装 PIL，跳过亮度扫描）")
        return rc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description="验收 /ai 页面：渲染、响应式、交互、截图")
    ap.add_argument("--url", default="http://localhost:3300/ai")
    ap.add_argument("--widths", nargs="+", type=int, default=[390, 768, 1440])
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--settle", type=float, default=4.0)
    ap.add_argument("--shot-dir", default=None)
    ap.add_argument("--only", choices=["all", "widths", "interactions"], default="all",
                    help="只跑多视口几何 / 只跑交互链路（调试用）")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
