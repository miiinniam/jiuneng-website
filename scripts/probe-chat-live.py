"""AI 对话**真服务端**端到端（无任何请求拦截/伪造）：
浏览器点开对话 → 真发 /api/agent-chat(SSE) → 服务端编排 → 真引擎工具 → 渲染回复。

为什么单独写：原 probe-chat-ui.py 用 CDP Fetch 伪造 SSE，从没跑过服务端这条路由，
所以「req.on('close') 让 SSE 一个事件都发不出去」的 bug 一直没被探针发现。

用法： python probe-chat-live.py [base_url]
"""
import asyncio, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3300"

ASK = "从南宁到河内20吨货大概多少钱"

SEND = r"""
(() => {
  const el = document.querySelector('.jx-chat-input');
  const btn = document.querySelector('.jx-chat-send');
  if (!el || !btn) return JSON.stringify({ ok: false });
  const proto = window.HTMLTextAreaElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, %s);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  btn.click();
  return JSON.stringify({ ok: true, btnDisabled: btn.disabled });
})()
""" % json.dumps(ASK, ensure_ascii=False)

READ = r"""
(() => {
  const q = (s) => document.querySelector(s);
  const msgs = [...document.querySelectorAll('.jx-chat-list > *')].map(e => e.innerText.trim());
  return JSON.stringify({
    fab: !!q('.jx-chat-fab'),
    panelOpen: !!q('.jx-chat-panel'),
    bubbles: [...document.querySelectorAll('.jx-chat-p, .jx-chat-b, .jx-chat-msg')].map(e => e.innerText.trim()),
    msgCount: document.querySelectorAll('.jx-chat-msg').length,
    msgRoles: [...document.querySelectorAll('.jx-chat-msg')].map(e => e.className),
    tools: [...document.querySelectorAll('.jx-chat-tool')].map(e => e.innerText.trim()),
    typing: !!q('.jx-chat-typing'),
    inputDisabled: q('.jx-chat-input') ? q('.jx-chat-input').disabled : null,
    disclaimer: (q('.jx-chat-disclaimer')?.innerText || '').trim(),
    listText: (q('.jx-chat-list')?.innerText || '').trim(),
    allText: document.body.innerText,
    overflow: { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth },
  });
})()
"""


async def main():
    port = 9803
    profile = Path(tempfile.gettempdir()) / "jx-chat-live"
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
                             "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            async def ev(expr):
                r = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                v = r.get("result", {}).get("result", {}).get("value")
                return json.loads(v) if v else None

            await cmd("Page.enable"); await cmd("Runtime.enable")
            await cmd("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await cmd("Page.navigate", {"url": f"{BASE}/ai?lang=zh"})
            await pump(3.5)

            print(f"===== 对话真链路 {BASE}/ai =====")
            await cmd("Runtime.evaluate", {"expression": "document.querySelector('.jx-chat-fab').click(); 1"})
            await pump(1.0)
            st0 = await ev(READ)
            print(f"  面板打开: {bool(st0 and st0['panelOpen'])}")

            sent = await ev(SEND)
            print(f"  发送: {sent}")
            await pump(3.0)
            st = await ev(READ)
            if not st:
                print("  ✗ 读不到状态"); fails.append("读不到状态")
            else:
                for m in st["bubbles"]:
                    print(f"    · 气泡: {m[:110]}")
                for t in st["tools"]:
                    print(f"    · 工具条: {t[:110]}")
                print(f"  打字中: {st['typing']} | 输入框禁用: {st['inputDisabled']}")
                print(f"  免责声明: {st['disclaimer'][:70]}")

                def need(cond, msg):
                    if not cond:
                        fails.append(msg)

                need(st0 and st0["panelOpen"], "对话面板没打开")
                need(bool(st["bubbles"]), "没有气泡（回复未渲染）")
                joined = st["listText"]
                need("初步测算" in joined or "参考价" in joined, "回复里没有测算/口径内容（SSE 可能为空流）")
                need("km" in joined or "公里" in joined, "回复里没有里程（工具未执行）")
                need(not st["typing"], "仍在打字状态（流没结束）")
                need(st["inputDisabled"] is False, "输入框仍禁用")
                need(st["overflow"]["sw"] <= st["overflow"]["cw"] + 1, "横向溢出")
                print(f"  消息节点数: {st['msgCount']}  类名: {st['msgRoles']}")
                need(st["msgCount"] == 2, f"消息节点数应为 2（用户+助手），实际 {st['msgCount']}")
                print("  ✓ 面板、气泡、工具条、口径、流结束、无溢出" if not fails else "  ✗ 见上面")
    finally:
        proc.terminate()
    print("\n" + ("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails)))
    return 1 if fails else 0


sys.exit(asyncio.run(main()))
