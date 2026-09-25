"""健康检查如实反映引擎依赖 —— 真杀进程、真恢复，不用 mock。

用法：
    python scripts/verify-health.py [site_url]

环境变量：
    SITE_URL / ENGINE_API_KEY(或 OSRM_ENGINE_KEY) / HEALTH_PROBE_WAIT（秒，默认 20）

覆盖断言：
  ① 轻量档：HTTP 200 + engine.configured=true + engine.base 只有 host（无路径/无密钥）+ lastProbe 字段齐全
  ② 轻量档在依赖死掉时也必须秒回 200（保活用，绝不能被拖死）
  ③ 真杀「官网 base 指向的那个服务」→ 轻量档 status=degraded + lastProbe.ok=false + reason ∈ 封闭枚举
     → ?deep=1 同样 degraded + reason 合理
  ④ 重新拉起 → 轻量档回到 status=ok + lastProbe.ok=true（拒绝谎报）
  ⑤ 取证：官网 base 指向 18001 时，单独杀 18000 的原始引擎进程会不会让官网降级（网关是否掩盖）
     —— 结果打印出来，断言只钉「轻量档仍然 200」这一保活不变量

本机 python urllib 走 127.0.0.1 会被环境拦截，统一 subprocess 调 curl（沿用 scripts/probe-quote-api.py 风格）。
"""
import json
import os
import subprocess
import sys
import time

SITE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SITE_URL", "http://127.0.0.1:3300")).rstrip("/")
ENGINE_PORT = 18000                                  # 原始引擎（AIOSRM++ run_server.py）
GATEWAY_PORT = 18001                                 # 官网专用网关（deploy/osrm-engine/server.py，内嵌引擎 app）
WAIT_BUDGET_S = int(os.environ.get("HEALTH_PROBE_WAIT", "20"))
KEY = os.environ.get("ENGINE_API_KEY") or os.environ.get("OSRM_ENGINE_KEY") or "test-key-abc123"
PY = "D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe"
ENGINE_CWD = "D:/01_业务/立三方/AIOSRM++/backend"
GATEWAY_CWD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy", "osrm-engine")
REASON_ENUM = {"not_configured", "timeout", "unreachable"}

fails: list[str] = []


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


