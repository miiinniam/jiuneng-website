#!/usr/bin/env python
"""
布局验证工具 —— 用 CDP 读真实 DOM 矩形，判断响应式布局是否有横向溢出。

为什么需要它：
  截图 + 视觉分析在布局判断上会严重误报（实测曾断言 375px 下「横向溢出、
  语言切换器被裁切、汉堡菜单不可见」，而 CDP 实测三项全错）。
  用 PIL 找「最右亮像素」同样不可靠 —— Hero 背景照片全幅铺满，
  最右亮像素来自照片高光而非内容。

依赖：Python `websockets`（已装）、本机 Chrome。
用法：
    # 先起生产服务器
    NODE_ENV=production PORT=3300 node dist/server.cjs

    python scripts/verify-layout.py                    # 默认查 375 / 680 / 1440
    python scripts/verify-layout.py --widths 320 375 768 1440
    python scripts/verify-layout.py --url http://localhost:3300/
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
  for (const el of document.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.left < -1) {
      const cs = getComputedStyle(el);
      overflowing.push({
        tag: el.tagName.toLowerCase(),
        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 50),
        left: Math.round(r.left), right: Math.round(r.right),
        width: Math.round(r.width), overflow: cs.overflow,
      });
    }
  }
  overflowing.sort((a, b) => b.right - a.right);

  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width),
             display: getComputedStyle(el).display };
  };

  return JSON.stringify({
    viewport: vw,
    scrollWidth: de.scrollWidth,
    horizontalOverflow: de.scrollWidth > vw + 1,
    overflowing: overflowing.slice(0, 12),
    key: {
      nav: rect('.nav'),
      brand: rect('.brand-logo'),
      navActions: rect('.nav-actions'),
      langSwitcher: rect('.language-switcher'),
      menuButton: rect('.menu-button'),
      desktopLinks: rect('.desktop-links'),
      navCta: rect('.nav-cta'),
      heroContent: rect('.hero-content'),
      heroStats: rect('.hero-stats'),
    },
  }, null, 1);
})()
"""

# 截图前注入：让入场动画以最终态渲染，避免无头环境下 motion 不跑导致内容停在 opacity:0
REVEAL_CSS = (
    ".hero-media,.hero-copy,.hero-panel,.hero-stats,section{"
    "opacity:1 !important;transform:none !important;animation:none !important}"
)


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists() or "/" not in c:
            return c
    sys.exit("找不到 Chrome，请用 --chrome 指定路径")


async def run(url: str, widths: list[int], chrome: str, settle: float,
              shot_dir: str | None = None) -> int:
    port = 9333
    profile = Path(tempfile.gettempdir()) / "jiuneng-verify-profile"
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check",
         f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rc = 0
    try:
        ws_url = None
        for _ in range(50):
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
            print("ERROR: CDP 调试端口未就绪")
            return 1

        try:
            import websockets
        except ImportError:
            print("ERROR: 需要 websockets —— pip install websockets")
            return 1

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            counter = 0

            async def cmd(method, params=None):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == counter:
                        return msg

            await cmd("Page.enable")
            await cmd("Runtime.enable")

            for w in widths:
                await cmd("Emulation.setDeviceMetricsOverride",
                          {"width": w, "height": 900, "deviceScaleFactor": 1, "mobile": w < 700})
                await cmd("Page.navigate", {"url": url})
                await asyncio.sleep(settle)
                res = await cmd("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})
                raw = res.get("result", {}).get("result", {}).get("value")
                print(f"{'=' * 62}\n视口 {w}px\n{'=' * 62}")
                if not raw:
                    print("  取值失败:", json.dumps(res)[:300])
                    rc = 1
                    continue
                d = json.loads(raw)

                bad = d["horizontalOverflow"]
                print(f"  scrollWidth={d['scrollWidth']}  viewport={d['viewport']}"
                      f"  → {'✗ 横向溢出' if bad else '✓ 无横向溢出'}")
                if bad:
                    rc = 1
                    print("  越界元素：")
                    for o in d["overflowing"]:
                        print(f"    {o['tag']}.{o['cls']:<32s} {o['left']:5d}→{o['right']:<5d} "
                              f"w={o['width']:<5d} overflow={o['overflow']}")
                else:
                    # 无溢出时，仍报告 key 元素（供对齐检查）
                    for name, r in d["key"].items():
                        if r is None:
                            print(f"    {name:14s} —")
                        elif r["display"] == "none":
                            print(f"    {name:14s} display:none")
                        else:
                            print(f"    {name:14s} {r['l']:5d}→{r['r']:<5d} w={r['w']:<5d} ({r['display']})")
                print()

                # 导航与内容网格对齐检查
                nav, hero = d["key"].get("nav"), d["key"].get("heroContent")
                if nav and hero and nav["display"] != "none":
                    nl = int(getattr(nav, "get", lambda *_: None)("l", nav["l"]))
                    pad_l = nav["l"]
                    # nav 是 0→viewport，用 brand 左边缘对比 heroContent 左边缘
                    brand = d["key"].get("brand")
                    if brand and brand["display"] != "none":
                        delta = abs(brand["l"] - hero["l"])
                        mark = "✓" if delta <= 6 else "✗"
                        print(f"  对齐检查: 品牌左边缘 {brand['l']} vs 内容左边缘 {hero['l']}"
                              f" → 差 {delta}px {mark}（≤6px 视为对齐，差值来自字形边距）\n")

                # 截图（同一视口，所以不会与上面的测量自相矛盾）
                if shot_dir:
                    # 注入 CSS 让入场动画直接以最终态渲染：
                    # 无头环境 motion 的动画循环不执行，不注入的话内容会停在 opacity:0
                    await cmd("Runtime.evaluate", {"expression": f"""
                        (() => {{
                          let s = document.getElementById('__verify_reveal');
                          if (!s) {{
                            s = document.createElement('style');
                            s.id = '__verify_reveal';
                            s.textContent = {json.dumps(REVEAL_CSS)};
                            document.head.appendChild(s);
                          }}
                        }})()
                    """})
                    await asyncio.sleep(0.6)
                    out_dir = Path(shot_dir)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    shot = await cmd("Page.captureScreenshot",
                                     {"format": "png", "captureBeyondViewport": False})
                    b64 = shot.get("result", {}).get("data")
                    if b64:
                        fp = out_dir / f"viewport-{w}.png"
                        fp.write_bytes(base64.b64decode(b64))
                        print(f"  截图 → {fp}\n")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="用 CDP 验证响应式布局是否有横向溢出，可选截图")
    ap.add_argument("--url", default="http://localhost:3300/")
    ap.add_argument("--widths", nargs="+", type=int, default=[375, 680, 768, 1440])
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--settle", type=float, default=5.0, help="每次导航后等待渲染的秒数")
    ap.add_argument("--shot-dir", default=None,
                    help="截图输出目录；截图走 CDP 同一视口，且注入 CSS 让动画以最终态渲染")
    a = ap.parse_args()
    return asyncio.run(run(a.url, a.widths, a.chrome or find_chrome(), a.settle, a.shot_dir))


if __name__ == "__main__":
    sys.exit(main())
