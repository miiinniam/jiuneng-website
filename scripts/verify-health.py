"""健康检查如实反映引擎依赖 —— 真杀进程、真恢复，不用 mock。

用法：
    ENGINE_API_KEY=... python scripts/verify-health.py [site_url]

环境变量：
    SITE_URL / ENGINE_API_KEY(或 OSRM_ENGINE_KEY，**必填**，拒绝默认值) / HEALTH_PROBE_WAIT（秒，默认 20）
    ENGINE_PY / ENGINE_CWD（覆盖本机引擎运行时路径，默认见下）

覆盖断言：
  ① 轻量档：HTTP 200 + engine.configured=true + engine.base 只有 host（无路径/无密钥）+ lastProbe 字段齐全
     —— 首个探针回包前 ok=null 属正常 pending（规格 §4 允许字段可空）；断言前先等回包，ok 只接受 boolean|null
  ①B 密钥门禁（**先于任何破坏性操作**）：脚本自带的 KEY 必须真能过上游鉴权，且带密钥走官网出口的测算必须
     拿到结果 —— 否则就是「健康检查报 ok、客户侧测算全 401」的假绿，必须非 0 退出
  ② deep=1：引擎在线 → ok=true；且 lastProbe.at >= time（at 是 after-await 的结果时刻，不是请求时刻）
  ③ 取证：打印本机 18000/18001 现状；**只有**官网 base 直连 18000 时才动 18000
  ④ 真杀「官网 base 指向的那个服务」→ 轻量档 status=degraded + lastProbe.ok=false + reason **必须** == 'unreachable'
     → ?deep=1 同样 degraded 且 reason=='unreachable'；轻量档仍秒回 200（保活不变量）
  ⑤ 重新拉起（只拉原本在跑的那个）→ 回到 status=ok + lastProbe.ok=true，且业务测算再次可用
  ⑥ 环境变量写错（HEALTH_PROBE_MS=abc）不得退化成忙循环（回归：Number('abc')=NaN / Number('')=0 喂给 setInterval）
  ⑦ 未配置分支（不设 OSRM_API_BASE）→ reason **必须** == 'not_configured'

安全护栏（别再删）：
  - 只对「本机回环 base + 已知开发端口」做杀进程实验；远端/未知 base 一律只跑只读断言
  - 杀之前核对进程命令行身份（kill_port 的 expect）；对不上就拒绝杀并记失败
  - 进杀进程阶段前记下哪些端口原本在跑；正常结束/异常/Ctrl-C 都只恢复原本在跑的那些，绝不留孤儿进程
  - 临时站点与假依赖一律 try/finally 收干净（非 daemon 线程 + shutdown/server_close/join，避免解释器关闭时
    与仍在写 stderr 的线程抢锁 → 断言全过却以 127 退出）

本机 python urllib 走 127.0.0.1 会被环境拦截，统一 subprocess 调 curl（沿用 scripts/probe-quote-api.py 风格）。
**退出码即结论**：0 = 全部通过，非 0 = 有失败项。
"""
import atexit
import http.server
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

# ── 配置 ───────────────────────────────────────────────────────────────
SITE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SITE_URL", "http://127.0.0.1:3300")).rstrip("/")

KEY = os.environ.get("ENGINE_API_KEY") or os.environ.get("OSRM_ENGINE_KEY")
if not KEY:
    # 绝不给默认值：默认密钥会让「密钥不一致」变成假绿 —— /health 免鉴权照样 200、脚本照样打印「全部通过」，
    # 而客户侧测算已经全 401。缺密钥就快速失败，别拿默认密钥去重启依赖。
    sys.exit("请显式提供 ENGINE_API_KEY（拒绝用默认密钥重启依赖）："
             "ENGINE_API_KEY=... python scripts/verify-health.py")

ENGINE_PORT = 18000                                  # 原始引擎（AIOSRM++ run_server.py）
GATEWAY_PORT = 18001                                 # 官网专用网关（deploy/osrm-engine/server.py，内嵌引擎 app）
try:
    WAIT_BUDGET_S = max(int(os.environ.get("HEALTH_PROBE_WAIT") or "20"), 0)
except ValueError:
    WAIT_BUDGET_S = 20
