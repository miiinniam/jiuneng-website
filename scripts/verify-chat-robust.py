#!/usr/bin/env python3
"""「对话不许静默」验收 —— 模型不吐字 / 中途抛错时，客户端必须仍拿到兜底正文 + done。

为什么需要它：线上真实事故 —— 客户问「上海到河内 20 吨多少钱」，SSE 只发了 tool_start/tool_done
就断了：**0 字正文、连 done 都没有**，客户点了发送什么也看不到。两个根因：

  ① 工具调完但模型一个字都没回（空回复 / 只吐了工具调用就停）→ 客户端看着转圈，正文永远是空的
  ② 模型中途抛错（第 2 轮调用失败）→ 异常抛到 server.ts 的 catch，「已吐出过内容」的分支
     只写一行 console.error、**一个 SSE 事件都不写** → 客户端连 done 都等不到

所以本脚本只钉一件事：**无论模型多不配合，客户端可见的事件序列必须收尾**（兜底正文 + done）。

  E1 scenario=empty  自测路由：模型一个事件都不吐           → 非空 text + done
  E2 scenario=abort  自测路由：先吐工具调用，第 2 轮抛错      → tool_start + tool_done + 非空 text + done
  E3 scenario=route  自测路由回归：正常路径不许被改坏         → 非空 text（含 (selftest)）+ done
  E4 真 SSE + 假 DeepSeek：工具轮完第 2 轮**空流**            → tool_start + tool_done + 非空 text + done
  E5 真 SSE + 假 DeepSeek：工具轮完第 2 轮**HTTP 500**        → tool_start + tool_done + 非空 text + done

E4/E5 特意打到**真实 SSE 路由**（/api/agent-chat）：缺陷若修在 server.ts 的 SSE catch 分支
（而不是编排层），只在自测 JSON 路由上断言会漏掉 —— 两条路径都得给出兜底正文 + done。

全程本地假模型 + 假引擎 + 临时站点：**不碰真密钥、不花钱**（假 DeepSeek 只验协议，不真调用）。
临时站点自带 AGENT_CHAT_SELFTEST=1 / 假引擎地址等环境，跑完即收，不影响你已开着的进程。

用法： python scripts/verify-chat-robust.py        （前置：npm run build）
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

FAKE_DEEPSEEK_KEY = "FAKE-KEY-for-verify-chat-robust"   # 假钥匙：只验协议，不涉及真密钥
FAKE_DEEPSEEK_MODEL = "deepseek-flash"
FAKE_PRICE = 77400453.3
AVOID_PORTS = {18000, 18001, 33000}

fails: list[str] = []
results: list[tuple[str, bool, str]] = []      # (场景名, 是否通过, 事件序列)
harness_notes: list[str] = []                  # 只记录「假引擎这一跳偶发」这类**非被测缺陷**的干扰
procs: list[subprocess.Popen] = []

# 假引擎侧连接级故障的摘要字样（见 server/osrmQuote.ts 的 reason 文案）：
# 命中它 = 本机 loopback 上这一跳没打通，不是「产品把工具跑挂了」。
HARNESS_HINTS = ("引擎连接失败", "engine_unreachable", "engine_error", "unreachable")


def pick_port() -> int:
    """在 **16000–32000** 取空闲端口（避开本机动态端口段，那会与站点出站源端口撞车）。"""
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


def fail(label: str, msg: str) -> None:
    fails.append(f"{label}：{msg}")


# ── 假引擎：让工具「真的跑通」（回合法 payload，混入内部字段诱饵）─────────────

class FakeEngine(BaseHTTPRequestHandler):
    hits = 0

    def _send(self, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):                                   # /health（站点探测会打）
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
            "breakdown": {"fuel": 1},                   # 诱饵：白名单必须一个都不回
            "profit_vnd": 999,
            "margin_rate": 0.2,
            "border_fees": {"x": 1},
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


# ── 假 DeepSeek：第 1 轮正常吐工具调用，第 2 轮按模式「装死 / 报错」────────────

class FakeDeepSeek(BaseHTTPRequestHandler):
    """mode:
    silent    → 第 1 轮吐工具调用；第 2 轮 HTTP 200 但**一个 content 片都不吐**（模型空回复）
    http500   → 第 1 轮吐工具调用；第 2 轮直接 HTTP 500（模型侧中途挂掉，= 线上第 2 轮抛错）
    ok        → 第 2 轮正常吐文本（回归用）
    """

    protocol_version = "HTTP/1.0"        # 无 Content-Length → 客户端读到连接关闭（SSE 语义）
    mode = "silent"
    rounds = 0                           # 收到的模型请求次数（第 1 轮 / 第 2 轮）

    def log_message(self, *a):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = {}
        type(self).rounds += 1
        msgs = body.get("messages") or []
        if type(self).mode == "http500" and type(self).rounds == 1:
            # http500 场景必须**先**走完工具轮再报错 —— 这才是线上事故的形态
            # （tool_start/tool_done 已发出，第 2 轮模型才挂）。不能只靠下面的 tool-role 判定：
            # 实测它在本场景不可靠，会让第 1 轮直接 500、工具轮根本没跑，断言随之假红。
            self._tool_round()
            return
        if not any(m.get("role") == "tool" for m in msgs):
            self._tool_round()
            return
        if type(self).mode == "http500":
            self._json(500, {"error": {"message": "selftest_fake_second_round_failure"}})
            return
        if type(self).mode == "silent":
            self._open_stream()
            self._chunk({}, finish="stop")            # 只有结束片，没有 content —— 装死
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        self._open_stream()
        for piece in ["(fake) 工具结果已收到，", "这里是正常文本。"]:
            self._chunk({"content": piece})
        self._chunk({}, finish="stop")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _json(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _open_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _chunk(self, delta: dict, finish=None) -> None:
        obj = {
            "id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": FAKE_DEEPSEEK_MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def _tool_round(self) -> None:
        args = json.dumps({"origin": "南宁", "destination": "河内", "border": "友谊关口岸",
                           "weight_kg": 20000, "mode": "full_truck",
                           "vehicle_model_id": "flatbed_13m"}, ensure_ascii=False)
        self._open_stream()
        self._chunk({"tool_calls": [{"index": 0, "id": "call_fake_1", "type": "function",
                                     "function": {"name": "query_route_cost", "arguments": ""}}]})
        self._chunk({"tool_calls": [{"index": 0, "function": {"arguments": args}}]})
        self._chunk({}, finish="tool_calls")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def start_fake_deepseek(mode: str):
    port = pick_port()
    FakeDeepSeek.mode = mode
    FakeDeepSeek.rounds = 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeDeepSeek)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, th, port


# ── 临时站点 ───────────────────────────────────────────────

def start_site(engine_port: int, extra_env: dict):
    port = pick_port()
    err_path = os.path.join(ERR_DIR, f"verify-chat-robust-{port}.err.log")
    env = {
        **os.environ,
        "NODE_ENV": "production",              # ⚠️ 否则走 Vite 中间件模式并以 stdin is not a tty 退出
        "PORT": str(port),
        "OSRM_API_BASE": f"http://127.0.0.1:{engine_port}",
        "OSRM_ENGINE_KEY": "verify-chat-robust",     # 假钥匙：假引擎不校验
        "HEALTH_PROBE_MS": "0",                      # 关周期探查：本轮只测对话，别让探测刷日志
        # 下面这些按 None = 「子进程环境里根本没有该变量」，避免继承宿主造成假绿：
        "AGENT_CHAT_DEMO": None,                     # 硬要求：演示模型不参与
        "GEMINI_API_KEY": None,
        "DEEPSEEK_API_KEY": None,
        "DEEPSEEK_BASE_URL": None,
        "CHAT_PROVIDER": None,
        "AGENT_CHAT_SELFTEST": None,
    }
    for k, v in extra_env.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
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


def post_json(url: str, payload: dict, timeout_s: float) -> str:
    """--data-binary @- 避免中文被 MSYS 弄乱。"""
    try:
        out = subprocess.run(
            ["curl", "-s", "-m", str(int(timeout_s)), "-H", "Content-Type: application/json",
             "--data-binary", "@-", url],
            input=json.dumps(payload).encode(), capture_output=True, timeout=timeout_s + 10)
        return out.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return ""


def chat(site_port: int, message: str, timeout_s: float = 60):
    """POST /api/agent-chat 收完整条 SSE → (elapsed, raw)。"""
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
        return time.monotonic() - t0, "（curl 自己超时：服务端一直没结束响应）"


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


def parse_events(raw: str):
    """兼容两种响应：自测路由的 JSON `{events:[{event,data}…]}` / 真 SSE 的 `event: …` 块。

    返回 (events, kind, extra)：kind = 'json' | 'sse' | 'empty'；extra = JSON 体（JSON 模式）。
    """
    text = (raw or "").strip()
    if text.startswith("{"):
        try:
            body = json.loads(text)
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("events"), list):
            events = []
            for e in body["events"]:
                if isinstance(e, dict) and "event" in e:
                    events.append((str(e["event"]), e.get("data") or {}))
            return events, "json", body
    if "event: " in raw:
        return parse_sse(raw), "sse", None
    return [], "empty", None


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


# ── 事件序列断言 ────────────────────────────────────────────

def seq_of(events) -> str:
    return "[" + ", ".join(e for e, _ in events) + "]" if events else "[]"


def joined_text(events) -> str:
    return "".join(str((d or {}).get("content", "")) for e, d in events if e == "text")


def require_closure(label: str, events) -> None:
    """公共收尾契约：至少 1 个**非空** text + done。"""
    if not any(e == "text" and str((d or {}).get("content", "")).strip() for e, d in events):
        got = [str((d or {}).get("content", ""))[:40] for e, d in events if e == "text"]
        fail(label, f"没有**非空** text 事件（= 客户端正文 0 字，什么都不显示）；实际 text 事件 {got}")
    if not any(e == "done" for e, _ in events):
        fail(label, f"没有 done 事件（= 流没有正常收尾，前端拿不到结束信号）；实际序列 {seq_of(events)}")


def require_tool_pair(label: str, events) -> None:
    if not any(e == "tool_start" and (d or {}).get("name") == "query_route_cost" for e, d in events):
        fail(label, f"缺少 tool_start(query_route_cost)；实际序列 {seq_of(events)}")
    done = [d for e, d in events if e == "tool_done"]
    if not done:
        fail(label, f"缺少 tool_done；实际序列 {seq_of(events)}")
    elif done[0].get("ok") is not True:
        fail(label, f"工具没真跑通（tool_done.ok={done[0].get('ok')!r}，应为 true）；摘要 {done[0].get('summary')!r}")


def run_selftest(scenario: str):
    """起临时站点（AGENT_CHAT_SELFTEST=1）→ POST 自测路由 → 收尾 → 返回 (events, raw, err, alive)。"""
    srv_e = th_e = proc = None
    try:
        srv_e, th_e, eport = start_fake_engine()
        proc, sport, err = start_site(eport, {"AGENT_CHAT_SELFTEST": "1"})
        if not proc:
            return None, "", err, False
        raw = post_json(f"http://127.0.0.1:{sport}/api/agent-chat/selftest",
                        {"scenario": scenario, "lang": "zh"}, 60)
        alive = proc.poll() is None
        events, kind, body = parse_events(raw)
        return events if kind != "empty" else None, raw, err, alive
    finally:
        stop(proc, (srv_e, th_e) if srv_e else None)


def only_harness_failure(items: list[str]) -> bool:
    """本轮新增的失败是否**全部**只是「假引擎这一跳偶发」（工具没真跑通 + 摘要含连接类字样）。

    只在这种「失败里没有一条关于正文/done 的断言」时才允许重跑一次 —— 真正的缺陷
    （没兜底正文 / 没 done）一定同时出现在失败列表里，所以重试**掩盖不了**被测问题；
    而 Windows loopback 上 undici 偶发的连接重置不会再伪装成「产品把工具跑挂了」。
    """
    if not items:
        return False
    for f in items:
        if "工具没真跑通" not in f:
            return False
        if not any(h in f for h in HARNESS_HINTS):
            return False
    return True


def scenario_selftest(label: str, scenario: str, want_text_substr: str = "",
                      want_tool: bool = False) -> tuple[bool, str]:
    """自测路由场景：偶发的假引擎连接重置自动重跑一次（**明说**，绝不静默）。"""
    for attempt in (1, 2):
        mark = len(fails)
        ok, seq = _selftest_attempt(label, scenario, want_text_substr, want_tool)
        new = fails[mark:]
        if attempt == 1 and only_harness_failure(new):
            note = (f"{label}：第 1 次跑时假引擎这一跳偶发连接重置（{new[0]}）"
                    f"→ 已重跑一次：这不是被测缺陷")
            harness_notes.append(note)
            print(f"   ! {note}")
            del fails[mark:]
            continue
        results.append((f"{label} scenario={scenario}", ok, seq))
        return ok, seq
    return False, "[]"


def _selftest_attempt(label: str, scenario: str, want_text_substr: str = "",
                      want_tool: bool = False) -> tuple[bool, str]:
    try:
        events, raw, err, alive = run_selftest(scenario)
    except Exception as exc:                       # 脚本自己出问题也要如实报，不许静默跳过
        fail(label, f"自测路由调用异常：{exc!r}")
        return False, f"(脚本异常 {exc!r})"

    if events is None:
        leak = read_err(err).strip().splitlines()[-3:]
        fail(label, f"自测路由没给出可解析的事件（HTTP 体 {raw[:160]!r}）；站点存活={alive}；站点日志尾部 {leak}")
        return False, f"(无响应 {raw[:80]!r})"

    seq = seq_of(events)
    print(f"   → 事件序列：{seq}")
    print(f"   → 正文：{joined_text(events)[:120]!r}")

    if want_tool:
        require_tool_pair(label, events)
    require_closure(label, events)
    if want_text_substr and want_text_substr not in joined_text(events):
        fail(label, f"正文里缺少 {want_text_substr!r}；实际 {joined_text(events)[:120]!r}")

    parsed = json.loads(raw) if raw.strip().startswith("{") else {}
    if parsed.get("modelError"):
        print(f"   · 参考信息：自测路由捕获到模型异常 {parsed['modelError']!r}"
              f"（不单独判失败：契约只要求仍有兜底正文 + done）")
    if not alive:
        fail(label, "临时站点进程在响应前后退出了（进程级崩溃，客户端只会看到连接被重置）")

    ok = not [f for f in fails if f.startswith(label)]
    return ok, seq


def scenario_sse(label: str, mode: str, message: str) -> tuple[bool, str]:
    """真 SSE 路由场景：同样的偶发连接重置处理（明说 + 重跑一次）。"""
    for attempt in (1, 2):
        mark = len(fails)
        ok, seq = _sse_attempt(label, mode, message)
        new = fails[mark:]
        if attempt == 1 and only_harness_failure(new):
            note = (f"{label}：第 1 次跑时假引擎这一跳偶发连接重置（{new[0]}）"
                    f"→ 已重跑一次：这不是被测缺陷")
            harness_notes.append(note)
            print(f"   ! {note}")
            del fails[mark:]
            continue
        results.append((f"{label} 真SSE+假DeepSeek({mode})", ok, seq))
        return ok, seq
    return False, "[]"


def _sse_attempt(label: str, mode: str, message: str) -> tuple[bool, str]:
    """真 SSE 路由 + 假 DeepSeek：第 1 轮吐工具调用，第 2 轮按 mode 装死 / 报错。"""
    srv_e = srv_d = th_e = th_d = proc = None
    try:
        # ⚠️ 假模型/假引擎的计数是**类变量**，跨场景不会自己归零：E4 跑完若不复位，
        # E5 的第 1 轮就会被当成「第 2 轮」直接 500（工具轮根本没跑），断言随之假红。
        FakeDeepSeek.rounds = 0
        FakeEngine.hits = 0
        srv_e, th_e, eport = start_fake_engine()
        srv_d, th_d, dport = start_fake_deepseek(mode)
        proc, sport, err = start_site(eport, {
            "DEEPSEEK_API_KEY": FAKE_DEEPSEEK_KEY,
            "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{dport}/v1",
        })
        if not proc:
            fail(label, "临时站点没起来")
            return False, "(站点未起)"
        elapsed, raw = chat(sport, message, 60)
        alive = proc.poll() is None
        events, kind, _ = parse_events(raw)
        seq = seq_of(events)
        print(f"   → {elapsed:.1f}s，假 DeepSeek 收到 {FakeDeepSeek.rounds} 轮请求，假引擎命中 {FakeEngine.hits} 次")
        print(f"   → 客户端收到的事件序列：{seq}")
        print(f"   → 正文：{joined_text(events)[:120]!r}")
        if kind == "empty":
            tail = read_err(err).strip().splitlines()[-3:]
            print(f"   → 原始响应：{raw[:160]!r}")
            print(f"   → 站点日志尾部：{tail}")
        if not events:
            fail(label, f"客户端一个事件都没收到（HTTP 体 {raw[:120]!r}）—— 这就是线上事故的形态")
        else:
            require_tool_pair(label, events)
            require_closure(label, events)
        if not alive:
            fail(label, "临时站点进程退出了（进程级崩溃）")
        ok = not [f for f in fails if f.startswith(label)]
        return ok, seq
    finally:
        stop(proc, (srv_e, th_e) if srv_e else None, (srv_d, th_d) if srv_d else None)


# ── 主流程 ──────────────────────────────────────────────────

def main() -> int:
    from shutil import which
    if which("node") is None or not os.path.exists(ENTRY):
        print("✗ 前置缺失：需要 node 与 dist/server.cjs（先 npm run build）")
        return 2

    print("=" * 68)
    print("对话健壮性验收：模型不吐字 / 中途抛错时，客户端必须仍拿到兜底正文 + done")
    print("（自测路由 + 真 SSE 双路径；本地假模型 + 假引擎 + 临时站点，不碰真密钥）")
    print(f"站点入口：{ENTRY}")
    print("=" * 68)

    print("\nE1 自测路由 scenario=empty：模型一个事件都不吐 → 必须兜底正文 + done")
    scenario_selftest("E1", "empty")

    print("\nE2 自测路由 scenario=abort：先吐工具调用、第 2 轮抛错 → 必须 tool_start/tool_done + 兜底正文 + done")
    scenario_selftest("E2", "abort", want_tool=True)

    print("\nE3 回归 自测路由 scenario=route：正常路径不许被改坏 → text 含 (selftest) + done")
    scenario_selftest("E3", "route", want_text_substr="(selftest)", want_tool=True)

    print("\nE4 真 SSE + 假 DeepSeek：工具轮完第 2 轮**空流**（模型一个字不回）→ 必须兜底正文 + done")
    scenario_sse("E4", "silent", "从南宁到河内 20 吨设备大概多少钱？")

    print("\nE5 真 SSE + 假 DeepSeek：工具轮完第 2 轮 **HTTP 500**（= 线上第 2 轮抛错）→ 必须兜底正文 + done")
    scenario_sse("E5", "http500", "从南宁到河内 20 吨设备大概多少钱？")

    # ── 收尾 ──
    print("\n" + "=" * 68)
    print(f"{'场景':<44} {'事件序列'}")
    for name, ok, seq in results:
        print(f"  {'✓' if ok else '✗'} {name:<42} {seq}")
    if harness_notes:
        print(f"\n· 干扰说明（已重跑，未计入失败）：")
        for n in harness_notes:
            print(f"   - {n}")
    if fails:
        print(f"\n✗ 失败 {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("\n✓ 全部通过：模型空回复 / 中途抛错两条路径都给出了兜底正文 + done，正常路径未回归")
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        for p in procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
    sys.exit(code)
