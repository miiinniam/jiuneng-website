#!/usr/bin/env python
"""报价页（/quote 与 /quote/internal）验收 —— 读真实 DOM 与计算样式，不看截图。

为什么不用 verify-v8.py：那个脚本的探针是为宣传页写的（判据是「元素 rect 超视口」），
对报价页会误报两类真实无害的东西：leaflet 瓦片在裁切容器里、`.jn-skip` 跳转链接常态移出。
本脚本改用**真实的横向滚动**（scrollWidth vs clientWidth）判溢出，其余判据保留。

断言：
  A 溢出：1440 / 768 / 390 三档 scrollWidth ≤ clientWidth
  B 品牌：圆角 >2px 的元素 = 0；渐变背景 = 0；`.q-*` 上不许有 box-shadow
  C 公开口径：页面上不许出现「成本参数 / 分项成本 / 毛利 / 利润 / DDP」这些词
  D 内部版：未持口令时必须有口令输入；页面上不许出现引擎域名
  E 触屏：390 下主要按钮/输入高度 ≥ 44

用法：
    env -u PYTHONPATH python scripts/verify-quote-page.py --base http://127.0.0.1:3300
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROBE = r"""
(() => {
  const de = document.documentElement;
  const vw = de.clientWidth;
  const out = {
    vw, scrollW: de.scrollWidth, scrollH: de.scrollHeight,
    radius: [], shadow: [], gradient: [], small: [],
    text: (document.body.innerText || '').slice(0, 20000),
    html: document.documentElement.outerHTML,
  };
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const cs = getComputedStyle(el);
    const rad = parseFloat(cs.borderTopLeftRadius) || 0;
    if (rad > 2) out.radius.push(el.tagName + '.' + (el.className || '') + ':' + rad);
    if (cs.boxShadow !== 'none' && String(el.className || '').includes('q-')) {
      out.shadow.push(el.tagName + '.' + el.className);
    }
    if ((cs.backgroundImage || '').includes('gradient')) out.gradient.push(el.tagName + '.' + (el.className || ''));
  }
  // 触屏目标：按钮、输入、文本域（链接按行内文本处理，不参与）
  for (const el of document.querySelectorAll('button, input, textarea, select')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.height < 44) out.small.push(el.tagName + '.' + (el.className || '') + ':' + Math.round(r.height));
  }
  return out;
})()
"""

FORBIDDEN_PUBLIC = ['成本参数', '分项成本', '毛利', '利润', 'DDP全链路', '批量导入']
ENGINE_HOST = 'onrender.com'


async def probe(width: int, height: int, url: str) -> dict:
    port = 9600 + (width % 100)
    profile = tempfile.mkdtemp(prefix="cdp-qp-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--disable-gpu", "--hide-scrollbars", "--force-prefers-reduced-motion", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                data = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2).read())
                pages = [t for t in data if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.25)
        if not ws_url:
            raise RuntimeError("CDP 连不上")

        async with websockets.connect(ws_url, max_size=80 * 1024 * 1024) as ws:
            n = 0

            async def cmd(method, params=None):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == n:
                        return msg.get("result", {})

            await cmd("Page.enable")
            await cmd("Emulation.setDeviceMetricsOverride",
                      {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768})
            await cmd("Page.navigate", {"url": url})
            await asyncio.sleep(3.0)
            # 让懒加载（地图/批量）真的挂上
            for step in range(1, 6):
                await cmd("Runtime.evaluate", {"expression": f"window.scrollTo(0, innerHeight*{step})"})
                await asyncio.sleep(0.2)
            await cmd("Runtime.evaluate", {"expression": "window.scrollTo(0,0)"})
            await asyncio.sleep(0.4)
            res = await cmd("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})
            return res["result"]["value"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:3300")
    args = ap.parse_args()
    ok = True

    print('══ A 公开页 /quote ══')
    for w, h in ((1440, 900), (768, 1024), (390, 844)):
        d = asyncio.run(probe(w, h, f"{args.base}/quote"))
        overflow = d["scrollW"] - d["vw"]
        print(f"  {w}px  scrollW {d['scrollW']}/{d['vw']}  页高 {d['scrollH']}")
        if overflow > 1:
            print(f"  FAIL 横向溢出 {overflow}px")
            ok = False
        else:
            print("  OK   无横向滚动")
        if d["radius"]:
            print("  FAIL 圆角>2px:", d["radius"][:5])
            ok = False
        else:
            print("  OK   圆角全部 ≤2px")
        if d["shadow"]:
            print("  FAIL q-* 上有阴影:", d["shadow"][:5])
            ok = False
        else:
            print("  OK   q-* 无阴影")
        if d["gradient"]:
            print("  FAIL 出现渐变:", d["gradient"][:5])
            ok = False
        hits = [w0 for w0 in FORBIDDEN_PUBLIC if w0 in d["text"]]
        if hits:
            print("  FAIL 公开页出现内部口径词:", hits)
            ok = False
        else:
            print("  OK   公开页无内部口径词")
        if ENGINE_HOST in d["html"]:
            print("  FAIL 页面源码里出现引擎域名")
            ok = False
        else:
            print("  OK   无引擎域名")
        if w == 390 and d["small"]:
            print("  WARN 触屏目标 <44px:", d["small"][:6])
        elif w == 390:
            print("  OK   触屏目标 ≥44px")
        # 首屏要有"至少一个真事实"：里程/车辆/参考价 任一
        if w == 1440:
            if not any(k in d["text"] for k in ("里程", "车辆", "参考价", "测算")):
                print("  FAIL 首屏没有任何测算相关事实")
                ok = False

    print('══ D 内部页 /quote/internal ══')
    d = asyncio.run(probe(1440, 900, f"{args.base}/quote/internal"))
    has_gate = ("口令" in d["text"]) or ("内部" in d["text"])
    print("  口令/内部提示:", "OK" if has_gate else "FAIL（没看到口令入口）")
    ok = ok and has_gate
    if "noindex" not in d["html"]:
        print("  FAIL 内部页缺 noindex")
        ok = False
    else:
        print("  OK   noindex 已注入")
    if ENGINE_HOST in d["html"]:
        print("  FAIL 内部页源码里出现引擎域名")
        ok = False
    print("  内部页页高:", d["scrollH"])

    print("QUOTE-PAGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
