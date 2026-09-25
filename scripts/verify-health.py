"""健康检查如实反映引擎依赖 —— 真杀进程、真恢复，不用 mock。

用法：
    ENGINE_API_KEY=... python scripts/verify-health.py [site_url]

环境变量：
    SITE_URL / ENGINE_API_KEY(或 OSRM_ENGINE_KEY，**必填**，拒绝默认值)
    HEALTH_PROBE_WAIT（秒，**显式覆盖**等待预算；不设则按实测探针间隔自动推 ≥ 2×间隔，下限 5s。
                       **只接受有限正值**：nan / inf / 负数 / 0 / 非数字一律记 fail + 明确报错 + 立刻以 2 退出，
                       绝不静默回落 —— nan/inf 会让 deadline 永不到期、脚本在失败路径上挂死）
    HEALTH_PROBE_MEASURE_CAP（秒，实测间隔的采样上限，默认 75）
    ENGINE_PY / ENGINE_CWD（覆盖本机引擎运行时路径，默认见下）

覆盖断言：
  ① 轻量档：HTTP 200 + engine.configured=true + engine.base 只有 host（无路径/无密钥）+ lastProbe 字段齐全
     —— 首个探针回包前 ok=null 属正常 pending（规格 §4 允许字段可空）；断言前先等回包，ok 只接受 boolean|null
     同时**先实测被测站点的探针间隔**（采样两次 lastProbe.at 求差，见下）并据此推等待预算
  ①B 密钥门禁（**先于任何破坏性操作**）：脚本自带的 KEY 必须真能过上游鉴权（只接受非 401 的 2xx/4xx，
     **HTTP 0（连不上）与 5xx 都算失败**），且带密钥走官网出口的测算必须拿到结果 —— 否则就是
     「健康检查报 ok、客户侧测算全 401」的假绿，必须非 0 退出
  ② deep=1：引擎在线 → ok=true；且 lastProbe.at 必须晚于请求时刻（at 是 after-await 的结果时刻）
  ②B deep **单飞合并**（不是 TTL 缓存）：慢依赖 + 30 个真并发 `?deep=1` → 上游 hits 增量 **==1**、
     30 个响应的 at 集合大小 **==1**；**紧接着立即单发 → hits 必须再 +1**（证明结算即失效、没有时间缓存）
  ②C `at` 时序：可控延迟假依赖（800ms）→ `at - time >= 400ms`（把 at 写成请求时刻的实现必须变红）
  ②D reason 覆盖：黑洞依赖（连上不回）→ `timeout`；`engineBase` 三种写法（根/带尾斜杠/.../api/v1）等价
  ③ 取证：打印本机 18000/18001 现状；**只有**官网 base 直连 18000 时才动 18000
  ④ 真杀「官网 base 指向的那个服务」→ 轻量档 status=degraded + lastProbe.ok=false + reason **必须** == 'unreachable'
     → ?deep=1 同样 degraded 且 reason=='unreachable'；轻量档仍秒回 200（保活不变量）
  ⑤ 重新拉起（只拉原本在跑的那个）→ 回到 status=ok + lastProbe.ok=true，且业务测算再次可用
  ⑥ tick 抛错不得带走进程（**在 dist 副本上注入必抛错**，不动仓库源文件）：stderr 失败日志 **≥2 条**且
     两次出现的间隔 **≥ 0.5×探针间隔**（证明「启动 tick」与「setInterval tick」两条路径都在跑且都被 catch），
     同时进程存活、`/api/health` 仍 200；deep 的异常分支 ms 必须是**实测耗时**（不是硬编码 0）
  ⑦ 环境变量边界（每个值都断言，含**上界**）：非有限/≤0 回落默认且 3s ≤1 次；过小夹到下限且 3s 约 3~6 次；
     >2³¹−1 夹到上限且 3s ≤1 次 —— 三种分支都必须在 stderr 出现
     `环境变量 <NAME>="<被拒原值>"`；HEALTH_DEEP_TIMEOUT_MS/HEALTH_PROBE_TIMEOUT_MS 写 2³² 时
     活引擎**不得**被误报 timeout（假告警回归）
  ⑧ 未配置分支（不设 OSRM_API_BASE）→ reason **必须** == 'not_configured'

安全护栏（别再删）：
  - 只对「本机回环 base + 已知开发端口」做杀进程实验；远端/未知 base 一律只跑只读断言
  - 杀之前核对进程命令行身份（kill_port）：**强标识**（命令行含绝对路径片段 deploy/osrm-engine、
    ENGINE_CWD 等）直接放行；只有**弱标识**（`server.py` 之类以 cwd 启动时才剩的串）时必须再做
    **端口自证**（`GET /gateway/health` 回出 `gateway: "jiuneng-osrm-gateway"` 指纹）；两者都不满足 → 拒杀并记失败
  - 端口**没有监听**时 kill_port 记为失败（不是静默跳过）：否则配置了依赖却没监听会整段跳过降级断言、
    脚本仍打「全部通过」= 假绿
  - 进杀进程阶段前记下哪些端口原本在跑（连同它们的 CommandLine）；正常结束/异常/Ctrl-C 都只恢复原本在跑的那些，
    绝不留孤儿进程。**「恢复」= 重新拉起的<新进程>，不等于还原原进程**（PID/命令行都会变）——
    报告里必须如实这么说，别把「端口又能应答了」说成「环境已还原」
  - 拉起的依赖进程，命令行里**必须带绝对路径**（start_port 用 abspath 强制）：否则 CommandLine 里只剩
    `server.py`，下一次身份核验只能靠弱标识 + 端口自证；从**副本**跑脚本时，绝对路径也是唯一能让人看出
    「18001 上坐的是副本进程」的线索 —— 这种情况必须**大声告警**（脚本会用它重启线上端口）
  - 临时站点与假依赖一律 try/finally 收干净（非 daemon 线程 + shutdown/server_close/join，避免解释器关闭时
    与仍在写 stderr 的线程抢锁 → 断言全过却以 127 退出）
  - **所有**子进程调用（curl / netstat / powershell）都带 Python 级 timeout：任一挂住 → 脚本永不退出，
    已经被 ④ 杀掉的依赖就永远等不到 finally/atexit 的恢复
  - **所有 deadline 必须有限**：`deadline = time.time() + nan/inf` 之后 `time.time() >= deadline` **恒为 False**
    → 轮询永不返回。所以 HEALTH_PROBE_WAIT 只接受有限正值（非法值记 fail + 报错 + 立刻以 2 退出，不静默回落），
    并且 poll_light/实测采样上限在算 deadline 前再过一道有限性兜底（将来新增入口也漏不进来）
  - 假依赖/黑洞依赖的监听端口**不落在本机动态端口范围**内（本机实测 1024–15000）：临时站点（node）的**出站
    连接也从这一段取源端口**，撞车时站点侧得到 ECONNREFUSED → `reason='unreachable'`，表现成「产品把活依赖
    误报成不可达」的**假红**（实测撞过一次，端口 4190）。见 `dynamic_safe_port()`

等待预算为什么不能写死：默认配置下（文档配方未设 HEALTH_PROBE_MS）探针间隔是 60s，依赖死后轻量档要
**约 60s** 才变 degraded；原版写死 20s = **必然假红**。所以先实测间隔（采样 lastProbe.at 两次求差）再推
`budget = max(2 × interval, 5.0)`；`HEALTH_PROBE_WAIT` 保留为显式覆盖。

覆盖值是**双刃剑**：非法的覆盖值曾经有两种坏结果 —— 非数字被**静默**换成写死的 20.0（运维以为生效了），
nan/inf 被 max(x, 0.0) 原样放行后灌进 deadline（永不退出，被杀掉的依赖等不到 atexit 恢复）。
现在两种都变成「记 fail + 明确报错 + 退出码 2」，且**在任何破坏性操作之前**拒绝启动。

本机 python urllib 走 127.0.0.1 会被环境拦截，统一 subprocess 调 curl（沿用 scripts/probe-quote-api.py 风格）。
**退出码即结论**：0 = 全部通过，非 0 = 有失败项。
"""
import atexit
import datetime
import http.server
import json
import math
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
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
# 等待预算：**不写死**。默认为 None → 由实测探针间隔推出（max(2×间隔, 5s)，见 measure_wait_budget）。
# HEALTH_PROBE_WAIT 仍可显式覆盖（原版写死 20s，在默认 60s 间隔的站点上必然假红）。
# 覆盖值本身要**过校验**（只接受有限正值）——校验在下面 fails 定义之后，非法值就地退出 2。
WAIT_BUDGET_OVERRIDE: float | None = None
WAIT_BUDGET_S: float = 20.0                  # 实测前的保守兜底（只在校验通过的路径上被覆盖）
MEASURED_INTERVAL_S: float | None = None
PY = os.environ.get("ENGINE_PY", "D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe")
ENGINE_CWD = os.environ.get("ENGINE_CWD", "D:/01_业务/立三方/AIOSRM++/backend")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_CWD = os.path.join(ROOT, "deploy", "osrm-engine")
# 脚本是不是「从仓库根跑」的：副本（临时拷贝、scratch 下的副本）里没有 .git。
# 这一位决定 ④⑤ 的「重新拉起」会不会拿**副本路径**去替换本机长驻服务 → 必须大声告警（见 start_port / 启动横幅）。
IS_REPO_ROOT = os.path.exists(os.path.join(ROOT, ".git"))
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
# 杀进程白名单：端口 → 命令行里**必须**出现的**弱**子串（以 cwd 方式启动时命令行只剩这些）。
# 原版只钉弱串就直接杀，实测会把无关进程（如 `python -m http.server 18014`）杀掉；现在弱串还要过「端口自证」，见 identity_check。
EXPECT_CMDLINE = {
    ENGINE_PORT: ("run_server.py",),
    GATEWAY_PORT: ("server.py",),
}
# 强标识：命令行里出现**绝对路径片段**（脚本自己的 start_port 就是这么起的）→ 无需自证
CMD_STRONG = {
    ENGINE_PORT: tuple(dict.fromkeys([os.path.join(ENGINE_CWD, "run_server.py"),
                                      ENGINE_CWD.replace("\\", "/"), ENGINE_CWD])),
    GATEWAY_PORT: tuple(dict.fromkeys([os.path.join(GATEWAY_CWD, "server.py"),
                                       GATEWAY_CWD, GATEWAY_CWD.replace("\\", "/"),
                                       "deploy/osrm-engine", "deploy\\osrm-engine"])),
}
NODE_EXE = shutil.which("node")
# 临时站点 stderr 落盘目录（断言 warn 文本用；脚本退出时整棵删掉）
SCRATCH_DIR = tempfile.mkdtemp(prefix="verify-health-")
atexit.register(lambda: shutil.rmtree(SCRATCH_DIR, ignore_errors=True))

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