def pid_on(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def kill_port(port):
    """Windows：taskkill 会静默失败，用 Stop-Process 并核对端口已释放。"""
    pid = pid_on(port)
    if not pid:
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
    return pid


def start_port(port):
    if port == ENGINE_PORT:
        subprocess.Popen([PY, "run_server.py", "--port", str(port)], cwd=ENGINE_CWD,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif port == GATEWAY_PORT:
        env = {**os.environ, "PORT": str(port), "ENGINE_API_KEY": KEY}
        subprocess.Popen([PY, "server.py"], cwd=GATEWAY_CWD, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        fails.append(f"不知道该怎样拉起端口 {port}")
        return False
    for _ in range(60):
        if curl(f"http://127.0.0.1:{port}/health", 3, want_code=True)[0] == 200:
            return True
        time.sleep(1)
    return False


def wait_light(pred, label, budget=WAIT_BUDGET_S):
    """轮询轻量档直到满足 pred（后台探针有 HEALTH_PROBE_MS 间隔，不能立刻断言）。"""
    deadline = time.time() + budget
    last = None
    while time.time() < deadline:
        code, body, raw = curl_json(f"{SITE}/api/health", 10)
        last = (code, body, raw)
        if code == 200 and body and pred(body):
            return True, last
        time.sleep(1)
    return False, last


def probe_ok(entry):
    return (entry or {}).get("engine", {}).get("lastProbe", {}).get("ok")


print(f"官网 = {SITE}\n引擎(原始) = 127.0.0.1:{ENGINE_PORT}\n网关 = 127.0.0.1:{GATEWAY_PORT}\n等待预算 = {WAIT_BUDGET_S}s\n")

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
        fails.append(f"engine.lastProbe 缺失（后台探针结果），实际 {lp!r}")
    else:
        for field in ("ok", "at", "ms"):
            if field not in lp:
                fails.append(f"lastProbe 缺字段 {field}，实际 {lp}")
        if not isinstance(lp.get("ok"), bool):
            fails.append(f"lastProbe.ok 应为布尔，实际 {lp.get('ok')!r}")
        if lp.get("ok") is False and not lp.get("reason"):
            fails.append(f"lastProbe.ok=false 时必须带 reason，实际 {lp}")
print(f"   {'✓' if not fails else '✗'} 轻量档字段检查（engine.configured / base 仅 host / lastProbe 齐全）")

# 契约不成立就没法做后面的降级断言（后置阶段会杀进程），这里快速失败
if not isinstance(eng, dict):
    print()
    print("存在问题：\n  - " + "\n  - ".join(fails))
    print("（轻量档缺 engine 契约，跳过降级/恢复实验）")
    sys.exit(1)

# 官网 base 指向哪个端口 —— 那才是官网真正的依赖（本机=网关 18001）
UPSTREAM_PORT = GATEWAY_PORT
if isinstance(eng, dict) and eng.get("base") and ":" in str(eng["base"]):
    try:
        UPSTREAM_PORT = int(str(eng["base"]).rsplit(":", 1)[1])
    except ValueError:
        pass
print(f"   → 官网依赖的端口：{UPSTREAM_PORT}（engine.base = {eng.get('base') if isinstance(eng, dict) else None}）")

# ── ② deep=1（依赖在线）────────────────────────────────────────────────
code, deep_up, raw_up = curl_json(f"{SITE}/api/health?deep=1", 20)
print(f"\n② deep=1 引擎在线 HTTP {code}\n   {raw_up[:300]}")
if code != 200 or not isinstance(deep_up, dict):
    fails.append(f"deep=1 应 HTTP 200 + JSON，实际 HTTP {code} body={raw_up[:200]}")
elif probe_ok(deep_up) is not True:
    fails.append(f"引擎在线时 deep=1 应 lastProbe.ok=true，实际 {json.dumps(deep_up, ensure_ascii=False)}")
elif deep_up.get("status") != "ok":
    fails.append(f"引擎在线时 deep=1 status 应为 ok，实际 {deep_up.get('status')!r}")

# ── ③ 取证：单杀 18000 原始引擎 —— 网关（官网真实依赖）会不会掩盖 ──────────
print("\n③ 取证：单独杀掉 18000 的原始引擎进程（官网依赖的是 %d）" % UPSTREAM_PORT)
gw_before = curl(f"http://127.0.0.1:{GATEWAY_PORT}/health", 10, want_code=True)
print(f"   杀之前 网关 {GATEWAY_PORT}/health → HTTP {gw_before[0]} {gw_before[1][:80]}")
eng_before = curl(f"http://127.0.0.1:{ENGINE_PORT}/health", 10, want_code=True)
print(f"   杀之前 引擎 {ENGINE_PORT}/health → HTTP {eng_before[0]} {eng_before[1][:80]}")

killed_18000 = kill_port(ENGINE_PORT)
print(f"   已杀 18000 PID={killed_18000}；等待 {WAIT_BUDGET_S}s 让后台探针至少跑一轮…")
eng_after = curl(f"http://127.0.0.1:{ENGINE_PORT}/health", 6, want_code=True)
gw_after = curl(f"http://127.0.0.1:{GATEWAY_PORT}/health", 10, want_code=True)
print(f"   杀之后 引擎 {ENGINE_PORT}/health → HTTP {eng_after[0]} {eng_after[1][:120] or '(空)'}")
print(f"   杀之后 网关 {GATEWAY_PORT}/health → HTTP {gw_after[0]} {gw_after[1][:120] or '(空)'}")

time.sleep(WAIT_BUDGET_S)
code, light_18000down, raw_l = curl_json(f"{SITE}/api/health", 10)
code_d, deep_18000down, raw_d = curl_json(f"{SITE}/api/health?deep=1", 20)
print(f"   官网轻量 → HTTP {code} {raw_l[:220]}")
print(f"   官网deep  → HTTP {code_d} {raw_d[:220]}")
if code != 200:
    fails.append(f"依赖不在线时轻量档仍必须 HTTP 200（保活），实际 {code}")
if UPSTREAM_PORT == ENGINE_PORT:
    print("   （官网 base 直连 18000，本段即降级验证）")
else:
    mask = "掩盖（仍 200）" if gw_after[0] == 200 else "未掩盖（非 200）"
    verdict = "degraded" if (light_18000down or {}).get("status") == "degraded" else str((light_18000down or {}).get("status"))
    print(f"   → 发现：网关对 18000 的死亡 {mask}；官网聚合状态 = {verdict}")
    print(f"   → 即：官网聚合结论对应的是它 base 指向的服务（{UPSTREAM_PORT}），不是 18000 —— 降级断言必须按 {UPSTREAM_PORT} 来杀")

print(f"   重新拉起 18000 … {'OK' if start_port(ENGINE_PORT) else '失败'}")

# ── ④ 核心：杀掉官网真实依赖（base 指向的端口）→ 必须降级 ────────────────
print(f"\n④ 杀掉官网真实依赖（{UPSTREAM_PORT}）")
killed = kill_port(UPSTREAM_PORT)
print(f"   已杀 PID={killed}；等后台探针降级（最多 {WAIT_BUDGET_S}s）")
ok, last = wait_light(lambda b: b.get("status") == "degraded" and probe_ok(b) is False, "degraded")
code, body, raw = last
print(f"   轻量 → HTTP {code} {raw[:260]}")
if not ok:
    fails.append(f"{WAIT_BUDGET_S}s 内轻量档未变为 status=degraded 且 lastProbe.ok=false，实际 {raw[:220]}")
else:
    r = body.get("engine", {}).get("lastProbe", {}).get("reason")
    if not r:
        fails.append("降级时 lastProbe 缺 reason")
    elif r not in REASON_ENUM and not str(r).startswith("status_"):
        fails.append(f"lastProbe.reason 不在封闭枚举内：{r!r}")
    print(f"   ✓ 轻量档如实降级：status=degraded lastProbe.ok=false reason={r!r}")

code, deep_down, raw_dd = curl_json(f"{SITE}/api/health?deep=1", 20)
print(f"   deep=1 → HTTP {code} {raw_dd[:260]}")
if code != 200 or not isinstance(deep_down, dict):
    fails.append(f"依赖死掉后 deep=1 应仍 HTTP 200 + JSON，实际 HTTP {code} {raw_dd[:160]}")
else:
    if deep_down.get("status") != "degraded":
        fails.append(f"依赖死掉后 deep=1 status 应为 degraded，实际 {deep_down.get('status')!r}")
    if probe_ok(deep_down) is not False:
        fails.append(f"依赖死掉后 deep=1 仍报 ok（谎报）：{json.dumps(deep_down, ensure_ascii=False)}")
    r = (deep_down.get("engine", {}).get("lastProbe", {}) or {}).get("reason")
    if not r:
        fails.append(f"依赖死掉后 deep=1 缺 reason：{json.dumps(deep_down, ensure_ascii=False)}")
    elif r not in REASON_ENUM and not str(r).startswith("status_"):
        fails.append(f"deep=1 reason 不在封闭枚举内：{r!r}")
    else:
        print(f"   ✓ deep=1 实时探测如实降级：status=degraded reason={r!r}")

# 轻量档在依赖死掉时必须仍然秒回（不能等探测）
t0 = time.time()
code, raw = curl(f"{SITE}/api/health", 10, want_code=True)
fast_ms = round((time.time() - t0) * 1000)
print(f"   轻量档（依赖已死）HTTP {code} 耗时 {fast_ms} ms")
if code != 200:
    fails.append(f"依赖死掉后轻量档必须 HTTP 200，实际 {code}")
if fast_ms > 1500:
    fails.append(f"依赖死掉后轻量档耗时 {fast_ms} ms（>1500ms），说明它在实时探测而没走缓存")

# ── ⑤ 恢复：拉回依赖 → 必须回到 ok ──────────────────────────────────────
print(f"\n⑤ 重新拉起 {UPSTREAM_PORT} 并等待恢复")
if not start_port(UPSTREAM_PORT):
    fails.append(f"端口 {UPSTREAM_PORT} 重启失败（环境问题，非本切片缺陷，请手工确认）")
else:
    ok, last = wait_light(lambda b: b.get("status") == "ok" and probe_ok(b) is True, "recovered")
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

print()
print("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails))
sys.exit(1 if fails else 0)
