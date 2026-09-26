#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T4 验收：`npm run engine:audit` —— 引擎参数体检导出（只读、每项带 source、缺项即失败）。

被测对象：`scripts/engine-audit.mjs`（= `npm run engine:audit`）。只通过**公开入口**驱动它：
  ① 正常路径（OSRM_API_BASE=http://127.0.0.1:18000，引擎在跑）→ 退出 0，两张产物齐全，
     五区块齐全（费率 / 汇率 / 油价 / 口岸费用 / 税率口径对照），且每个数字带 source（端点 + 字段路径）；
  ② **真值核对**：体检表记的油价、两条税率必须与验收脚本**自己现拉**的一致 —— 防「表是编的」。
     同一 HS 两种口径不一致时必须**并列记录**且不许自己选一个当正确值；
  ③ **缺项必须明说**：样本 0 条 / 版本 0 个 / price_factor active=false / 油价 manual_default
     必须在 `flags` 里显式列出（不许静默留空）；md 里也要看得见「未校准/未启用/默认值」；
  ④ 死端口（OSRM_API_BASE=http://127.0.0.1:19999）→ **必须非 0 退出**，且**不得**把已产出的
     好表覆盖成半空表（「出一张半空的表当成功」正是要防的假绿面）；
  ⑤ 缺 OSRM_API_BASE → **必须非 0 退出**（不许猜一个默认地址去体检）。

纪律（每条都对应本仓库已踩过的坑）：
  1. **ROOT 绝不硬编码**（仓库路径含中文**和空格**，换机器/换目录就挂）→ 按脚本自身路径推断。
  2. 所有子进程调用都带 Python 级 `timeout`；`TimeoutExpired` **记 fail**（任一挂住 = 脚本永不退出）。
  3. 读子进程输出一律 bytes + `errors='replace'`（Windows 控制台/管道编码不是 UTF-8）。
  4. **「没做成」一律记 fail**：绝不允许静默跳过断言还打「全部通过」。
  5. 引擎自带 IP 限流（实测 60 req/min 触发过 429）→ 本脚本自己的请求也**顺序 + 间隔**，不并发轰炸。
  6. 临时产物只落 `$LOCALAPPDATA/hermes/cache/scratch` 下的自有子目录（TMPDIR）。

退出码：0 = 全绿；1 = 有断言失败；2 = 参数/环境非法（未进任何破坏性阶段）。

注意：本脚本**只读**引擎（GET + 一个纯计算的 POST import-tax，无状态、无外部额度），
绝不调用 /route/cost（配额与限流）与任何写端点。
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:                                     # 控制台编码兜底：中文日志不得因 cp936 抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 路径与常量（ROOT 按脚本自身推断，绝不硬编码）─────────────────────────
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "engine-audit.mjs"
OUT_DIR = ROOT / "docs" / "engine-audit"
NODE = shutil.which("node")
SCRATCH = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or ".",
               "hermes", "cache", "scratch", "t4-engine-audit")
SCRATCH.mkdir(parents=True, exist_ok=True)

ENGINE_BASE = (os.environ.get("AUDIT_ENGINE_BASE") or "http://127.0.0.1:18000").rstrip("/")
DEAD_BASE = (os.environ.get("AUDIT_DEAD_BASE") or "http://127.0.0.1:19999").rstrip("/")
MD_GLOB = "*-engine-audit.md"
MD_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-engine-audit\.md$")
JSON_NAME = "engine-params.json"
SECTIONS = ["费率", "汇率", "油价", "口岸费用", "税率口径对照"]
HS_SAMPLE = "730890"
CARGO_VALUE_RMB = 500000
HTTP_SPACING_S = 1.2                     # 引擎 60 req/min 滑动窗口 → 顺序 + 间隔，不并发

fails: list[str] = []


def fail(msg: str) -> None:
    fails.append(msg)
    print(f"   ✗ {msg}")


def ok(msg: str) -> None:
    print(f"   ✓ {msg}")