# ── HEALTH_PROBE_WAIT 校验（必须在任何破坏性操作之前）────────────────────
def parse_wait_override(raw):
    """HEALTH_PROBE_WAIT → (覆盖值 | None, 错误说明 | None)。**只接受有限正值**，绝不静默回落。

    为什么必须拒 nan / inf：`deadline = time.time() + nan` 之后 `time.time() >= deadline` **恒为 False**
    （inf 同理）→ `poll_light` 永不返回。在 ④「依赖已杀、站点又始终不降级」这条**失败路径**上，
    脚本就挂死在那里；而恢复逻辑只在 atexit / Ctrl-C 里跑 ⇒ 被杀的依赖永远等不到恢复。
    为什么必须拒非数字 / ≤0，而不是回落默认：原实现把非数字**静默**换成写死的 20.0（正是本次从
    measure_wait_budget 删掉的那个值），运维会以为自己设的覆盖生效了；≤0 则让每个等待预算立刻到期，
    ④⑤ 的降级/恢复断言必然假红。
    """
    if raw is None or raw.strip() == "":
        return None, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, (f"HEALTH_PROBE_WAIT={raw!r} 不是数字：只接受有限正值秒数（例：HEALTH_PROBE_WAIT=30）")
    if not math.isfinite(value):
        return None, (f"HEALTH_PROBE_WAIT={raw!r} 不是有限值：nan/inf 会让 deadline 永不到期"
                      f"（time.time() >= time.time()+nan 恒为 False）→ 脚本在失败路径（依赖已杀、站点不降级）"
                      f"上永不退出，被杀的依赖等不到 atexit 恢复")
    if value <= 0:
        return None, (f"HEALTH_PROBE_WAIT={raw!r} 不是正值：≤0 会让每个等待预算立刻到期，"
                      f"④⑤ 的降级/恢复断言必然假红")
    return value, None


WAIT_BUDGET_OVERRIDE, _WAIT_ERR = parse_wait_override(os.environ.get("HEALTH_PROBE_WAIT"))
if _WAIT_ERR:
    # 非法 = 失败：记 fail + 明确报错 + **立刻**以 2 退出（2 = 参数/环境非法，区别于断言失败的 1）。
    # 必须在这里就停：再往下走一步就会先做破坏性操作（杀依赖），而挂死时没人恢复它。
    fails.append(_WAIT_ERR)
    print(f"\n✗ {_WAIT_ERR}")
    print("  拒绝启动：HEALTH_PROBE_WAIT 只接受**有限正值**（不接受 nan / inf / 负数 / 0 / 非数字），"
          "不允许静默回落。")
    print("  未做任何破坏性操作：依赖（18000/18001）未被触碰。")
    print("\n存在问题：\n  - " + "\n  - ".join(fails))
    print("（退出码 2 = 参数/环境非法，不是断言失败）")
    sys.exit(2)


# ── HTTP（统一走 curl：本机 urllib 直连 127.0.0.1 会被环境拦截）──────────
def run_cmd(args, timeout, input=None, label=None, quiet=False):
    """**带 Python 级 timeout** 的 subprocess.run。

    原版所有调用都没有 timeout：curl / netstat / powershell 任一挂住 → 脚本永不退出 →
    已经被 ④ 杀掉的依赖永远等不到 finally/atexit 的恢复。超时即记失败（quiet 用于纯信息性探测）。
    """
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, input=input)
    except subprocess.TimeoutExpired:
        if not quiet:
            fails.append(f"{label or args[0]} 超时（>{timeout}s）—— 已记失败，避免脚本挂死")
        return None


def _split_code(out):
    body, _, code = out.rpartition("\n")
    try:
        code_i = int(code.strip() or 0)
    except ValueError:
        code_i = 0
    return code_i, body.strip()


def curl(url, timeout=20, want_code=False, quiet=False):
    """curl -s → (http_code, body_text)。返回码 0 表示连不上（**也是超时/失败的取值**）。"""
    p = run_cmd(["curl", "-s", "-m", str(timeout), url, "-w", "\n%{http_code}"],
                timeout=timeout + 10, label=f"curl {url}", quiet=quiet)
    if p is None:
        return (0, "") if want_code else ""
    code_i, body = _split_code(p.stdout.decode("utf-8", "replace"))
    return (code_i, body) if want_code else body


def curl_json(url, timeout=20, quiet=False):
    """→ (http_code, obj|None, raw_text)"""
    code, body = curl(url, timeout, want_code=True, quiet=quiet)
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
    p = run_cmd(args, timeout=timeout + 10, input=json.dumps(payload).encode(), label=f"curl POST {url}")
    if p is None:
        return 0, ""
    return _split_code(p.stdout.decode("utf-8", "replace"))


# ── 进程/端口 ──────────────────────────────────────────────────────────
def pid_on(port):
    p = run_cmd(["netstat", "-ano"], 30, label="netstat -ano")
    if p is None:
        return None
    out = p.stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def proc_info(pid):
    """→ (Name, CommandLine)。进程已退出则返回 ("", "")。"""
    p = run_cmd(["powershell", "-NoProfile", "-Command",
                 f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
                 f"Select-Object Name,CommandLine | ConvertTo-Json -Compress"],
                20, label=f"powershell Get-CimInstance ProcessId={pid}")
    if p is None:
        return "", ""
    txt = p.stdout.decode("utf-8", "replace").strip()
    try:
        obj = json.loads(txt) if txt else {}
    except Exception:
        obj = {}
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    return str(obj.get("Name") or ""), str(obj.get("CommandLine") or "")


def port_self_identity(port):
    """**端口自证**：该端口上的服务自己回出本项目特有的指纹，才算身份对得上。

    为什么需要这一层：网关以 `python server.py`（cwd=deploy/osrm-engine）启动时，Windows 的
    CommandLine **不含** cwd，命令行里只剩 `server.py` 这个弱串 —— 弱串不足以区分
    `python -m http.server 18001` 之类的无关进程（审查实验室实测把无关进程杀掉过）。
    现在弱串必须再过自证：网关的 `GET /gateway/health`（KEY_FREE，无需密钥）回
    `{"status":"ok","gateway":"jiuneng-osrm-gateway"}`。
    """
    if port == GATEWAY_PORT:
        code, body, _ = curl_json(f"http://127.0.0.1:{port}/gateway/health", 6, quiet=True)
        return code == 200 and isinstance(body, dict) and body.get("gateway") == "jiuneng-osrm-gateway"
    if port == ENGINE_PORT:
        code, body, _ = curl_json(f"http://127.0.0.1:{port}/health", 6, quiet=True)
        return code == 200 and isinstance(body, dict) and body.get("status") == "ok"
    return False


