#!/usr/bin/env python
"""/quote 页面探针：列出真正溢出视口的元素（verify-v8 只给计数，这里给罪魁）。

用法：
    env -u PYTHONPATH python scripts/probe-quote-overflow.py --url http://127.0.0.1:3300/quote --width 1440
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
  const out = { vw, scrollW: de.scrollWidth, items: [] };
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.left < -1) {
      const cs = getComputedStyle(el);
      out.items.push({
        tag: el.tagName,
        cls: (el.className || '').toString().slice(0, 80),
        left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width),
        pos: cs.position, ow: cs.overflowX,
      });
    }
  }
  out.items = out.items.slice(0, 40);
  return out;
})()
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3300/quote")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    port = 9500 + (args.width % 100)
    profile = tempfile.mkdtemp(prefix="cdp-qo-")
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

        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
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
                      {"width": args.width, "height": args.height, "deviceScaleFactor": 1,
                       "mobile": args.width < 768})
            await cmd("Page.navigate", {"url": args.url})
            await asyncio.sleep(3.5)
            res = await cmd("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})
            data = res["result"]["value"]
            print(f"viewport {data['vw']}  scrollWidth {data['scrollW']}  overflow elements {len(data['items'])}")
            for it in data["items"]:
                print(f"  {it['tag']}.{it['cls']}  left={it['left']} right={it['right']} w={it['w']} pos={it['pos']} ox={it['ow']}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
