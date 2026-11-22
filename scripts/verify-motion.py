#!/usr/bin/env python
"""动效层验收（v9.1）：用 CDP 读真实计算样式，不靠"看着挺顺".

断言的都是会失败的东西：
  A 基线：过渡是显式属性（不是 all）、时长走令牌、触屏点击无延迟、
          悬停按钮真的变色、悬停分类卡的下划线真的长出来；
  B 触屏（hover: none）：悬停样式**不生效**（防点完粘住）；
  C 减少动效（prefers-reduced-motion: reduce）：过渡时长归零、锚点滚动不滑。

用法：
    NODE_ENV=production PORT=3300 node dist/server.cjs
    env -u PYTHONPATH python scripts/verify-motion.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

READ = r"""
(() => {
  const pick = (sel) => document.querySelector(sel);
  const cs = (el, pseudo) => el ? getComputedStyle(el, pseudo || null) : null;
  const btn = pick('.btn');
  const entry = pick('.cat-entry');
  const meta = entry ? entry.querySelector('.cat-entry-meta') : null;
  const idx = pick('.cat-index a');
  const out = {
    scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
    btn: null, entry: null, idx: null, after: null,
  };
  if (btn) {
    const s = cs(btn);
    out.btn = {
      transitionProperty: s.transitionProperty,
      transitionDuration: s.transitionDuration,
      touchAction: s.touchAction,
      bg: s.backgroundColor,
      transform: s.transform,
    };
  }
  if (entry) {
    const s = cs(entry);
    out.entry = { touchAction: s.touchAction, transitionDuration: s.transitionDuration, transform: s.transform };
  }
  if (idx) out.idx = { transitionDuration: cs(idx).transitionDuration };
  if (meta) out.after = { transform: cs(meta, '::after').transform };
  return out;
})()
"""


async def _rect(cmd, selector: str):
    r = await cmd(
        "Runtime.evaluate",
        {
            "expression": f"(() => {{ const e = document.querySelector({selector!r});"
            " if (!e) return null; const r = e.getBoundingClientRect();"
            " return {x: r.x + r.width/2, y: r.y + r.height/2}; })()",
            "returnByValue": True,
        },
    )
    return r["result"].get("value")


async def hover(cmd, selector: str) -> bool:
    # 注意：本站锚点滚动是 smooth，scrollIntoView 会动画——必须等它停再量坐标，
    # 否则鼠标落在滚动前的位置上，:hover 永远进不去（第一版就栽在这）。
    await cmd(
        "Runtime.evaluate",
        {"expression": f"(() => {{ const e = document.querySelector({selector!r});"
                       " if (e) e.scrollIntoView({block:'center', behavior:'instant'}); })()"},
    )
    await asyncio.sleep(0.35)
    pt = await _rect(cmd, selector)
    if not pt:
        return False
    await cmd("Input.dispatchMouseEvent",
              {"type": "mouseMoved", "x": pt["x"], "y": pt["y"], "buttons": 0, "pointerType": "mouse"})
    await asyncio.sleep(0.5)  # 等过渡跑完（最长 240ms）
    return True


async def unhover(cmd):
    await cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 2, "y": 2, "button": "none"})
    await asyncio.sleep(0.35)


async def main_async(url: str) -> int:
    port = 9420
    profile = tempfile.mkdtemp(prefix="cdp-motion-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--disable-gpu", "--hide-scrollbars", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    fails: list[str] = []
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

        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            n = 0

            async def cmd(method: str, params: dict | None = None) -> dict:
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == n:
                        return msg.get("result", {})

            async def evaluate() -> dict:
                r = await cmd("Runtime.evaluate", {"expression": READ, "returnByValue": True})
                return r["result"]["value"]

            def check(cond: bool, ok: str, bad: str):
                print(("  OK  " if cond else "  X   ") + (ok if cond else bad))
                if not cond:
                    fails.append(bad)

            await cmd("Page.enable")
            await cmd("Emulation.setDeviceMetricsOverride",
                      {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await cmd("Page.navigate", {"url": url})
            await asyncio.sleep(2.5)

            # ── A 基线 ─────────────────────────────────────────
            print("── A 基线（hover 可用 / 正常动效）")
            base = await evaluate()
            check(base["scrollBehavior"] == "smooth", "锚点平滑滚动 = smooth", f"scroll-behavior={base['scrollBehavior']}（应 smooth）")

            hover_works = False
            btn = base["btn"]
            if btn:
                props = btn["transitionProperty"].split(",")
                props = [p.strip() for p in props]
                check("all" not in props, "按钮过渡不是 transition: all", f"按钮用了 transition: all（{btn['transitionProperty']}）")
                for need in ("background-color", "border-color", "color", "transform"):
                    check(need in props, f"按钮过渡含 {need}", f"按钮缺 {need} 过渡（{btn['transitionProperty']}）")
                check(btn["touchAction"] == "manipulation", "按钮 touch-action=manipulation",
                      f"按钮 touch-action={btn['touchAction']}（触屏会有 300ms 点按延迟）")
                resting = btn["bg"]
                await hover(cmd, ".btn")
                hov = await evaluate()
                hover_works = hov["btn"]["bg"] != resting
                check(hover_works, f"悬停按钮底色变化（{resting} → {hov['btn']['bg']}）",
                      f"悬停按钮底色没变（{resting}）——鼠标事件没进到元素，或 :hover 规则没生效")
                await unhover(cmd)
            else:
                fails.append("页面没有 .btn，A 段无效")

            entry = base["entry"]
            if entry:
                check(entry["touchAction"] == "manipulation", "分类卡 touch-action=manipulation",
                      f"分类卡 touch-action={entry['touchAction']}")
                a0 = base["after"]["transform"] if base["after"] else ""
                await hover(cmd, ".cat-entry")
                hovE = await evaluate()
                a1 = hovE["after"]["transform"] if hovE["after"] else ""
                grown = a1.startswith("matrix(") and abs(float(a1[7:a1.index(",")]) - 1.0) < 0.02
                check(grown, f"悬停分类卡下划线长出（{a0} → {a1}）", f"悬停分类卡下划线没长（{a0} → {a1}）")
                await unhover(cmd)
            else:
                print("  -   本页无 .cat-entry（首页才有），跳过卡片项")

            # ── C 减少动效 ──────────────────────────────────────
            print("── C 减少动效（prefers-reduced-motion: reduce）")
            await cmd("Emulation.setEmulatedMedia",
                      {"media": "screen", "features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
            await asyncio.sleep(0.3)
            red = await evaluate()
            check(red["scrollBehavior"] == "auto", "reduce 下锚点不滑动（auto）", f"reduce 下仍 {red['scrollBehavior']}（应 auto）")
            if red["btn"]:
                dur = red["btn"]["transitionDuration"]
                allzero = all(float(x.strip().rstrip("s") or 0) == 0 for x in dur.split(","))
                check(allzero, f"reduce 下按钮过渡归零（{dur}）", f"reduce 下仍有过渡时长（{dur}）")

            # ── B 触屏 ─────────────────────────────────────────
            print("── B 触屏（hover: none）")
            # Chrome 的 setEmulatedMedia 不支持 hover/pointer；只有「移动端指标 + 触摸模拟」
            # 才会真的把 (hover:none) and (pointer:coarse) 打开。所以先断言媒体查询真的翻了。
            await cmd("Emulation.setEmulatedMedia",
                      {"media": "screen", "features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
            await cmd("Emulation.setDeviceMetricsOverride",
                      {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True})
            await cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
            await asyncio.sleep(0.4)
            gate = await cmd("Runtime.evaluate", {
                "expression": "matchMedia('(hover: hover) and (pointer: fine)').matches",
                "returnByValue": True})
            gate_matches = gate["result"]["value"]
            if gate_matches:
                print("  -   B 段无效：(hover:hover) 仍为真，触摸模拟没生效")
                fails.append("B 段无效（触摸模拟没生效，媒体查询未翻转）")
                gate_matches = None
            before = await evaluate()
            await hover(cmd, ".btn")
            after = await evaluate()
            if gate_matches is None:
                pass
            elif not hover_works:
                # 先证明"悬停本来会变色"，否则这段永远是绿的：假通过。
                print("  -   B 段无效：A 段悬停未生效，无法判断门禁是否起作用")
                fails.append("B 段无效（A 段悬停未生效）")
            elif before["btn"]:
                check(before["btn"]["bg"] == after["btn"]["bg"],
                      "触屏悬停不改底色（无粘住的假选中态）",
                      f"触屏悬停仍变色（{before['btn']['bg']} → {after['btn']['bg']}），说明 @media (hover:hover) 门禁没生效")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    if fails:
        print("\n失败 %d 项：" % len(fails))
        for f in fails:
            print("  X", f)
        return 1
    print("\n动效层全部通过")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3300/")
    a = ap.parse_args()
    sys.exit(asyncio.run(main_async(a.url)))