def identity_check(port, name, cmd):
    """→ (ok, 说明)。强标识（绝对路径片段）直接放行；弱标识必须过端口自证；都不满足 → 拒杀。"""
    strong = [s for s in CMD_STRONG.get(port, ()) if s and s in cmd]
    if strong:
        return True, f"命令行含绝对路径片段 {strong[0]!r}"
    weak = [s for s in EXPECT_CMDLINE.get(port, ()) if s and s in cmd]
    if not weak:
        return False, (f"命令行既没有绝对路径片段 {CMD_STRONG.get(port)!r} 也没有弱标识 "
                       f"{EXPECT_CMDLINE.get(port)!r}")
    if port_self_identity(port):
        return True, f"命令行只有弱标识 {weak[0]!r}（cwd 启动），但端口自证通过（本项目服务指纹匹配）"
    return False, f"命令行只有弱标识 {weak!r} 且端口自证失败（不是本项目服务）"


def kill_port(port, expect=None):
    """Windows：taskkill 会静默失败，用 Stop-Process 并核对端口已释放。

    ⚠️ 两条纪律（都来自实测事故）：
    1. 杀之前**必须核对身份**（identity_check）：弱标识不够，还要过端口自证；
    2. 端口**没有监听**要**记失败**，不能静默 return —— 否则「configured=true 却没监听」会让 ④/⑤ 整段
       跳过，而脚本照样打「全部通过」（假绿）。
    """
    pid = pid_on(port)
    if not pid:
        fails.append(f"{port} 端口没有监听进程：依赖没在跑 → 无法验证降级/恢复（configured=true 却是这个"
                     f"状态本身就是缺陷，不是「没什么可做的」）")
        print(f"   ✗ {port} 没有监听进程：记失败（不许静默跳过 ④/⑤）")
        return None
    name, cmd = proc_info(pid)
    ok, why = identity_check(port, name, cmd)
    if not ok or not name.lower().startswith("python"):
        fails.append(f"拒绝杀 {port} 端口 PID {pid}：进程身份对不上（Name={name!r} {why}；"
                     f"CommandLine={cmd[:200]!r}）")
        print(f"   ✗ 拒绝杀 PID {pid}：身份对不上（Name={name!r}；{why}）")
        return None
    print(f"   （身份核对通过：{why}）")
    p = run_cmd(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                20, label=f"Stop-Process {pid}")
    if p is None:
        return None
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
    """只认识本机开发端口（18000/18001）；别的端口不许乱拉，避免留孤儿进程。

    ⚠️ 两条纪律（都来自实测事故）：
    ① **命令行里必须放绝对路径**（下面用 os.path.abspath 强制）。原版把 `os.path.join(ENGINE_CWD, ...)`
       原样传进 Popen：ENGINE_CWD 一旦是相对路径，Windows 的 CommandLine 里就只剩 `run_server.py`/
       `server.py` 这种弱串 —— 下一次身份核验只能靠「弱标识 + 端口自证」，实测根本核不出 18001 上坐的是谁。
    ② 从**副本**跑本脚本时，这条启动路径会拿副本里的 `server.py` 去顶替线上 18001 —— 必须大声告警，
       并且报告里如实说「恢复 = 新进程」（PID / 命令行 / 代码版本都不等价于原进程）。
    """
    if port == ENGINE_PORT:
        cwd = os.path.abspath(ENGINE_CWD)
        exe = os.path.abspath(os.path.join(cwd, "run_server.py"))
        cmd, env = [PY, exe, "--port", str(port)], None
    elif port == GATEWAY_PORT:
        cwd = os.path.abspath(GATEWAY_CWD)
        exe = os.path.abspath(os.path.join(cwd, "server.py"))
        cmd, env = [PY, exe], {**os.environ, "PORT": str(port), "ENGINE_API_KEY": KEY}
    else:
        fails.append(f"不知道该怎样拉起端口 {port}（不是本机已知开发端口）")
        return False
    if not IS_REPO_ROOT:
        print(f"   ⚠️⚠️ 警告：本脚本不是从仓库根跑的（ROOT={ROOT} 下没有 .git）——\n"
              f"        现在用**副本路径** {exe} 重启线上端口 {port}。\n"
              f"        新进程是「副本进程」：身份 / 命令行 / 代码版本都不等价于原来的进程，"
              f"核验时一律按这条绝对路径认（别按端口号猜）。", flush=True)
    print(f"   拉起 {port}：{cmd[0]} {exe}（cwd={cwd}；命令行含绝对路径 → CommandLine 可直接核身份）", flush=True)
    proc = subprocess.Popen(cmd, cwd=cwd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if curl(f"http://127.0.0.1:{port}/health", 3, want_code=True)[0] == 200:
            pid = pid_on(port)
            _name, cl = proc_info(pid) if pid else ("", "")
            print(f"   ✓ {port} 已就绪：**新进程** PID={pid}（「恢复」不等于还原原进程：PID/命令行都会变）"
                  f"\n      新进程 CommandLine = {cl[:200]!r}", flush=True)
            return True
        time.sleep(1)
    try:
        if proc.poll() is not None:
            fails.append(f"拉起 {port} 的进程已退出（exit {proc.returncode}）：多半是端口被占/"
                         f"路径或运行时不对 —— 命令行 {cmd!r}")
    except Exception:
        pass
    return False


# ── 恢复护栏：只恢复「进杀进程阶段前原本在跑」的端口；异常/Ctrl-C 也要恢复 ──
ports_running_before: dict[int, bool] = {}
ports_argv_before: dict[int, str] = {}       # 杀之前的 CommandLine（报告里对比「新进程 ≠ 原进程」）
ports_pid_before: dict[int, str] = {}        # 杀之前的 PID（用来判「是不是同一个进程」）
_restoring = False


def snapshot_ports():
    for p in (ENGINE_PORT, GATEWAY_PORT):
        pid = pid_on(p)
        ports_running_before[p] = pid is not None
        if pid:
            ports_pid_before[p] = pid
            _name, cl = proc_info(pid)
            ports_argv_before[p] = f"PID {pid} · {cl}"
    print(f"   （环境快照：原本在跑 = {[p for p, up in ports_running_before.items() if up] or '无'}）")
    for p, desc in ports_argv_before.items():
        print(f"      {p} 原进程 = {desc[:220]}")
    if not IS_REPO_ROOT:
        print(f"   ⚠️ 本脚本不是从仓库根跑的（ROOT={ROOT}）→ 一旦需要「重新拉起」，用的会是**副本路径**。")


def restore_all():
    """幂等：只在「原本在跑、现在掉了」时才拉起。

    ⚠️ 如实说清：「恢复」= 用 start_port 拉起的**新进程**，不是把原进程还原回来 ——
    PID、CommandLine、进程内状态（计数/缓存）都会变。别把「端口又能应答了」当成「环境已还原」。
    """
    global _restoring
    if _restoring:
        return
    _restoring = True
    try:
        for p, was_running in ports_running_before.items():
            if not was_running:
                continue
            if pid_on(p) is None:
                print(f"   [恢复] {p} 原本在跑但现在掉了 → 用**新进程**重新拉起 …", flush=True)
                if ports_argv_before.get(p):
                    print(f"          （原进程 = {ports_argv_before[p][:200]}）", flush=True)
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
def finite_budget(value, what="等待预算", fallback=20.0):
    """**deadline 的最后一道闸**：非有限/非正的值一律不许变成 deadline。

    `deadline = time.time() + nan/inf` 之后 `time.time() >= deadline` 恒为 False → 轮询永不返回。
    HEALTH_PROBE_WAIT 已在启动时被拒（退出 2），这里是给「将来新增的入口」兜底：一旦漏进来，
    就地记 fail + 夹成有限值，绝不让脚本挂死。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = float("nan")
    if not math.isfinite(v) or v <= 0:
        fails.append(f"{what}={value!r} 非有限/非正值：会造成永不到期的 deadline（脚本永不退出），"
                     f"已强制回落到 {fallback}s")
        print(f"   ✗ {what}={value!r} 非有限/非正 → deadline 兜底为 {fallback}s（并记失败）")
        return float(fallback)
    return v


def poll_light(pred, budget=None, interval=1.0, url=None):
    """轮询轻量档直到 pred(body) 为真（后台探针有 HEALTH_PROBE_MS 间隔，不能立刻断言）。

    **至少发一次请求**（即使 budget<=0），所以返回的 last 永远不是 None —— 原版
    `HEALTH_PROBE_WAIT=0` 时会返回 (False, None)，调用方一解包就 TypeError，而那一刻依赖刚被杀掉。
    """
    url = url or f"{SITE}/api/health"
    deadline = time.time() + finite_budget(WAIT_BUDGET_S if budget is None else budget, "poll_light 等待预算")
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


def probe_at(entry):
    lp = (entry or {}).get("engine", {}).get("lastProbe") or {}
    return lp.get("at")


def probe_ms(entry):
    lp = (entry or {}).get("engine", {}).get("lastProbe") or {}
    return lp.get("ms")


def parse_iso(s):
    """ISO 时间串 → datetime（'Z' 结尾）。解析不了返回 None。"""
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def measure_wait_budget():
    """**实测被测站点的探针间隔**，据此推等待预算 —— 绝不写死。

    默认配置（文档配方未设 HEALTH_PROBE_MS）下间隔是 60s：依赖死后轻量档要**约 60s** 才变 degraded，
    原版写死 20s 在标准配置上**必然假红**。做法：采样两次 `lastProbe.at` 求差（必要时先等一次变化）。
    `HEALTH_PROBE_WAIT` 是显式覆盖，设了就完全按它来（并打印说明）。
    """
    global WAIT_BUDGET_S, MEASURED_INTERVAL_S
    url = f"{SITE}/api/health"
    if WAIT_BUDGET_OVERRIDE is not None:
        WAIT_BUDGET_S = finite_budget(WAIT_BUDGET_OVERRIDE, "HEALTH_PROBE_WAIT", 20.0)
        print(f"   （等待预算 {WAIT_BUDGET_S}s 来自显式覆盖 HEALTH_PROBE_WAIT，不做间隔实测）")
        return
    try:
        cap = float(os.environ.get("HEALTH_PROBE_MEASURE_CAP") or 75)
    except ValueError:
        cap = 75.0
    cap = finite_budget(cap, "HEALTH_PROBE_MEASURE_CAP", 75.0)     # 采样上限同样不许非有限（否则轮询挂死）
    _code, body, _raw = curl_json(url, 15)
    at1 = probe_at(body)
    if at1 is None:
        # 站点刚起：首个探针可能还没回包 —— 先等 at 变成非空（这一段等价于 §① 的 pending 等待）
        pend_deadline = time.time() + max(cap, 30.0)
        while time.time() < pend_deadline and at1 is None:
            time.sleep(0.5)
            _code, body, _raw = curl_json(url, 15)
            at1 = probe_at(body)
    if at1 is None:
        fails.append(f"无法实测探针间隔：{url} 的 lastProbe.at 始终为空（首个探针没回包 / 后台探针没在跑）")
        print(f"   ✗ 无法实测探针间隔（lastProbe.at 为空）→ 退回默认预算 {WAIT_BUDGET_S}s")
        return
    deadline = time.time() + cap
    while time.time() < deadline:
        time.sleep(0.5)
        _code, body, _raw = curl_json(url, 15)
        at2 = probe_at(body)
        if at2 and at2 != at1:
            d1, d2 = parse_iso(at1), parse_iso(at2)
            if d1 and d2:
                MEASURED_INTERVAL_S = (d2 - d1).total_seconds()
                break
    if MEASURED_INTERVAL_S is None or MEASURED_INTERVAL_S <= 0:
        fails.append(f"无法实测探针间隔：{cap}s 内 lastProbe.at 始终没变化（后台探针没在跑？）")
        print(f"   ✗ {cap}s 内 lastProbe.at 未变化 → 退回默认预算 {WAIT_BUDGET_S}s（并记失败）")
        return
    WAIT_BUDGET_S = finite_budget(max(2 * MEASURED_INTERVAL_S, 5.0), "由实测间隔推出的等待预算", 20.0)
    print(f"   实测探针间隔 = {MEASURED_INTERVAL_S:.1f}s（采样 lastProbe.at 两次求差）"
          f" → 等待预算 = max(2×间隔, 5s) = {WAIT_BUDGET_S:.1f}s")


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


# ── 临时站点 / 假依赖（②B②C②D⑥⑦⑧ 用；一律 try/finally 收干净）──────────
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


_STDERR_SEQ = {"n": 0}


def start_temp_site(overrides, cwd=None, entry="dist/server.cjs"):
    """起一个临时官网（默认 dist/server.cjs），返回 (proc, port, stderr_path)。

    stderr **不再丢 DEVNULL**：① 断言 warn 文本（`环境变量 <NAME>="<被拒原值>"`）必须有落点；
    ② ⑥ 的 tick 失败日志要在文件里数条数与时间间隔。
    调用方必须 try/finally 收掉。
    """
    port = free_port()
    env = {**os.environ, "NODE_ENV": "production", "PORT": str(port)}
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    _STDERR_SEQ["n"] += 1
    err_path = os.path.join(SCRATCH_DIR, f"site-{_STDERR_SEQ['n']}-{port}.stderr.log")
    errf = open(err_path, "wb")
    proc = subprocess.Popen([NODE_EXE, entry], cwd=cwd or ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=errf)
    errf.close()                                     # 子进程已继承句柄，父进程这侧关掉
    return proc, port, err_path


def start_temp_site_ready(overrides, cwd=None, entry="dist/server.cjs", attempts=3, ready_timeout=25):
    """起临时站点并确认 `GET /api/health` 200。

    **为什么要有重试**：`free_port()` 是「bind(0) → close → 再 bind」的经典竞态 —— 中间被别的进程
    抢走端口，站点就起不来（复核实验室实测撞车）。起不来就换端口重试（≥2 次），不要靠运气。
    → (proc, port, err_path) 或 (None, None, None)（已记失败）
    """
    last_err = ""
    for i in range(max(attempts, 2)):
        proc, port, err_path = start_temp_site(overrides, cwd=cwd, entry=entry)
        deadline = time.time() + ready_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                last_err = f"进程已退出（exit {proc.returncode}），多半是端口 {port} 被抢"
                break
            code = curl(f"http://127.0.0.1:{port}/api/health", 3, want_code=True, quiet=True)[0]
            if code == 200:
                if i:
                    print(f"   （临时站点第 {i + 1} 次尝试起在 PORT={port} 成功）")
                return proc, port, err_path
            time.sleep(0.5)
        last_err = last_err or f"PORT={port} 在 {ready_timeout}s 内没回 200"
        stop_temp_site(proc)
        print(f"   （临时站点第 {i + 1} 次没起来：{last_err} → 换端口重试）")
    fails.append(f"临时站点起不来（已重试 {attempts} 次）：{last_err}")
    return None, None, None


def read_err(err_path):
    try:
        with open(err_path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except Exception:
        return ""


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


# 假依赖 / 黑洞依赖的监听端口必须**避开本机动态端口范围**：本机 `netsh int ipv4 show dynamicport tcp`
# = 起始 1024、13977 个（→ 1024–15000），而临时站点（node）的**出站连接也从这一段取源端口**。
# 实测撞过一次：假依赖 bind 在 4190，站点侧对它的探测一律 ECONNREFUSED → `reason='unreachable'`，
# 表现成「产品把活依赖误报成不可达」的**假红**（而产品没问题）。做法：只在动态范围之上取端口，
# 并把长驻服务端口排除掉。
DYNAMIC_PORT_MAX = 15000
DEP_PORT_MIN = DYNAMIC_PORT_MAX + 1000                       # 16000
DEP_PORT_MAX = 32000
RESERVED_PORTS = {ENGINE_PORT, GATEWAY_PORT, 18123}          # 长驻引擎/网关 + 另一个脚本的挂起桩


def dynamic_safe_port():
    """在动态端口范围之外取一个「此刻真能 bind」的端口（避开与出站源端口撞车）。拿不到就退回 0（OS 自选）。"""
    for _ in range(50):
        port = random.randint(DEP_PORT_MIN, DEP_PORT_MAX)
        if port in RESERVED_PORTS:
            continue
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            probe.close()
        return port
    fails.append(f"动态端口范围之外（>{DYNAMIC_PORT_MAX}）找不到可用端口 → 退回让 OS 自选；"
                 f"在本机上这与出站源端口撞车过一次（假依赖不可达 = 假红）")
    return 0


def start_fake_dep(delay_s=0.0, body=b'{"status":"ok"}'):
    """计数用的假依赖（可加**可控延迟**：并发断言必须让请求真的重叠，at 时序断言需要确定的耗时差）。

    **非 daemon 线程**：daemon 线程在解释器关闭时与仍在写 stderr 的线程抢锁，
    会让进程以 127 退出（Fatal Python error: _enter_buffered_busy）——那样「退出码即结论」就废了。
    """
    state = {"hits": 0}

    class _Handler(http.server.BaseHTTPRequestHandler):
        # HTTP/1.1 + 显式 Content-Length：与 Node fetch(undici) 的 keep-alive 语义一致。
        # 用默认的 HTTP/1.0 时不发 Connection: close，客户端可能把连接当 keep-alive 复用、
        # 而服务端已关闭 → 复用时偶发 ECONNRESET，表现为「探针偶发 ok=false」的**假红**。
        protocol_version = "HTTP/1.1"

        def do_GET(self):                                      # noqa: N802
            state["hits"] += 1
            if delay_s:
                time.sleep(delay_s)
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

    srv = _Quiet(("127.0.0.1", dynamic_safe_port()), _Handler)
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


def start_blackhole_dep():
    """黑洞依赖：**能连上但永不回包** → 探针必须在预算内 abort，reason == 'timeout'。

    （`unreachable` 用「连不上」造；`timeout` 必须用这种「连接建立后假死」的形态造，
    规格 §4.1 的封闭枚举要求这一支也被覆盖。）
    """
    lsock = socket.socket()
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", dynamic_safe_port()))
    lsock.listen(64)
    port = lsock.getsockname()[1]
    state = {"accepted": 0, "stop": False}

    def _loop():
        while not state["stop"]:
            try:
                conn, _addr = lsock.accept()
            except OSError:
                return
            state["accepted"] += 1
            # 故意什么都不回：连接保持打开，客户端只能等到自己的超时

    thread = threading.Thread(target=_loop, name="blackhole-dep", daemon=False)
    thread.start()
    return lsock, thread, state, port


def stop_blackhole_dep(lsock, thread):
    try:
        if lsock:
            lsock.close()
    except Exception:
        pass
    if thread:
        try:
            thread.join(timeout=5)
        except Exception:
            pass


def make_mutant_site_bundle():
    """把 `dist/` 复制到临时目录并**在副本里**注入必抛错（**绝不动仓库源文件/dist**）。

    注入点：`probeEngine` 一开头 `await 300ms` 后必抛 —— 这样「启动 tick」与「setInterval tick」
    两条路径都会 reject，deep 的异常分支耗时也不是 0（用来断言 ms 是实测耗时而不是硬编码 0）。
    → (cwd, entry) 或 None（记失败）
    """
    src = os.path.join(ROOT, "dist")
    if not os.path.isdir(src):
        fails.append(f"找不到 {src}（先 npm run build），无法做 tick 兜底回归")
        return None
    dst = os.path.join(SCRATCH_DIR, "mutant")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, os.path.join(dst, "dist"))
    entry_path = os.path.join(dst, "dist", "server.cjs")
    with open(entry_path, "r", encoding="utf-8") as f:
        code = f.read()
    anchor = "async function probeEngine(timeoutMs = 3e3) {"
    if anchor not in code:
        fails.append(f"dist 副本里找不到注入锚点 {anchor!r}（bundle 结构变了，需同步本脚本）")
        return None
    injected = (anchor + "\n  await new Promise((r) => setTimeout(r, 300));\n"
                "  throw new Error(\"MUTATION: injected probeEngine failure (tick catch regression)\");")
    code = code.replace(anchor, injected, 1)
    with open(entry_path, "w", encoding="utf-8") as f:
        f.write(code)
    return dst, os.path.join("dist", "server.cjs")


print(f"官网 = {SITE}\n引擎(原始) = 127.0.0.1:{ENGINE_PORT}\n网关 = 127.0.0.1:{GATEWAY_PORT}\n"
      f"密钥 = 已提供（长度 {len(KEY)}，不在输出里回显）\n")
if not IS_REPO_ROOT:
    # 副本跑的后果：④ 会杀掉线上依赖，⑤/atexit 会用**副本里的脚本**把它拉起来 —— 线上 18001 上就换成了
    # 副本进程（实测：留下孤儿副本、真网关被替换，且命令行里看不出是谁）。所以先在动任何东西之前喊出来。
    print("⚠️⚠️⚠️  本脚本不是从仓库根跑的（ROOT 下没有 .git）：")
    print(f"       ROOT = {ROOT}")
    print(f"       ④⑤ 若需要重启 18001/18000，用到的会是**副本路径**：")
    print(f"           {os.path.abspath(os.path.join(GATEWAY_CWD, 'server.py'))}")
    print(f"           {os.path.abspath(os.path.join(os.path.abspath(ENGINE_CWD), 'run_server.py'))}")
    print("       ⇒ 线上服务会被**副本进程**顶替（身份/代码版本不等价），且「恢复」只是新进程，不是还原原进程。")
    print("       要跑真仓库，请用仓库根的 scripts/verify-health.py。\n")

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
    # **先实测探针间隔**再推等待预算：④⑤ 的等待全靠它 —— 写死 20s 在默认 60s 间隔的站点上必然假红
    print("   → 实测探针间隔（决定 ④⑤ 的等待预算）…")
    measure_wait_budget()
    lp = eng.get("lastProbe")
    if not isinstance(lp, dict):
        fails.append(f"engine.lastProbe 必须是对象且字段齐全（ok/at/ms，可为 null），实际 {lp!r}")
    else:
        for field in ("ok", "at", "ms"):
            if field not in lp:
                fails.append(f"lastProbe 缺字段 {field}，实际 {lp}")
        if probe_ok(light) is None:
            # 首个探针还没回包 → pending（规格允许字段为 null）。断言前先给它时间，避免刚重启就假失败。
            print(f"   （pending：lastProbe.ok=null，首个探针尚未回包）最多等 {WAIT_BUDGET_S:.1f}s …")
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
    code_key, raw_key = curl_post(f"http://{UP_HOST}:{UPSTREAM_PORT}/api/v1/route/cost", QUOTE_BODY, key=KEY)
    print(f"   直连上游 {UP_HOST}:{UPSTREAM_PORT} 带 X-API-Key 的测算 → HTTP {code_key} {raw_key[:160]}")
    # ⚠️「连不上（HTTP 0）」**不能算通过**：原版只判 ==401，于是上游根本没在监听时这一关照样过，
    #    后面全靠官网业务断言兜底 —— 而上游死了本来正是最该立刻停下的时候。只接受非 401 的 2xx/4xx。
    if code_key == 0:
        fails.append(f"直连上游 {UP_HOST}:{UPSTREAM_PORT} 连不上（HTTP 0）：上游没在监听/链路断了。"
                     f"这不是「通过」，也不是密钥问题 —— 拒绝继续做破坏性实验")
        print("   ✗ HTTP 0（连不上）：不能当通过。")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        sys.exit(1)
    if code_key == 401:
        fails.append("脚本自带的 KEY 过不了上游鉴权（HTTP 401）：密钥不一致 —— "
                     "健康检查会照常报 ok，而客户侧测算会全 401（假绿）")
        print("   ✗ 401：KEY 与上游不一致。健康检查的 ok 是假绿，拒绝继续做破坏性实验。")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        sys.exit(1)
    if not (200 <= code_key < 500):
        fails.append(f"直连上游带密钥测算返回 HTTP {code_key}（只接受非 401 的 2xx/4xx）："
                     f"上游行为异常，不能当通过")
        print(f"   ✗ HTTP {code_key} 不在可接受范围内。")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        sys.exit(1)
    print(f"   ✓ 直连上游可达且未被 401 拒绝（HTTP {code_key}）")
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

# ── ②B deep 单飞合并 vs TTL 缓存（匿名并发不得 1:1 放大成对引擎的外打）────
print("\n②B deep 单飞合并：30 个真并发必须合并成 1 次上游请求，且**不许有 TTL 缓存**")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法做单飞/TTL 缓存回归")
else:
    srv = thread = None
    proc = None
    try:
        # 慢依赖（1.5s）：保证 30 个并发请求真的重叠 —— 否则「单飞合并」与「各自探测」无法区分
        srv, thread, dep_state, dep_port = start_fake_dep(delay_s=1.5)
        proc, site_port, err_path = start_temp_site_ready({
            "OSRM_API_BASE": f"http://127.0.0.1:{dep_port}",
            "HEALTH_PROBE_MS": "60000",          # 背景探针不掺进计数（启动那一次已单独排掉）
            "HEALTH_DEEP_TIMEOUT_MS": "10000",
        })
        if proc:
            base_url = f"http://127.0.0.1:{site_port}"
            ready, last_rdy = poll_light(lambda b: probe_ok(b) is True,
                                        budget=40, interval=0.5, url=f"{base_url}/api/health")
            if not ready:
                fails.append(f"②B 临时站点 {site_port} 的启动探针没在 40s 内回 ok=true："
                             f"{str(last_rdy[2])[:160]}")
            else:
                dep_state["hits"] = 0            # 排掉启动探测那一次
                n = 30
                results: list = [None] * n
                starts: list = [0.0] * n
                barrier = threading.Barrier(n)

                def one_deep(i):
                    barrier.wait()               # 同一刻发出，才是真并发
                    starts[i] = time.time()
                    results[i] = curl_json(f"{base_url}/api/health?deep=1", 40)[1]

                workers = [threading.Thread(target=one_deep, args=(i,), name=f"deep-{i}") for i in range(n)]
                for w in workers:
                    w.start()
                for w in workers:
                    w.join(timeout=60)
                hits_burst = dep_state["hits"]
                spread_ms = round((max(starts) - min(starts)) * 1000) if max(starts) else 0
                ats = {str(probe_at(r)) for r in results}
                oks = [probe_ok(r) for r in results]
                print(f"   30 个并发 ?deep=1（假依赖延迟 1.5s，发起时刻跨度 {spread_ms}ms）")
                print(f"   上游 hits 增量 = {hits_burst}（应 == 1）；响应 at 集合 = {ats}（应只有 1 个元素）")
                if hits_burst != 1:
                    fails.append(f"deep 单飞失败：30 个匿名并发被放大成 {hits_burst} 次上游请求（应 == 1）"
                                 f" —— 官网成了打自己引擎的放大器，会把引擎 IP 限流额度吃光")
                if len(ats) != 1:
                    fails.append(f"deep 单飞失败：30 个并发响应的 lastProbe.at 有 {len(ats)} 个不同取值"
                                 f"（应 == 1，都是同一次探测的结果）")
                if any(o is not True for o in oks):
                    fails.append(f"②B 并发 deep 里出现非 ok=true 的响应：{oks[:20]}")
                # 紧接着**立即**单发一次：hits 必须再 +1 —— 「不许做时间缓存」的正面证据
                t0 = time.time()
                _c2, _b2, raw_after = curl_json(f"{base_url}/api/health?deep=1", 40)
                hits_second = dep_state["hits"]
                delta2 = hits_second - hits_burst
                print(f"   紧接着立即单发（{round((time.time() - t0) * 1000)}ms）→ hits 增量 = {delta2}"
                      f"（应 == 1，证明结算即失效、没有 TTL）")
                if delta2 != 1:
                    fails.append(f"deep 做了时间缓存（TTL）：紧接着的单发没有再次探测上游"
                                 f"（hits {hits_burst} → {hits_second}）。TTL 会把「依赖被杀 → 立刻 degraded」"
                                 f"变成假绿。原始响应 {raw_after[:160]}")
                else:
                    print("   ✓ 单飞合并 + 无 TTL：并发合并成 1 次上游请求，结算后立刻失效")
    finally:
        stop_temp_site(proc)
        stop_fake_dep(srv, thread)

# ── ②C deep 的 at 必须是「拿到结果」的时刻（可控延迟 800ms 假依赖）────────
print("\n②C deep 的 lastProbe.at 必须晚于请求时刻（延迟 800ms 的假依赖 → at-time ≥ 400ms）")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法做 at 时序回归")
else:
    srv = thread = None
    proc = None
    try:
        srv, thread, dep_state, dep_port = start_fake_dep(delay_s=0.8)
        proc, site_port, err_path = start_temp_site_ready({
            "OSRM_API_BASE": f"http://127.0.0.1:{dep_port}",
            "HEALTH_PROBE_MS": "60000",
            "HEALTH_DEEP_TIMEOUT_MS": "8000",
        })
        if proc:
            base_url = f"http://127.0.0.1:{site_port}"
            code, deep_d, raw_d = curl_json(f"{base_url}/api/health?deep=1", 30)
            print(f"   延迟 800ms 的依赖 → HTTP {code} {raw_d[:240]}")
            at_d, time_d = parse_iso(probe_at(deep_d)), parse_iso((deep_d or {}).get("time"))
            if not at_d or not time_d:
                fails.append(f"②C 无法解析 at/time（at={probe_at(deep_d)!r} time={(deep_d or {}).get('time')!r}）")
            else:
                gap_ms = round((at_d - time_d).total_seconds() * 1000)
                print(f"   at - time = {gap_ms}ms（阈值 ≥ 400ms = 延迟 ×0.5）")
                if gap_ms < 400:
                    fails.append(f"deep 的 at 取值不对：at - time = {gap_ms}ms，小于延迟的 50%（400ms）"
                                 f" —— at 必须取 await 之后的**结果**时刻，不是请求时刻")
                else:
                    print("   ✓ at 是结果时刻（把 at 写成请求时刻的实现会在这里变红）")
    finally:
        stop_temp_site(proc)
        stop_fake_dep(srv, thread)

# ── ②D reason 覆盖：黑洞依赖 → timeout；并且三种 engineBase 写法等价 ──────
print("\n②D reason 覆盖（黑洞依赖 → timeout）与 engineBase 三种写法等价性")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法做 reason/base 覆盖")
else:
    # (a) 黑洞：连上但永不回包 → timeout（unreachable 由 ④ 的杀进程覆盖；not_configured 由 ⑧ 覆盖）
    lsock = bthread = None
    proc = None
    try:
        lsock, bthread, bstate, bh_port = start_blackhole_dep()
        proc, site_port, err_path = start_temp_site_ready({
            "OSRM_API_BASE": f"http://127.0.0.1:{bh_port}",
            "HEALTH_PROBE_MS": "1500",
            "HEALTH_PROBE_TIMEOUT_MS": "800",
            "HEALTH_DEEP_TIMEOUT_MS": "800",
        })
        if proc:
            base_url = f"http://127.0.0.1:{site_port}"
            code, deep_bh, raw_bh = curl_json(f"{base_url}/api/health?deep=1", 20)
            print(f"   黑洞依赖 deep=1 → HTTP {code} {raw_bh[:220]}")
            if code != 200:
                fails.append(f"②D 黑洞依赖下 deep=1 应仍 HTTP 200，实际 {code}")
            if probe_reason(deep_bh) != "timeout":
                fails.append(f"②D 黑洞依赖（连上不回包）的 reason 必须是 'timeout'，实际 "
                             f"{probe_reason(deep_bh)!r}（reason 枚举分类反转必须在这里暴露）")
            elif probe_ok(deep_bh) is not False:
                fails.append(f"②D 黑洞依赖下 deep=1 必须 ok=false，实际 {probe_ok(deep_bh)!r}")
            else:
                ms_bh = probe_ms(deep_bh)
                print(f"   ✓ deep reason='timeout'（ms={ms_bh}，预算 800ms）")
                if not isinstance(ms_bh, (int, float)) or ms_bh < 400:
                    fails.append(f"②D 超时分支的 ms 应接近预算（≈800ms），实际 {ms_bh!r}")
            # 轻量档（后台探针，预算 800ms）也必须归为 timeout
            ok_bh, last_bh = poll_light(lambda b: probe_reason(b) == "timeout",
                                        budget=15, interval=0.5, url=f"{base_url}/api/health")
            if not ok_bh:
                fails.append(f"②D 后台探针遇到黑洞依赖未给出 reason='timeout'，实际 "
                             f"{str(last_bh[2])[:200]}")
            else:
                print(f"   ✓ 后台探针同样如实报 reason='timeout'（{str(last_bh[2])[:140]}）")
    finally:
        stop_temp_site(proc)
        stop_blackhole_dep(lsock, bthread)

    # (b) engineBase 三种写法等价：根 / 根+尾斜杠 / 完整 .../api/v1
    srv = thread = None
    try:
        srv, thread, dep_state, dep_port = start_fake_dep()
        forms = [("根地址", f"http://127.0.0.1:{dep_port}"),
                 ("根地址+尾斜杠", f"http://127.0.0.1:{dep_port}/"),
                 ("完整 .../api/v1", f"http://127.0.0.1:{dep_port}/api/v1")]
        for label, base_val in forms:
            proc = None
            try:
                proc, site_port, err_path = start_temp_site_ready({
                    "OSRM_API_BASE": base_val, "HEALTH_PROBE_MS": "2000"})
                if not proc:
                    continue
                base_url = f"http://127.0.0.1:{site_port}"
                code, body_f, raw_f = curl_json(f"{base_url}/api/health", 10)
                ok_f, last_f = poll_light(lambda b: probe_ok(b) is True,
                                          budget=20, interval=0.5, url=f"{base_url}/api/health")
                shown = (last_f[1] if ok_f else body_f) or {}
                got_base = ((shown.get("engine") or {}).get("base"))
                print(f"   engineBase {label}（{base_val}）→ HTTP {code} base={got_base!r} "
                      f"ok={probe_ok(shown)!r} reason={probe_reason(shown)!r}")
                if not ok_f:
                    fails.append(f"②D engineBase 写法 {label}（{base_val}）下探针没报 ok=true："
                                 f"{str(last_f[2])[:200]}")
                if got_base != f"127.0.0.1:{dep_port}":
                    fails.append(f"②D engineBase 写法 {label} 的 engine.base 应为 "
                                 f"'127.0.0.1:{dep_port}'，实际 {got_base!r}")
                if probe_reason(shown) is not None:
                    fails.append(f"②D engineBase 写法 {label} 下不该有 reason，实际 {probe_reason(shown)!r}")
            finally:
                stop_temp_site(proc)
        print("   ✓ 三种 engineBase 写法都能探到同一个假依赖（根/带尾斜杠/完整前缀等价）")
    finally:
        stop_fake_dep(srv, thread)


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

# ── ⑥ tick 抛错不得带走进程（**在 dist 副本上注入必抛错**，不动仓库源文件）──
# 断言强度说明：只断「进程存活 + 全 200」分不清「tick 干脆不跑了」——把启动 tick 与 setInterval
# 全删掉也能满足。所以这里注入必抛错后，要求 stderr 出现 **≥2 条**失败日志，且第 2 条比第 1 条
# 晚 **≥0.5×探针间隔**：证明「启动 tick」与「setInterval tick」两条路径都在跑、且都被 catch 兜住。
print("\n⑥ tick 抛错不得带走进程：启动 tick + setInterval tick 两条路径都必须被 catch")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法做 tick 兜底回归")
else:
    mutant = make_mutant_site_bundle()
    if not mutant:
        print("   ✗ 无法构造注入副本（见 fails）")
    else:
        mcwd, mentry = mutant
        proc = None
        interval_ms = 2000
        try:
            proc, site_port, err_path = start_temp_site_ready(
                {"HEALTH_PROBE_MS": str(interval_ms),
                 "NODE_PATH": os.path.join(ROOT, "node_modules")},
                cwd=mcwd, entry=mentry)
            if proc:
                print(f"   注入副本 PORT={site_port}（dist 副本在 {mcwd}，仓库 dist 未被改动）")
                t_start = time.time()
                deadline = t_start + (2 * interval_ms / 1000) + 5
                samples = []
                while time.time() < deadline:
                    samples.append((time.time() - t_start, read_err(err_path).count("探针 tick 失败")))
                    time.sleep(0.25)
                n_fail = samples[-1][1] if samples else 0
                t_first = next((t for t, c in samples if c >= 1), None)
                t_second = next((t for t, c in samples if c >= 2), None)
                print(f"   stderr 里「探针 tick 失败」= {n_fail} 条；第 1 条出现在 "
                      f"{'%.2fs' % t_first if t_first is not None else 'N/A'}，第 2 条 "
                      f"{'%.2fs' % t_second if t_second is not None else 'N/A'}"
                      f"（探针间隔 {interval_ms}ms）")
                if n_fail < 2:
                    fails.append(f"注入必抛错后只看到 {n_fail} 条 tick 失败日志（应 ≥2：启动 tick + "
                                 f"setInterval tick 各一次）—— 要么定时器没在跑，要么失败没被 catch 下来")
                elif t_first is None or t_second is None or (t_second - t_first) < interval_ms / 1000 * 0.5:
                    fails.append(f"两条 tick 失败日志间隔只有 "
                                 f"{'%.2fs' % (t_second - t_first) if t_first is not None and t_second is not None else 'N/A'}"
                                 f"，短于 0.5×间隔（{interval_ms / 1000 * 0.5:.1f}s）—— 定时器那条路径没真在跑")
                else:
                    print(f"   ✓ 两条 tick 路径都在跑且都被 catch（间隔 {t_second - t_first:.2f}s ≥ "
                          f"0.5×{interval_ms}ms）")
                if proc.poll() is not None:
                    fails.append(f"注入必抛错后进程死了（exit {proc.returncode}）：未捕获的 rejection 带走了"
                                 f"整个进程，官网连同保活端点一起挂")
                else:
                    code, _body, raw = curl_json(f"http://127.0.0.1:{site_port}/api/health", 10)
                    print(f"   进程存活；轻量档 → HTTP {code}")
                    if code != 200:
                        fails.append(f"tick 持续失败时轻量档应仍 HTTP 200，实际 {code} {raw[:160]}")
                # deep 的异常分支：ms 必须是**实测耗时**（不许硬编码 0），日志要能区分「内部异常」与「依赖不可达」
                code_d, deep_m, raw_d = curl_json(f"http://127.0.0.1:{site_port}/api/health?deep=1", 20)
                ms_m = probe_ms(deep_m)
                print(f"   deep=1（探测内部必抛错）→ HTTP {code_d} ms={ms_m!r} "
                      f"reason={probe_reason(deep_m)!r}")
                if code_d != 200 or probe_ok(deep_m) is not False:
                    fails.append(f"deep 探测内部异常时应 HTTP 200 + ok=false，实际 {code_d} {raw_d[:160]}")
                if probe_reason(deep_m) not in ("unreachable", "internal"):
                    fails.append(f"deep 异常分支的 reason 必须在枚举内，实际 {probe_reason(deep_m)!r}")
                if not isinstance(ms_m, (int, float)) or ms_m < 150:
                    fails.append(f"deep 异常分支的 ms 必须是**实测耗时**（注入的失败在 300ms 后抛出），"
                                 f"实际 {ms_m!r} —— 硬编码 0 会把「测量失败」伪装成「未测量」")
                else:
                    print(f"   ✓ deep 异常分支 ms={ms_m} 是实测耗时（不是硬编码 0）")
                err_now = read_err(err_path)
                if "deep 探测内部异常" not in err_now:
                    fails.append("deep 异常分支的日志没有区分「内部异常」与「依赖不可达」（必须能区分，"
                                 "否则代码 bug 会被伪装成依赖故障）")
                else:
                    print("   ✓ 日志里明确标出「deep 探测内部异常（不是依赖不可达）」")
                print(f"   （stderr 尾部：{err_now.strip().splitlines()[-1][:160] if err_now.strip() else '(空)'}）")
        finally:
            stop_temp_site(proc)            # 先停临时站点（它会一直打假依赖）

# ── ⑦ 环境变量边界：回落 / 夹下限 / **夹上界**，三种分支都不得变成忙循环 ──
# 阈值按分支收紧（原版只有 'abc' 一例且阈值 8，注释自称应 ≤2）：
#   回落（abc / 0 / 空串）→ 3s 内 ≤1 次（启动那一次在窗口开始前就打完了）；夹下限（50→1000ms）→ 6s 内 ~6 次；
#   夹上限（2³² → 2³¹−1）→ 3s 内 ≤1 次。**并且必须在 stderr 看到被拒的原始值**（静默夹紧 = 运维查不出）。
# ⚠️ 夹下限那条的下限**必须留足余量**：实测（同一台机、同一探针间隔，用脚本自己的 start_temp_site_ready
#    起站点）节奏是「每 ~2.0s 命中 2 次」，3s 窗口只数得到 2 次 —— 原阈值恰好 == 实测下限，余量为 0，
#    机器一抖就变假红（复核方三次实测 2/3/3）。所以夹下限用 **6s 窗口 + 下限 3 次**：6 次实测 6s 窗口
#    hits=[6,5,5,5,5,5]（min=5），下限 3 留出 **2 次余量**（= 一整个探测节奏）。
#    分辨力不受影响：回落到 60s 时 6s 窗口内是 **0** 次（0 < 3，红），回绕成 1ms 时是上千次（> 14，红）。
print("\n⑦ 环境变量边界：回落 / 夹下限 / 夹上限，且都必须把被拒的原始值打进 stderr")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法做 env 边界回归")
else:
    srv = thread = None
    try:
        srv, thread, dep_state, dep_port = start_fake_dep()
        # (值, 分支, 观察窗口秒, 窗口内 hits 下限, 上限, 必需告警文本)
        # 窗口按分支取：回落/上界分支不需要长窗口（它们要证的是「≤1 次」），夹下限要留余量（见上面的实测）。
        cases = [
            ("abc", "fallback", 3.0, None, 1, None),
            ("0", "fallback", 3.0, None, 1, None),
            ("", "fallback", 3.0, None, 1, None),
            ("50", "clamp_low", 6.0, 3, 14, "低于下限"),
            ("4294967296", "clamp_high", 3.0, None, 1, "超过上限"),
        ]
        for value, kind, window_s, min_hits, max_hits, expect_warn in cases:
            proc = None
            try:
                proc, site_port, err_path = start_temp_site_ready({
                    "OSRM_API_BASE": f"http://127.0.0.1:{dep_port}",
                    "HEALTH_PROBE_MS": value})
                if not proc:
                    continue
                dep_state["hits"] = 0
                time.sleep(window_s)
                hits = dep_state["hits"]
                err_text = read_err(err_path)
                shown = json.dumps(value)
                print(f"   HEALTH_PROBE_MS={shown:<14}（{kind}）{window_s:.0f} 秒内假依赖收到 {hits} 次 /health")
                if hits > max_hits:
                    fails.append(f"HEALTH_PROBE_MS={shown}（{kind}）让探针变成了忙循环：{window_s:.0f} 秒 {hits} 次"
                                 f"（应 ≤{max_hits}）—— 会把引擎 IP 限流额度吃光，客户测算会吃 429")
                if min_hits is not None and hits < min_hits:
                    fails.append(f"HEALTH_PROBE_MS={shown} 应夹到下限 1000ms（{window_s:.0f} 秒该有 ~{window_s:.0f} 次探针；"
                                 f"下限 {min_hits} 已比实测下限低 2 次，不是 0 余量），实际只探了 {hits} 次 —— 夹下限没生效")
                if f'环境变量 HEALTH_PROBE_MS={shown}' not in err_text:
                    fails.append(f"HEALTH_PROBE_MS={shown}（{kind}）被拒/被夹时**没有**在 stderr 打出被拒的"
                                 f"原始值（运维看不出自己的值没生效）")
                if expect_warn and expect_warn not in err_text:
                    fails.append(f"HEALTH_PROBE_MS={shown} 的告警文本里没有「{expect_warn}」："
                                 f"stderr={err_text.strip()[:200]!r}")
                if (f'环境变量 HEALTH_PROBE_MS={shown}' in err_text
                        and (not expect_warn or expect_warn in err_text)):
                    print(f"   ✓ {kind}：已按规则处理，且 stderr 有告警（含被拒原值）")
                code, body, raw = curl_json(f"http://127.0.0.1:{site_port}/api/health", 5)
                if code != 200:
                    fails.append(f"env 边界用例 {shown}：临时站点健康检查异常 HTTP {code} {raw[:160]}")
                elif probe_ok(body) is not True:
                    # 回落分支的站点 60s 才探第二次，只靠「启动那一次」判 ok=true 会被环境抖动放大成假红。
                    # 兜底再证一次：deep=1 是当场实时探测（独立请求），它 ok=true 就说明探针本身没坏。
                    _c3, deep_e, raw_e = curl_json(f"http://127.0.0.1:{site_port}/api/health?deep=1", 20)
                    if probe_ok(deep_e) is not True:
                        fails.append(f"env 边界用例 {shown}：探针打不通假依赖（轻量 {raw[:160]} / "
                                     f"deep {raw_e[:160]}）—— 归一逻辑把探测弄坏了")
                    else:
                        print(f"   （启动那次探针 ok=false（reason={probe_reason(body)!r}），"
                              f"deep=1 实时探测 ok=true → 按环境抖动处理，不判失败）")
            finally:
                stop_temp_site(proc)

        # 同类漏洞的另两张脸：超上限的**预算**会把活引擎误报成 timeout（假告警）
        # Node 定时器把 2³² 回绕成 ~1ms → abort 立刻触发 → **活引擎**被判 timeout。
        # 这里用**慢依赖（1.5s 回包）**让这件事可确定地暴露：预算若真被夹到上限，1.5s 的探测照样成功；
        # 若没夹（回绕成 1ms），abort 会在依赖回包前触发 → 活依赖被误报 ok=false/reason='timeout'。
        print("   → HEALTH_DEEP_TIMEOUT_MS / HEALTH_PROBE_TIMEOUT_MS 写 2³² 不得把活引擎误报成 timeout")
        srv2 = thread2 = None
        proc = None
        try:
            srv2, thread2, _st2, slow_port = start_fake_dep(delay_s=1.5)
            proc, site_port, err_path = start_temp_site_ready({
                "OSRM_API_BASE": f"http://127.0.0.1:{slow_port}",
                "HEALTH_DEEP_TIMEOUT_MS": "4294967296",
                "HEALTH_PROBE_TIMEOUT_MS": "4294967296",
                "HEALTH_PROBE_MS": "2000"})
            if proc:
                code, deep_b, raw_b = curl_json(f"http://127.0.0.1:{site_port}/api/health?deep=1", 20)
                print(f"   活依赖（1.5s 回包）deep=1 → HTTP {code} {raw_b[:200]}")
                if code != 200 or probe_ok(deep_b) is not True:
                    fails.append(f"预算写 2³² 时活依赖被误报成不可达/超时（假告警）：{raw_b[:220]}")
                elif probe_reason(deep_b) is not None:
                    fails.append(f"活依赖不该有 reason，实际 {probe_reason(deep_b)!r}（预算回绕成 ~1ms → 假 timeout）")
                else:
                    print(f"   ✓ 预算超上限被夹紧，活依赖仍如实报 ok=true（ms={probe_ms(deep_b)}）")
                ok_bg, last_bg = poll_light(lambda b: probe_ok(b) is not None and probe_ok(b) is True,
                                            budget=15, interval=0.5,
                                            url=f"http://127.0.0.1:{site_port}/api/health")
                if not ok_bg:
                    fails.append(f"后台探针的预算写 2³² 后把活依赖误报成不可达：{str(last_bg[2])[:200]}")
                else:
                    print("   ✓ 后台探针（预算同样夹到上限）也如实报 ok=true")
                err_text = read_err(err_path)
                for name in ("HEALTH_DEEP_TIMEOUT_MS", "HEALTH_PROBE_TIMEOUT_MS"):
                    if f'环境变量 {name}="4294967296"' not in err_text or "超过上限" not in err_text:
                        fails.append(f"{name}=4294967296 被夹紧时没有在 stderr 打出被拒原值 + 「超过上限」："
                                     f"stderr={err_text.strip()[:200]!r}")
                if f'环境变量 HEALTH_DEEP_TIMEOUT_MS="4294967296"' in err_text and "超过上限" in err_text:
                    print("   ✓ 两个超上限预算都在 stderr 打了被拒原值与「超过上限」告警")
        finally:
            stop_temp_site(proc)
            stop_fake_dep(srv2, thread2)
    finally:
        stop_fake_dep(srv, thread)      # 非 daemon 线程必须 join，否则退出码不可信

# ── ⑧ 未配置分支：不设 OSRM_API_BASE → reason 必须 == 'not_configured' ────
print("\n⑧ 未配置分支：不设 OSRM_API_BASE → reason 必须 == 'not_configured'")
if not NODE_EXE:
    fails.append("找不到 node 可执行文件，无法验证未配置分支")
else:
    proc = None
    try:
        proc, site_port, err_path = start_temp_site_ready({"OSRM_API_BASE": None, "HEALTH_PROBE_MS": "4000"})
        if proc:
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
print("（说明：本脚本的「恢复」= 用 start_port 拉起的**新进程**，不是把原进程还原回来 —— "
      "PID / CommandLine / 进程内状态都会变；上面各步打印的新进程 CommandLine 就是核身份的凭据。）")
for _p in (ENGINE_PORT, GATEWAY_PORT):
    if ports_argv_before.get(_p):
        _pid_now = pid_on(_p)
        _n, _cl = proc_info(_pid_now) if _pid_now else ("", "")
        _same = _pid_now is not None and _pid_now == ports_pid_before.get(_p)
        print(f"   {_p}：原进程 = {ports_argv_before[_p][:160]}")
        print(f"   {_p}：现进程 = PID {_pid_now} · {_cl[:160]}"
              f"{'（同一个进程·未被替换）' if _same else '（不是原进程 → 「恢复」是新进程，不是还原）'}")
if MEASURED_INTERVAL_S is not None:
    print(f"（实测探针间隔 {MEASURED_INTERVAL_S:.1f}s → 等待预算 {WAIT_BUDGET_S:.1f}s）")
print("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails))
sys.exit(1 if fails else 0)
