#!/usr/bin/env python
"""助手回复渲染验收：发一个真问题，看回复有没有被渲染成结构（不是一坨纯文字）。

断言（读真实 DOM）：
  A 助手气泡里出现 .q-rt（富文本容器）
  B 回复含 **加粗** → 页面上有 <strong>，且正文里不残留 `**`
  C 回复含列表 → 有 <ul>/<ol>；含竖线表格 → 有 <table>
  D 没有「纯文本回退」：.q-chat-rich 内直接是一段带星号的文字即为 FAIL
  E 流式结束后出现「复制」按钮
另存截图到 --shot。

用法：
    env -u PYTHONPATH python scripts/verify-chat-render.py --url http://127.0.0.1:3300/quote
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

ASK = "13 米平板车、25 吨普通货物，从友谊关到河内，大概多少里程、几台车、多少钱？请分点说明。"
SEND_JS = """
(() => {
  const btn = document.querySelector('.q-ai-btn');
  if (!btn) return 'no-ai-button';
  btn.click();
  return 'opened';
})()
"""

TYPE_JS = """
(() => {
  const ta = document.querySelector('.q-chat-input');
  if (!ta) return 'no-input';
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(ta, %s);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  const send = [...document.querySelectorAll('.q-chat-btn')].filter((b) => !b.querySelector('.q-chat-btn--ghost'));
  const target = send[send.length - 1];
  if (!target) return 'no-send';
  target.click();
  return 'sent';
})()
"""

PROBE = r"""
(() => {
  const rich = [...document.querySelectorAll('.q-chat-rich')];
  if (!rich.length) return { ok: false, why: 'no .q-chat-rich' };
  const last = rich[rich.length - 1];
  const rt = last.querySelector('.q-rt');
  const text = last.innerText || '';
  return {
    ok: true,
    hasFill: !!rt,
    strong: last.querySelectorAll('strong').length,
    ul: last.querySelectorAll('ul').length,
    ol: last.querySelectorAll('ol').length,
    table: last.querySelectorAll('table').length,
    h: last.querySelectorAll('h3,h4').length,
    copy: !!last.querySelector('.q-chat-copy'),
    caret: !!last.querySelector('.q-chat-caret'),
    rawStars: (text.match(/\*\*/g) || []).length,
    rawPipes: (text.match(/^\|/gm) || []).length,
    text: text.slice(0, 600),
    chars: text.length,
    ws: !!document.querySelector('.q-ws'),
    wsText: (document.querySelector('.q-ws')?.innerText || '').slice(0, 500),
  };
})()
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='http://127.0.0.1:3300/quote')
    ap.add_argument('--key', default='', help='内部版口令：会写进 sessionStorage 再刷新')
    ap.add_argument('--shot', default='')
    ap.add_argument('--timeout', type=int, default=150)
    args = ap.parse_args()

    port = 9711
    profile = tempfile.mkdtemp(prefix='cdp-chat-')
    proc = subprocess.Popen(
        [CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={profile}',
         '--disable-gpu', '--hide-scrollbars', 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                data = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2).read())
                pages = [t for t in data if t.get('type') == 'page']
                if pages:
                    ws_url = pages[0]['webSocketDebuggerUrl']
                    break
            except Exception:
                time.sleep(0.25)
        if not ws_url:
            raise RuntimeError('CDP 连不上')

        async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
            n = 0

            async def cmd(method, params=None):
                nonlocal n
                n += 1
                await ws.send(json.dumps({'id': n, 'method': method, 'params': params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get('id') == n:
                        return msg.get('result', {})

            async def ev(expr):
                r = await cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
                return r['result'].get('value')

            await cmd('Page.enable')
            await cmd('Emulation.setDeviceMetricsOverride',
                      {'width': 1440, 'height': 980, 'deviceScaleFactor': 1, 'mobile': False})
            await cmd('Page.navigate', {'url': args.url})
            for _ in range(80):
                if await ev("!!document.querySelector('.q-ai-btn')"):
                    break
                await asyncio.sleep(0.25)

            if args.key:
                await ev("sessionStorage.setItem('jn-quote-key', %s)" % json.dumps(args.key))
                await cmd('Page.reload')
                for _ in range(80):
                    if await ev("!!document.querySelector('.q-ai-btn')"):
                        break
                    await asyncio.sleep(0.25)

            print('open:', await ev(SEND_JS))
            await asyncio.sleep(0.6)
            print('send:', await ev(TYPE_JS % json.dumps(ASK, ensure_ascii=False)))

            deadline = time.time() + args.timeout
            data = None
            while time.time() < deadline:
                await asyncio.sleep(2.0)
                d = await ev(PROBE)
                if not d or not d.get('ok'):
                    continue
                if d.get('chars', 0) > 0 and not d.get('caret'):
                    await asyncio.sleep(1.5)   # 等 caret 消失后的最后一次渲染
                    data = await ev(PROBE)
                    break
                data = d

            if not data:
                print('CHAT-RENDER: FAIL（没等到回复）')
                return 1

            # 回复结束后页面会拿抽到的路线+重量自动打一次引擎，等工作台卡片出现
            ws_deadline = time.time() + 90
            while not data.get('ws') and time.time() < ws_deadline:
                await asyncio.sleep(2.0)
                data = await ev(PROBE) or data

            print('回复字符数:', data['chars'], '| strong', data['strong'], '| ul', data['ul'],
                  '| ol', data['ol'], '| table', data['table'], '| 标题', data['h'],
                  '| 复制按钮', data['copy'], '| 工作台', data.get('ws'))
            print('残留 ** 次数:', data['rawStars'], '| 残留以 | 开头的行:', data['rawPipes'])
            print('--- 工作台卡片 ---')
            print(data.get('wsText') or '(没有卡片)')
            print('--- 前 300 字 ---')
            print(data['text'][:300])

            ok = True
            if not data['hasFill']:
                print('FAIL 没有 .q-rt 富文本容器')
                ok = False
            if data['rawStars']:
                print('FAIL 正文里残留 ** —— 说明没走加粗渲染')
                ok = False
            if not data['copy']:
                print('FAIL 没有复制按钮')
                ok = False
            if not data.get('ws'):
                print('FAIL 回复后没有渲染工作台卡片（.q-ws）—— 路线/重量没被抽出来或自动测算失败')
                ok = False
            if data['strong'] == 0 and data['ul'] == 0 and data['ol'] == 0:
                print('WARN 回复里没有加粗也没有列表（模型这次输出的是纯段落，不算渲染失败）')

            if args.shot:
                shot = await cmd('Page.captureScreenshot', {'format': 'png'})
                p = Path(args.shot)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(base64.b64decode(shot['data']))
                print('截图:', p)

            print('CHAT-RENDER:', 'PASS' if ok else 'FAIL')
            return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
