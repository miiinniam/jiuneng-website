#!/usr/bin/env python
"""报价页 5 步改版验收 —— 走**真实用户路径**点穿（walkthrough）。

为什么不能用步骤条跳转验收：`StepBar` 只允许回跳已走过的步骤（未到步的按钮 disabled），
这是正确 UX，但也意味着脚本没法「跳到第 4 步」看渲染。所以本脚本按真实流程走：

  1) 发货地/目的地：往 `.q-addr-input` 打字 → 等 geocode 防抖 → 点 `.q-suggest-item`
  2) 第 3 步：填总重量
  3) 第 4 步：等 `/api/quote/fit` 自动预填车型（没预填则手选第一辆，验证降级路径）
  4) 第 5 步：核对页 + 「提交测算」

断言：
  A 步骤条 5 步
  B 第 2 步 5 类货物分类齐全
  C 第 3 步 总重量 + 货值
  D 第 4 步 出现「引擎推荐」/「自动匹配暂不可用」（允许引擎未配置时降级）
  E 第 5 步 出现「提交测算」
  F 全程无 console error / 未捕获异常

用法：
    env -u PYTHONPATH python scripts/verify-quote-walkthrough.py --base http://127.0.0.1:3471
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
CLASS_NAMES = ["普通货物", "机械设备", "大型机械", "超大型超限货物", "小件货物"]

# 填两个地址：打字 → 等防抖 → 点该字段自己的建议项（没建议就按 Enter 选第一项）
FILL_ADDRS = r"""
(async () => {
  const setV = (el, v) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const groups = [...document.querySelectorAll('.q-addr')];
  const log = [];
  const pick = async (gi, text) => {
    const g = groups[gi];
    if (!g) { log.push({ gi, err: 'no-group' }); return false; }
    const inp = g.querySelector('.q-addr-input');
    if (!inp) { log.push({ gi, err: 'no-input' }); return false; }
    inp.focus();
    setV(inp, text);
    // 轮询等建议项出现（300ms 防抖 + 网络 + 渲染）—— 写死 1.1s 实测会漏，导致「没有匹配地址」误判
    let item = null;
    let waited = 0;
    for (let i = 0; i < 24; i++) {
      await new Promise(r => setTimeout(r, 150));
      waited += 150;
      item = g.querySelector('.q-suggest-item');
      if (item) break;
    }
    if (item) { item.click(); }
    else { inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); }
    await new Promise(r => setTimeout(r, 500));
    log.push({
      gi, text,
      valueAfter: inp.value,
      suggest: !!item,
      waitedMs: waited,
      none: (g.innerText || '').includes('没有匹配'),
      connected: document.contains(inp),
    });
    return true;
  };
  await pick(0, '凭祥');
  await pick(1, '河内');
  await new Promise(r => setTimeout(r, 600));
  return log;
})()
"""

NEXT = r"""
(() => {
  const b = [...document.querySelectorAll('button')]
    .find(x => /下一步/.test(x.textContent || '') && !x.disabled);
  if (!b) return 'no-button';
  b.click();
  return 'clicked';
})()
"""

PROBE = r"""
(() => {
  const steps = [...document.querySelectorAll('.q-step .q-step-l')].map(e => e.textContent.trim());
  const cur = document.querySelector('.q-step.is-current .q-step-l');
  const panel = document.querySelector('.q-panel') || document.body;
  const body = (panel.innerText || '').slice(0, 6000);
  return { steps, cur: cur ? cur.textContent.trim() : null, body };
})()
"""


async def run(base: str) -> int:
    port = 9713
    profile = tempfile.mkdtemp(prefix="cdp-qw-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--disable-gpu", "--hide-scrollbars", "--force-prefers-reduced-motion", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ok = True
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
            errors: list[str] = []

            async def cmd(method, params=None):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == n:
                        return msg.get("result", {})
                    m = msg.get("method")
                    if m == "Runtime.exceptionThrown":
                        d = msg["params"].get("exceptionDetails", {})
                        errors.append("exception: " + str(
                            d.get("exception", {}).get("description") or d.get("text"))[:200])
                    elif m == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
                        args = msg["params"].get("args", [])
                        errors.append("console.error: " + " ".join(
                            str(a.get("value") or a.get("description") or "") for a in args)[:200])

            async def js(expr: str, await_promise: bool = False):
                r = await cmd("Runtime.evaluate", {
                    "expression": expr, "returnByValue": True, "awaitPromise": await_promise})
                return r.get("result", {}).get("value")

            async def probe():
                return await js(PROBE)

            await cmd("Runtime.enable")
            await cmd("Page.enable")
            await cmd("Emulation.setDeviceMetricsOverride",
                      {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await cmd("Page.navigate", {"url": base + "/quote"})
            await asyncio.sleep(4.5)

            print("══ A 步骤条 ══")
            d = await probe()
            print(f"  {d['steps']}")
            if len(d["steps"]) != 5:
                print(f"  FAIL 步骤数 {len(d['steps'])}，期望 5")
                ok = False
            else:
                print("  OK   5 步")

            print("══ 第 1 步：地址 ══")
            addr_log = await js(FILL_ADDRS, await_promise=True)
            print(f"  填写过程: {json.dumps(addr_log, ensure_ascii=False)}")
            d = await probe()
            body = d["body"] or ""
            if "km" in body or "里程" in body:
                print("  OK   地址已选，里程已出")
            else:
                print("  WARN 未见里程（geocode 可能无结果），仍继续")
            r = await js(NEXT)
            print(f"  下一步：{r}")
            await asyncio.sleep(0.9)

            print("══ 第 2 步：货物分类 ══")
            d = await probe()
            if d["cur"] != "货物分类":
                print(f"  FAIL 未进入第 2 步（当前：{d['cur']}）")
                ok = False
            else:
                body = d["body"] or ""
                missing = [c for c in CLASS_NAMES if c not in body]
                if missing:
                    print("  FAIL 缺分类:", missing)
                    ok = False
                else:
                    print("  OK   5 类齐全")
                    clicked = await js(
                        "(() => { const b=[...document.querySelectorAll('.q-class')]"
                        ".find(x=>/超大型超限/.test(x.textContent||'')); if(!b) return false; b.click(); return true; })()")
                    print(f"  选中「超大型超限」：{clicked}")
                    await asyncio.sleep(0.35)
                    r = await js(NEXT)
                    print(f"  下一步：{r}")
                    await asyncio.sleep(0.9)

            print("══ 第 3 步：重量与明细 ══")
            d = await probe()
            body = d["body"] or ""
            missing = [c for c in ("货物重量", "货值") if c not in body]
            if missing:
                print(f"  FAIL 缺字段 {missing} | 正文前 160 字: {body[:160]}")
                ok = False
            else:
                print("  OK   货物重量 + 货值都在")
                filled = await js(
                    "(() => {"
                    " const panel=document.querySelector('.q-panel')||document.body;"
                    " const inp=panel.querySelector('.q-inline .q-input')||panel.querySelector('.q-input');"
                    " if(!inp) return 'no-input';"
                    " const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
                    " s.call(inp,'25'); inp.dispatchEvent(new Event('input',{bubbles:true}));"
                    " return 'filled'; })()")
                print(f"  填总重：{filled}")
                # 再加一条单件明细（超限货必须有尺寸，否则第 4 步走的是降级路径，
                # 测不到「引擎推荐 + 许可档位」这条主路径）
                detail = await js(
                    "(() => {"
                    " const panel=document.querySelector('.q-panel')||document.body;"
                    " const add=[...panel.querySelectorAll('button')].find(b=>/添加单件/.test(b.textContent||''));"
                    " if(!add) return 'no-add-btn';"
                    " add.click();"
                    " return 'added'; })()")
                await asyncio.sleep(0.5)
                detail2 = await js(
                    "(() => {"
                    " const panel=document.querySelector('.q-panel')||document.body;"
                    " const item=panel.querySelector('.q-item');"
                    " if(!item) return 'no-item';"
                    " const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
                    " const ins=[...item.querySelectorAll('input')];"
                    " const vals=['塔筒节','30','3','3','25','1'];"
                    " ins.slice(0,6).forEach((el,i)=>{ s.call(el,vals[i]); el.dispatchEvent(new Event('input',{bubbles:true})); });"
                    " return 'inputs='+ins.length; })()")
                print(f"  加明细：{detail} / 填值：{detail2}")
                await asyncio.sleep(0.6)
                r = await js(NEXT)
                print(f"  下一步：{r}")
                await asyncio.sleep(1.2)

            print("══ 第 4 步：车型推荐 ══")
            await asyncio.sleep(2.5)     # 等 /api/quote/fit
            d = await probe()
            body = d["body"] or ""
            hit = [k for k in ("引擎推荐", "自动匹配暂不可用", "正在按货物匹配", "超限货物请先") if k in body]
            if hit:
                print(f"  OK   推荐区出现（{hit[0]}）")
            else:
                print(f"  FAIL 既无推荐卡也无降级提示 | 正文前 200 字: {body[:200]}")
                ok = False
            r = await js(NEXT)
            if r == "no-button":
                picked = await js(
                    "(() => { const b=document.querySelector('.q-vrow'); if(!b) return false; b.click(); return true; })()")
                print(f"  推荐未预填车型，手选第一辆：{picked}")
                await asyncio.sleep(0.5)
                r = await js(NEXT)
            print(f"  下一步：{r}")
            await asyncio.sleep(0.9)

            print("══ 第 5 步：提交确认 ══")
            d = await probe()
            body = d["body"] or ""
            if "提交测算" not in body and d["cur"] != "提交测算":
                print(f"  FAIL 未到提交页（当前：{d['cur']}）| 正文前 200 字: {body[:200]}")
                ok = False
            else:
                has_review = any(k in body for k in ("线路", "货物", "车型", "许可"))
                print(f"  OK   到提交页；核对表：{'有' if has_review else '未见'}")

            print("══ F 控制台 ══")
            if errors:
                print(f"  FAIL {len(errors)} 条运行时错误:")
                for e in errors[:6]:
                    print("    -", e)
                ok = False
            else:
                print("  OK   无 console error / 未捕获异常")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print("QUOTE-WALKTHROUGH:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:3471")
    args = ap.parse_args()
    return asyncio.run(run(args.base))


if __name__ == "__main__":
    raise SystemExit(main())