# ── 子进程（统一带 timeout；超时记 fail，绝不静默）──────────────────────
def run_cmd(args: list[str], timeout: float, env: dict | None = None,
            cwd: str | None = None, label: str | None = None):
    """→ CompletedProcess | None（超时/无法执行一律记 fail）。

    故意不用 `subprocess.run(timeout=)`：它超时那条路径上 kill 之后还会**无超时地**排空管道，
    只要还有别的进程握着写端就永不返回（本仓库 T3 脚本第一版就死在这里）。这里 kill 后有界排空。
    """
    name = label or " ".join(args)
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=cwd, env=env)
    except OSError as exc:
        fail(f"{name} 无法执行：{exc}")
        return None
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.communicate(timeout=5)              # 有界排空：孙子进程可能一直握着写端
        except Exception:
            pass
        fail(f"{name} 超时（>{timeout}s）—— 记失败，避免脚本挂死")
        return None
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


def run_audit(base: str | None, timeout: float, label: str, drop_base: bool = False):
    """跑体检脚本。base=None + drop_base=True 时**删掉** OSRM_API_BASE（验「缺变量必须失败」）。"""
    env = {**os.environ}
    if drop_base:
        env.pop("OSRM_API_BASE", None)
    else:
        env["OSRM_API_BASE"] = base
    t0 = time.time()
    proc = run_cmd([NODE, str(AUDIT)], timeout, env=env, cwd=str(ROOT),
                   label=f"node scripts/engine-audit.mjs（{label}）")
    return proc, t0


def decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", "replace")


# ── HTTP 小工具（只读；带 timeout；顺序 + 间隔）─────────────────────────
def http_json(path_qs: str, method: str = "GET", timeout: float = 25, attempts: int = 3):
    """→ (code, obj|None, raw)；code 0 = 连不上/超时。

    只对**连接级**错误重试（本机引擎偶发 `WinError 10054 远程主机强迫关闭连接`，实测每次换一个端点：
    引擎明明在线、其他请求都 200 —— 这类瞬时抖动不该让验收假红）。
    HTTP 错误码**立即返回**（429/405/500 都是确定性结果，重试会把「端点写错」掩盖成偶发）。
    重试次数有界 → **真不可达（死端口）重试完仍然失败**，「不可达 = 失败」的语义不变。
    """
    url = f"{ENGINE_BASE}/api/v1{path_qs}"
    data = b"" if method == "POST" else None
    last = ""
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=data, method=method,
                                    headers={"User-Agent": "jiuneng-engine-audit-verify"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
                code = resp.status
            try:
                return code, json.loads(body), body
            except Exception:
                return code, None, body
        except urllib.error.HTTPError as exc:
            return exc.code, None, exc.read().decode("utf-8", "replace")
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(0.6 * attempt)
    return 0, None, last


def health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{ENGINE_BASE}/health", timeout=10) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status == 200 and '"ok"' in body
    except Exception:
        return False


# ── 产物读取 ───────────────────────────────────────────────────────────
def artifact_snapshot() -> dict[str, bytes]:
    """产物目录全部文件 → {相对路径: 原始字节}（用于证明失败路径**没有**覆盖好表）。"""
    snap: dict[str, bytes] = {}
    if not OUT_DIR.is_dir():
        return snap
    for p in sorted(OUT_DIR.rglob("*")):
        if p.is_file():
            try:
                snap[str(p.relative_to(ROOT))] = p.read_bytes()
            except Exception:
                pass
    return snap


def md_files() -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(OUT_DIR / MD_GLOB)))


def newer_than(paths: list[Path], ts: float) -> list[Path]:
    """本次运行**写出**的文件（mtime ≥ ts）—— 不用文件名猜日期（node 用 UTC、本机是 +07）。"""
    out = []
    for p in paths:
        try:
            if p.stat().st_mtime >= ts - 1.0:
                out.append(p)
        except OSError:
            pass
    return out


