#!/usr/bin/env python
"""v10 动效探针：证明 GSAP 真的在跑（不是"代码写了但没接上"）。

不截图、不靠肉眼，直接读：
  A 无 reduce：Hero 照片 clip-path 在加载瞬间是被裁的（动画进行中），2.5s 后回到完整矩形；
             标题行 transform 从非 0 位移回 0。
  B 无 reduce：滚到句点段时 .tagline-w 的 opacity 处于 0.28..1 之间（scrub 进行中），滚过之后为 1。
  C 有 reduce：clip-path 全程 none、transform 全程 none、.tagline-w 全程 opacity 1（内容不消失）。
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SAMPLE = r"""
(() => {
  const img = document.querySelector('.hero-fig img');
  const line = document.querySelector('.hero-t-line');
  const words = [...document.querySelectorAll('.tagline-w')];
  const cs = img ? getComputedStyle(img) : null;
  return {
    clip: cs ? cs.clipPath : null,
    imgTransform: cs ? cs.transform : null,
    lineTransform: line ? getComputedStyle(line).transform : null,
    lineOpacity: line ? getComputedStyle(line).opacity : null,
    scrollY: Math.round(window.scrollY),
    words: words.map(w => Number(getComputedStyle(w).opacity.slice(0, 5))),
  };
})()
"""


async def run(reduce: bool, url: str) -> dict:
    port = 9411 if reduce else 9410
    profile = tempfile.mkdtemp(prefix="cdp-m10-")
    args = [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--disable-gpu", "--hide-scrollbars", "about:blank"]
    if reduce:
        args.insert(-1, "--force-prefers-reduced-motion")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

            async def ev(expr):
                r = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                return r["result"].get("value")

            await cmd("Page.enable")
            await cmd("Emulation.setDeviceMetricsOverride",
                      {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await cmd("Page.navigate", {"url": url})
            # 等 React 挂载完（首包下载 + 渲染），再抓动画进行中的一帧
            for _ in range(60):
                ready = await ev("!!document.querySelector('.hero-fig img')")
                if ready:
                    break
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.45)
            early = await ev(SAMPLE)
            await asyncio.sleep(2.6)
            settled = await ev(SAMPLE)
            # 滚到句点段 scrub 区间的 45%（起点 top 82% / 终点 bottom 55%）
            await ev("(() => { const t = document.querySelector('.tagline');"
                     " const vh = innerHeight;"
                     " const s = t.offsetTop - 0.82 * vh;"
                     " const e = t.offsetTop + t.offsetHeight - 0.55 * vh;"
                     " window.scrollTo(0, s + (e - s) * 0.45); })()")
            await asyncio.sleep(1.0)
            mid = await ev(SAMPLE)
            await ev("(() => { const t = document.querySelector('.tagline');"
                     " window.scrollTo(0, t.offsetTop + t.offsetHeight * 1.6); })()")
            await asyncio.sleep(1.0)
            past = await ev(SAMPLE)
            # 案例段第一张照片的 moment：滚到 scrub 区间 50%（图顶 92% → 45%）
            await ev("(() => { const f = document.querySelector('[data-moment=\"expand\"]');"
                     " const vh = innerHeight;"
                     " const s = f.offsetTop - 0.92 * vh;"
                     " const e = f.offsetTop - 0.45 * vh;"
                     " window.scrollTo(0, s + (e - s) * 0.5); })()")
            await asyncio.sleep(1.2)
            moment = await ev("(() => { const i = document.querySelector('[data-moment=\"expand\"] img');"
                              " return { clip: getComputedStyle(i).clipPath, t: getComputedStyle(i).transform,"
                              " y: Math.round(scrollY) }; })()")
            await ev("(() => { const f = document.querySelector('[data-moment=\"expand\"]');"
                     " window.scrollTo(0, f.offsetTop - innerHeight * 0.2); })()")
            await asyncio.sleep(1.0)
            momentEnd = await ev("(() => { const i = document.querySelector('[data-moment=\"expand\"] img');"
                                 " return { clip: getComputedStyle(i).clipPath, t: getComputedStyle(i).transform }; })()")
            return {"early": early, "settled": settled, "mid": mid, "past": past,
                    "moment": moment, "momentEnd": momentEnd}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3300/"
    ok = True

    a = asyncio.run(run(False, url))
    print("── A/B 无 reduce ──")
    print("  early  clip:", a["early"]["clip"], "| line:", a["early"]["lineTransform"],
          "| words[0..3]:", a["early"]["words"][:4])
    print("  settle clip:", a["settled"]["clip"], "| line:", a["settled"]["lineTransform"])
    print("  mid    words:", [round(w, 2) for w in a["mid"]["words"]],
          "| scrollY:", a["mid"]["scrollY"])
    print("  past   words:", [round(w, 2) for w in a["past"]["words"]],
          "| scrollY:", a["past"]["scrollY"])
    print("  moment mid clip:", a["moment"]["clip"], "| transform:", a["moment"]["t"])
    print("  moment end clip:", a["momentEnd"]["clip"], "| transform:", a["momentEnd"]["t"])
    if "inset" in (a["moment"]["clip"] or "") and "inset(0%" not in (a["moment"]["clip"] or ""):
        print("  OK   案例照片 moment 处于中间展开态")
    else:
        print("  FAIL 案例照片 moment 没有展开过程：", a["moment"]["clip"])
        ok = False
    if (a["momentEnd"]["clip"] or "").startswith(("inset(0%", "inset(0px", "none")):
        print("  OK   moment 结束时照片满格")
    else:
        print("  FAIL moment 结束仍未满格：", a["momentEnd"]["clip"])
        ok = False

    if "inset" not in (a["early"]["clip"] or ""):
        print("  FAIL 入场瞬间照片没有被裁 —— GSAP 没跑")
        ok = False
    else:
        print("  OK   入场瞬间照片被 clip-path 裁切（动画进行中）")
    if a["settled"]["clip"] not in ("none", "inset(0px)", "inset(0%)"):
        print("  WARN 2.6s 后 clip 仍未归位：", a["settled"]["clip"])
    else:
        print("  OK   动画结束回到完整矩形")
    mids = a["mid"]["words"]
    if mids and any(0.3 < w < 0.99 for w in mids):
        print("  OK   句点段 scrub 处于中间浓度（滚动进度驱动）")
    else:
        print("  FAIL 句点段没有中间态：", mids)
        ok = False
    if a["past"]["words"] and all(w > 0.99 for w in a["past"]["words"]):
        print("  OK   滚过之后全部实色")
    else:
        print("  FAIL 滚过之后没有全部实色：", a["past"]["words"])
        ok = False

    c = asyncio.run(run(True, url))
    print("── C 有 reduce ──")
    print("  early clip:", c["early"]["clip"], "| line:", c["early"]["lineTransform"],
          "| words:", [round(w, 2) for w in c["early"]["words"][:4]])
    if (c["early"]["clip"] in ("none", "inset(0px)", "inset(0%)")
            and c["early"]["lineTransform"] in ("none", "matrix(1, 0, 0, 1, 0, 0)")
            and all(w > 0.99 for w in c["early"]["words"])):
        print("  OK   reduce 下无动画、内容全实色")
    else:
        print("  FAIL reduce 下仍有动画或内容被压暗")
        ok = False

    print("MOTION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