PY = os.environ.get("ENGINE_PY", "D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe")
ENGINE_CWD = os.environ.get("ENGINE_CWD", "D:/01_业务/立三方/AIOSRM++/backend")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_CWD = os.path.join(ROOT, "deploy", "osrm-engine")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
# 杀进程白名单：端口 → 命令行里**必须**出现的子串（杀前核对身份，防止像原版那样把无关进程杀掉：
# 审查实测把 kill_port 原样抄到 scratch，对另一个 `python -m http.server 18014` 跑，真被杀了）。
# 注：本机网关以 `python server.py`（cwd=deploy/osrm-engine）启动，命令行里**不含** "osrm-engine"
#     （cwd 不在 CommandLine 里），所以这里只能钉 "server.py"。
EXPECT_CMDLINE = {
    ENGINE_PORT: ("run_server.py",),
    GATEWAY_PORT: ("server.py",),
}
NODE_EXE = shutil.which("node")

# 业务断言用的最小合法请求（与 scripts/probe-quote-api.py 同一条线路）
QUOTE_BODY = {
    "route": {"origin": {"lat": 31.2304, "lng": 121.4737},
              "destination": {"lat": 21.0278, "lng": 105.8342},
              "border": {"lat": 21.9755, "lng": 106.7089}},
    "cargo": {"weight_kg": 20000, "volume_m3": 60, "type": "normal"},
    "vehicle": {"loading_mode": "full_truck", "vehicle_model_id": "flatbed_13m"},
}
SITE_QUOTE_BODY = {"origin": "上海", "destination": "河内", "border": "友谊关口岸",
                   "weight_kg": 20000, "volume_m3": 60, "mode": "full_truck",
                   "vehicle_model_id": "flatbed_13m"}

fails: list[str] = []


# ── HTTP（统一走 curl：本机 urllib 直连 127.0.0.1 会被环境拦截）──────────
def curl(url, timeout=20, want_code=False):
    """curl -s → (http_code, body_text)。返回码 0 表示连不上。"""
    p = subprocess.run(["curl", "-s", "-m", str(timeout), url, "-w", "\n%{http_code}"],
                       capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    body, _, code = out.rpartition("\n")
    try:
        code_i = int(code.strip() or 0)
    except ValueError:
        code_i = 0
    return (code_i, body.strip()) if want_code else body.strip()


def curl_json(url, timeout=20):
    """→ (http_code, obj|None, raw_text)"""
    code, body = curl(url, timeout, want_code=True)
    try:
        return code, json.loads(body), body
    except Exception:
        return code, None, body


def curl_post(url, payload, key=None, timeout=60):
    """带（可选）X-API-Key 的 JSON POST → (http_code, raw_text)。"""
    args = ["curl", "-s", "-m", str(timeout), "-X", "POST", url, "-H", "Content-Type: application/json"]
    if key:
        args += ["-H", f"X-API-Key: {key}"]
    args += ["--data-binary", "@-", "-w", "\n%{http_code}"]
    p = subprocess.run(args, input=json.dumps(payload).encode(), capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    body, _, code = out.rpartition("\n")
    try:
        code_i = int(code.strip() or 0)
    except ValueError:
        code_i = 0
    return code_i, body.strip()


# ── 进程/端口 ──────────────────────────────────────────────────────────
def pid_on(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def proc_info(pid):
    """→ (Name, CommandLine)。进程已退出则返回 ("", "")。"""
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
                        f"Select-Object Name,CommandLine | ConvertTo-Json -Compress"],
                       capture_output=True)
    txt = p.stdout.decode("utf-8", "replace").strip()
    try:
        obj = json.loads(txt) if txt else {}
    except Exception:
        obj = {}
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    return str(obj.get("Name") or ""), str(obj.get("CommandLine") or "")


def kill_port(port, expect):
    """Windows：taskkill 会静默失败，用 Stop-Process 并核对端口已释放。

    ⚠️ 杀之前**必须核对进程身份**（expect = 命令行里必须出现的子串）：原版没有这一步，实测会把
    无关进程（如 `python -m http.server 18014`）一起杀掉。对不上就拒绝杀并记失败。
    """
    pid = pid_on(port)
    if not pid:
        print(f"   （端口 {port} 上没有监听进程，没有可杀的）")
        return None
    name, cmd = proc_info(pid)
    missing = [s for s in expect if s not in cmd]
    if missing or not name.lower().startswith("python"):
        fails.append(f"拒绝杀 {port} 端口 PID {pid}：进程身份对不上"
                     f"（Name={name!r} 缺 {missing} CommandLine={cmd[:200]!r}）")
        print(f"   ✗ 拒绝杀 PID {pid}：身份对不上（Name={name!r}，命令行缺 {missing}）")
        return None
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                   capture_output=True)
    for _ in range(10):
        if pid_on(port) is None:
            break
        time.sleep(0.5)
    left = pid_on(port)
    if left:
        fails.append(f"杀 {port} 端口失败：PID {pid} 仍在监听（PID {left}）")
        print(f"   ✗ 杀 {port} 失败：PID {left} 仍在监听")
        return None
    return pid


