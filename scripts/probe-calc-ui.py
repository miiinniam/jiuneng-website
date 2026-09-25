"""「快速测算」UI 端到端：真引擎（18000）→ 官网出口 → 面板渲染 → 一键带到询价表单。
用法： python probe-calc-ui.py [base_url]
覆盖：中/越/英 三语 + 结果字段 + 口径声明 + 内部字段零泄漏 + 预填联动 + 横向溢出
"""
import asyncio, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3300"

FILL = r"""
(() => {
  const q = (s) => document.querySelector(s);
  const setVal = (sel, v) => {
    const el = q(sel); if (!el) return false;
    const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const okWeight = setVal('#calc input[type=number]', '20');
  const vol = document.querySelectorAll('#calc input[type=number]')[1];
  if (vol) { okWeight && setVal('#calc input[type=number]:nth-of-type(1)', '20'); }
  // 体积（拼车必填）：直接给第二个数字输入赋值
  const nums = [...document.querySelectorAll('#calc input[type=number]')];
  const okVolume = nums[1] ? (() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(nums[1], '60');
    nums[1].dispatchEvent(new Event('input', { bubbles: true }));
    nums[1].dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })() : false;
  return JSON.stringify({ okWeight, okVolume });
})()
"""

SUBMIT = r"""
(() => {
  const btns = [...document.querySelectorAll('#calc button')];
  const b = btns.find(x => x.type === 'submit');
  if (!b) return JSON.stringify({ clicked: false });
  b.click();
  return JSON.stringify({ clicked: true, disabled: b.disabled });
})()
"""

READ = r"""
(() => {
  const q = (s) => document.querySelector(s);
  const txt = (s) => (q(s)?.textContent || '').trim();
  const all = (s) => [...document.querySelectorAll(s)].map(e => e.textContent.trim());
  const stats = [...document.querySelectorAll('.jx-calc-stats > div')].map(d => ({
    label: d.querySelector('span')?.textContent.trim(), value: d.querySelector('strong')?.textContent.trim() }));
  return JSON.stringify({
    hasCalc: !!q('#calc'),
    title: txt('.jx-calc-title'),
    selects: {
      origin: [...document.querySelectorAll('#calc select')][0]?.options.length || 0,
      destination: [...document.querySelectorAll('#calc select')][1]?.options.length || 0,
      border: [...document.querySelectorAll('#calc select')][2]?.options.length || 0,
    },
    stats: stats,
    priceLabel: txt('.jx-calc-price span'),
    priceValue: txt('.jx-calc-price strong'),
    note: txt('.jx-calc-note'),
    source: txt('.jx-calc-source'),
    profileNote: txt('.jx-calc-profile'),
    error: txt('.jx-calc-error'),
    ctaText: txt('.jx-calc-cta'),
    bodyHasInternal: /breakdown|profit_vnd|margin_rate|border_fees|cost_distance|cost_fuel|geometry/.test(document.body.innerText),
    bodyText: document.body.innerText,
    overflow: { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth },
    pageHasCalcSection: !!q('#consult #calc'),
  });
})()
"""

CLICK_CTA = r"""
(() => {
  const b = document.querySelector('.jx-calc-cta');
  if (!b) return JSON.stringify({ clicked: false });
  b.click();
  return JSON.stringify({ clicked: true });
})()
"""


