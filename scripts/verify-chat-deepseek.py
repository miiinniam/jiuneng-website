#!/usr/bin/env python3
"""右下角「AI 数字员工」对话换成 **DeepSeek** 的端到端验收 —— 全程真服务端编排 + 真工具执行。

为什么这么测：真 DeepSeek 要密钥、要花钱、每次回答都不一样；而「换 provider」这件事的风险点
**全在协议层**，跟模型聪明不聪明无关：

  ① 请求形状：model / stream:true / tools[].function / Authorization —— 少一个就是 4xx 或降级成不调工具
  ② 流式分片：工具参数在 OpenAI 协议里是**跨多片字符串拼接**的，必须拼完再 parse（拼一半就 parse → 必炸）
  ③ 配对：assistant.tool_calls[].id 必须与后续 role:'tool'.tool_call_id 一致，否则模型收到「无主结果」
  ④ 失败路径：DeepSeek 401/400 时**回退 Gemini**；Gemini 也没有时必须**如实报错**，
     绝不能让模型绕开工具自己编里程和价格（站内规矩，见 src/agent/content.ts 文件头）
  ⑤ 白名单：工具结果里混入 breakdown/profit_vnd/margin_rate/border_fees 等内部字段，官网一个都不许漏

所以本脚本用一个说 OpenAI 协议的**本地假 DeepSeek**（可控、可断言）把 ①–⑤ 钉死；
真 key 的活链路另用 `scripts/probe-chat-live.py` 打真站点。

用法： python scripts/verify-chat-deepseek.py      （前置：npm run build）
退出码：0 全过；1 有失败；2 前置缺失（找不到 node / dist/server.cjs）
"""

import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "dist", "server.cjs")
ERR_DIR = os.path.join(ROOT, "dist")

FAKE_KEY = "FAKE-DEEPSEEK-KEY-for-verify"        # 假钥匙：只验「有没有带上」，不涉及真密钥
FAKE_DEEPSEEK_MODEL = "deepseek-flash"
FAKE_PRICE = 77400453.3                          # 与生产基线同值 → 区间应为 69,700,000 / 85,100,000
LEAK_KEYS = ("breakdown", "profit_vnd", "margin_rate", "border_fees", "geometry", "cost_distance")
AVOID_PORTS = {18000, 18001, 33000}

fails: list[str] = []
procs: list[subprocess.Popen] = []


def pick_port() -> int:
    """在 16000–32000 取空闲端口（避开本机动态端口段 1024–15000，那会与站点自己的出站源端口撞车）。"""
    for _ in range(80):
        port = random.randint(16000, 32000)
        if port in AVOID_PORTS:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    print("✗ 找不到空闲端口（16000–32000）")
    sys.exit(2)


# ── 假引擎（与 verify-quote-timeout.py 同款：真字段名 + 内部字段诱饵）────────────

class FakeEngine(BaseHTTPRequestHandler):
    hits = 0

    def _send(self, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._send({"status": "ok"})

    def do_POST(self):
        type(self).hits += 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send({
            "price_vnd": FAKE_PRICE,
            "route": {"distance_km": 2243.0265, "adjusted_duration_h": 29.89},
            "vehicle_count": 1,
            "profile_honored": True,
            "suggestions": [{"code": "ok_note"}],
            "breakdown": {"fuel": 1},          # ↓ 诱饵：官网白名单必须一个都不回
            "profit_vnd": 999,
            "margin_rate": 0.2,
            "border_fees": {"x": 1},
            "geometry": "SECRET",
            "cost_distance": 1,
        })

    def log_message(self, *a):
        pass


def start_fake_engine():
    port = pick_port()
    FakeEngine.hits = 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeEngine)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, th, port


# ── 假 DeepSeek（OpenAI 兼容，SSE 流式 + 工具调用）────────────────────────────

