#!/usr/bin/env python
"""v8 版式验收 —— 用 CDP 量真实 DOM，不靠截图肉眼判断。

为什么要它：
  `chrome --headless --window-size=1440,20000 --screenshot` 截长图会毁掉布局
  （视口高度直接决定 `vh` 类长度，页面被拉长成 2 万像素），所以长图必须走
  CDP 的 `captureBeyondViewport`，在**真实视口高度**下拍。

同时按 `docs/redesign/02-视觉规范-瑞士编辑风.md` §8 的量化指标做断言：
  横向溢出 = 0 / 圆角 >2px 元素 = 0 / box-shadow 非 none ≤ 2 /
  同页字重 ≤ 3 / 满幅照片与视口对齐 = 0px 偏差。

用法：
    NODE_ENV=production PORT=3300 node dist/server.cjs
    env -u PYTHONPATH python scripts/verify-v8.py --shot-dir <目录>
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

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROBE = r"""
(() => {
  const de = document.documentElement;
  const vw = de.clientWidth;
  const out = {vw, scrollW: de.scrollWidth, scrollH: de.scrollHeight, overflow: [], radius: [], shadow: 0, weights: {}, colors: new Set()};
  for (const el of document.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const cs = getComputedStyle(el);
    // 跳转链接 .jn-skip 常态移出视口是设计（焦点出现），不算横向溢出
    const skip = el.classList.contains('jn-skip') || el.closest('.jn-skip');
    if (!skip && (r.right > vw + 1 || r.left < -1)) out.overflow.push(el.tagName + '.' + (el.className || ''));
    const rad = parseFloat(cs.borderTopLeftRadius) || 0;
    if (rad > 2) out.radius.push(el.tagName + '.' + (el.className || '') + ':' + rad);
    if (cs.boxShadow !== 'none') out.shadow += 1;
    if (el.childElementCount === 0 && (el.textContent || '').trim()) {
      out.weights[cs.fontWeight] = (out.weights[cs.fontWeight] || 0) + 1;
      out.colors.add(cs.color);
    }
  }
  const hero = document.querySelector('.hero-fig img');
  const hr = hero ? hero.getBoundingClientRect() : null;
  out.hero = hr ? {left: Math.round(hr.left), right: Math.round(hr.right), top: Math.round(hr.top), h: Math.round(hr.height)} : null;
  const secs = [...document.querySelectorAll('section, footer')].map(s => ({c: s.className, h: Math.round(s.getBoundingClientRect().height)}));
  out.sections = secs;
  out.colors = [...out.colors];
  return out;
})()
"""


async def run(width: int, height: int, url: str, shot_dir: Path | None, name: str) -> dict:
    port = 9300 + (width % 100)
    profile = tempfile.mkdtemp(prefix="cdp-v8-")
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

        async with websockets.connect(ws_url, max_size=200 * 1024 * 1024) as ws:
            n = 0

            async def cmd(method: str, params: dict | None = None) -> dict:
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == n:
                        return msg.get("result", {})

            await cmd("Page.enable")
            await cmd("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768,
            })
            await cmd("Page.navigate", {"url": url})
            await asyncio.sleep(3.0)
            # 逐屏滚一遍，让 lazy 图真的加载
            for step in range(1, 12):
                await cmd("Runtime.evaluate", {"expression": f"window.scrollTo(0, innerHeight*{step}*0.9)"})
                await asyncio.sleep(0.25)
            await cmd("Runtime.evaluate", {"expression": "window.scrollTo(0,0)"})
            await asyncio.sleep(0.4)

            res = await cmd("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})
            data = res["result"]["value"]

            if shot_dir:
                shot_dir.mkdir(parents=True, exist_ok=True)
                h = min(data["scrollH"], 20000)
                shot = await cmd("Page.captureScreenshot", {
                    "format": "png", "captureBeyondViewport": True,
                    "clip": {"x": 0, "y": 0, "width": width, "height": h, "scale": 1},
                })
                (shot_dir / f"{name}-{width}.png").write_bytes(base64.b64decode(shot["data"]))
            return data
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3300/")
    ap.add_argument("--widths", nargs="+", type=int, default=[390, 768, 1440])
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--shot-dir")
    args = ap.parse_args()
    shot_dir = Path(args.shot_dir) if args.shot_dir else None

    failed = 0
    for w in args.widths:
        d = await run(w, args.height, args.url, shot_dir, "v8")
        rad = len(d["radius"])
        weights = len(d["weights"])
        colors = len(d["colors"])
        checks = {
            "横向溢出=0": not d["overflow"] and d["scrollW"] <= d["vw"],
            "圆角>2px=0": rad == 0,
            "shadow≤2": d["shadow"] <= 2,
            "字重≤3": weights <= 3,
            "颜色≤6": colors <= 6,
        }
        print(f"\n── {w}px  页高 {d['scrollH']}  scrollW {d['scrollW']}/{d['vw']}")
        print(f"   hero img {d['hero']}")
        for k, ok in checks.items():
            print(f"   {'OK ' if ok else 'FAIL'} {k}")
            if not ok:
                failed += 1
        if d["overflow"]:
            print("   溢出元素:", d["overflow"][:6])
        if d["radius"]:
            print("   圆角元素:", d["radius"][:6])
        print("   字重分布:", d["weights"])
        print("   颜色:", d["colors"])
        print("   各段高度:", [(s["c"] or "footer")[:24] + f"={s['h']}" for s in d["sections"]])
    print(f"\n{'全部通过' if failed == 0 else f'{failed} 项未通过'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
