#!/usr/bin/env python3
"""测算预算（OSRM_QUOTE_TIMEOUT_MS）验收 —— 「引擎按需休眠」的配套证据脚本。

为什么需要它：引擎改为**按需唤醒**后（站点默认关闭周期探查，见 server.ts 的 probeIntervalMs），
Render 免费层实例休眠时首个测算请求要等冷启动（实测 30–60s）。预算太短 → 把「正在唤醒」误报成
engine_timeout，客户白等还拿不到结果；预算被配错（非法值 / 2³² 回绕）→ 更坏，abort **立刻**触发，
活引擎被误报超时。本脚本用**假引擎**（可控延迟）把边界钉死：

  A 默认（未设 OSRM_QUOTE_TIMEOUT_MS）+ 引擎延迟 30s → 必须 200 ok:true，且区间与生产基线**逐位一致**
    （里程 2243.0 km / 69,700,000–85,100,000 VND）—— 证明「冷启动能等住」而不是白等
  B OSRM_QUOTE_TIMEOUT_MS=3000 + 延迟 10s → 干净 reason='engine_timeout'，耗时 ≈3s
  C =50（→ 夹到下限 1000ms）+ 延迟 10s → 同样 timeout，但耗时 ≈1s
    （B/C 构成判别力：证明夹下限真的生效，而不是「反正都超时」）
  D =4294967296（2³² → 夹到 2³¹−1）+ 延迟 5s → 必须 ok:true
    （回归旧坑：Node 定时器把 2³² 回绕成 ~1ms → abort 立刻触发 → **活引擎被误报超时**）
  E =abc（非法）→ 回落默认 75s 且 stderr 打出被拒原值；延迟 5s → ok:true
    （行为上证明回落到了**长**预算，而不是 0/1ms）

  G 引擎**冷启动瞬时 502**（第一个 /route/cost 回 502、第二个正常）→ 必须自动重试一次：
    ok:true 且引擎被请求 ≥2 次（当前实现不重试 → 会把活引擎报成 engine_error）
    （追加段；脚本里 F 已被下面「真实测算刷新健康状态」占用，故编号顺延为 G。A–E 行为不变。）

另外每个 ok:true 的响应都回归**白名单**：假引擎故意混入 breakdown / profit_vnd / margin_rate /
border_fees / geometry，官网一个都不许漏出来。

用法： python scripts/verify-quote-timeout.py        （前置：npm run build）
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
ERR_DIR = os.path.join(ROOT, "dist")          # 站点 stderr 落盘位置（与 verify-health.py 同风格）

FAKE_PRICE = 77400453.3                        # 与生产基线同值：区间必须算成 69,700,000 / 85,100,000
EXPECT_MIN, EXPECT_MAX = 69_700_000, 85_100_000
LEAK_KEYS = ("breakdown", "profit_vnd", "margin_rate", "border_fees", "geometry", "cost_")
AVOID_PORTS = {18000, 18001, 33000}            # 本机真实引擎/网关/其它占用，避开

fails: list[str] = []
procs: list[subprocess.Popen] = []


def pick_port() -> int:
    """在 **16000–32000** 里取空闲端口。

    为什么不交给 OS 随机（bind(0)）：本机动态端口段是 1024–15000，而**站点自己的出站连接也从
    这一段取源端口** —— 假依赖若落在那里会与站点出站撞车 → 站点侧拿到 ECONNREFUSED → 表现成
    「产品把活依赖误报成不可达」的**假红**（实测撞过一次，端口 4190）。
    """
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


class FakeEngine(BaseHTTPRequestHandler):
    """假引擎：延迟 delay_s 后回一份**真字段名**的最小响应（含内部字段，用于回归白名单）。"""

    delay_s = 0.0
    hits = 0

    def _send(self, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):                       # /health（site 的 deep 探测会打）
        self._send({"status": "ok"})

    def do_POST(self):
        type(self).hits += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        time.sleep(type(self).delay_s)
        self._send({
            "price_vnd": FAKE_PRICE,
            "route": {"distance_km": 2243.0265, "adjusted_duration_h": 29.89},
            "vehicle_count": 1,
            "profile_honored": True,
            "suggestions": [{"code": "ok_note"}],
            # ↓ 故意混入内部字段：官网侧白名单必须一个都不回（漏一个就是成本/利润泄露）
            "breakdown": {"fuel": 1},
            "profit_vnd": 999,
            "margin_rate": 0.2,
            "border_fees": {"x": 1},
            "geometry": "SECRET",
            "cost_distance": 1,
        })

    def log_message(self, *args):            # 静音，别污染验收输出
        pass


def start_fake_engine(delay_s: float):
    port = pick_port()
    FakeEngine.delay_s = delay_s
    FakeEngine.hits = 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeEngine)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread, port


class FakeEngine502Once(BaseHTTPRequestHandler):
    """引擎**冷启动瞬时 502** 的假引擎：把 /route/cost 的**第一次**请求回 502，之后回合法 payload。

    为什么要有它：引擎按需唤醒（Render 免费层休眠）时，第一个请求偶尔先吃一个 5xx
    （实例正在拉起 / 网关在换后端），紧接着就能正常服务。当前实现把任何非 2xx 都判成
    engine_error 直接回客户 —— 客户第一次点「测算」看到「引擎暂时不可用」就走了，
    其实同一份请求再打一次就成。本段断言「瞬时 5xx 必须自动重试一次」。

    ⚠️ 502 由 `pending_502` 显式**武装**，不是「第 1 次请求无条件 502」：站点启动自检 /
    体检探测若先打过来，会白白消耗掉那次 502，让断言变成假绿（hits 计数同理，只数武装之后的）。
    """

    hits = 0                       # 武装之后的 POST /route/cost 次数（GET /health 不计数）
    pending_502 = False

    def _send(self, obj: dict, code: int = 200) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):                          # /health：永远正常
        self._send({"status": "ok"})

    def do_POST(self):
        type(self).hits += 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if type(self).pending_502:
            type(self).pending_502 = False
            self._send({"detail": "fake cold-start 502 (instance waking up)"}, code=502)
            return
        self._send({                            # ↓ 与 FakeEngine 同形状的合法 payload
            "price_vnd": FAKE_PRICE,
            "route": {"distance_km": 2243.0265, "adjusted_duration_h": 29.89},
            "vehicle_count": 1,
            "profile_honored": True,
            "suggestions": [{"code": "ok_note"}],
            "breakdown": {"fuel": 1},
            "profit_vnd": 999,
            "margin_rate": 0.2,
            "border_fees": {"x": 1},
            "geometry": "SECRET",
            "cost_distance": 1,
        })

    def log_message(self, *args):
        pass


def start_fake_engine_502_once():
    port = pick_port()
    FakeEngine502Once.hits = 0
    FakeEngine502Once.pending_502 = True        # 武装：下一次 /route/cost 回 502
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeEngine502Once)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread, port


def start_site(engine_port: int, extra_env: dict):
    """起官网并等 /api/health 200。→ (proc, port, err_path) 或 (None, None, None)"""
    port = pick_port()
    err_path = os.path.join(ERR_DIR, f"verify-quote-timeout-{port}.err.log")
    env = {
        **os.environ,
        "NODE_ENV": "production",
        "PORT": str(port),
        "AGENT_CHAT_DEMO": "1",                       # 本机无 GEMINI_API_KEY：对话走演示模式（本脚本不测对话）
        "OSRM_API_BASE": f"http://127.0.0.1:{engine_port}",
        "OSRM_ENGINE_KEY": "verify-quote-timeout-test",   # 假钥匙：假引擎不校验
    }
    for k, v in extra_env.items():
        if v is None:
            env.pop(k, None)                          # None = **不设**该变量（走代码默认）
        else:
            env[k] = v
    # stdout 与 stderr 写**同一个**文件：启动日志（预算 / 周期探查状态）走 console.info → **stdout**，
    # 告警走 console.warn → **stderr**；只看 stderr 会漏掉前者（本脚本首跑就是因为这条断言红了）。
    err_file = open(err_path, "wb")
    proc = subprocess.Popen(["node", ENTRY], cwd=ROOT, env=env,
                            stdout=err_file, stderr=err_file)
    procs.append(proc)
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"   ✗ 站点进程退出（exit {proc.returncode}），stderr 见 {err_path}")
            return None, None, err_path
        code = curl(f"http://127.0.0.1:{port}/api/health", 3, want_code=True)
        if code == 200:
            return proc, port, err_path
        time.sleep(0.4)
    print(f"   ✗ 站点 30s 内没回 200（PORT={port}）")
    return None, None, err_path


def curl(url: str, timeout_s: float, want_code: bool = False):
    """只用 curl 判活：本机 python urllib 走 127.0.0.1 会被环境拦截（实测）。"""
    cmd = ["curl", "-s", "-m", str(int(timeout_s)), "-o", os.devnull,
           "-w", "%{http_code}", url] if want_code else ["curl", "-s", "-m", str(int(timeout_s)), url]
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


def post_quote(site_port: int, timeout_s: float, payload: dict | None = None):
    """POST /api/osrm-quote（--data-binary @- 避免中文被 MSYS 弄乱）→ (elapsed, code, body_dict|None, raw)

    payload 缺省 = A–E 段一直用的那份上海→河内整车请求；G 段会传入南宁→河内的整车请求。
    """
    if payload is None:
        payload = {"origin": "上海", "destination": "河内", "border": "友谊关口岸",
                   "weight_kg": 20000, "volume_m3": 60,
                   "mode": "full_truck", "vehicle_model_id": "flatbed_13m"}
    t0 = time.monotonic()
    try:
        out = subprocess.run(
            ["curl", "-s", "-m", str(int(timeout_s)), "-w", "\n%{http_code}",
             "-H", "Content-Type: application/json", "--data-binary", "@-",
             f"http://127.0.0.1:{site_port}/api/osrm-quote"],
            input=json.dumps(payload).encode(), capture_output=True, timeout=timeout_s + 10)
        elapsed = time.monotonic() - t0
        text = out.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return time.monotonic() - t0, 0, None, "（curl 自己超时）"
    raw, _, code_s = text.rpartition("\n")
    try:
        return elapsed, int(code_s.strip()), json.loads(raw), raw
    except (ValueError, json.JSONDecodeError):
        return elapsed, 0, None, text[:300]


def read_err(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def stop(proc, srv=None, thread=None):
    if srv is not None:
        srv.shutdown()
        srv.server_close()
        if thread is not None:
            thread.join(timeout=5)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def close_stderr_handles():
    for p in procs:
        for f in (p.stdout, p.stderr):
            try:
                if f:
                    f.close()
            except Exception:
                pass


def leak_check(raw: str, label: str) -> None:
    for k in LEAK_KEYS:
        if k in raw:
            fails.append(f"{label}：响应里出现了内部字段「{k}」—— 白名单泄露（成本/利润不能出官网）")


def main() -> int:
    print("测算预算（OSRM_QUOTE_TIMEOUT_MS）验收 —— 假引擎可控延迟，边界逐条钉住")
    if not os.path.exists(ENTRY):
        print(f"✗ 找不到 {ENTRY} —— 先跑 npm run build")
        return 2
    print(f"   站点入口：{ENTRY}")

    # ── A 默认预算 + 引擎延迟 30s：必须等出真结果（区间与生产基线逐位一致）──
    print("\nA 默认预算（未设 OSRM_QUOTE_TIMEOUT_MS）+ 引擎延迟 30s → 必须等出结果")
    srv = thread = proc = None
    try:
        srv, thread, eport = start_fake_engine(30.0)
        proc, sport, err = start_site(eport, {"OSRM_QUOTE_TIMEOUT_MS": None, "HEALTH_PROBE_MS": "0"})
        if proc:
            elapsed, code, body, raw = post_quote(sport, 90)
            print(f"   → HTTP {code}，耗时 {elapsed:.1f}s，体长 {len(raw)}")
            print(f"   → {json.dumps(body, ensure_ascii=False)[:260] if body else raw[:260]}")
            if code != 200 or not (body or {}).get("ok"):
                fails.append(f"A：默认预算下 30s 冷启动没等住（HTTP {code}，reason={(body or {}).get('reason')!r}）"
                             f"—— 客户第一次测算会白等一场")
            else:
                if body.get("price_min_vnd") != EXPECT_MIN or body.get("price_max_vnd") != EXPECT_MAX:
                    fails.append(f"A：区间不对：{body.get('price_min_vnd')}/{body.get('price_max_vnd')}"
                                 f"，应为 {EXPECT_MIN}/{EXPECT_MAX}（售价 ±10% 取整到 10 万）")
                if body.get("distance_km") != 2243.0:
                    fails.append(f"A：里程应为 2243.0，实际 {body.get('distance_km')!r}")
                if elapsed < 25:
                    fails.append(f"A：耗时只 {elapsed:.1f}s < 25s —— 没有真的等引擎（假引擎延迟 30s），"
                                 f"结果来源可疑")
                if code == 200 and not fails:
                    print("   ✓ 等住了，且区间/里程与生产基线逐位一致")
            leak_check(raw, "A")
            err_text = read_err(err)
            if "测算调用预算 75000ms" not in err_text:
                fails.append(f"A：默认预算的启动日志没打出 75000ms：{err_text.strip()[:200]!r}")
            else:
                print("   ✓ 启动日志确认默认预算 = 75000ms")
    finally:
        stop(proc, srv, thread)

    # ── B/C 显式预算 + 夹下限：都超时，但耗时必须不同（判别力）──
    measured = {}
    for label, value, want_elapsed_max, want_elapsed_min in (("B", "3000", 9.0, 2.0), ("C", "50", 2.5, 0.0)):
        print(f"\n{label} OSRM_QUOTE_TIMEOUT_MS={value}"
              f"{'（→ 夹到下限 1000ms）' if label == 'C' else ''} + 引擎延迟 10s → 必须干净 timeout")
        srv = thread = proc = None
        try:
            srv, thread, eport = start_fake_engine(10.0)
            proc, sport, err = start_site(eport, {"OSRM_QUOTE_TIMEOUT_MS": value, "HEALTH_PROBE_MS": "0"})
            if proc:
                elapsed, code, body, raw = post_quote(sport, 60)
                measured[label] = elapsed
                print(f"   → HTTP {code}，耗时 {elapsed:.1f}s，reason={(body or {}).get('reason')!r}")
                if code != 200:
                    fails.append(f"{label}：预算生效时站点应回 200 + ok:false（而不是 HTTP {code}）")
                if (body or {}).get("reason") != "engine_timeout":
                    fails.append(f"{label}：应回 reason='engine_timeout'，实际 {(body or {}).get('reason')!r}")
                if not (want_elapsed_min <= elapsed <= want_elapsed_max):
                    fails.append(f"{label}：耗时 {elapsed:.1f}s 不在 [{want_elapsed_min}, {want_elapsed_max}]s —— "
                                 f"预算没按预期生效")
                else:
                    print(f"   ✓ 在 {elapsed:.1f}s 干脆超时（预算生效，不是挂死）")
                err_text = read_err(err)
                if f'环境变量 OSRM_QUOTE_TIMEOUT_MS="{value}"' not in err_text:
                    if label == "C":
                        fails.append(f"C：夹下限时没在 stderr 打出被拒原值 \"50\"：{err_text.strip()[:200]!r}")
                elif label == "C" and "低于下限" not in err_text:
                    fails.append(f"C：stderr 少了「低于下限」：{err_text.strip()[:200]!r}")
                elif label == "C":
                    print("   ✓ stderr 打出被拒原值 + 「低于下限」")
        finally:
            stop(proc, srv, thread)
    if "B" in measured and "C" in measured and not measured["C"] < measured["B"]:
        fails.append(f"C：夹到 1000ms 后耗时 {measured['C']:.1f}s 不小于 B 的 {measured['B']:.1f}s "
                     f"—— 夹下限没生效（两例都超时，只有耗时能分辨）")
    elif "B" in measured and "C" in measured:
        print(f"\n   ✓ 判别力成立：B（3000ms）{measured['B']:.1f}s > C（夹到 1000ms）{measured['C']:.1f}s")

    # ── D/E 上限与非法值：都是「不能把活引擎误报超时」的回归 ──
    for label, value, expect_warn in (("D", "4294967296", "超过上限"), ("E", "abc", "不是有限正值")):
        print(f"\n{label} OSRM_QUOTE_TIMEOUT_MS={value}（{'2³² → 夹到上限' if label == 'D' else '非法 → 回落默认'}）"
              f" + 引擎延迟 5s → 必须 ok:true")
        srv = thread = proc = None
        try:
            srv, thread, eport = start_fake_engine(5.0)
            proc, sport, err = start_site(eport, {"OSRM_QUOTE_TIMEOUT_MS": value, "HEALTH_PROBE_MS": "0"})
            if proc:
                elapsed, code, body, raw = post_quote(sport, 60)
                ok = (body or {}).get("ok") is True
                print(f"   → HTTP {code}，耗时 {elapsed:.1f}s，ok={ok}")
                if not ok:
                    fails.append(f"{label}：活引擎（延迟 5s）被误报成 {(body or {}).get('reason')!r}"
                                 f"—— 预算没夹/没回落，abort 提前触发（假告警）")
                elif elapsed < 4.0:
                    fails.append(f"{label}：耗时只 {elapsed:.1f}s < 4s —— 没等假引擎回包，结果来源可疑")
                else:
                    print(f"   ✓ 等到 {elapsed:.1f}s 拿到真结果（预算没被回绕成 1ms）")
                leak_check(raw, label)
                err_text = read_err(err)
                if f'环境变量 OSRM_QUOTE_TIMEOUT_MS="{value}"' not in err_text or expect_warn not in err_text:
                    fails.append(f"{label}：stderr 必须同时含被拒原值 \"{value}\" 与「{expect_warn}」，"
                                 f"实际 {err_text.strip()[:220]!r}")
                else:
                    print(f"   ✓ stderr 打出被拒原值 + 「{expect_warn}」")
        finally:
            stop(proc, srv, thread)

    # ── F 真实测算也要刷新健康状态（按需唤醒下的新鲜信号）──
    # 为什么要有这段：周期探查关闭后，lastProbe 只靠启动自检 + 客户真实请求更新；
    # 若不把真实测算写进状态，/api/health 会长时间停在陈旧结果上（部署期间一次瞬时 502 就能挂几小时）。
    print("\nF 真实测算结果写进 /api/health（source='quote'）—— 保活不必唤醒引擎，客户一用就刷新")
    srv = thread = proc = None

    def get_json(url, timeout_s=10):
        raw = curl(url, timeout_s)
        try:
            return json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return None

    try:
        # ⚠️ 延迟必须**明显大于**预算，否则两条路径同时到期、谁赢看定时器粒度：
        #    实测延迟 2.0s vs 预算 2000ms 时结果先回（ms=2010 ok=true）→ 断言随机假红。
        #    这里用 6.0s vs 2000ms，超时是确定的。
        srv, thread, eport = start_fake_engine(6.0)
        proc, sport, err = start_site(eport, {"OSRM_QUOTE_TIMEOUT_MS": "2000", "HEALTH_PROBE_MS": "0"})
        if proc:
            post_quote(sport, 60)                       # 延迟 6s > 预算 2000ms → 引擎级超时
            hb = get_json(f"http://127.0.0.1:{sport}/api/health") or {}
            eng = hb.get("engine") or {}
            lp = eng.get("lastProbe") or {}
            print(f"   超时后 → status={hb.get('status')!r} lastProbe.ok={lp.get('ok')!r} source={lp.get('source')!r} "
                  f"reason={lp.get('reason')!r} stale={eng.get('stale')!r} probeMode={eng.get('probeMode')!r}")
            if lp.get("source") != "quote":
                fails.append(f"F：真实测算后 lastProbe.source 应为 'quote'，实际 {lp.get('source')!r}"
                             f"（健康状态没跟上真实流量）")
            if lp.get("ok") is not False or lp.get("reason") != "engine_timeout":
                fails.append(f"F：引擎超时后应记 ok=false/reason=engine_timeout，实际 {lp!r}")
            if eng.get("stale") is not False:
                fails.append(f"F：刚发生的失败不该标 stale，实际 {eng.get('stale')!r}")
            if hb.get("status") != "degraded":
                fails.append(f"F：新鲜失败应判 degraded，实际 {hb.get('status')!r}")
            if eng.get("probeMode") != "on_demand":
                fails.append(f"F：probeMode 应为 on_demand，实际 {eng.get('probeMode')!r}")

            FakeEngine.delay_s = 0.0                    # 让下一次测算转成功
            elapsed2, code2, body2, _raw2 = post_quote(sport, 60)
            hb2 = get_json(f"http://127.0.0.1:{sport}/api/health") or {}
            eng2 = hb2.get("engine") or {}
            lp2 = eng2.get("lastProbe") or {}
            print(f"   成功后 → HTTP {code2} ok={(body2 or {}).get('ok')!r} / status={hb2.get('status')!r} "
                  f"lastProbe.ok={lp2.get('ok')!r} source={lp2.get('source')!r}")
            if (body2 or {}).get("ok") is not True:
                fails.append(f"F：延迟归零后测算应成功，实际 {body2!r}")
            if lp2.get("ok") is not True or lp2.get("source") != "quote":
                fails.append(f"F：成功测算后应记 ok=true/source='quote'，实际 {lp2!r}")
            if hb2.get("status") != "ok":
                fails.append(f"F：引擎恢复后 status 应为 ok，实际 {hb2.get('status')!r}")
            if not [f for f in fails if f.startswith("F：")]:
                print("   ✓ 真实测算会刷新健康状态：超时→degraded(quote)，成功→ok(quote)")
    finally:
        stop(proc, srv, thread)

    # ── G 引擎冷启动「瞬时 502」：必须自动重试一次（追加段；F 已被上面的健康刷新段占用，编号顺延）──
    # 线上形态：引擎休眠时第一个请求先吃一个 5xx，紧接着就正常。当前实现非 2xx 直接判 engine_error
    # 回客户 → 客户第一次点「测算」看到「引擎暂时不可用」，其实同一份请求再打一次就成。
    print("\nG 引擎瞬时 502（冷启动）：官网必须自动重试一次，别把活引擎报成 engine_error")
    srv = thread = proc = None
    try:
        srv, thread, eport = start_fake_engine_502_once()
        proc, sport, err = start_site(eport, {"OSRM_QUOTE_TIMEOUT_MS": None, "HEALTH_PROBE_MS": "0"})
        if proc:
            # 武装之后才开始算：下一次 /route/cost 回 502，再下一次正常
            FakeEngine502Once.hits = 0
            FakeEngine502Once.pending_502 = True
            nn_payload = {"origin": "南宁", "destination": "河内", "border": "友谊关口岸",
                          "weight_kg": 20000, "mode": "full_truck",
                          "vehicle_model_id": "flatbed_13m"}
            elapsed, code, body, raw = post_quote(sport, 60, nn_payload)
            hits = FakeEngine502Once.hits
            print(f"   → HTTP {code}，耗时 {elapsed:.1f}s，ok={(body or {}).get('ok')!r} "
                  f"reason={(body or {}).get('reason')!r}")
            print(f"   → 假引擎 /route/cost 命中 {hits} 次（首次被武装为 502）")
            print(f"   → 响应：{json.dumps(body, ensure_ascii=False)[:240] if body else raw[:240]}")
            if hits < 2:
                fails.append(f"G：引擎只被请求 {hits} 次 —— 瞬时 502 没有触发重试"
                             f"（客户第一次点测算就吃瘪，其实再打一次就好）")
            if (body or {}).get("ok") is not True:
                fails.append(f"G：首次 502、第二次正常时测算应 ok:true（重试生效），"
                             f"实际 ok={(body or {}).get('ok')!r} reason={(body or {}).get('reason')!r}")
            else:
                if body.get("price_min_vnd") != EXPECT_MIN or body.get("price_max_vnd") != EXPECT_MAX:
                    fails.append(f"G：重试后的区间不对：{body.get('price_min_vnd')}/{body.get('price_max_vnd')}，"
                                 f"应为 {EXPECT_MIN}/{EXPECT_MAX}（售价 ±10% 取整到 10 万）")
                if body.get("distance_km") != 2243.0:
                    fails.append(f"G：重试后的里程应为 2243.0，实际 {body.get('distance_km')!r}")
            leak_check(raw, "G")
            if not [f for f in fails if f.startswith("G：")]:
                print(f"   ✓ 瞬时 502 自动重试成功：引擎被请求 {hits} 次，客户拿到正常结果")
    finally:
        stop(proc, srv, thread)

    # ── 收尾 ──
    print("\n" + "=" * 68)
    if fails:
        print(f"✗ 失败 {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✓ 全部通过：默认 75s 能等住冷启动；预算可配且夹上下限；非法值回落并告警；白名单无泄露")
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        close_stderr_handles()
        for p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
    sys.exit(code)