def start_port(port):
    """只认识本机开发端口（18000/18001）；别的端口不许乱拉，避免留孤儿进程。"""
    if port == ENGINE_PORT:
        subprocess.Popen([PY, os.path.join(ENGINE_CWD, "run_server.py"), "--port", str(port)],
                         cwd=ENGINE_CWD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif port == GATEWAY_PORT:
        env = {**os.environ, "PORT": str(port), "ENGINE_API_KEY": KEY}
        subprocess.Popen([PY, os.path.join(GATEWAY_CWD, "server.py")], cwd=GATEWAY_CWD, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        fails.append(f"不知道该怎样拉起端口 {port}（不是本机已知开发端口）")
        return False
    for _ in range(60):
        if curl(f"http://127.0.0.1:{port}/health", 3, want_code=True)[0] == 200:
            return True
        time.sleep(1)
    return False


# ── 恢复护栏：只恢复「进杀进程阶段前原本在跑」的端口；异常/Ctrl-C 也要恢复 ──
ports_running_before: dict[int, bool] = {}
_restoring = False


def snapshot_ports():
    for p in (ENGINE_PORT, GATEWAY_PORT):
        ports_running_before[p] = pid_on(p) is not None
    print(f"   （环境快照：原本在跑 = {[p for p, up in ports_running_before.items() if up] or '无'}）")


def restore_all():
    """幂等：只在「原本在跑、现在掉了」时才拉起。"""
    global _restoring
    if _restoring:
        return
    _restoring = True
    try:
        for p, was_running in ports_running_before.items():
            if not was_running:
                continue
            if pid_on(p) is None:
                print(f"   [恢复] {p} 原本在跑但现在掉了 → 重新拉起 …", flush=True)
                start_port(p)
    except Exception as exc:                                   # 恢复失败也不能再往外抛
        print(f"   [恢复] 出错：{exc}", flush=True)
    finally:
        _restoring = False


def _on_signal(signum, _frame):
    print(f"\n收到信号 {signum}：先把环境恢复回去再退出 …", flush=True)
    restore_all()
    sys.exit(130)


atexit.register(restore_all)
signal.signal(signal.SIGINT, _on_signal)
try:
    signal.signal(signal.SIGTERM, _on_signal)
except (ValueError, AttributeError, OSError):
    pass


# ── 轮询/断言小工具 ────────────────────────────────────────────────────
def poll_light(pred, budget=None, interval=1.0, url=None):
    """轮询轻量档直到 pred(body) 为真（后台探针有 HEALTH_PROBE_MS 间隔，不能立刻断言）。

    **至少发一次请求**（即使 budget<=0），所以返回的 last 永远不是 None —— 原版
    `HEALTH_PROBE_WAIT=0` 时会返回 (False, None)，调用方一解包就 TypeError，而那一刻依赖刚被杀掉。
    """
    url = url or f"{SITE}/api/health"
    deadline = time.time() + (WAIT_BUDGET_S if budget is None else budget)
    while True:
        last = curl_json(url, 10)
        code, body, _raw = last
        if code == 200 and isinstance(body, dict) and pred(body):
            return True, last
        if time.time() >= deadline:
            return False, last
        time.sleep(interval)


def probe_ok(entry):
    return (entry or {}).get("engine", {}).get("lastProbe", {}).get("ok")


def probe_reason(entry):
    lp = (entry or {}).get("engine", {}).get("lastProbe") or {}
    return lp.get("reason")


def parse_host_port(base):
    """engine.base 只含 host（可能带端口）→ (host, port|None)。解析不出端口就返回 None，**不回落默认值**。"""
    b = str(base or "").strip()
    if not b:
        return None, None
    if b.startswith("["):                                      # [::1]:18001
        host, _, rest = b.partition("]")
        if rest.startswith(":") and rest[1:].isdigit():
            return host + "]", int(rest[1:])
        return host + "]", None
    if ":" in b:
        host, _, port = b.rpartition(":")
        return host, (int(port) if port.isdigit() else None)
    return b, None


def business_quote(label):
    """带密钥走**官网出口**（客户真实路径）。健康检查报 ok 而这里 401 = 假绿。"""
    code, raw = curl_post(f"{SITE}/api/osrm-quote", SITE_QUOTE_BODY, timeout=90)
    try:
        obj = json.loads(raw)
    except Exception:
        obj = None
    if code == 200 and isinstance(obj, dict) and obj.get("ok") is True:
        print(f"   ✓ {label}官网测算可用（HTTP 200 ok=true，里程 {obj.get('distance_km')} km）")
        return True
    detail = json.dumps(obj, ensure_ascii=False)[:240] if obj is not None else raw[:240]
    reason = (obj or {}).get("reason") if isinstance(obj, dict) else None
    status = (obj or {}).get("status") if isinstance(obj, dict) else None
    fails.append(f"{label}官网出口测算失败（HTTP {code} reason={reason!r} engine_status={status!r}）：{detail}")
    print(f"   ✗ {label}官网测算失败：HTTP {code} reason={reason!r} engine_status={status!r} {detail}")
    return False


# ── 临时站点 / 假依赖（§⑥§⑦ 用；一律 try/finally 收干净）──────────────
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_temp_site(overrides):
    """起一个临时官网（dist/server.cjs），返回 (proc, port)。调用方必须 try/finally 收掉。"""
    port = free_port()
    env = {**os.environ, "NODE_ENV": "production", "PORT": str(port)}
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    proc = subprocess.Popen([NODE_EXE, "dist/server.cjs"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, port


def stop_temp_site(proc):
    if not proc:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass


def start_fake_dep():
    """计数用的假依赖。**非 daemon 线程**：daemon 线程在解释器关闭时与仍在写 stderr 的线程抢锁，
    会让进程以 127 退出（Fatal Python error: _enter_buffered_busy）——那样「退出码即结论」就废了。"""
    state = {"hits": 0}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                      # noqa: N802
            state["hits"] += 1
            body = b'{"status":"ok"}'
            try:                                               # 站点被 terminate 时连接被掐断，别让异常冒到 stderr
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def log_message(self, *a):                             # 静音
            pass

    class _Quiet(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):        # socketserver 默认会把整段 traceback 打进 stderr
            pass

    srv = _Quiet(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, name="fake-dep", daemon=False)
    thread.start()
    return srv, thread, state, port


def stop_fake_dep(srv, thread):
    if not srv:
        return
    try:
        srv.shutdown()
    except Exception:
        pass
    try:
        srv.server_close()
    except Exception:
        pass
    if thread:
        try:
            thread.join(timeout=5)
        except Exception:
            pass


print(f"官网 = {SITE}\n引擎(原始) = 127.0.0.1:{ENGINE_PORT}\n网关 = 127.0.0.1:{GATEWAY_PORT}\n"
      f"等待预算 = {WAIT_BUDGET_S}s\n密钥 = 已提供（长度 {len(KEY)}，不在输出里回显）\n")

# ── ① 轻量档 ───────────────────────────────────────────────────────────
t0 = time.time()
code, light, raw = curl_json(f"{SITE}/api/health", 15)
light_ms = round((time.time() - t0) * 1000)
print(f"① 轻量档 HTTP {code}（{light_ms} ms）\n   {raw[:300]}")
if code != 200 or not isinstance(light, dict):
    fails.append(f"轻量 /api/health 应 HTTP 200 + JSON，实际 HTTP {code} body={raw[:200]}")
    print("\n存在问题：\n  - " + "\n  - ".join(fails))
    sys.exit(1)

for field in ("status", "time"):
    if field not in light:
        fails.append(f"轻量档缺既有兼容字段 {field}")
eng = light.get("engine")
if not isinstance(eng, dict):
    fails.append(f"轻量档缺 engine 对象，实际 {json.dumps(light, ensure_ascii=False)[:200]}")
else:
    if eng.get("configured") is not True:
        fails.append(f"engine.configured 应为 true（官网已配 OSRM_API_BASE），实际 {eng.get('configured')!r}")
    base = eng.get("base")
    if not base:
        fails.append(f"engine.base 应给出 host，实际 {base!r}")
    else:
        if "/" in base or "?" in base or "key" in base.lower() or "token" in base.lower():
            fails.append(f"engine.base 泄露了路径/查询串/密钥，实际 {base!r}（只应给 host）")
    lp = eng.get("lastProbe")
    if not isinstance(lp, dict):
        fails.append(f"engine.lastProbe 必须是对象且字段齐全（ok/at/ms，可为 null），实际 {lp!r}")
    else:
        for field in ("ok", "at", "ms"):
            if field not in lp:
                fails.append(f"lastProbe 缺字段 {field}，实际 {lp}")
        if probe_ok(light) is None:
            # 首个探针还没回包 → pending（规格允许字段为 null）。断言前先给它时间，避免刚重启就假失败。
            print(f"   （pending：lastProbe.ok=null，首个探针尚未回包）最多等 {WAIT_BUDGET_S}s …")
            _ok_first, last_first = poll_light(lambda b: probe_ok(b) is not None)
            code, light, raw = last_first
            print(f"   等待后：HTTP {code} {raw[:220]}")
            lp = (light.get("engine") or {}).get("lastProbe") if isinstance(light, dict) else None
        ok_val = (lp or {}).get("ok")
        if ok_val is not None and not isinstance(ok_val, bool):
            fails.append(f"lastProbe.ok 只允许 boolean|null（pending 用 null），实际 {ok_val!r}")
        if ok_val is None:
            print("   （仍为 pending ok=null：字段齐全即合规；后台探针是否真在跑，由 ④/⑤ 的降级-恢复断言钉住）")
        if ok_val is False and not (lp or {}).get("reason"):
            fails.append(f"lastProbe.ok=false 时必须带 reason，实际 {lp}")
print(f"   {'✓' if not fails else '✗'} 轻量档字段检查（engine.configured / base 仅 host / lastProbe 齐全可空）")

# 契约不成立就没法做后面的降级断言（后置阶段会杀进程），这里快速失败
if not isinstance(eng, dict):
    print()
    print("存在问题：\n  - " + "\n  - ".join(fails))
    print("（轻量档缺 engine 契约，跳过降级/恢复实验）")
    sys.exit(1)

# 官网 base 指向哪个端口 + 主机 —— 那才是官网真正的依赖（本机=网关 18001）
base_str = str(eng.get("base") or "")
UP_HOST, UPSTREAM_PORT = parse_host_port(base_str)
print(f"   → 官网依赖：{base_str or '(未知)'}"
      f"（解析 host={UP_HOST!r} port={UPSTREAM_PORT!r}；解析不出端口不回落默认值）")

LOCAL_UPSTREAM = UP_HOST in LOOPBACK_HOSTS and UPSTREAM_PORT is not None
KILLABLE = LOCAL_UPSTREAM and UPSTREAM_PORT in EXPECT_CMDLINE
if UPSTREAM_PORT is None:
    print("   → base 里没有端口，无法定位本机依赖：跳过杀进程实验，只跑只读断言")
elif UP_HOST not in LOOPBACK_HOSTS:
    print(f"   → base 指向非本机回环主机 {UP_HOST!r}：跳过杀进程实验"
          f"（绝不拿远端/生产做杀进程实验），只跑只读断言")
elif UPSTREAM_PORT not in EXPECT_CMDLINE:
    print(f"   → base 端口 {UPSTREAM_PORT} 不是本机已知开发端口（{sorted(EXPECT_CMDLINE)}）："
          f"进程身份无从核对，跳过杀进程实验")
else:
    print(f"   → 本机依赖端口 {UPSTREAM_PORT}：可做杀进程实验（杀前核对命令行身份 {EXPECT_CMDLINE[UPSTREAM_PORT]}）")

# ── ①B 密钥门禁（必须先于任何破坏性操作：密钥不一致时健康检查假绿）──────
print("\n①B 密钥一致性门禁")
if LOCAL_UPSTREAM:
    code_key, _raw_key = curl_post(f"http://{UP_HOST}:{UPSTREAM_PORT}/api/v1/route/cost", QUOTE_BODY, key=KEY)
    print(f"   直连上游 {UP_HOST}:{UPSTREAM_PORT} 带 X-API-Key 的测算 → HTTP {code_key}")
    if code_key == 401:
        fails.append("脚本自带的 KEY 过不了上游鉴权（HTTP 401）：密钥不一致 —— "
                     "健康检查会照常报 ok，而客户侧测算会全 401（假绿）")
        print("   ✗ 401：KEY 与上游不一致。健康检查的 ok 是假绿，拒绝继续做破坏性实验。")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        sys.exit(1)
    print(f"   ✓ 直连上游未被 401 拒绝（HTTP {code_key}）")
else:
    print("   （非本机回环 base：跳过直连鉴权门禁，由下面的官网业务断言兜底）")
if not business_quote("①B "):
    print("\n存在问题：\n  - " + "\n  - ".join(fails))
    sys.exit(1)

# ── ② deep=1（依赖在线）────────────────────────────────────────────────
code, deep_up, raw_up = curl_json(f"{SITE}/api/health?deep=1", 20)
print(f"\n② deep=1 引擎在线 HTTP {code}\n   {raw_up[:300]}")
if code != 200 or not isinstance(deep_up, dict):
    fails.append(f"deep=1 应 HTTP 200 + JSON，实际 HTTP {code} body={raw_up[:200]}")
else:
    if probe_ok(deep_up) is not True:
        fails.append(f"引擎在线时 deep=1 应 lastProbe.ok=true，实际 {json.dumps(deep_up, ensure_ascii=False)}")
    if deep_up.get("status") != "ok":
        fails.append(f"引擎在线时 deep=1 status 应为 ok，实际 {deep_up.get('status')!r}")
    lp_up = (deep_up.get("engine") or {}).get("lastProbe") or {}
    at_up, time_up = str(lp_up.get("at") or ""), str(deep_up.get("time") or "")
    if at_up and time_up and at_up < time_up:
        fails.append(f"deep 的 lastProbe.at（{at_up}）早于请求时刻 time（{time_up}）—— at 必须是 await 之后的结果时刻")
    elif at_up:
        print(f"   ✓ lastProbe.at={at_up} ≥ time={time_up}（at 取的是结果时刻）")

# 环境快照：必须在任何杀进程动作之前
snapshot_ports()

# ── ③ 取证：18000/18001 现状（只有 base 直连 18000 时才动 18000）───────
print(f"\n③ 取证：官网依赖 = {UPSTREAM_PORT}")
gw_before = curl(f"http://127.0.0.1:{GATEWAY_PORT}/health", 10, want_code=True)
eng_before = curl(f"http://127.0.0.1:{ENGINE_PORT}/health", 10, want_code=True)
print(f"   网关 {GATEWAY_PORT}/health → HTTP {gw_before[0]} {gw_before[1][:80]}")
print(f"   引擎 {ENGINE_PORT}/health → HTTP {eng_before[0]} {eng_before[1][:80]}")
if KILLABLE and UPSTREAM_PORT == ENGINE_PORT:
    print(f"   （官网 base 直连 {ENGINE_PORT}，本段即降级验证）杀 {ENGINE_PORT} …")
    killed_18000 = kill_port(ENGINE_PORT, EXPECT_CMDLINE[ENGINE_PORT])
    if killed_18000:
        time.sleep(min(WAIT_BUDGET_S, 8))
        eng_after = curl(f"http://127.0.0.1:{ENGINE_PORT}/health", 6, want_code=True)
        gw_after = curl(f"http://127.0.0.1:{GATEWAY_PORT}/health", 10, want_code=True)
        print(f"   杀之后 引擎 {ENGINE_PORT} → HTTP {eng_after[0]} {eng_after[1][:80] or '(空)'}")
        print(f"   杀之后 网关 {GATEWAY_PORT} → HTTP {gw_after[0]} {gw_after[1][:80] or '(空)'}")
        if ports_running_before.get(ENGINE_PORT):
            print(f"   重新拉起 {ENGINE_PORT} … {'OK' if start_port(ENGINE_PORT) else '失败'}")
        else:
            print(f"   （{ENGINE_PORT} 杀之前本来就没在跑 → 不拉起，避免留孤儿进程）")
else:
    print(f"   → base 指向 {UPSTREAM_PORT} 而不是 {ENGINE_PORT}：本段不杀 {ENGINE_PORT}"
          f"（对无关服务做杀进程实验既无意义也危险），只登记现状；降级验证在 ④ 按 {UPSTREAM_PORT} 做")

# ── ④ 核心：杀掉官网真实依赖（base 指向的端口）→ 必须降级 ────────────────
if not KILLABLE:
    print("\n④⑤ 杀进程实验已跳过（见上面的 base 判定）：只跑只读断言")
else:
    print(f"\n④ 杀掉官网真实依赖（{UPSTREAM_PORT}）")
    killed = kill_port(UPSTREAM_PORT, EXPECT_CMDLINE[UPSTREAM_PORT])
    if not killed:
        print("   ✗ 依赖没被杀成（端口无监听 / 身份不符 / 杀不掉，见上面 fails）→ 跳过降级与恢复断言")
    else:
        print(f"   已杀 PID={killed}；等后台探针降级（最多 {WAIT_BUDGET_S}s）")
        ok, last = poll_light(lambda b: b.get("status") == "degraded" and probe_ok(b) is False)
        code, body, raw = last
        print(f"   轻量 → HTTP {code} {raw[:260]}")
        if not ok:
            fails.append(f"{WAIT_BUDGET_S}s 内轻量档未变为 status=degraded 且 lastProbe.ok=false，实际 {raw[:220]}")
        else:
            r = probe_reason(body)
            if r != "unreachable":
                fails.append(f"依赖被杀后 lastProbe.reason 必须是 'unreachable'（不是「在枚举内即可」），实际 {r!r}")
            else:
                print("   ✓ 轻量档如实降级：status=degraded lastProbe.ok=false reason='unreachable'")

        code, deep_down, raw_dd = curl_json(f"{SITE}/api/health?deep=1", 20)
        print(f"   deep=1 → HTTP {code} {raw_dd[:260]}")
        if code != 200 or not isinstance(deep_down, dict):
            fails.append(f"依赖死掉后 deep=1 应仍 HTTP 200 + JSON，实际 HTTP {code} {raw_dd[:160]}")
        else:
            if deep_down.get("status") != "degraded":
                fails.append(f"依赖死掉后 deep=1 status 应为 degraded，实际 {deep_down.get('status')!r}")
            if probe_ok(deep_down) is not False:
                fails.append(f"依赖死掉后 deep=1 仍报 ok（谎报）：{json.dumps(deep_down, ensure_ascii=False)}")
            r = probe_reason(deep_down)
            if r != "unreachable":
                fails.append(f"依赖死掉后 deep=1 reason 必须是 'unreachable'，实际 {r!r}")
            else:
                print("   ✓ deep=1 实时探测如实降级：status=degraded reason='unreachable'")

        # 轻量档在依赖死掉时必须仍然秒回（不能等探测）
        t0 = time.time()
        code, raw = curl(f"{SITE}/api/health", 10, want_code=True)
        fast_ms = round((time.time() - t0) * 1000)
        print(f"   轻量档（依赖已死）HTTP {code} 耗时 {fast_ms} ms")
        if code != 200:
            fails.append(f"依赖死掉后轻量档必须 HTTP 200，实际 {code}")
        if fast_ms > 1500:
            fails.append(f"依赖死掉后轻量档耗时 {fast_ms} ms（>1500ms），说明它在实时探测而没走缓存")

        # ── ⑤ 恢复：拉回依赖 → 必须回到 ok ─────────────────────────────────
        print(f"\n⑤ 重新拉起 {UPSTREAM_PORT}")
        if not ports_running_before.get(UPSTREAM_PORT):
            print(f"   （{UPSTREAM_PORT} 杀之前本来就没在跑：按「只恢复原本在跑的」纪律不拉起，跳过恢复断言）")
        elif not start_port(UPSTREAM_PORT):
            fails.append(f"端口 {UPSTREAM_PORT} 重启失败（环境问题，非本切片缺陷，请手工确认）")
        else:
            ok, last = poll_light(lambda b: b.get("status") == "ok" and probe_ok(b) is True)
            code, body, raw = last
            print(f"   轻量 → HTTP {code} {raw[:260]}")
            if not ok:
                fails.append(f"依赖恢复后 {WAIT_BUDGET_S}s 内未回到 status=ok 且 lastProbe.ok=true，实际 {raw[:220]}")
            else:
                print("   ✓ 轻量档恢复：status=ok lastProbe.ok=true（不谎报、也不误伤）")
            code, deep_up2, raw_u2 = curl_json(f"{SITE}/api/health?deep=1", 20)
            print(f"   deep=1 → HTTP {code} {raw_u2[:260]}")
            if probe_ok(deep_up2) is not True:
                fails.append(f"恢复后 deep=1 应 ok=true，实际 {raw_u2[:220]}")
            # 业务断言：恢复后客户真实路径必须真的能用（密钥一致性钉在这里）
            business_quote("⑤ 恢复后")

# ── ⑥ 环境变量写错不得变成忙循环（回归：Number('abc')=NaN / Number('')=0 喂给 setInterval 会退化成 1ms）
print("\n⑥ 环境变量边界：HEALTH_PROBE_MS=abc（运维写错）不得退化成忙循环")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法做 env 边界回归")
else:
    srv = thread = None
    proc = None
    try:
        srv, thread, state, dep_port = start_fake_dep()
        proc, site_port = start_temp_site({"OSRM_API_BASE": f"http://127.0.0.1:{dep_port}",
                                           "HEALTH_PROBE_MS": "abc"})
        print(f"   临时站点 PORT={site_port} / 假依赖 PORT={dep_port}（HEALTH_PROBE_MS=abc）")
        up = False
        for _ in range(40):
            if curl(f"http://127.0.0.1:{site_port}/api/health", 3, want_code=True)[0] == 200:
                up = True
                break
            time.sleep(0.5)
        if not up:
            fails.append(f"env 边界用例：临时站点 {site_port} 未起来（跳过频率断言）")
        else:
            state["hits"] = 0
            time.sleep(3)
            hits = state["hits"]
            print(f"   3 秒内假依赖收到 {hits} 次 /health")
            if hits > 8:
                fails.append(f"HEALTH_PROBE_MS=abc 让探针变成了忙循环：3 秒 {hits} 次"
                             f"（应 ≤2；归一后应为 1 次启动探测 + 60s 间隔）")
            else:
                print("   ✓ env 写错时已回落到默认间隔（没有变成忙循环）")
            code, body, raw = curl_json(f"http://127.0.0.1:{site_port}/api/health", 5)
            if code != 200 or probe_ok(body) is not True:
                fails.append(f"env 边界用例：临时站点健康检查异常 HTTP {code} {raw[:160]}")
    finally:
        stop_temp_site(proc)            # 先停临时站点（它会一直打假依赖）
        stop_fake_dep(srv, thread)      # 再收假依赖：非 daemon 线程必须 join，否则退出码不可信

# ── ⑦ 未配置分支：不设 OSRM_API_BASE → reason 必须 == 'not_configured' ────
print("\n⑦ 未配置分支：不设 OSRM_API_BASE → reason 必须 == 'not_configured'")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法验证未配置分支")
else:
    proc = None
    try:
        proc, site_port = start_temp_site({"OSRM_API_BASE": None, "HEALTH_PROBE_MS": "4000"})
        print(f"   临时站点 PORT={site_port}（OSRM_API_BASE 未设）")
        ok, last = poll_light(lambda b: probe_reason(b) == "not_configured",
                              url=f"http://127.0.0.1:{site_port}/api/health", budget=20, interval=0.5)
        code, body, raw = last
        print(f"   轻量 → HTTP {code} {raw[:260]}")
        if not ok:
            fails.append(f"未配置 OSRM_API_BASE 时 lastProbe.reason 必须是 'not_configured'，"
                         f"实际 {probe_reason(body)!r}")
        else:
            eng7 = (body or {}).get("engine") or {}
            lp7 = eng7.get("lastProbe") or {}
            if eng7.get("configured") is not False:
                fails.append(f"未配置时 engine.configured 应为 false，实际 {eng7.get('configured')!r}")
            if eng7.get("base") is not None:
                fails.append(f"未配置时 engine.base 应为 null，实际 {eng7.get('base')!r}")
            if lp7.get("ok") is not False:
                fails.append(f"未配置时 lastProbe.ok 应为 false，实际 {lp7.get('ok')!r}")
            if lp7.get("ms") != 0:
                fails.append(f"未配置时 lastProbe.ms 应为 0（不发起任何请求），实际 {lp7.get('ms')!r}")
            print("   ✓ 未配置分支如实报告：configured=false lastProbe.reason='not_configured'")
    finally:
        stop_temp_site(proc)

# ── 收尾 ───────────────────────────────────────────────────────────────
restore_all()      # 幂等：只补回「原本在跑、现在掉了」的端口（正常路径下是空操作）
print()
print("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails))
sys.exit(1 if fails else 0)