class FakeDeepSeek(BaseHTTPRequestHandler):
    """三种模式：
    ok           → 第一轮分片吐工具调用，第二轮吐文本（覆盖分片拼接 + tool_call_id 配对）
    unauthorized → 401（覆盖「回退 Gemini」路径）
    no_tools     → 带 tools 的请求回 400（覆盖「模型不支持工具」是否如实报错）
    """

    protocol_version = "HTTP/1.0"     # 无 Content-Length → 客户端读到连接关闭（SSE 语义）
    mode = "ok"
    requests: list = []               # 每次请求的 path/auth/body/raw，供断言

    def log_message(self, *a):
        pass

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            self.send_error(404)
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = {}
        type(self).requests.append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": body,
            "raw": raw.decode("utf-8", "replace"),
        })

        if type(self).mode == "unauthorized":
            self._json(401, {"error": {"message": "Authentication Fails, Your api key is invalid"}})
            return
        if type(self).mode == "no_tools" and body.get("tools"):
            self._json(400, {"error": {"message": "tools is not supported by this model"}})
            return
        self._stream(body)

    def _json(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _chunk(self, delta: dict, finish=None) -> None:
        obj = {
            "id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": FAKE_DEEPSEEK_MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def _stream(self, body: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        msgs = body.get("messages") or []
        if any(m.get("role") == "tool" for m in msgs):
            for piece in ["根据引擎测算，", "南宁→河内约 2243 km、预计行驶 29.9 小时、1 车；",
                          "金额为参考价区间、初步测算，正式价格请提交询价。"]:
                self._chunk({"content": piece})
            self._chunk({}, finish="stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        # 第一轮：把工具参数**切成三片**吐（真实 OpenAI 协议就是分片的，必须拼完再 parse）
        args = json.dumps({"origin": "南宁", "destination": "河内", "weight_kg": 20000,
                           "mode": "full_truck", "vehicle_model_id": "flatbed_13m"}, ensure_ascii=False)
        cut = len(args) // 3
        pieces = [args[:cut], args[cut:2 * cut], args[2 * cut:]]
        self._chunk({"tool_calls": [{"index": 0, "id": "call_fake_1", "type": "function",
                                     "function": {"name": "query_route_cost", "arguments": ""}}]})
        for p in pieces:
            self._chunk({"tool_calls": [{"index": 0, "function": {"arguments": p}}]})
        self._chunk({}, finish="tool_calls")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def start_fake_deepseek(mode: str = "ok"):
    port = pick_port()
    FakeDeepSeek.mode = mode
    FakeDeepSeek.requests = []
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeDeepSeek)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, th, port


# ── 官网临时站点 ─────────────────────────────────────────────

def start_site(engine_port: int, extra_env: dict):
    port = pick_port()
    err_path = os.path.join(ERR_DIR, f"verify-chat-deepseek-{port}.err.log")
    env = {
        **os.environ,
        "NODE_ENV": "production",
        "PORT": str(port),
        "OSRM_API_BASE": f"http://127.0.0.1:{engine_port}",
        "OSRM_ENGINE_KEY": "verify-chat-test",     # 假钥匙：假引擎不校验
        # 下面三个由调用方通过 extra_env 明确指定（None = 不设），避免继承宿主环境造成假绿：
        "AGENT_CHAT_DEMO": None,
        "GEMINI_API_KEY": None,
        "DEEPSEEK_API_KEY": None,
        "DEEPSEEK_BASE_URL": None,
        "DEEPSEEK_MODEL": None,
        "CHAT_PROVIDER": None,
    }
    for k, v in extra_env.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    # ⚠️ Popen 的 env 不接受 None 值：上面用来**声明「不设该变量」**的 None 必须在这里滤掉
    #    （首跑就是崩在这行之前的 Popen 上）。滤掉 = 子进程环境里根本没有该变量，正是想要的语义。
    env = {k: v for k, v in env.items() if v is not None}
    err_file = open(err_path, "wb")
    proc = subprocess.Popen(["node", ENTRY], cwd=ROOT, env=env, stdout=err_file, stderr=err_file)
    procs.append(proc)
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"   ✗ 站点进程退出（exit {proc.returncode}），日志见 {err_path}")
            return None, None, err_path
        if curl(f"http://127.0.0.1:{port}/api/health", 3, want_code=True) == 200:
            return proc, port, err_path
        time.sleep(0.4)
    print(f"   ✗ 站点 30s 内没回 200（PORT={port}）")
    return None, None, err_path


def curl(url: str, timeout_s: float, want_code: bool = False):
    cmd = (["curl", "-s", "-m", str(int(timeout_s)), "-o", os.devnull, "-w", "%{http_code}", url]
           if want_code else ["curl", "-s", "-m", str(int(timeout_s)), url])
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout_s + 5)
    except subprocess.TimeoutExpired:
        return 0 if want_code else ""
    if want_code:
        try:
            return int(out.stdout.decode("utf-8", "replace").strip() or 0)
        except ValueError:
            return 0
    return out.stdout.decode("utf-8", "replace")


def chat(site_port: int, message: str, timeout_s: float = 90):
    """POST /api/agent-chat 读完整条 SSE（--data-binary @- 避免中文被 MSYS 弄乱）。"""
    payload = {"messages": [{"role": "user", "text": message}], "lang": "zh"}
    t0 = time.monotonic()
    try:
        out = subprocess.run(
            ["curl", "-s", "-N", "-m", str(int(timeout_s)),
             "-H", "Content-Type: application/json", "--data-binary", "@-",
             f"http://127.0.0.1:{site_port}/api/agent-chat"],
            input=json.dumps(payload).encode(), capture_output=True, timeout=timeout_s + 15)
        return time.monotonic() - t0, out.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return time.monotonic() - t0, "(curl 自己超时)"


def parse_sse(raw: str):
    events = []
    for block in raw.split("\n\n"):
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:]
        if ev and data is not None:
            try:
                events.append((ev, json.loads(data)))
            except ValueError:
                events.append((ev, {"_raw": data}))
    return events


