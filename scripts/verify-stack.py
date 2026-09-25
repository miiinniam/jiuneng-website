#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T3 验收：`npm run stack` —— 本机三服务守护（崩溃自恢复）。

被测对象：`scripts/serve-stack.mjs`（= `npm run stack`）。本脚本只通过**公开入口**驱动它：
  ① 端口占用前置检查：三端口已被占用时，守护必须**明确报出占用 PID + 命令行**、以非 0 退出，且**不碰**现有服务；
  ② 崩溃恢复（计划 Task 3 的原验收）：故意杀引擎(18000) → 退避后自动重启（**新 PID、父进程 = 守护**）→ 引擎健康 →
     官网测算接口仍可用（真实 POST /api/osrm-quote，ok=true 且非 401）；
  ③ 端到端恢复（补 ② 的假绿面）：杀**站点真实依赖**网关(18001) → 测算**必须先失败**（否则说明 18001 上还有别的
     监听者在顶着，正是「杀一个静默影响另一个」那个坑）→ 守护重启网关 → 测算回到 ok=true；
  ④ 超限全停：STACK_MAX_RESTARTS=1 时连杀 2 次 → 守护**停掉全部子进程**、以非 0 退出并打印明确报错；
  ⑤ 收尾：三服务恢复到在跑（各 **1 行** LISTENING、CommandLine 含绝对路径）+ 再跑一次真实测算。

纪律（每条都对应本仓库已踩过的坑，别再退回去）：
  1. **杀/停任何进程前先核身份**；清场 =「命令行里的绝对路径片段 / 弱标识 + 端口自证」双核对。
     **严禁按端口号段扫**（14013-14023 是微信 Weixin.exe、17551 是用户 anhem 桌面版，扫号段必误伤）。
  2. **数端口只认 `LISTENING` 行数**：Windows 的 SO_REUSEADDR 允许同端口多 listener，
     只判「端口在不在」会漏掉重复监听者（杀一个静默影响另一个，身份判定也不可靠）。
  3. 所有子进程调用都带 Python 级 `timeout`；`TimeoutExpired` **记 fail**（任一挂住 = 脚本永不退出 =
     已经被杀的服务等不到恢复）。
  4. **「没做成」一律记 fail**：绝不允许静默 return 把整段断言跳过还打「全部通过」。
  5. 等待预算**不写死**：恢复预算 = `max(3 × 实测该服务冷启动秒数, 15s)`；`STACK_RECOVER_WAIT` 可显式覆盖，
     覆盖值过**有限性/正性**校验（nan/inf/0/负数/非数字 → 记 fail + 立刻退出 2，且发生在任何破坏性操作之前）。
  6. 临时文件只落 `$LOCALAPPDATA/hermes/cache/scratch` 下的自有子目录（TMPDIR）。

环境变量（都有校验，非法即退出 2，绝不静默回落）：
  ENGINE_API_KEY / OSRM_ENGINE_KEY  必填（拒绝默认密钥：默认密钥会让「密钥不一致」变假绿）
  ENGINE_PY / ENGINE_CWD            本机引擎运行时路径覆盖
  STACK_RECOVER_WAIT                恢复等待预算（秒，显式覆盖）
  STACK_READY_WAIT                  首次就绪等待预算（秒，显式覆盖）
  STACK_LIMIT_MAX_RESTARTS          超限实验用的上限（默认 1，整数 0..100）