# ─────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 78)
    print("T4 验收：npm run engine:audit（引擎参数体检导出）")
    print(f"ROOT        = {ROOT}")
    print(f"体检脚本    = {AUDIT}")
    print(f"产物目录    = {OUT_DIR}")
    print(f"引擎        = {ENGINE_BASE}")
    print(f"死端口      = {DEAD_BASE}")
    print(f"node        = {NODE}")
    print(f"本次 scratch= {SCRATCH}")
    if os.environ.get("PYTHONPATH"):
        print("（提示：本仓库验收请用 `env -u PYTHONPATH python scripts/verify-engine-audit.py`）")
    print("=" * 78)

    if not NODE:
        fail("PATH 里找不到 node（体检脚本要用它跑）")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1

    # ── 前置：被测对象存在吗 ─────────────────────────────────────────
    print("\n⓪ 前置：被测脚本存在")
    if not AUDIT.is_file():
        fail(f"被测对象不存在：{AUDIT}（TDD 首轮的预期失败点）")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1
    ok(f"存在：{AUDIT}")

    # ── 前置：引擎必须可达（不可达 = 失败，不是跳过）───────────────────
    print(f"\n⓪ 前置：引擎健康检查（{ENGINE_BASE}/health）")
    if not health_ok():
        fail(f"引擎不可达（{ENGINE_BASE}/health 非 200）→ 体检无法进行，本次验收按**失败**计（不是跳过）")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1
    ok("引擎在线")

    # ── 验收脚本自己现拉真值（供 ② 核对）─────────────────────────────
    print("\n⓪ 验收脚本自拉真值（顺序 + 间隔，避免撞引擎 60 req/min 限流）")
    live: dict[str, object] = {}
    probes = [("samples", "/rates/samples", "GET"),
              ("versions", "/rates/versions", "GET"),
              ("current", "/rates/current", "GET"),
              ("fuel", "/reference/fuel-price", "GET"),
              ("hs_lookup", f"/border/hs-lookup?hs_code={HS_SAMPLE}", "GET"),
              ("import_tax", f"/border/import-tax?cargo_value_rmb={CARGO_VALUE_RMB}&hs_code={HS_SAMPLE}", "POST")]
    for name, qs, method in probes:
        code, obj, raw = http_json(qs, method)
        if code != 200 or not isinstance(obj, (dict, list)):
            fail(f"验收脚本自拉 {method} {qs} 失败（HTTP {code}，{raw[:160]!r}）→ 无法做真值核对")
        else:
            live[name] = obj
            print(f"   · {method} {qs} → HTTP 200")
        time.sleep(HTTP_SPACING_S)
    if len(live) != len(probes):
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1

    # ── ① 正常路径 ───────────────────────────────────────────────────
    print("\n① 正常路径：引擎在 18000 → 体检脚本必须退出 0 并产出两张产物")
    proc, t0 = run_audit(ENGINE_BASE, 900, "正常路径")
    if proc is None:
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1
    out_txt, err_txt = decode(proc.stdout), decode(proc.stderr)
    print(f"   退出码 = {proc.returncode}")
    print("   ---- stdout 尾部 ----")
    for line in out_txt.strip().splitlines()[-14:]:
        print("   " + line)
    if err_txt.strip():
        print("   ---- stderr 尾部 ----")
        for line in err_txt.strip().splitlines()[-14:]:
            print("   " + line)
    if proc.returncode != 0:
        fail(f"正常路径应退出 0，实际 {proc.returncode}")

    md_new = newer_than(md_files(), t0)
    json_path = OUT_DIR / JSON_NAME
    json_new = json_path.is_file() and json_path.stat().st_mtime >= t0 - 1.0
    if not md_new:
        fail(f"本次运行未产出 {MD_GLOB}（目录里现有：{[p.name for p in md_files()] or '（空）'}）")
    else:
        table = max(md_new, key=lambda p: p.stat().st_mtime)
        ok(f"产出 {table.relative_to(ROOT)}")
        if not MD_NAME_RE.match(table.name):
            fail(f"产文件名应为 <YYYY-MM-DD>-engine-audit.md，实际 {table.name!r}")
    if not json_new:
        fail(f"本次运行未产出 {OUT_DIR / JSON_NAME}")
    else:
        ok(f"产出 {(OUT_DIR / JSON_NAME).relative_to(ROOT)}")

    if not md_new or not json_new:
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1

    md = max(md_new, key=lambda p: p.stat().st_mtime).read_text(encoding="utf-8", errors="replace")
    try:
        snap_json = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        fail(f"{JSON_NAME} 不是合法 JSON：{exc}")
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1
    ok("engine-params.json 可解析")

    # ── ①a 五区块 + source 标注 ──────────────────────────────────────
    print("\n①a 体检表：五区块齐全 + 每个数字带 source（端点 · 字段路径）")
    for section in SECTIONS:
        if section in md:
            ok(f"区块「{section}」在表里")
        else:
            fail(f"体检表缺区块：{section}")
    if "source" in md:
        ok("表里有 source 字样")
    else:
        fail("体检表未标注 source（无法判断数据真伪）")
    n_get = len(re.findall(r"GET /api/v1/", md))
    if n_get >= 8:
        ok(f"表里 {n_get} 处 GET 端点标注（每个数字都能追到端点）")
    else:
        fail(f"表里只找到 {n_get} 处 `GET /api/v1/` 端点标注（每个数字都应能追到端点 + 字段路径）")
    if "POST /api/v1/border/import-tax" in md:
        ok("税率对照区标了 POST /api/v1/border/import-tax（GET 会 405，必须写清方法）")
    else:
        fail("税率对照区没标出 POST /api/v1/border/import-tax（该端点是 POST，GET 会 405）")
    if " · " in md:
        ok("source 单元格带字段路径（`端点 · 字段`）")
    else:
        fail("source 只写了端点、没写**字段路径**（追不到原值出自哪个字段）")

    # ── ①b 机器可读版的结构 ─────────────────────────────────────────
    print("\n①b engine-params.json：provenance / flags / tax_comparison 结构")
    prov = snap_json.get("provenance")
    if not isinstance(prov, list) or not prov:
        fail("engine-params.json 缺 provenance（每个数字 → 端点 + 字段路径 + 原值）")
    else:
        bad = [e for e in prov if not isinstance(e, dict)
               or not str((e.get("source") or {}).get("endpoint") or "").strip()
               or not str((e.get("source") or {}).get("field") or "").strip()]
        if bad:
            fail(f"provenance 有 {len(bad)} 条缺 endpoint/field（例：{json.dumps(bad[0], ensure_ascii=False)[:200]}）")
        else:
            ok(f"provenance {len(prov)} 条，条条带 endpoint + field")
        if len(prov) < 15:
            fail(f"provenance 只有 {len(prov)} 条（费率/汇率/油价/口岸费用等关键数字都该有出处）")

    # ── ② 真值核对（防「表是编的」）───────────────────────────────────
    print("\n② 真值核对：表里的数字 = 验收脚本现拉的数字")
    sec = snap_json.get("sections") if isinstance(snap_json.get("sections"), dict) else {}
    lf = live.get("fuel") or {}
    af = (sec.get("reference_fuel_price") or {}) if isinstance(sec, dict) else {}
    if af.get("price_vnd") == lf.get("price_vnd") and af.get("source") == lf.get("source"):
        ok(f"油价一致：price_vnd={af.get('price_vnd')} source={af.get('source')!r}")
    else:
        fail(f"油价与现拉值不一致：表里 price_vnd={af.get('price_vnd')} source={af.get('source')!r}，"
             f"现拉 price_vnd={lf.get('price_vnd')} source={lf.get('source')!r}")
    if str(lf.get("price_vnd")) and f"{float(lf['price_vnd']):g}" in md:
        ok(f"体检表里能看到现拉油价原值 {float(lf['price_vnd']):g}")
    else:
        fail(f"体检表里找不到现拉油价原值 {lf.get('price_vnd')}（表可能是拼的）")

    tc = snap_json.get("tax_comparison") if isinstance(snap_json.get("tax_comparison"), dict) else {}
    hl, it = tc.get("hs_lookup") or {}, tc.get("import_tax") or {}
    live_hl = live.get("hs_lookup") or {}
    live_it = live.get("import_tax") or {}
    if hl.get("duty_rate") == live_hl.get("import_duty_rate"):
        ok(f"hs-lookup 税率一致：{hl.get('duty_rate')}（source={hl.get('duty_source')!r}）")
    else:
        fail(f"hs-lookup 税率与现拉值不一致：表里 {hl.get('duty_rate')}，现拉 {live_hl.get('import_duty_rate')}")
    if it.get("duty_rate") == live_it.get("duty_rate"):
        ok(f"import-tax 税率一致：{it.get('duty_rate')}（source={it.get('duty_source')!r}）")
    else:
        fail(f"import-tax 税率与现拉值不一致：表里 {it.get('duty_rate')}，现拉 {live_it.get('duty_rate')}")
    if str(hl.get("duty_source") or "") in md and str(it.get("duty_source") or "") in md:
        ok("两条口径的 duty_source 都写进了表")
    else:
        fail("税率对照区没写出两条口径各自的 duty_source")
    if hl.get("duty_rate") != it.get("duty_rate"):
        if tc.get("conflict") is True:
            ok("两口径不一致 → conflict=true 已标出（不自己选一个当正确值）")
        else:
            fail(f"两口径不一致（hs-lookup {hl.get('duty_rate')} vs import-tax {it.get('duty_rate')}）"
                 f"但 tax_comparison.conflict != true —— 不许悄悄选一个当正确值")
        for token in ("hs-lookup", "import-tax"):
            if token not in md:
                fail(f"税率口径对照区没并列指出 {token}（两个端点各取一次、并列对比）")
        note = str(tc.get("note") or "")
        if note:
            ok(f"对照区有说明：{note[:100]}")
        else:
            fail("tax_comparison.note 为空：不一致时必须写清「待业务方拍板」")

    # ── ③ 缺项必须明说（不许静默留空）────────────────────────────────
    print("\n③ 缺项明说：样本 0 条 / 版本 0 个 / 系数未启用 / 油价默认值 必须在 flags 里")
    ls = live.get("samples") or {}
    lv = live.get("versions") or {}
    lc = live.get("current") or {}
    flags = snap_json.get("flags")
    if not isinstance(flags, list) or not flags:
        fail("engine-params.json 缺 flags：缺失/未校准/未启用的参数必须**显式列出**，不能静默留空")
        flags = []
    else:
        bad = [f_ for f_ in flags if not isinstance(f_, dict)
               or not str(f_.get("reason") or "").strip() or not str(f_.get("source") or "").strip()]
        if bad:
            fail(f"flags 有 {len(bad)} 条缺 reason/source（例：{json.dumps(bad[0], ensure_ascii=False)[:200]}）")
        else:
            ok(f"flags {len(flags)} 条，条条带 reason + source")

    def flagged(*tokens: str) -> bool:
        blob = json.dumps(flags, ensure_ascii=False)
        return any(t in blob for t in tokens)

    live_samples_total = ((ls.get("stats") or {}) if isinstance(ls, dict) else {}).get("total")
    live_versions_n = len(lv.get("versions") or []) if isinstance(lv, dict) else None
    live_factor_active = ((lc.get("price_factor") or {}) if isinstance(lc, dict) else {}).get("active")
    live_fuel_src = lf.get("source")

    checks = [(live_samples_total == 0, ("样本",), "费率样本 0 条（未校准）"),
              (live_versions_n == 0, ("版本",), "费率版本 0 个"),
              (live_factor_active is False, ("系数",), "price_factor active=false（未启用）"),
              (live_fuel_src == "manual_default", ("油价", "燃料"), "油价 manual_default（默认值非实时）")]
    for cond, tokens, desc in checks:
        if cond is True:
            if flagged(*tokens):
                ok(f"已显式标出：{desc}")
            else:
                fail(f"{desc} 但 flags 里没有对应条目 → 静默留空")
        else:
            print(f"   （引擎当前无此项，跳过条件断言：{desc}）")
    if live_samples_total == 0:
        if "未校准" in md or "0 条" in md:
            ok("体检表里也看得见「未校准 / 0 条」")
        else:
            fail("体检表里看不到样本 0 条的说明（业务方会以为费率是真校准过的）")

    if snap_json.get("problems"):
        fail(f"正常路径不该有拉取问题，实际 problems={json.dumps(snap_json['problems'], ensure_ascii=False)[:300]}")
    else:
        n_sec = len([s for s in (snap_json.get("read_only_sections") or []) if s.get("status") == 200])
        ok(f"problems 为空（{n_sec} 个只读区块全部 200）")

    # ── ④ 死端口必须非 0 退出，且不得覆盖好表 ─────────────────────────
    print(f"\n④ 失败路径：OSRM_API_BASE={DEAD_BASE}（死端口）→ 必须非 0 退出，且不得覆盖已产出的好表")
    before = artifact_snapshot()
    proc2, _ = run_audit(DEAD_BASE, 300, "死端口")
    if proc2 is None:
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1
    out2, err2 = decode(proc2.stdout), decode(proc2.stderr)
    print(f"   退出码 = {proc2.returncode}")
    print("   ---- 输出尾部 ----")
    for line in (out2 + err2).strip().splitlines()[-12:]:
        print("   " + line)
    if proc2.returncode == 0:
        fail("引擎不可达时体检脚本**退出 0** —— 不能出一张半空的表当成功（必须非 0）")
    else:
        ok(f"死端口非 0 退出（{proc2.returncode}）")
    blob = out2 + err2
    if any(t in blob for t in ("health", "健康", "不可达", "连不上", DEAD_BASE, "19999")):
        ok("报错说清了「引擎不在」")
    else:
        fail(f"死端口路径的报错没说清引擎不可达（输出里既没有 health/健康/不可达，也没有 {DEAD_BASE}）")
    after = artifact_snapshot()
    changed = sorted(set(before) ^ set(after)) + sorted(k for k in before if k in after and before[k] != after[k])
    if changed:
        fail(f"失败路径**改写了产物**：{changed} —— 半空的表绝不能覆盖已产出的好表")
    else:
        ok(f"失败路径零副作用：{len(before)} 份产物字节级未变")

    # ── ⑤ 缺 OSRM_API_BASE 必须非 0 退出 ─────────────────────────────
    print("\n⑤ 失败路径：不设 OSRM_API_BASE → 必须非 0 退出（不许猜一个默认地址去体检）")
    proc3, _ = run_audit(None, 120, "缺环境变量", drop_base=True)
    if proc3 is None:
        print("\n存在问题：\n  - " + "\n  - ".join(fails))
        return 1
    print(f"   退出码 = {proc3.returncode}")
    print("   ---- 输出尾部 ----")
    for line in (decode(proc3.stdout) + decode(proc3.stderr)).strip().splitlines()[-6:]:
        print("   " + line)
    if proc3.returncode == 0:
        fail("没设 OSRM_API_BASE 时体检脚本退出 0（会去猜一个地址，体检结果不可信）")
    else:
        ok(f"缺环境变量非 0 退出（{proc3.returncode}）")
    if artifact_snapshot() != before:
        fail("缺环境变量路径改写了产物")

    print()
    if fails:
        print(f"存在问题（{len(fails)} 条）：\n  - " + "\n  - ".join(fails))
        print(f"（异常产物保留在：{SCRATCH}）")
        return 1
    print("全部通过 ✅")
    print(f"（体检表：{max(md_new, key=lambda p: p.stat().st_mtime).relative_to(ROOT)}；"
          f"快照：{(OUT_DIR / JSON_NAME).relative_to(ROOT)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