def read_err(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def stop(proc, *srvs):
    for item in srvs:
        if item is None:
            continue
        srv, th = item
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def has_leak(text: str) -> str | None:
    low = text.lower()
    for k in LEAK_KEYS:
        if k.lower() in low:
            return k
    return None


# ── 主流程 ──────────────────────────────────────────────────

def main() -> int:
    if not shutil_which_node() or not os.path.exists(ENTRY):
        print("✗ 前置缺失：需要 node 与 dist/server.cjs（先 npm run build）")
        return 2

    print("=" * 68)
    print("DeepSeek 对话验收（假 DeepSeek 服务 + 假引擎 + 临时站点，不用真密钥）")
    print("=" * 68)

    # ── A 工具往返：DeepSeek 分片吐工具调用 → 官网真跑引擎 → 第二轮吐文本 ──
    print("\nA 协议链路：请求形状（model/stream/tools/Authorization）+ 分片参数拼接 + tool_call_id 配对")
    srv_e = srv_d = proc = None
    try:
        srv_e, th_e, eport = start_fake_engine()
        srv_d, th_d, dport = start_fake_deepseek("ok")
        proc, sport, err = start_site(eport, {
            "DEEPSEEK_API_KEY": FAKE_KEY,
            "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{dport}/v1",
        })
        if proc:
            elapsed, raw = chat(sport, "从南宁到河内 20 吨设备大概多少钱？")
            events = parse_sse(raw)
            kinds = [e for e, _ in events]
            print(f"   → {elapsed:.1f}s，事件序列：{kinds}")
            print(f"   → 假 DeepSeek 收到 {len(FakeDeepSeek.requests)} 次请求；假引擎命中 {FakeEngine.hits} 次")

            if len(FakeDeepSeek.requests) != 2:
                fails.append(f"A：应为 2 次模型请求（工具轮 + 文本轮），实际 {len(FakeDeepSeek.requests)}")
            if FakeEngine.hits < 1:
                fails.append("A：工具没真跑引擎（假引擎 0 次命中）")

            if FakeDeepSeek.requests:
                r0 = FakeDeepSeek.requests[0]
                b0 = r0["body"]
                if b0.get("model") != FAKE_DEEPSEEK_MODEL:
                    fails.append(f"A：model 应为 {FAKE_DEEPSEEK_MODEL}，实际 {b0.get('model')!r}")
                if b0.get("stream") is not True:
                    fails.append(f"A：必须 stream:true，实际 {b0.get('stream')!r}")
                if r0["auth"] != f"Bearer {FAKE_KEY}":
                    fails.append(f"A：Authorization 应为 Bearer <key>，实际 {r0['auth']!r}")
                tools = b0.get("tools") or []
                names = [(t.get("function") or {}).get("name") for t in tools]
                if not tools or any(t.get("type") != "function" for t in tools):
                    fails.append(f"A：tools 必须是 OpenAI 形状 [{{type:'function',function:{{...}}}}]，实际 {tools[:1]}")
                for need in ("query_route_cost", "lookup_service_info"):
                    if need not in names:
                        fails.append(f"A：tools 里缺少 {need}（实际 {names}）")
                msgs0 = b0.get("messages") or []
                if not msgs0 or msgs0[0].get("role") != "system":
                    fails.append(f"A：messages[0] 必须是 system，实际 {msgs0[:1]}")

            if len(FakeDeepSeek.requests) >= 2:
                b1 = FakeDeepSeek.requests[1]
                msgs1 = b1["body"].get("messages") or []
                tool_msgs = [m for m in msgs1 if m.get("role") == "tool"]
                if not tool_msgs:
                    fails.append(f"A：第二轮必须带 role:'tool' 的结果消息，实际角色序列 {[m.get('role') for m in msgs1]}")
                else:
                    if tool_msgs[0].get("tool_call_id") != "call_fake_1":
                        fails.append("A：tool_call_id 必须与流式给出的 id 配对（call_fake_1），"
                                     f"实际 {tool_msgs[0].get('tool_call_id')!r}")
                    if not isinstance(tool_msgs[0].get("content"), str):
                        fails.append("A：role:'tool' 的 content 必须是字符串（OpenAI 协议要求）")
                leak = has_leak(b1["raw"])
                if leak:
                    fails.append(f"A：出站请求里带上了内部字段 {leak!r}（白名单在 server/osrmQuote.ts 应已剥离）")

            leak = has_leak(raw)
            if leak:
                fails.append(f"A：SSE 里带上了内部字段 {leak!r}")
            texts = "".join(d.get("content", "") for e, d in events if e == "text")
            tool_done = [d for e, d in events if e == "tool_done"]
            if not any(e == "tool_start" and d.get("name") == "query_route_cost" for e, d in events):
                fails.append("A：缺少 tool_start(query_route_cost) 事件")
            if not tool_done or tool_done[0].get("ok") is not True:
                fails.append(f"A：tool_done 应为 ok=true，实际 {tool_done[:1]}")
            else:
                summary = tool_done[0].get("summary", "")
                if "69,700,000" not in summary:
                    fails.append(f"A：工具摘要里应含引擎回的真实区间（69,700,000），实际 {summary!r}")
                if "非正式报价" not in summary:
                    fails.append(f"A：工具摘要必须带「非正式报价」限定，实际 {summary!r}")
            if not texts.strip():
                fails.append("A：没有 text 事件（模型第二轮文本没流出来）")
            done = [d for e, d in events if e == "done"]
            if not done or done[0].get("tools") != 1:
                fails.append(f"A：done.tools 应为 1，实际 {done[:1]}")
            if not [f for f in fails if f.startswith("A")]:
                print("   ✓ 请求形状/分片拼接/id 配对/真引擎工具/文本流 全对，且内部字段零泄漏")
    finally:
        stop(proc, (srv_e, th_e) if srv_e else None, (srv_d, th_d) if srv_d else None)

    # ── B 失败路径：DeepSeek 401 + 没配 Gemini → 必须如实报错，不许编答案 ──
    print("\nB DeepSeek 401 且未配 Gemini：必须回退尝试 Gemini，失败后**如实报错**（不许假装答对）")
    srv_e = srv_d = proc = None
    try:
        srv_e, th_e, eport = start_fake_engine()
        srv_d, th_d, dport = start_fake_deepseek("unauthorized")
        proc, sport, err = start_site(eport, {
            "DEEPSEEK_API_KEY": "WRONG-KEY",
            "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{dport}/v1",
        })
        if proc:
            elapsed, raw = chat(sport, "南宁到河内多少钱？", timeout_s=60)
            events = parse_sse(raw)
            log = read_err(err)
            print(f"   → {elapsed:.1f}s，事件：{[e for e, _ in events]}")
            if FakeDeepSeek.requests and FakeDeepSeek.requests[0]["auth"] != "Bearer WRONG-KEY":
                fails.append(f"B：Authorization 应带上去配的密钥，实际 {FakeDeepSeek.requests[0]['auth']!r}")
            if not any(e == "error" for e, _ in events):
                fails.append("B：密钥无效时必须回 error 事件（不能静默）")
            texts = "".join(d.get("content", "") for e, d in events if e == "text")
            if texts.strip():
                fails.append(f"B：密钥无效时不该有文本回答（会变成编造），实际 {texts[:80]!r}")
            if "DeepSeek" not in log or "Gemini" not in log:
                fails.append("B：服务端日志应写明「DeepSeek 失败 → 回退 Gemini」（回退这件事必须可追溯）")
            if not [f for f in fails if f.startswith("B")]:
                print("   ✓ 401 走回退、无 Gemini 时如实报错，且日志可追溯")
    finally:
        stop(proc, (srv_e, th_e) if srv_e else None, (srv_d, th_d) if srv_d else None)

    # ── C 显式指定 provider：CHAT_PROVIDER=gemini 时不许碰 DeepSeek ──
    print("\nC CHAT_PROVIDER=gemini 强制指定：即使配了 DeepSeek 密钥也不许调它")
    srv_e = srv_d = proc = None
    try:
        srv_e, th_e, eport = start_fake_engine()
        srv_d, th_d, dport = start_fake_deepseek("ok")
        proc, sport, err = start_site(eport, {
            "DEEPSEEK_API_KEY": FAKE_KEY,
            "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{dport}/v1",
            "CHAT_PROVIDER": "gemini",
        })
        if proc:
            _, raw = chat(sport, "测试", timeout_s=45)
            events = parse_sse(raw)
            print(f"   → 假 DeepSeek 命中 {len(FakeDeepSeek.requests)} 次；事件：{[e for e, _ in events]}")
            if FakeDeepSeek.requests:
                fails.append(f"C：CHAT_PROVIDER=gemini 却调了 DeepSeek（{len(FakeDeepSeek.requests)} 次）")
            if not any(e == "error" for e, _ in events):
                fails.append("C：强制 gemini 但没配 GEMINI_API_KEY，应回 error 事件")
            if not [f for f in fails if f.startswith("C")]:
                print("   ✓ provider 强制生效（0 次 DeepSeek 调用）")
    finally:
        stop(proc, (srv_e, th_e) if srv_e else None, (srv_d, th_d) if srv_d else None)

    # ── D 回归：自测路由（脚本化假模型）—— 证明改 provider 没弄坏编排/工具/事件契约 ──
    print("\nD 回归 AGENT_CHAT_SELFTEST=1：脚本化假模型 + 真工具，事件契约必须与改造前一致")
    srv_e = proc = None

    def post_json(url: str, payload: dict, timeout_s: float) -> str:
        try:
            out = subprocess.run(
                ["curl", "-s", "-m", str(int(timeout_s)), "-H", "Content-Type: application/json",
                 "--data-binary", "@-", url],
                input=json.dumps(payload).encode(), capture_output=True, timeout=timeout_s + 10)
            return out.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            return ""

    try:
        srv_e, th_e, eport = start_fake_engine()
        proc, sport, err = start_site(eport, {"AGENT_CHAT_SELFTEST": "1"})
        if proc:
            raw = post_json(f"http://127.0.0.1:{sport}/api/agent-chat/selftest", {"scenario": "route"}, 60)
            body = json.loads(raw) if raw.strip().startswith("{") else {}
            kinds = [(e or {}).get("event") for e in (body.get("events") or [])]
            print(f"   → chatProvider={body.get('chatProvider')!r}；事件：{kinds}")
            for need in ("tool_start", "tool_done", "done"):
                if need not in kinds:
                    fails.append(f"D：selftest 事件缺少 {need}，实际 {kinds}")
            if "chatProvider" not in body:
                fails.append("D：selftest 响应应带 chatProvider（便于线上自检模型选择）")
            if not [f for f in fails if f.startswith("D")]:
                print("   ✓ 编排/工具/事件契约未受影响")
    finally:
        stop(proc, (srv_e, th_e) if srv_e else None)

    print("\n" + "=" * 68)
    if fails:
        print(f"✗ 失败 {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✓ 全部通过：DeepSeek 协议层（形状/分片/配对）+ 真工具链 + 失败回退 + 白名单零泄漏")
    return 0


def shutil_which_node() -> bool:
    from shutil import which
    return which("node") is not None


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