async def main():
    port = 9801
    profile = Path(tempfile.gettempdir()) / "jx-calc-probe"
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
                             "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rc = 0
    fails = []
    try:
        ws_url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as fh:
                    pages = [t for t in json.load(fh) if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]; break
            except Exception:
                pass
            time.sleep(0.3)
        import websockets
        async with websockets.connect(ws_url, max_size=80 * 1024 * 1024) as ws:
            c = 0
            async def cmd(m, p=None):
                nonlocal c
                c += 1
                await ws.send(json.dumps({"id": c, "method": m, "params": p or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == c:
                        return msg
            async def pump(sec):
                end = time.time() + sec
                while time.time() < end:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
                    except asyncio.TimeoutError:
                        return
            async def ev(expr, await_promise=False):
                r = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": await_promise})
                v = r.get("result", {}).get("result", {}).get("value")
                return json.loads(v) if v else None

            await cmd("Page.enable"); await cmd("Runtime.enable")
            await cmd("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})

            for lang, price_words in (("zh", ["初步测算", "非正式报价"]), ("vi", ["ước tính", "báo giá"]), ("en", ["preliminary", "not a quotation"])):
                await cmd("Page.navigate", {"url": f"{BASE}/ai?lang={lang}"})
                await pump(3.0)
                await cmd("Runtime.evaluate", {"expression":
                    "(async () => { const H = window.innerHeight; for (let y = 0; y < document.body.scrollHeight; y += H * 0.8) "
                    "{ window.scrollTo(0, y); await new Promise(r => setTimeout(r, 150)); } })()", "awaitPromise": True})
                await pump(1.5)
                await cmd("Runtime.evaluate", {"expression": "document.querySelector('#consult')?.scrollIntoView()"})
                await pump(0.8)

                print(f"\n===== [{lang}] {BASE}/ai?lang={lang} =====")
                f = await ev(FILL)
                await pump(0.4)
                s = await ev(SUBMIT)
                print(f"  填表: {f} / 提交: {s}")
                await pump(6.0)
                st = await ev(READ)
                if not st:
                    fails.append(f"{lang}: 读不到状态"); print("  ✗ 读不到状态"); continue

                print(f"  面板在位: {st['hasCalc']} | 位于 #consult 内: {st['pageHasCalcSection']}")
                print(f"  标题: {st['title']}")
                print(f"  下拉项数: 起点 {st['selects']['origin']} / 终点 {st['selects']['destination']} / 口岸 {st['selects']['border']}")
                for d in st["stats"]:
                    print(f"    · {d['label']} = {d['value']}")
                print(f"  {st['priceLabel']}: {st['priceValue']}")
                print(f"  口径: {st['note'][:60]}")
                print(f"  引擎备注: {(st['profileNote'] or '(无)')[:70]}")
                print(f"  错误提示: {st['error'] or '(无)'}")
                print(f"  横向溢出: {st['overflow']['sw']} vs {st['overflow']['cw']}")

                def need(cond, msg):
                    if not cond: fails.append(f"{lang}: {msg}")

                need(st["hasCalc"] and st["pageHasCalcSection"], "测算面板不在 #consult 内")
                need(st["selects"]["origin"] >= 5, f"起点下拉只有 {st['selects']['origin']} 项")
                need(st["selects"]["destination"] >= 4, f"终点下拉只有 {st['selects']['destination']} 项")
                need(not st["error"], f"出现错误提示 {st['error']}")
                need(st["priceValue"].endswith("VND"), f"价位未渲染：{st['priceValue']}")
                need(" km" in (st["stats"][0]["value"] if st["stats"] else ""), "里程未渲染")
                need(any(w in st["note"] for w in price_words), f"口径声明缺关键词 {price_words}")
                need(not st["bodyHasInternal"], "页面上出现内部成本字段名")
                need(st["overflow"]["sw"] <= st["overflow"]["cw"] + 1, "横向溢出")
                print("  ✓ 结构、价位、口径、无泄漏、无溢出" if not any(lang in x for x in fails) else "  ✗ 见上面")

                ct = await ev(CLICK_CTA)
                await pump(0.8)
                pre = await ev("(() => { const t = document.querySelector('#consult textarea'); return JSON.stringify({ text: t ? t.value : null }); })()")
                print(f"  一键带到询价表单: 点击={ct and ct.get('clicked')}")
                print(f"    预填内容: {pre and pre.get('text')}")
                need(bool(pre and pre.get("text")), "询价表单没有被预填")
                need(bool(pre and pre.get("text") and ("VND" in pre["text"])), "预填内容里没有价位")
    finally:
        proc.terminate()
    print("\n" + ("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails)))
    return 1 if fails else 0


sys.exit(asyncio.run(main()))