退出码：0 = 全绿；1 = 有断言失败；2 = 参数/环境非法（未进任何破坏性阶段）；130 = 被 Ctrl-C 打断。
"""

import atexit
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

try:                                     # 控制台编码兜底：中文日志不得因 cp936 抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 路径与常量 ─────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.abspath(os.path.join(ROOT, "scripts", "serve-stack.mjs"))
ENGINE_PY = os.path.abspath(os.environ.get("ENGINE_PY", "D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe"))
ENGINE_CWD = os.path.abspath(os.environ.get("ENGINE_CWD", "D:/01_业务/立三方/AIOSRM++/backend"))
ENGINE_SCRIPT = os.path.abspath(os.path.join(ENGINE_CWD, "run_server.py"))
GATEWAY_CWD = os.path.abspath(os.path.join(ROOT, "deploy", "osrm-engine"))
GATEWAY_SCRIPT = os.path.abspath(os.path.join(GATEWAY_CWD, "server.py"))
SITE_ENTRY = os.path.abspath(os.path.join(ROOT, "dist", "server.cjs"))
NODE_EXE = shutil.which("node")
IS_REPO_ROOT = os.path.exists(os.path.join(ROOT, ".git"))
PORTS = {"engine": 18000, "gateway": 18001, "site": 3300}
ROLES = ("engine", "gateway", "site")
BACKOFF_S = [1, 2, 4, 8, 16]                    # 守护的退避表（预算推算用）
STACK_LOG_DIR = os.environ.get("STACK_LOG_DIR") or os.path.join(ROOT, ".stack-logs")
# 临时目录**显式**落在 hermes scratch 下（不靠 tempfile：本机它给的是 %TEMP%，
# 而纪律要求「别用 /tmp，用 $LOCALAPPDATA/hermes/cache/scratch/ 下自己的子目录」）
SCRATCH_ROOT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                            "hermes", "cache", "scratch")
os.makedirs(SCRATCH_ROOT, exist_ok=True)
SCRATCH = os.path.join(SCRATCH_ROOT, f"verify-stack-{os.getpid()}-{int(time.time())}")
os.makedirs(SCRATCH, exist_ok=True)
SITE_QUOTE = f"http://127.0.0.1:{PORTS['site']}/api/osrm-quote"
# 真实测算请求（与 scripts/probe-quote-api.py 同一条线路；南宁→河内 20t 拼车）
QUOTE_BODY = {"origin": "nanning", "destination": "hanoi", "border": "youyiguan",
              "weight_kg": 20000, "volume_m3": 60, "mode": "consolidated"}

# PowerShell 输出编码：**必须**显式设成 UTF-8。默认走控制台代码页（本机 cp936）时，
# CommandLine 里的中文路径会被写成 GBK 字节，脚本按 UTF-8 解码 → 乱码 → 绝对路径身份核对永远对不上
# （实测：不加这一行，PID 444 的命令行里查不到「玖能」；加了就有）。
PS_ENC = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "

fails: list[str] = []
ORIGINAL: dict[str, dict] = {}                   # ① 的原进程快照（收尾对比「恢复 = 新进程」）
guard_procs: list = []                           # 我起过的守护进程（Popen 句柄，收尾兜底停）


# ── 参数/环境校验：必须发生在**任何破坏性操作之前** ─────────────────────
def parse_override(raw, name, default=None, minimum=None, maximum=None):
    """→ (值 | default, 错误说明 | None)。只接受有限值，区间外/非数字**绝不静默回落**。"""
    if raw is None or str(raw).strip() == "":
        return default, None
    text = str(raw).strip()
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None, f"{name}={raw!r} 不是数字：只接受有限数值（例：{name}=30）"
    if not math.isfinite(value):
        return None, (f"{name}={raw!r} 不是有限值：nan/inf 会让 `time.time() + budget` 的 deadline 永不到期"
                      f"（time.time() >= deadline 恒为 False）→ 失败路径上脚本永不退出，"
                      f"而被杀的服务等不到恢复")
    if minimum is not None and value < minimum:
        return None, f"{name}={raw!r} 小于下限 {minimum}"
    if maximum is not None and value > maximum:
        return None, f"{name}={raw!r} 超过上限 {maximum}"
    return value, None


KEY = os.environ.get("ENGINE_API_KEY") or os.environ.get("OSRM_ENGINE_KEY")
if not KEY:
    # 绝不给默认值：默认密钥会让「密钥不一致」变假绿（/health 免鉴权照样 200，而客户测算全 401）。
    sys.exit("请显式提供 ENGINE_API_KEY（拒绝用默认密钥）：ENGINE_API_KEY=... python scripts/verify-stack.py")
if "'" in KEY:
    sys.exit("ENGINE_API_KEY 不能含单引号（脚本要把它注入 PowerShell 环境与子进程 env）")

RECOVER_WAIT_OVERRIDE, _err = parse_override(os.environ.get("STACK_RECOVER_WAIT"), "STACK_RECOVER_WAIT",
                                             minimum=1.0, maximum=600.0)
READY_WAIT_OVERRIDE, _err2 = parse_override(os.environ.get("STACK_READY_WAIT"), "STACK_READY_WAIT",
                                            minimum=1.0, maximum=600.0)
LIMIT_MAX_RESTARTS, _err3 = parse_override(os.environ.get("STACK_LIMIT_MAX_RESTARTS"), "STACK_LIMIT_MAX_RESTARTS",
                                           default=1.0, minimum=0.0, maximum=100.0)
_bad = [e for e in (_err, _err2, _err3) if e]
if _bad:
    for e in _bad:
        fails.append(e)
        print(f"\n✗ {e}")
    print("  拒绝启动：这些覆盖值会被当成等待预算/上限用，非法值要么让脚本挂死、要么让断言必然假红。"
          "**不允许静默回落**。")
    print("  未做任何破坏性操作：三个服务（18000/18001/3300）未被触碰。")
    print("\n存在问题：\n  - " + "\n  - ".join(fails))
    print("（退出码 2 = 参数/环境非法，不是断言失败）")
    sys.exit(2)

if not NODE_EXE:
    sys.exit("PATH 里找不到 node（守护脚本要用它启动官网与自身）")

READY_FIRST_BUDGET_S = float(READY_WAIT_OVERRIDE or 120.0)     # 首次启动无实测基线 → 显式默认 + 可覆盖
if READY_WAIT_OVERRIDE is not None:
    print(f"（首次就绪预算 {READY_FIRST_BUDGET_S}s 来自显式覆盖 STACK_READY_WAIT）")


# ── 子进程/HTTP 小工具（统一带 timeout；超时记 fail）────────────────────
def run_cmd(args, timeout, input=None, label=None, quiet=False, to_files=None):
    """**带 Python 级 timeout** 的子进程调用 → CompletedProcess | None（超时/失败一律记 fail）。

    ⚠️ 这里**故意不用** `subprocess.run(capture_output=True, timeout=T)`：它超时那条路径上是
    `kill()` 之后再 `communicate()` **无超时地**排空管道 —— 只要还有别的进程握着这根管道的写端，
    排空就永不返回，`TimeoutExpired` 压根抛不出来，脚本直接挂死（本脚本第一版就死在这里）。
    谁握着写端？**PowerShell `Start-Process`**：它起的分离进程会**继承** powershell 自己的句柄
    （实测：加了 `-RedirectStandardOutput` 反而稳定复现 —— 被拉起的服务活着多久，管道就多久不 EOF，
    20s 的占位进程让 `communicate()` 足足等了 20.4s）。所以：

    * `to_files=(out_path, err_path)`：**完全不用管道**，让 PowerShell 写文件；分离进程再继承也只会
      继承文件句柄（没人等 EOF）→ 拉起分离服务必须走这条路；
    * 默认（管道）：只给**短命**的查询命令用（netstat / Get-CimInstance / curl），且 kill 之后
      **有界**排空（≤5s），拿不到输出也照样记 fail 返回。
    """
    if to_files:
        out_path, err_path = to_files
        fo, fe = open(out_path, "wb"), open(err_path, "wb")
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE if input is not None else None,
                                   stdout=fo, stderr=fe)
        except OSError as exc:
            fo.close()
            fe.close()
            if not quiet:
                fails.append(f"{label or args[0]} 无法执行：{exc}")
                print(f"   ✗ {label or args[0]} 无法执行：{exc}")
            return None
        finally:
            fo.close()
            fe.close()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            if not quiet:
                fails.append(f"{label or args[0]} 超时（>{timeout}s）—— 记失败，避免脚本挂死")
                print(f"   ✗ {label or args[0]} 超时（>{timeout}s）→ 记失败")
            return None
        return subprocess.CompletedProcess(args, proc.returncode,
                                           read_bytes(out_path), read_bytes(err_path))
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE if input is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        if not quiet:
            fails.append(f"{label or args[0]} 无法执行：{exc}")
            print(f"   ✗ {label or args[0]} 无法执行：{exc}")
        return None
    try:
        out, err = proc.communicate(input=input, timeout=timeout)
        return subprocess.CompletedProcess(args, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.communicate(timeout=5)                 # 有界排空：孙子进程可能一直握着写端
        except Exception:
            pass
        if not quiet:
            fails.append(f"{label or args[0]} 超时（>{timeout}s）—— 记失败，避免脚本挂死")
            print(f"   ✗ {label or args[0]} 超时（>{timeout}s）→ 记失败")
        return None


def ps(command, timeout=25, label="powershell", quiet=True, to_files=None):
    """跑 PowerShell（统一前缀 UTF-8 输出编码，否则中文 CommandLine 会乱码）。

    `to_files=` 是给「会拉起分离进程」的命令用的：那种命令必须走文件，不能走管道（见 run_cmd）。
    """
    return run_cmd(["powershell", "-NoProfile", "-Command", PS_ENC + command], timeout,
                   label=label, quiet=quiet, to_files=to_files)


def _split_code(out):
    body, _, code = out.rpartition("\n")
    try:
        code_i = int(code.strip() or 0)
    except ValueError:
        code_i = 0
    return code_i, body.strip()


def curl(url, timeout=20, want_code=False, quiet=True):
    """curl -s → (code, body) 或 body。code 0 = 连不上/超时（也是失败的取值）。"""
    p = run_cmd(["curl", "-s", "-m", str(timeout), url, "-w", "\n%{http_code}"],
                timeout=timeout + 10, label=f"curl {url}", quiet=quiet)
    if p is None:
        return (0, "") if want_code else ""
    code_i, body = _split_code(p.stdout.decode("utf-8", "replace"))
    return (code_i, body) if want_code else body


def curl_json(url, timeout=20, quiet=True):
    code, body = curl(url, timeout, want_code=True, quiet=quiet)
    try:
        return code, json.loads(body), body
    except Exception:
        return code, None, body


def curl_post(url, payload, timeout=90):
    args = ["curl", "-s", "-m", str(timeout), "-X", "POST", url, "-H", "Content-Type: application/json",
            "--data-binary", "@-", "-w", "\n%{http_code}"]
    p = run_cmd(args, timeout=timeout + 15, input=json.dumps(payload).encode(), label=f"curl POST {url}")
    if p is None:
        return 0, ""
    return _split_code(p.stdout.decode("utf-8", "replace"))


# ── 进程/端口 ─────────────────────────────────────────────────────────
def listeners(port):
    """该端口上**全部** LISTENING 行 → [(pid, local_addr), ...]；None = netstat 失败（已记 fail）。

    必须数行：Windows 允许同端口多 listener，`pid_on`（取第一行）会把这种状态看成正常。
    """
    p = run_cmd(["netstat", "-ano"], 30, label="netstat -ano")
    if p is None:
        return None
    rows = []
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING" and parts[1].endswith(":" + str(port)):
            rows.append((parts[4], parts[1]))
    return rows


def proc_info(pid):
    """→ dict(ProcessId/ParentProcessId/Name/CommandLine)；进程不存在或查询失败 → {}（quiet）。"""
    p = ps(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
           f"Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress",
           25, label=f"查 PID {pid}")
    if p is None:
        return {}
    txt = p.stdout.decode("utf-8", "replace").strip()
    try:
        obj = json.loads(txt) if txt else {}
    except Exception:
        return {}
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    return obj if isinstance(obj, dict) else {}


def procs_by_parent(pid):
    """以 pid 为父的全部进程 → [dict, ...]（守护被强杀后子进程会变孤儿，靠父子关系认人）。"""
    p = ps(f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | "
           f"Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress", 25, label="按父进程查子进程")
    if p is None:
        return None
    txt = p.stdout.decode("utf-8", "replace").strip()
    try:
        obj = json.loads(txt) if txt else []
    except Exception:
        return []
    if isinstance(obj, dict):
        obj = [obj]
    return obj if isinstance(obj, list) else []


def fingerprint_ok(role):
    """**端口自证**：端口上的服务自己回出本项目特有的指纹（弱标识不足以认人）。"""
    if role == "engine":
        code, body, _ = curl_json(f"http://127.0.0.1:{PORTS['engine']}/health", 8)
        return code == 200 and isinstance(body, dict) and body.get("status") == "ok"
    if role == "gateway":
        code, body, _ = curl_json(f"http://127.0.0.1:{PORTS['gateway']}/gateway/health", 8)
        return code == 200 and isinstance(body, dict) and body.get("gateway") == "jiuneng-osrm-gateway"
    if role == "site":
        code, body, _ = curl_json(f"http://127.0.0.1:{PORTS['site']}/api/health", 10)
        return code == 200 and isinstance(body, dict) and body.get("status") in ("ok", "degraded")
    return False


# 强标识：命令行里出现**绝对路径片段**（守护自己 spawn 的服务必须是这种形态）
STRONG = {
    "engine": [ENGINE_SCRIPT, ENGINE_SCRIPT.replace("\\", "/"), ENGINE_CWD, ENGINE_CWD.replace("\\", "/")],
    "gateway": [GATEWAY_SCRIPT, GATEWAY_SCRIPT.replace("\\", "/"), GATEWAY_CWD, GATEWAY_CWD.replace("\\", "/"),
                "deploy/osrm-engine", "deploy\\osrm-engine"],
    "site": [SITE_ENTRY, SITE_ENTRY.replace("\\", "/")],
}
# 弱标识：以 cwd 方式启动时命令行里只剩脚本名（本机现存的三服务就是这样跑的）
WEAK = {"engine": ("run_server.py",), "gateway": ("server.py",), "site": ("server.cjs",)}


def identity(role, cmd, name=""):
    """→ (ok, why)。强标识（绝对路径片段）直接放行；只有弱标识时必须过**端口自证**；都不满足 → 拒。

    比较时**斜杠归一**：同一条路径可能是 `...\\a\\b`、`.../a/b` 或 `...\\a/b`（Start-Process 与 cwd
    混用会产出混合形态，实测过），不归一会把「绝对路径放在那儿」误判成弱标识。
    """
    cmd = str(cmd or "").replace("\\", "/")
    strong = [s for s in STRONG[role] if s and s.replace("\\", "/") in cmd]
    if strong:
        return True, f"命令行含绝对路径片段 {strong[0]!r}"
    weak = [w for w in WEAK[role] if w in cmd]
    if not weak:
        return False, f"命令行里既没有绝对路径片段 {STRONG[role]!r} 也没有弱标识 {WEAK[role]!r}"
    if fingerprint_ok(role):
        return True, f"命令行只有弱标识 {weak[0]!r}（cwd 启动），但端口自证通过（本服务指纹匹配）"
    return False, f"命令行只有弱标识 {weak!r} 且端口自证失败（不是本项目服务）"


def ancestry(pid, depth=3):
    """pid 的**祖先生成链**（不含自己，最多 depth 层）。父进程已死 → 链在此断掉。

    为什么不用 `ParentProcessId == 守护 PID` 直接判所有权：本机的 venv
    `Scripts/python.exe` 是**跳板**（实测：venv 的 python.exe 又 spawn 出
    `uv/.../python.exe` 才真正 listen）→ 监听者 PID ≠ 守护 spawn 的 PID、其父进程也不是守护。
    所以所有权要判「守护 PID 在监听者的祖先链里（≤3 层）+ 监听者命令行含绝对路径」。
    """
    chain, cur = [], str(pid)
    for _ in range(depth):
        info = proc_info(cur)
        parent = str(info.get("ParentProcessId") or "")
        if not parent or parent in ("0", cur) or parent in chain:
            break
        chain.append(parent)
        cur = parent
    return chain


def owned_by(pid, owner_pid):
    """该监听进程是否属于 owner_pid 起的进程树（含 owner 自己 / 跳板子进程）。"""
    if owner_pid is None:
        return True
    return str(pid) == str(owner_pid) or str(owner_pid) in ancestry(pid)


def stop_role(role, expect_parent=None, allow_absent=False):
    """按身份停掉该角色端口上的监听进程 → bool。停不掉/身份对不上/端口没有监听 → **记 fail**（不静默跳过）。"""
    port = PORTS[role]
    rows = listeners(port)
    if rows is None:
        return False
    if not rows:
        if allow_absent:
            return True
        fails.append(f"{role}({port}) 没有 LISTENING 进程：无法按身份停掉它（这不是「没什么可做的」，是失败）")
        print(f"   ✗ {role}({port}) 端口无监听 → 记失败（不静默跳过）")
        return False
    if len(rows) > 1:
        fails.append(f"{role}({port}) 有 **{len(rows)} 行** LISTENING（{rows}）：Windows 允许同端口多监听者，"
                     f"此时身份判定不可靠 → 拒绝盲杀（先人工清掉重复监听者）")
        print(f"   ✗ {role}({port}) 有 {len(rows)} 行 LISTENING → 拒绝盲杀（重复监听者会让「杀一个」静默影响另一个）")
        return False
    pid = rows[0][0]
    info = proc_info(pid)
    if not info:
        fails.append(f"{role}({port}) 的 PID {pid} 查不到进程信息（可能刚退出）→ 记失败")
        return False
    ok, why = identity(role, str(info.get("CommandLine") or ""), str(info.get("Name") or ""))
    if not ok:
        fails.append(f"拒绝停 {role}({port}) PID {pid}：身份对不上（{why}；"
                     f"CommandLine={str(info.get('CommandLine'))[:200]!r}）")
        print(f"   ✗ 拒绝停 PID {pid}：身份对不上（{why}）")
        return False
    if expect_parent is not None and not owned_by(pid, expect_parent):
        fails.append(f"拒绝停 {role}({port}) PID {pid}：不在守护 PID {expect_parent} 的进程树里"
                     f"（祖先链 {ancestry(pid)}）—— 杀错进程的典型来源")
        print(f"   ✗ 拒绝停 PID {pid}：不在守护 {expect_parent} 的进程树里（祖先链 {ancestry(pid)}）")
        return False
    print(f"   （身份核对通过：{why}；PID={pid} 祖先链={ancestry(pid)}）")
    p = ps(f"Stop-Process -Id {pid} -Force; 'done'", 25, label=f"Stop-Process {pid}")
    if p is None:
        return False
    for _ in range(24):                                  # ≤12s
        left = listeners(port)
        if left is not None and not left:
            return True
        time.sleep(0.5)
    left = listeners(port) or []
    fails.append(f"停 {role}({port}) 失败：PID {pid} 被杀后端口仍有 {len(left)} 行 LISTENING（{left}）")
    print(f"   ✗ 停 {role}({port}) 失败：端口仍有 {len(left)} 行 LISTENING")
    return False


def stop_pid(pid, must_cmd_substr, label):
    """停一个非端口角色（守护自身）：命令行必须含 `must_cmd_substr`（绝对路径）才允许停。"""
    info = proc_info(pid)
    if not info:
        print(f"   （{label} PID {pid} 已不存在，无需停）")
        return True
    cmd = str(info.get("CommandLine") or "")
    if must_cmd_substr not in cmd and must_cmd_substr.replace("\\", "/") not in cmd:
        fails.append(f"拒绝停{label} PID {pid}：命令行里没有 {must_cmd_substr!r}（CommandLine={cmd[:200]!r}）")
        print(f"   ✗ 拒绝停{label} PID {pid}：身份对不上")
        return False
    p = ps(f"Stop-Process -Id {pid} -Force; 'done'", 25, label=f"Stop-Process {pid}")
    if p is None:
        return False
    for _ in range(24):
        if not proc_info(pid):
            return True
        time.sleep(0.5)
    fails.append(f"停{label} PID {pid} 失败：进程仍在")
    print(f"   ✗ 停{label} PID {pid} 失败")
    return False


# ── 就绪判定（每角色：1 行 LISTENING + 指纹 200 + 父进程 = 守护 + 命令行含绝对路径）──
def role_state(role, expect_parent=None):
    """→ (ready: bool, why: str, pid: str | None)"""
    port = PORTS[role]
    rows = listeners(port)
    if rows is None:
        return False, "netstat 失败", None
    if len(rows) != 1:
        return False, f"{port} 上 LISTENING 行数 = {len(rows)}（应为 1）", None
    pid = rows[0][0]
    info = proc_info(pid)
    if not info:
        return False, f"PID {pid} 查不到进程信息", pid
    cmd = str(info.get("CommandLine") or "")
    ok, why = identity(role, cmd)
    if not ok:
        return False, f"PID {pid} 身份对不上：{why}", pid
    if "绝对路径片段" not in why:
        return False, f"PID {pid} 命令行里没有绝对路径（{why}）—— 事后核不出端口上是谁", pid
    if expect_parent is not None and not owned_by(pid, expect_parent):
        return False, f"PID {pid} 不在守护 {expect_parent} 的进程树里（祖先链 {ancestry(pid)}）", pid
    if not fingerprint_ok(role):
        return False, f"PID {pid} 的 {role} 指纹/健康检查不通过", pid
    return True, f"PID={pid} 祖先链={ancestry(pid)}", pid


def wait_ready(expect_parent, budget, label, roles=ROLES, interval=2.0, guard_proc=None):
    """轮询到三角色都就绪。→ (ok, elapsed, cold: dict[role]=秒, detail)

    `guard_proc` 给了就每轮核对守护是否还活着：守护已经退出时，就绪**不可能**再达成 → 立刻返回，
    不要空等满预算（实测守护超限自停后脚本还干等了 120s，日志里一句原因都没有）。
    """
    start = time.time()
    deadline = start + budget
    cold: dict[str, float] = {}
    detail = ""
    while True:
        if guard_proc is not None and guard_proc.poll() is not None:
            return (False, round(time.time() - start, 2), cold,
                    f"守护进程已退出（exit {guard_proc.returncode}）→ 就绪不可能达成")
        pending = []
        for role in roles:
            if role in cold:
                continue
            ok, why, _pid = role_state(role, expect_parent)
            if ok:
                cold[role] = round(time.time() - start, 2)
            else:
                pending.append(f"{role}: {why}")
        if not pending:
            return True, round(time.time() - start, 2), cold, ""
        detail = "；".join(pending)
        if time.time() >= deadline:
            return False, round(time.time() - start, 2), cold, detail
        print(f"   … 等 {label}：{detail}")
        time.sleep(interval)


def ready_budget(cold_seconds, override=None):
    """恢复预算 = max(3 × 实测冷启动, 15s)（写死会被换配置打假红；实测 + 显式覆盖才稳）。"""
    if override is not None:
        return float(override), f"显式覆盖 STACK_RECOVER_WAIT={override}s"
    return max(3.0 * float(cold_seconds), 15.0), f"max(3 × 实测冷启动 {round(float(cold_seconds), 2)}s, 15s)"


# ── 守护进程的起停（Popen：我们需要它的**退出码**与 stdout/stderr 原文）──
_GUARD_SEQ = {"n": 0}


def start_guard(extra_env=None, tag="guard"):
    _GUARD_SEQ["n"] += 1
    out = os.path.join(SCRATCH, f"{tag}-{_GUARD_SEQ['n']}.stdout.log")
    err = os.path.join(SCRATCH, f"{tag}-{_GUARD_SEQ['n']}.stderr.log")
    env = {**os.environ, "ENGINE_API_KEY": KEY}
    if extra_env:
        env.update(extra_env)
    fo, fe = open(out, "wb"), open(err, "wb")
    try:
        proc = subprocess.Popen([NODE_EXE, GUARD], cwd=ROOT, env=env, stdout=fo, stderr=fe)
    finally:
        fo.close()
        fe.close()
    guard_procs.append(proc)
    print(f"   启动守护 PID={proc.pid}：{NODE_EXE} {GUARD}（cwd={ROOT}）")
    return proc, out, err


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return b""


def read_text(path):
    return read_bytes(path).decode("utf-8", "replace")


def tail_file(path, lines=12):
    txt = read_text(path)
    return "\n".join(txt.splitlines()[-lines:])


# ── 真实业务断言：官网测算（站点 → 网关 → 引擎），密钥错会 401 ──────────
def quote_once(label, quiet=False):
    """→ (http_code, obj|None, raw)。HTTP 0 = 连不上。"""
    code, raw = curl_post(SITE_QUOTE, QUOTE_BODY, timeout=90)
    try:
        obj = json.loads(raw)
    except Exception:
        obj = None
    if not quiet:
        print(f"   {label}：HTTP {code} body={raw[:180]!r}")
    return code, obj, raw


def quote_is_ok(code, obj):
    return code == 200 and isinstance(obj, dict) and obj.get("ok") is True and obj.get("reason") != "engine_error"


def assert_quote_ok(label):
    code, obj, raw = quote_once(label)
    if code == 401:
        fails.append(f"{label}：测算返回 401（密钥不一致）—— 这正是「/health 正常但客户测算全 401」的假绿面")
        return False
    if not quote_is_ok(code, obj):
        fails.append(f"{label}：测算未成功（HTTP {code}，body={raw[:160]!r}）")
        print(f"   ✗ {label}：测算未成功")
        return False
    print(f"   ✓ {label}：ok=true（里程 {obj.get('distance_km')} km / 车数 {obj.get('vehicle_count')}）")
    return True


def wait_quote_ok(label, budget, interval=2.0):
    deadline = time.time() + budget
    last = ""
    while True:
        code, obj, raw = quote_once(label, quiet=True)
        if quote_is_ok(code, obj):
            print(f"   ✓ {label}：测算恢复 ok=true（HTTP {code}）")
            return True
        last = f"HTTP {code} {raw[:140]!r}"
        if time.time() >= deadline:
            fails.append(f"{label}：{round(budget, 1)}s 内测算未恢复（末次 {last}）")
            print(f"   ✗ {label}：{round(budget, 1)}s 内测算未恢复（末次 {last}）")
            return False
        print(f"   … 等测算恢复：{last}")
        time.sleep(interval)


# ── 收尾恢复：按「运维配方」用 PowerShell Start-Process 起（绝对路径 → CommandLine 可核身份）─
def start_role_detached(role):
    """按运维配方拉起一个角色（绝对路径 + 完整 env）。→ PID | None

    ⚠️ 两条实测坑：
    ① `-ArgumentList` **不会自动给带空格的参数加引号**（.NET 只是把列表用空格拼起来）：
       本仓库路径含「JIUNENG 官网」这种空格 → 不套内层双引号时子进程收到的是被空格切碎的路径，
       python 报 `can't open file 'D:\\01_业务\\玖能\\JIUNENG'`、node 报 `MODULE_NOT_FOUND`
       （第一次真跑就是这样拉起失败、还静默继续等）。所以每个参数都套 `"..."`。
    ② PowerShell 的输出**必须落文件**（`to_files`），不能用管道 —— 分离进程会继承管道写端，
       管道永远不 EOF（见 run_cmd 的注释）。
    """
    if role == "engine":
        env_extra, exe, args, cwd = {}, ENGINE_PY, [ENGINE_SCRIPT, "--port", str(PORTS["engine"])], ENGINE_CWD
    elif role == "gateway":
        env_extra = {"PORT": str(PORTS["gateway"]), "ENGINE_API_KEY": KEY}
        exe, args, cwd = ENGINE_PY, [GATEWAY_SCRIPT], GATEWAY_CWD
    elif role == "site":
        env_extra = {"NODE_ENV": "production", "PORT": str(PORTS["site"]), "HEALTH_PROBE_MS": "5000",
                     "AGENT_CHAT_DEMO": "1", "OSRM_API_BASE": f"http://127.0.0.1:{PORTS['gateway']}",
                     "OSRM_ENGINE_KEY": KEY}
        exe, args, cwd = NODE_EXE, [SITE_ENTRY], ROOT
    else:
        fails.append(f"不知道该怎样拉起角色 {role}")
        print(f"   ✗ 不知道该怎样拉起角色 {role}")
        return None
    for v in env_extra.values():
        if "'" in str(v):
            fails.append(f"拉起 {role} 失败：env 值含单引号（会破坏 PowerShell 注入）")
            print(f"   ✗ 拉起 {role} 失败：env 值含单引号")
            return None
    prefix = "".join(f"$env:{k}='{v}'; " for k, v in env_extra.items())
    # 每个参数都套引号（坑 ①），且**必须让双引号成为「数据」而不是 PowerShell 的语法**：
    # 正确形态是 `-ArgumentList '"D:\a b\x.py"'`（外层单引号 + 内层双引号）。只写 `"D:\a b\x.py"`
    # 会被 PowerShell 当成字符串表达式解析、双引号消失，.NET 再把参数用空格拼起来 → 路径在空格处被切碎
    # （实测症状：python 报 `can't open file 'D:\01_业务\玖能\JIUNENG'`、node 报 MODULE_NOT_FOUND）。
    arglist = ",".join("'\"" + str(a).replace('"', '\\"') + "\"'" for a in args)
    svc_out = os.path.join(SCRATCH, f"restored-{role}.out.log")
    svc_err = os.path.join(SCRATCH, f"restored-{role}.err.log")
    cmd = (f"{prefix}$p = Start-Process -FilePath '{exe}' -ArgumentList {arglist} "
           f"-WorkingDirectory '{cwd}' -PassThru -WindowStyle Hidden "
           f"-RedirectStandardOutput '{svc_out}' -RedirectStandardError '{svc_err}'; $p.Id")
    ps_out = os.path.join(SCRATCH, f"start-{role}.ps.out.log")
    ps_err = os.path.join(SCRATCH, f"start-{role}.ps.err.log")
    p = ps(cmd, 30, label=f"Start-Process {role}", to_files=(ps_out, ps_err))       # 坑 ②
    if p is None:
        print(f"   ✗ 拉起 {role} 的 PowerShell 调用失败（超时/无法执行）")
        return None
    pid = read_text(ps_out).strip().splitlines()[-1].strip() if read_text(ps_out).strip() else ""
    if not pid:
        fails.append(f"拉起 {role} 没拿到 PID：powershell stderr={read_text(ps_err)[:200]!r}")
        print(f"   ✗ 拉起 {role} 没拿到 PID（powershell stderr={read_text(ps_err)[:160]!r}）")
        return None
    print(f"   拉起 {role}：{exe} {' '.join(args)}（cwd={cwd}）→ PID {pid}（服务日志 {svc_err}）")
    return pid


# 恢复护栏：finally + atexit + SIGINT 三处都调；幂等
_restoring = False
_original_snapshot: dict[str, dict] = {}


def restore_services(reason="收尾"):
    global _restoring
    if _restoring:
        return
    _restoring = True
    try:
        print(f"\n[恢复] {reason}：确保三服务在跑（**恢复 = 新进程**，PID/命令行都会变）", flush=True)
        guard_pids = [str(p.pid) for p in guard_procs]
        for proc in guard_procs:                       # 我起的守护一律停掉（它会带走自己的子进程）
            if proc.poll() is None:
                print(f"   [恢复] 停掉我起的守护 PID {proc.pid}", flush=True)
                try:
                    proc.terminate()
                    proc.wait(timeout=15)
                except Exception:
                    pass
        # 只清理「我起的守护留下的**孤儿**」；本来就在跑、身份对得上的服务不动
        # （否则脚本每次退出都会把三个好端端的服务白重启一遍）
        for role in ROLES:
            rows = listeners(PORTS[role])
            if not rows:
                continue
            pid = rows[0][0]
            if any(str(pid) == gp or gp in ancestry(pid) for gp in guard_pids):
                print(f"   [恢复] {role}({PORTS[role]}) PID {pid} 属于我起的守护（孤儿）→ 停掉重起", flush=True)
                stop_role(role, allow_absent=True)
        for role in ROLES:
            if not listeners(PORTS[role]):
                start_role_detached(role)
        ok, elapsed, _cold, detail = wait_ready(None, READY_FIRST_BUDGET_S, "恢复后就绪", interval=2.0)
        print(f"   [恢复] {'就绪' if ok else '未就绪：' + detail}（{elapsed}s）", flush=True)
        for role in ROLES:
            rows = listeners(PORTS[role]) or []
            pid = rows[0][0] if rows else None
            info = proc_info(pid) if pid else {}
            orig = _original_snapshot.get(role, {})
            print(f"   [恢复] {role}({PORTS[role]}) 原 PID={orig.get('pid')} → 现 PID={pid}"
                  f"（{len(rows)} 行 LISTENING）", flush=True)
            if pid:
                print(f"          现 CommandLine = {str(info.get('CommandLine'))[:200]}", flush=True)
        code, obj, _ = quote_once("恢复后测算", quiet=True)
        print(f"   [恢复] 恢复后测算：HTTP {code} ok={isinstance(obj, dict) and obj.get('ok')}", flush=True)
    except Exception as exc:
        print(f"   [恢复] 出错：{exc}", flush=True)
    finally:
        _restoring = False


def _on_signal(signum, _frame):
    print(f"\n收到信号 {signum}：先把环境恢复回去再退出 …", flush=True)
    restore_services("Ctrl-C")
    sys.exit(130)


atexit.register(restore_services)
signal.signal(signal.SIGINT, _on_signal)
try:
    signal.signal(signal.SIGTERM, _on_signal)
except (ValueError, AttributeError, OSError):
    pass


# ─────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 78)
    print("T3 验收：npm run stack（三服务守护）")
    print(f"ROOT        = {ROOT}")
    print(f"守护脚本    = {GUARD}")
    print(f"node        = {NODE_EXE}")
    print(f"引擎        = {ENGINE_PY} {ENGINE_SCRIPT} --port {PORTS['engine']}")
    print(f"网关        = {ENGINE_PY} {GATEWAY_SCRIPT}")
    print(f"官网        = {NODE_EXE} {SITE_ENTRY}")
    print(f"守护日志    = {STACK_LOG_DIR}")
    print(f"本次 scratch= {SCRATCH}")
    if not IS_REPO_ROOT:
        print(f"⚠️  ROOT 下没有 .git → 这是**副本**：拉起/停止的会是副本路径下的服务，别拿它做真实验证")
    if os.environ.get("PYTHONPATH"):
        print("（提示：本仓库验收请用 `env -u PYTHONPATH python scripts/verify-stack.py`）")
    print("=" * 78)

    # ① 环境快照 ------------------------------------------------------
    print("\n① 环境快照：三端口 LISTENING **行数** + 身份（严禁按端口号段扫）")
    ok_snapshot = True
    for role in ROLES:
        port = PORTS[role]
        rows = listeners(port)
        if rows is None:
            ok_snapshot = False
            continue
        if len(rows) != 1:
            fails.append(f"① {role}({port}) 的 LISTENING 行数 = {len(rows)}（期望 1；"
                         f"0 = 服务没在跑，>1 = 有重复监听者，身份判定不可靠）")
            print(f"   ✗ {role}({port}) LISTENING 行数 = {len(rows)}（期望 1）")
            ok_snapshot = False
            continue
        pid = rows[0][0]
        info = proc_info(pid)
        cmd = str(info.get("CommandLine") or "")
        ok_id, why = identity(role, cmd)
        _original_snapshot[role] = {"pid": pid, "cmd": cmd, "parent": info.get("ParentProcessId"),
                                    "listeners": len(rows)}
        ORIGINAL[role] = _original_snapshot[role]
        mark = "✓" if ok_id else "✗"
        print(f"   {mark} {role}({port}) 1 行 LISTENING PID={pid} parent={info.get('ParentProcessId')}")
        print(f"        CommandLine = {cmd[:190]}")
        print(f"        身份：{why}")
        if not ok_id:
            fails.append(f"① {role}({port}) 端口上的服务身份对不上（{why}）→ 后面的杀/停都会拒绝执行")
            ok_snapshot = False
    if os.path.exists(GUARD):
        print(f"   （守护脚本存在：{GUARD}）")
    else:
        print(f"   （守护脚本**还不存在**：{GUARD} —— 首轮 TDD 的预期失败点）")

    # ② 端口占用前置检查（守护必须拒绝启动 + 报出占用 PID）-------------
    print("\n② 端口占用前置检查：三端口被占时，守护必须**报出占用 PID** 并以非 0 退出，且不碰现有服务")
    # 输出落文件（不用管道）：万一是「没有前置检查」的变异体，守护会一直跑下去并拉子进程，
    # 子进程继承管道写端 → 管道永不 EOF → 脚本挂死（这条坑实测踩过一次）。
    pre_out = os.path.join(SCRATCH, "precheck.stdout.log")
    pre_err = os.path.join(SCRATCH, "precheck.stderr.log")
    pre = run_cmd([NODE_EXE, GUARD], 25, label="node serve-stack.mjs（前置检查，前台）",
                  to_files=(pre_out, pre_err))
    if pre is None:
        fails.append("② 前置检查未生效：守护在三端口被占用的情况下**没有退出**（前台 25s 超时）——"
                     "「占用即拒绝启动」这条护栏没实现")
        print("   ✗ 守护没在三端口被占时退出（超时）→ 记失败")
    else:
        out = (pre.stdout + pre.stderr).decode("utf-8", "replace")
        print(f"   退出码 = {pre.returncode}")
        print("   ---- 输出 ----")
        print("\n".join("   " + ln for ln in out.strip().splitlines()[-20:]))
        if pre.returncode != 3:
            fails.append(f"② 前置检查应以**退出码 3**（端口占用）失败，实际 {pre.returncode}"
                         f"（1 往往意味着脚本压根没跑起来，别把两种失败混为一谈）")
        if "已被占用" not in out:
            fails.append("② 前置检查输出里没有「已被占用」字样 → 没有明确报出占用")
        hit_pids = [p for p in (v.get("pid") for v in _original_snapshot.values()) if p and p in out]
        if len(hit_pids) < len(_original_snapshot) or not hit_pids:
            fails.append(f"② 前置检查没有报出**占用 PID**：期望输出里能看到 {sorted(hit_pids)} 之外的"
                         f"实际占用 PID {[v.get('pid') for v in _original_snapshot.values()]}（规格 §6 验收 #5）")
        else:
            print(f"   ✓ 报出了占用 PID：{sorted(set(hit_pids))}")
        # 前置检查不得有副作用
        for role in ROLES:
            rows = listeners(PORTS[role]) or []
            same = len(rows) == 1 and rows[0][0] == _original_snapshot.get(role, {}).get("pid")
            if not same:
                fails.append(f"② 前置检查有副作用：{role}({PORTS[role]}) 现在 = {rows}，"
                             f"原本 PID {_original_snapshot.get(role, {}).get('pid')} 单行 LISTENING")
                print(f"   ✗ {role}({PORTS[role]}) 被前置检查动过：{rows}")
        print("   ✓ 前置检查无副作用：三服务仍是原 PID 单行 LISTENING"
              if not any("② 前置检查有副作用" in f for f in fails) else "   ✗ 前置检查有副作用（见上）")

    # ③ 清场 ----------------------------------------------------------
    print("\n③ 清场：按身份停掉现有三服务（守护要求三端口空闲才肯启动）")
    ok_clear = True
    for role in ROLES:
        if not stop_role(role):
            ok_clear = False
        rows = listeners(PORTS[role])
        print(f"   {role}({PORTS[role]}) LISTENING 行数 = {len(rows) if rows is not None else 'netstat 失败'}")
        if rows:
            fails.append(f"③ 清场后 {role}({PORTS[role]}) 仍有 {len(rows)} 行 LISTENING（{rows}）")
            ok_clear = False

    # ④ 起守护并等三服务就绪 ------------------------------------------
    cold = {}
    recover_budgets = {}
    if not ok_clear:
        fails.append("④ 前置清场失败 → 守护无法在空闲端口上启动，本阶段按**失败**计（不是跳过）")
        print("\n④ ✗ 清场失败 → 后续阶段无法进行，按失败计")
    else:
        print("\n④ 起守护（前台 Popen，脚本绝对路径）→ 等三服务就绪（1 行 LISTENING + 指纹 + 父进程 = 守护 + 绝对路径）")
        proc, out_path, err_path = start_guard()
        ok_ready, elapsed, cold, detail = wait_ready(proc.pid, READY_FIRST_BUDGET_S, "三服务就绪", guard_proc=proc)
        if not ok_ready:
            fails.append(f"④ 守护启动后 {READY_FIRST_BUDGET_S}s 内三服务未全部就绪：{detail}")
            print(f"   ✗ 未就绪（{elapsed}s）：{detail}")
            print("   ---- 守护 stderr 尾部 ----")
            print("\n".join("   " + ln for ln in tail_file(err_path).splitlines()))
            print("   ---- 守护 stdout 尾部 ----")
            print("\n".join("   " + ln for ln in tail_file(out_path).splitlines()))
        else:
            print(f"   ✓ 三服务就绪（{elapsed}s）")
            for role in ROLES:
                _ok, why, _pid = role_state(role, proc.pid)
                print(f"     {role}: {why}；冷启动 {cold.get(role)}s")
            g_out = read_text(out_path)
            missing = [p for p in (ENGINE_SCRIPT, GATEWAY_SCRIPT, SITE_ENTRY) if p not in g_out]
            if missing:
                fails.append(f"④ 守护日志里没有这些**绝对路径**：{missing} → 启动命令用了相对路径，"
                             f"事后无法用 CommandLine 认出端口上是谁（纪律 2）")
                print(f"   ✗ 守护日志缺少绝对路径：{missing}")
            else:
                print("   ✓ 守护日志里的启动命令都含**绝对路径**（CommandLine 可直接核身份）")
            if os.path.isdir(STACK_LOG_DIR):
                logs = sorted(os.listdir(STACK_LOG_DIR))
                print(f"   ✓ 日志目录 {STACK_LOG_DIR}：{logs}")
                for role in ROLES:
                    if f"{role}.log" not in logs:
                        fails.append(f"④ 日志目录里没有 {role}.log（验收要求：每进程一个日志文件）")
            else:
                fails.append(f"④ 守护没有创建日志目录 {STACK_LOG_DIR}")
            if proc.poll() is not None:
                fails.append(f"④ 守护进程在就绪后已退出（exit {proc.returncode}）—— 守护不该自己退")
            for role in ("engine", "gateway"):
                if role not in cold:
                    fails.append(f"④ 没拿到 {role} 的实测冷启动时间 → 恢复预算只能靠猜")
                else:
                    budget, why = ready_budget(cold[role], RECOVER_WAIT_OVERRIDE)
                    recover_budgets[role] = budget
                    print(f"   （{role} 恢复预算 {round(budget, 1)}s = {why}）")

    # ⑤A 杀引擎 → 自动重启（计划 Task 3 的原验收）----------------------
    ok_restart = False
    if "engine" not in recover_budgets:
        fails.append("⑤ 缺少引擎冷启动实测/预算（④ 未就绪）→ 本阶段按**失败**计（不是跳过）")
        print("\n⑤A ✗ 前置不足 → 按失败计")
    else:
        proc = guard_procs[-1]
        print(f"\n⑤A 崩溃恢复：故意杀引擎({PORTS['engine']}) → 应在 {round(recover_budgets['engine'], 1)}s 内自动重启")
        rows = listeners(PORTS["engine"]) or []
        old_pid = rows[0][0] if rows else None
        print(f"   杀之前引擎 PID = {old_pid}")
        if not stop_role("engine", expect_parent=proc.pid):
            fails.append("⑤A 杀引擎失败（净场/身份门拒绝）→ 恢复断言无法进行")
        else:
            ok_ready, elapsed, _c, detail = wait_ready(proc.pid, recover_budgets["engine"], "引擎自动重启",
                                                       roles=("engine",))
            if not ok_ready:
                fails.append(f"⑤A 杀引擎后 {round(recover_budgets['engine'], 1)}s 内没有自动重启到就绪：{detail}")
                print(f"   ✗ 未恢复（{elapsed}s）：{detail}")
                print("   ---- .stack-logs/engine.log 尾部 ----")
                print("\n".join("   " + ln for ln in tail_file(
                    os.path.join(STACK_LOG_DIR, "engine.log")).splitlines()))
            else:
                new_pid = role_state("engine", proc.pid)[2]
                ok_restart = True
                print(f"   ✓ 引擎自动重启：PID {old_pid} → {new_pid}（{elapsed}s，父进程 = 守护 PID {proc.pid}）")
                if str(new_pid) == str(old_pid):
                    fails.append("⑤A 「新 PID」与旧 PID 相同 → 不是重启（恢复 ≠ 还原原进程）")
                if proc.poll() is not None:
                    fails.append(f"⑤A 守护在重启过程中退出了（exit {proc.returncode}）")
                if not assert_quote_ok("⑤A 重启后测算（引擎）"):
                    print("   （注：网关 18001 内嵌了自己的引擎 app，杀 18000 本不该打断客户测算；"
                          "这里顺势做一次端到端回归）")

    # ⑤B 杀网关（站点真实依赖）→ 测算必须先坏后好 ----------------------
    if "gateway" not in recover_budgets:
        fails.append("⑤B 缺少网关冷启动实测/预算 → 本阶段按**失败**计（不是跳过）")
        print("\n⑤B ✗ 前置不足 → 按失败计")
    else:
        proc = guard_procs[-1]
        print(f"\n⑤B 端到端恢复：杀站点真实依赖网关({PORTS['gateway']}) → 测算必须先失败 → 重启后回到 ok=true")
        rows = listeners(PORTS["gateway"]) or []
        gw_old = rows[0][0] if rows else None
        if not stop_role("gateway", expect_parent=proc.pid):
            fails.append("⑤B 杀网关失败（净场/身份门拒绝）→ 端到端恢复断言无法进行")
        else:
            code, obj, raw = quote_once("   杀网关后立刻测算")
            if quote_is_ok(code, obj):
                fails.append(f"⑤B 杀掉网关后测算**仍然 ok**（HTTP {code}）→ 说明 {PORTS['gateway']} 上还有别的"
                             f"监听者顶着（重复监听者），或断言根本没打在真实依赖上")
            else:
                print(f"   ✓ 依赖确实断了：测算不再 ok（HTTP {code}）")
            ok_ready, elapsed, _c, detail = wait_ready(proc.pid, recover_budgets["gateway"], "网关自动重启",
                                                       roles=("gateway",))
            if not ok_ready:
                fails.append(f"⑤B 杀网关后 {round(recover_budgets['gateway'], 1)}s 内没有自动重启到就绪：{detail}")
                print(f"   ✗ 未恢复（{elapsed}s）：{detail}")
                print("   ---- .stack-logs/gateway.log 尾部 ----")
                print("\n".join("   " + ln for ln in tail_file(
                    os.path.join(STACK_LOG_DIR, "gateway.log")).splitlines()))
            else:
                gw_new = role_state("gateway", proc.pid)[2]
                print(f"   ✓ 网关自动重启：PID {gw_old} → {gw_new}（{elapsed}s）")
                if str(gw_new) == str(gw_old):
                    fails.append("⑤B 「新 PID」与旧 PID 相同 → 不是重启")
                wait_quote_ok("⑤B 网关重启后测算", recover_budgets["gateway"] + 10.0)

    # ⑥ 超限全停 ------------------------------------------------------
    if not ok_restart:
        fails.append("⑥ 前置（自动重启）未验证成功 → 超限实验按**失败**计（不是跳过）")
        print("\n⑥ ✗ 前置不足 → 按失败计")
    else:
        print(f"\n⑥ 超限全停：STACK_MAX_RESTARTS={int(LIMIT_MAX_RESTARTS)} 时连杀 2 次 → "
              f"守护必须**停掉全部子进程**、以非 0 退出并打印明确报错")
        proc = guard_procs[-1]
        guard_pid = proc.pid
        print(f"   先停掉守护 PID {guard_pid} 及其孤儿子进程（Windows 强杀守护**不会**带走子进程）")
        stop_pid(guard_pid, GUARD, "守护")
        for role in ROLES:                              # 子进程的父 = 刚死的守护 → 双重核对
            stop_role(role, expect_parent=guard_pid, allow_absent=True)
        for role in ROLES:
            rows = listeners(PORTS[role])
            print(f"   {role}({PORTS[role]}) LISTENING 行数 = {len(rows) if rows is not None else 'netstat 失败'}")
            if rows:
                fails.append(f"⑥ 清场后 {role}({PORTS[role]}) 仍有 {len(rows)} 行 LISTENING（{rows}）")
        leftovers = procs_by_parent(guard_pid) or []
        if leftovers:
            fails.append(f"⑥ 守护 PID {guard_pid} 还留着子进程："
                         f"{[(o.get('ProcessId'), str(o.get('CommandLine'))[:80]) for o in leftovers]}")
        if not all(listeners(PORTS[r]) == [] for r in ROLES):
            fails.append("⑥ 端口没清干净 → 守护 #2 起不来，超限实验按失败计")
            print("   ✗ 端口没清干净 → 按失败计")
        else:
            proc2, out2, err2 = start_guard({"STACK_MAX_RESTARTS": str(int(LIMIT_MAX_RESTARTS))}, tag="guard-limit")
            ok_ready, elapsed, cold2, detail = wait_ready(proc2.pid, READY_FIRST_BUDGET_S, "守护#2 三服务就绪",
                                                          guard_proc=proc2)
            if not ok_ready:
                fails.append(f"⑥ 守护#2 启动后 {READY_FIRST_BUDGET_S}s 内未就绪：{detail}")
                print(f"   ✗ 守护#2 未就绪（{elapsed}s）：{detail}")
                print("\n".join("   " + ln for ln in tail_file(err2).splitlines()))
            else:
                print(f"   ✓ 守护#2 就绪（PID {proc2.pid}，{elapsed}s）")
                b_engine, _why = ready_budget(cold2.get("engine", 5.0), RECOVER_WAIT_OVERRIDE)
                kill_budget = b_engine + 10.0
                kill_count = int(LIMIT_MAX_RESTARTS) + 1
                for i in range(1, kill_count + 1):
                    rows = listeners(PORTS["engine"]) or []
                    if not rows:
                        fails.append(f"⑥ 第 {i} 次杀引擎前 {PORTS['engine']} 上没有监听进程 → 实验不成立（记失败）")
                        break
                    pid_i = rows[0][0]
                    print(f"   第 {i}/{kill_count} 次杀引擎（PID {pid_i}，父进程 = 守护#2 {proc2.pid}）")
                    if not stop_role("engine", expect_parent=proc2.pid):
                        fails.append(f"⑥ 第 {i} 次杀引擎失败（身份门拒绝）→ 超限实验不成立")
                        break
                    if i < kill_count:
                        ok_r, el_r, _cc, det_r = wait_ready(proc2.pid, b_engine, f"第 {i} 次重启",
                                                            roles=("engine",))
                        if not ok_r:
                            fails.append(f"⑥ 第 {i} 次杀引擎后 {round(b_engine, 1)}s 内没有自动重启（{det_r}）"
                                         f"→ 超限实验不成立")
                            break
                        print(f"   ✓ 第 {i} 次已自动重启（{el_r}s）")
                        if proc2.poll() is not None:
                            fails.append(f"⑥ 守护#2 在第 {i} 次重启后就退出了（exit {proc2.returncode}）"
                                         f"→ 上限判定过早")
                            break
                # 守护必须退出（超限 → 全停 + 报错）
                try:
                    rc = proc2.wait(timeout=kill_budget + 20.0)
                except subprocess.TimeoutExpired:
                    rc = None
                if rc is None:
                    fails.append(f"⑥ 连杀 {kill_count} 次后守护#2 没有退出（超限判据未生效：应为「全停 + 非 0 退出」）")
                    print("   ✗ 守护#2 仍未退出 → 记失败")
                    print("\n".join("   " + ln for ln in tail_file(err2).splitlines()))
                else:
                    print(f"   ✓ 守护#2 已退出，退出码 = {rc}")
                    if rc == 0:
                        fails.append("⑥ 守护超限退出码为 0（应非 0：超限是失败，不是正常结束）")
                    err_txt = read_text(err2)
                    for needle in ("重启已达上限", "全部子进程已停止", "engine.log"):
                        if needle not in err_txt:
                            fails.append(f"⑥ 守护超限退出时 stderr 里没有 {needle!r}（报错必须明确到「哪个服务、"
                                         f"几次、去哪看日志」）")
                    if "重启已达上限" in err_txt and "全部子进程已停止" in err_txt:
                        print("   ✓ 报错明确：含「重启已达上限」「全部子进程已停止」与日志路径")
                    print("   ---- 守护#2 stderr 尾部 ----")
                    print("\n".join("   " + ln for ln in tail_file(err2, 14).splitlines()))
                for role in ROLES:
                    rows = listeners(PORTS[role]) or []
                    print(f"   {role}({PORTS[role]}) LISTENING 行数 = {len(rows)}")
                    if rows:
                        fails.append(f"⑥ 超限退出后 {role}({PORTS[role]}) 仍有 {len(rows)} 行 LISTENING → "
                                     f"没有「全部停掉」（{rows}）")
                left2 = procs_by_parent(proc2.pid) or []
                if left2:
                    fails.append(f"⑥ 守护#2 退出后仍留下子进程："
                                 f"{[(o.get('ProcessId'), str(o.get('CommandLine'))[:80]) for o in left2]}")
                else:
                    print("   ✓ 守护#2 没有留下任何子进程")

    # ⑦ 收尾恢复 ------------------------------------------------------
    print("\n⑦ 收尾：三服务恢复到在跑（绝对路径启动；「恢复 = 新进程」）")
    for proc in guard_procs:
        if proc.poll() is None:
            stop_pid(proc.pid, GUARD, "守护")
    for role in ROLES:
        stop_role(role, allow_absent=True)
    for role in ROLES:
        start_role_detached(role)
    ok_ready, elapsed, _cold, detail = wait_ready(None, READY_FIRST_BUDGET_S, "收尾后就绪")
    if not ok_ready:
        fails.append(f"⑦ 收尾后三服务未就绪（{detail}）")
        print(f"   ✗ 未就绪（{elapsed}s）：{detail}")
    else:
        print(f"   ✓ 三服务就绪（{elapsed}s）")
        for role in ROLES:
            rows = listeners(PORTS[role]) or []
            pid = rows[0][0] if rows else None
            info = proc_info(pid) if pid else {}
            orig = _original_snapshot.get(role, {})
            print(f"   {role}({PORTS[role]}) LISTENING 行数 = {len(rows)}（**必须为 1**）")
            print(f"        原 PID {orig.get('pid')} · 原 CommandLine = {str(orig.get('cmd'))[:150]}")
            print(f"        现 PID {pid} · 现 CommandLine = {str(info.get('CommandLine'))[:150]}")
            if len(rows) != 1:
                fails.append(f"⑦ 收尾后 {role}({PORTS[role]}) 有 {len(rows)} 行 LISTENING（必须 1）")
        assert_quote_ok("⑦ 收尾后测算")


main()

print()
if fails:
    print(f"存在问题（{len(fails)} 条）：\n  - " + "\n  - ".join(fails))
    print("（临时日志保留在：" + SCRATCH + "）")
    sys.exit(1)
print("全部通过 ✅")
print(f"（守护/子进程日志：{STACK_LOG_DIR}；本次 scratch：{SCRATCH}）")
sys.exit(0)
