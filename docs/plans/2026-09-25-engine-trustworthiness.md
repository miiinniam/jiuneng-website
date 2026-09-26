# 引擎可信度与可用性加固 实现计划（A 切片）

> **For implementer:** 本项目没有单测框架，验收手段是「真跑探针脚本」——所以 TDD 在这里的含义是：**先写会失败的验收脚本 → 跑到失败 → 再实现 → 跑到通过 → commit**。任何一步都不许用 mock 冒充通过。

**Goal:** 让官网对客的参考价区间建立在**可核对、可监控、可自恢复**的引擎之上：导出引擎参数供业务方核对、健康检查如实反映依赖、本机引擎崩溃自动恢复、云上实跑对比验证。

**Architecture:** 复用 `server/osrmQuote.ts` 已有的 `engineBase()` 解析逻辑，新增同模块导出的 `probeEngine()`；`server.ts` 用它做后台探针 + `/api/health?deep=1`；新增两个独立脚本（`serve-stack.mjs` 守护三服务、`engine-audit.mjs` 只读拉参数出表）；云上验证依赖业务方先填 Render 环境变量。

**Tech Stack:** Node 22（ESM `.mjs` / tsx 跑 TS）、Express 4、fetch（Node 内置）、Python 3.11（探针脚本，沿用项目既有探针风格）、curl（探针内一律用 curl，本机 Python urllib 走 127.0.0.1 会挂）

**关联设计文档:** `docs/superpowers/specs/2026-09-25-engine-trustworthiness-design.md`（已 commit `43e32ce`）

---

## 前置条件（开工前确认）

```bash
# 三个服务在跑（引擎/网关/官网），否则 Task 1 的 live 分支无法验证
for p in 18000 18001 3300; do echo "$p -> $(curl -s -o /dev/null -m 6 -w '%{http_code}' http://127.0.0.1:$p/health)"; done
# 期望：18000 -> 200（引擎 /health）、18001 -> 200（网关）、3300 -> 200（官网）
# 若引擎掉了：npm run stack（Task 3 完成后）或手工重启
```

**本机重启三服务的命令（Task 3 交付前手工用）**

```bash
cd "D:/01_业务/立三方/AIOSRM++/backend" && "D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe" run_server.py --port 18000
cd "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4/deploy/osrm-engine" && PORT=18001 ENGINE_API_KEY=test-key-abc123 "D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe" server.py
cd "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4" && NODE_ENV=production PORT=3300 AGENT_CHAT_DEMO=1 OSRM_API_BASE=http://127.0.0.1:18001 OSRM_ENGINE_KEY=test-key-abc123 node dist/server.cjs
```

---

## Task 1: `probeEngine()` —— 引擎可达性探测（复用 engineBase）

**Files:**
- Modify: `server/osrmQuote.ts`（在 `engineBase()` 之后新增导出函数）
- Create: `scripts/verify-engine-probe.ts`
- Test: `scripts/verify-engine-probe.ts`

**Step 1: 先写会失败的验收脚本**

创建 `scripts/verify-engine-probe.ts`：

```ts
/** probeEngine 三分支验收：可达 / 死端口 / 未配置。用法：npx tsx scripts/verify-engine-probe.ts */
import { probeEngine } from '../server/osrmQuote';

const fails: string[] = [];

process.env.OSRM_API_BASE = 'http://127.0.0.1:18000';
const live = await probeEngine(5000);
console.log('live  :', JSON.stringify(live));

process.env.OSRM_API_BASE = 'http://127.0.0.1:19999';   // 没人监听
const dead = await probeEngine(1200);
console.log('dead  :', JSON.stringify(dead));

process.env.OSRM_API_BASE = '';
const none = await probeEngine(500);
console.log('none  :', JSON.stringify(none));

if (!live.ok) fails.push(`引擎在 18000 应判可达，实际 ${JSON.stringify(live)}`);
if (live.ms <= 0) fails.push(`live.ms 应为正数，实际 ${live.ms}`);
if (dead.ok || !dead.reason) fails.push(`死端口应判失败且带 reason，实际 ${JSON.stringify(dead)}`);
if (none.reason !== 'not_configured') fails.push(`未配置应 reason=not_configured，实际 ${JSON.stringify(none)}`);

console.log(fails.length ? `✗ ${fails.join(' | ')}` : '✓ probeEngine 三分支正确');
process.exit(fails.length ? 1 : 0);
```

**Step 2: 跑它，确认失败**

```bash
cd "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4" && npx tsx scripts/verify-engine-probe.ts
```

Expected: FAIL —— `SyntaxError: The requested module '../server/osrmQuote' does not provide an export named 'probeEngine'`

**Step 3: 实现**

在 `server/osrmQuote.ts` 的 `engineBase()`（当前 109-115 行）之后插入：

```ts
/** 引擎根地址（去掉 /api/v1 后缀）—— 引擎的 /health 挂在根路径上。 */
function engineRoot(): string {
  return engineBase().replace(/\/api\/v1$/, '');
}

/**
 * 轻量探测引擎是否可达。给健康检查复用，**不抛异常**，只回结果。
 * 注意：引擎在 Render 免费层会休眠，探测超时要显式小于官网业务超时（40s）。
 */
export async function probeEngine(timeoutMs = 3_000): Promise<{ ok: boolean; ms: number; reason?: string }> {
  const base = engineBase();
  if (!base) return { ok: false, ms: 0, reason: 'not_configured' };

  const started = Date.now();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${engineRoot()}/health`, {
      signal: ctrl.signal,
      headers: { 'User-Agent': 'jiuneng-website-healthcheck' },
    });
    const ms = Date.now() - started;
    if (!res.ok) return { ok: false, ms, reason: `status_${res.status}` };
    return { ok: true, ms };
  } catch (error: any) {
    const ms = Date.now() - started;
    // AbortError 是超时；其余按不可达归类，便于健康检查区分展示
    return { ok: false, ms, reason: error?.name === 'AbortError' ? 'timeout' : 'unreachable' };
  } finally {
    clearTimeout(timer);
  }
}
```

**Step 4: 跑测试，确认通过**

```bash
npx tsx scripts/verify-engine-probe.ts
npm run lint
```

Expected: `✓ probeEngine 三分支正确`；TS 错误数 0

**Step 5: 提交**

```bash
git add server/osrmQuote.ts scripts/verify-engine-probe.ts
git commit -m "feat(engine): 导出 probeEngine 可达性探测（健康检查复用，三分支验收）"
```

---

## Task 2: `/api/health` 如实反映依赖（轻量 + `?deep=1`）

**Files:**
- Modify: `server.ts`（import、探针、`/api/health` 处理器；当前处理器在 49-51 行）
- Create: `scripts/verify-health.py`
- Test: `scripts/verify-health.py`

**Step 1: 先写会失败的验收脚本**

创建 `scripts/verify-health.py`：

```python
"""健康检查如实反映引擎状态 —— 真杀进程、真恢复，不用 mock。
用法：python scripts/verify-health.py [site_url]
"""
import json, subprocess, sys, time

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3300"
ENGINE_PORT = 18000
ENGINE_CMD = ["D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe", "run_server.py", "--port", str(ENGINE_PORT)]
ENGINE_CWD = "D:/01_业务/立三方/AIOSRM++/backend"
fails = []


def curl_json(url, timeout=15):
    r = subprocess.run(["curl", "-s", "-m", str(timeout), url], capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception:
        return None


def engine_pid():
    out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if f":{ENGINE_PORT} " in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def kill_engine():
    pid = engine_pid()
    if pid:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                       capture_output=True)
    return pid


def start_engine():
    subprocess.Popen(ENGINE_CMD, cwd=ENGINE_CWD,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if curl_json(f"http://127.0.0.1:{ENGINE_PORT}/health", 3):
            return True
        time.sleep(1)
    return False


light = curl_json(f"{SITE}/api/health")
print("轻量:", json.dumps(light, ensure_ascii=False)[:200] if light else None)
if not light:
    fails.append("轻量 /api/health 无响应")
else:
    if "engine" not in light:
        fails.append("轻量 /api/health 缺 engine 字段")
    else:
        if "configured" not in light["engine"]:
            fails.append("engine.configured 缺失")
        if light["engine"].get("base") and ("key" in light["engine"]["base"] or "/" in light["engine"]["base"]):
            fails.append("engine.base 泄露了路径或密钥（只应给 host）")

deep_up = curl_json(f"{SITE}/api/health?deep=1", 20)
print("深探测(引擎在):", json.dumps(deep_up, ensure_ascii=False)[:200] if deep_up else None)
if not deep_up or deep_up.get("engine", {}).get("lastProbe", {}).get("ok") is not True:
    fails.append(f"引擎在线时 deep=1 应 ok=true，实际 {deep_up}")

print("杀掉引擎…")
print("  被杀的 PID:", kill_engine())
time.sleep(2)

deep_down = curl_json(f"{SITE}/api/health?deep=1", 20)
print("深探测(引擎挂):", json.dumps(deep_down, ensure_ascii=False)[:220] if deep_down else None)
if not deep_down:
    fails.append("引擎挂掉后 deep=1 无响应")
else:
    if deep_down.get("status") != "degraded":
        fails.append(f"引擎挂掉后 status 应为 degraded，实际 {deep_down.get('status')}")
    if deep_down.get("engine", {}).get("lastProbe", {}).get("ok") is not False:
        fails.append("引擎挂掉后 deep 探测仍报 ok（谎报）")
    if not deep_down.get("engine", {}).get("lastProbe", {}).get("reason"):
        fails.append("引擎挂掉后缺 reason")

light_down = curl_json(f"{SITE}/api/health")
if not light_down or light_down.get("status") not in ("ok", "degraded"):
    fails.append("引擎挂掉后轻量模式必须仍返回可用 JSON（保活用）")

print("重新拉起引擎…")
if not start_engine():
    fails.append("引擎重启失败（环境问题，非本切片缺陷，请手工确认）")
else:
    ok = False
    for _ in range(20):
        d = curl_json(f"{SITE}/api/health?deep=1", 20)
        if d and d.get("engine", {}).get("lastProbe", {}).get("ok") is True:
            ok = True
            break
        time.sleep(3)
    print("恢复后深探测 ok:", ok)
    if not ok:
        fails.append("引擎恢复后健康检查未回到 ok=true")

print()
print("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails))
sys.exit(1 if fails else 0)
```

**Step 2: 跑它，确认失败**

```bash
python scripts/verify-health.py
```

Expected: FAIL —— `轻量 /api/health 缺 engine 字段`（当前实现只返回 `{status, time}`）

**Step 3: 实现**

`server.ts` 改动一：import 加 `probeEngine`

```ts
import { runQuote, PLACES, VEHICLES, probeEngine } from './server/osrmQuote';
```

改动二：把 49-51 行的处理器替换为下面整段（探针 + 双模式）

```ts
// API: Health probe —— 如实反映依赖状态。
// 轻量模式必须永远快、永远 200（UptimeRobot 保活依赖它）；深探测只在 ?deep=1 时实时打引擎。
const PROBE_INTERVAL_MS = Number(process.env.HEALTH_PROBE_MS ?? 60_000);
const DEEP_TIMEOUT_MS = Number(process.env.HEALTH_DEEP_TIMEOUT_MS ?? 3_000);
const PROBE_TIMEOUT_MS = Number(process.env.HEALTH_PROBE_TIMEOUT_MS ?? 5_000);

type LastProbe = { ok: boolean; at: string; ms: number; reason?: string };
let lastProbe: LastProbe | null = null;

async function tickProbe(): Promise<void> {
  const r = await probeEngine(PROBE_TIMEOUT_MS);
  lastProbe = { ok: r.ok, at: new Date().toISOString(), ms: r.ms, ...(r.reason ? { reason: r.reason } : {}) };
}

void tickProbe();
setInterval(() => { void tickProbe(); }, PROBE_INTERVAL_MS).unref?.();

/** 只暴露 host，绝不带路径/查询串（避免把密钥或内部路径泄给监控页面）。 */
function engineSnapshot(): { configured: boolean; base: string | null; lastProbe: LastProbe | null } {
  const raw = (process.env.OSRM_API_BASE || '').trim();
  let host: string | null = null;
  try { host = raw ? new URL(raw).host : null; } catch { host = null; }
  return { configured: Boolean(raw), base: host, lastProbe };
}

app.get('/api/health', async (req: Request, res: Response) => {
  const snap = engineSnapshot();
  const now = new Date().toISOString();

  if (req.query.deep === '1') {
    const r = await probeEngine(DEEP_TIMEOUT_MS);
    const probe: LastProbe = { ok: r.ok, at: now, ms: r.ms, ...(r.reason ? { reason: r.reason } : {}) };
    res.json({
      status: snap.configured && !r.ok ? 'degraded' : 'ok',
      time: now,
      engine: { ...snap, lastProbe: probe },
    });
    return;
  }

  const degraded = snap.configured && snap.lastProbe !== null && !snap.lastProbe.ok;
  res.json({ status: degraded ? 'degraded' : 'ok', time: now, engine: snap });
});
```

**Step 4: 跑测试，确认通过**

```bash
npm run build && npm run lint
# 重启官网（务必核对端口已释放 + PID 变了，taskkill 会静默失败）
PID=$(netstat -ano | grep ":3300 " | grep LISTENING | awk '{print $NF}' | head -1)
powershell -NoProfile -Command "Stop-Process -Id $PID -Force -ErrorAction SilentlyContinue"; sleep 3
[ -z "$(netstat -ano | grep ':3300 ' | grep LISTENING)" ] && echo "端口已释放" || echo "仍在占用，别继续"
NODE_ENV=production PORT=3300 AGENT_CHAT_DEMO=1 OSRM_API_BASE=http://127.0.0.1:18001 OSRM_ENGINE_KEY=test-key-abc123 node dist/server.cjs &
python scripts/verify-health.py
```

Expected: `全部通过 ✅`（含杀引擎 → degraded → 自动恢复 ok=true 的全过程）

**Step 5: 提交**

```bash
git add server.ts scripts/verify-health.py
git commit -m "feat(health): /api/health 如实反映引擎状态（后台探针 + deep=1 实时探测）"
```

### T2 评审后追加要求（2026-09-25 双评审，**优先级高于上面 Step 4/5 原文**）

1. **报告字段**：`lastProbe` 首探前是 `{ok:null, at:null, ms:null}`（不是 `null`）；`at` 取探针**结束**时刻；顶层 `time` 同理。
2. **探针不得成为新的失败面**：`tickProbe()` 必须自带 `try/catch`（未捕获拒绝会**带走整个进程**，实测 exit 1）；`HEALTH_PROBE_MS` 归一 + 下限 1s，非有限/≤0 的**原始值要 `console.warn`**（否则运维永远看不出自己的值被拒）；`?deep=1` 必须**在途合并**（匿名并发不得 1:1 放大成对引擎的外打），且**不做时间缓存**（否则破坏"杀了依赖立刻 degraded"）。
3. **`verify-health.py` 的破坏性与假绿必须消掉（T2 收尾硬门槛）**：
   - 引擎密钥**必填、无默认值**；重启站点后必须加一条真实测算断言（`!= 401`）——否则密钥错时会打"全部通过"而客户测算已经 401；
   - 杀进程前**校验 CommandLine 身份**；只对**回环** base 做杀进程实验；③ 只在 base 指向 `18000` 时才杀它（否则会杀本机 3300 自己）；
   - `try/finally + atexit + SIGINT`，只恢复**原本在跑**的服务；
   - 断言**钉具体取值**（`reason == 'unreachable'`，不是"有 reason"）；
   - `PY` / `ENGINE_CWD` 可用环境变量覆盖；`package.json` 加 `verify:health`。
4. **§⑥（env 边界回归）自身退出码必须稳定为 0**：假依赖用**非 daemon** 线程 + `shutdown()`→`server_close()`→`join()`，并重载 `handle_error` 静默（实现在我本机跑出过 `Fatal Python error: _enter_buffered_busy` → **EXIT=127**，即在断言全过时脚本仍报失败）。验收方式：**连跑两次并贴出两次 `echo $?`**。
5. **命令坑**：上面 Step 4 的 `node dist/server.cjs &` 在本机（git-bash）**必挂**（只输出 `stdin is not a tty`，exit 1）——改用 PowerShell `Start-Process` 分离启动，再用 `curl` 确认端口确属该 PID。
6. **反向自证（缺一不可）**：① 用**错的**密钥跑脚本必须**快速失败**、不得打印"全部通过"；② 把 `probeEngine` 临时替换为必抛错版本 → 站点**存活**且日志出现 tick 失败 → 还原后 `git diff` 为空。
7. **已知取舍要写进文档**（不是缺陷）：因 `/health` 免鉴权 + 探测不发密钥，**密钥错时 `/health` 仍 ok** —— 「健康 ok」不等于「密钥正确」，排查必须另测真实测算；探针与业务**共用引擎 IP 限流额度**（实测失控时客户测算直接吃 429）。

### T2 第二轮复核后追加要求（2026-09-25 独立代码复核：产品侧 7 项已落地，补下列缺口）

8. **env 归一必须夹上界（产品侧，P0）**：`positiveEnvMs` 只夹下限不夹上界 → `HEALTH_PROBE_MS=4294967296`(2³²) 被 Node 定时器**静默改成 1ms** → 3 秒上千次探针（复核方 1639 次/3s、用户方 399 次/3s）且**产品侧一条告警都没有**（⚠️ 措辞更正：Node 自己会打 `TimeoutOverflowWarning: ... Timeout duration was set to 1.`，但那是运行时泛化警告，日志里**看不出是哪个 env 的哪个值**被改成了 1ms，运维照样查不出自己写错了 —— 真问题是「产品侧无告警 + 值被静默改成 1ms」，不是「没有任何警告」）；同类 `HEALTH_DEEP_TIMEOUT_MS`/`HEALTH_PROBE_TIMEOUT_MS=2³²` 会把**活引擎误报 `{ok:false, ms:13, reason:'timeout'}`**（假告警）。修法：`> 2³¹−1` → 夹到 `2147483647` + `console.warn`（文本含被拒原始值）；**两侧都改**——`server.ts` 的 `positiveEnvMs` 与 `server/osrmQuote.ts` 的 `probeEngine` 预算归一（`normalizeProbeBudget`）。
9. **`verify-health.py` 的假红/假绿面（P0/P1）**：
   - **假红：等待预算不得写死**（原 `WAIT_BUDGET_S = env or 20`）：默认配置站点间隔 60s，依赖死后要 ~60s 才 degraded → 必然假红。改为**先实测间隔**（采样两次 `lastProbe.at` 求差，必要时先等一次变化）→ `budget = max(2×interval, 5.0)`；`HEALTH_PROBE_WAIT` 保留为显式覆盖；**新验收：默认 60s 间隔的站点必须全绿**；
   - **假绿①**：`kill_port` 端口无监听时静默返回 → ④/⑤ 整段跳过却仍可打「全部通过」→ 改为 `fails.append`；
   - **假绿②**：①B 把「连不上（HTTP 0）」当通过（只判 `==401`）→ HTTP 0 与 5xx 都 fail，只接受非 401 的 2xx/4xx；
   - **挂死风险**：所有子进程调用（curl / netstat / powershell）必须带 Python 级 `timeout` + `TimeoutExpired` 记 fail（任一挂住 → 脚本永不退出 → 已被 ④ 杀掉的依赖等不到 finally/atexit 恢复）；
   - **选端口竞态**：临时站点 `free_port()`（bind(0)→close）被抢就起不来 → 起不来换端口重试 ≥2 次；
   - **断言强度**：`at` 由「`at >= time`」（把 at 写成请求时刻+1ms 也能过）改为**可控延迟假依赖（800ms）断言 `at - time >= 400ms`**；`reason` 补 `timeout` 支（黑洞依赖）+ 三种 base 写法等价；warn 由「零断言」改为断言 stderr 出现 `环境变量 <NAME>="<被拒原值>"`（含上界分支）；env 边界由单例 `'abc'` 扩为 `['abc','0','','50','4294967296']` 逐个断言。**阈值后来按实测余量修正（第三轮）**：回落/上界分支 3s ≤1 次；夹下限分支改用 **6s 窗口 + ≥3 次**（改后实测 6 次 `hits=[6,5,5,5,5,5]`，min=5 ⇒ 留 2 次余量）—— 原「3s / ≥2 次」的实测下限恰好 == 阈值（三次实测 2/3/3），余量为 0 ⇒ 机器一抖就假红。
10. **入库回归（把只在对话里成立的证据写进脚本，P1）**：① deep **单飞 vs TTL 缓存**（弱实现加 2s TTL 能全绿通过）→ 30 个真并发断言 hits 增量 ==1 且 `at` 集合大小 ==1，**紧接着立即单发断言 hits 再 +1**（成对，缺一不可）；② **tick 抛错不得带走进程** → 在 **dist 副本**注入必抛错，断言 stderr 失败日志 ≥2 条且间隔 ≥0.5×探针间隔（分得清「tick 干脆不跑了」）+ 进程存活 + `/api/health` 200 + deep 异常分支 `ms` 为**实测耗时**。
11. **杀进程身份门（P1）**：`EXPECT_CMDLINE[18001]=("server.py",)` 太弱（`python -m http.server` 不匹配，但任何同名脚本都能骗过）→ 改为**三层**：命令行含**绝对路径片段**（`deploy/osrm-engine`、`GATEWAY_CWD`，脚本自己的 `start_port` 就是这么起的）直接放行；只有**弱标识**（cwd 启动时命令行只剩 `server.py`）时必须过**端口自证**（`GET /gateway/health` 回出 `gateway: "jiuneng-osrm-gateway"` 指纹）；两者都不满足 → **拒杀并记失败**。低优：deep 异常分支 `ms` 用实测耗时、日志区分「内部异常」与「依赖不可达」（`reason` 保留 `unreachable`，不改封闭枚举）。
12. **变异自证（每条都要成对：注入 → 红，还原 → 绿）**：① deep 改 2s TTL 缓存 → ②B 红；② 去掉上界夹紧 → ⑦ 上界断言红（实测 1449~1639 次/3s 的失控探针；⚠️ 措辞更正：说「忙循环」不准确 —— 不是进程空转，而是**探针被 1ms 定时器打成千次/3s**，且**产品侧无告警**，Node 只有 `TimeoutOverflowWarning ... set to 1.` 这种看不出 env 名的运行时警告）；③ `kill_port` 无监听改回静默 → ③/④ 不再记 fail、脚本打「全部通过」= 假绿复现；④ 去掉 `normalizeProbeBudget` 的上界夹紧 → `scripts/verify-engine-probe.ts` 的**直调**用例红（活引擎被误报 timeout + 无「超过上限」告警）。
13. **环境坑（本机实测，别踩）**：Windows 的 `SO_REUSEADDR` 允许**两个网关同时 bind 18001**，杀其中一个会让另一个的 netstat 视图错乱（看起来"端口没了"实际还在服务）→ 反复重启网关会攒出重复监听者，杀进程实验会变得不可复现。验收前先确认 18001 **只有一个** LISTENING PID。另：**`dist/*.cjs` 里 grep 中文一律为 0**（esbuild 默认 `charset=ascii`，中文被转义成**大写**十六进制 `\u8D85...`），所以"改动是否进了构建产物"不能靠 `grep 中文`判断 —— 要么 grep ASCII 常量（如 `2147483647` / `MAX_TIMER_MS` / 函数名），要么直接看**行为断言**（实测已在这里踩过一次假阴性）。

---

### T2 第三轮复核后追加要求（2026-09-25 第三方只读复核：4 条 fail_item 全真闭环，另修下列假红/挂死/换进程面）

14. **`HEALTH_PROBE_WAIT` 必须拒非有限值（P0，挂死面）**：原实现 `max(float(x), 0.0)` 不滤 `nan/inf` → `deadline = time.time() + nan` → `time.time() >= deadline` **恒为 False** → 在 ④「依赖已杀、站点又始终不降级」这条**失败路径**上脚本永不退出，而恢复逻辑只在 `atexit`/Ctrl-C 里跑 ⇒ 被杀的依赖永久留在杀掉状态（实测：真脚本 + `HEALTH_PROBE_WAIT=nan` / `inf`，45s 内不退出，只能硬杀）。另两张脸同样没有一句报错：非数字被**静默**换成写死的 `20.0`（正是本轮从 `measure_wait_budget` 删掉的值）、`0`/`-5` 被静默夹成 `0.0`（每个等待预算立刻到期 ⇒ ④⑤ 必然假红）。修法：**只接受有限正值**；非法值 → 记 fail + 明确报错 + **立刻以 2 退出**（在任何破坏性操作之前，退出码 2 表示「参数/环境非法」而非断言失败）；并且所有 deadline 计算前再过一道有限性兜底（`finite_budget`，将来新增入口也漏不进来）。
15. **⑦ 夹下限余量（P1，假红源）**：原断言是「3s 窗口 `hits >= 2`」，而夹下限后的 `interval=1000ms` → 余量恰好一个 tick。实测（脚本自己的 `start_temp_site_ready` + 计数假依赖，10 次）3s 窗口 `hits = [2,2,2,2,2,2,2,3,2,2]`（**min == 阈值**），节奏实测是「每 ~2.0s 命中 2 次」（8s 窗口 7~8 次）。修法：夹下限分支改 **6s 窗口 + 下限 3 次 + 上限 14 次**；改后同法实测 6 次 `hits = [6,5,5,5,5,5]`（min=5）⇒ 下限 3 留出 **2 次余量**（一整个探测节奏）。分辨力不变：回落到 60s 时 6s 窗口内是 **0** 次（0 < 3，红），回绕成 1ms 时是上千次（> 14，红）。
16. **从副本跑会替换线上网关（P1，换进程面）**：`start_port` 用脚本自身 `ROOT` 重启依赖 ⇒ 从副本跑就是拿副本的 `deploy/osrm-engine/server.py` 顶替线上 18001（实测留下孤儿副本、真网关被替），而输出里**没有任何提示**；命令行缺绝对路径时更是核不出身份。修法：① `start_port` 用 `os.path.abspath` 强制**绝对路径**并打印新进程 `CommandLine`；② `ROOT` 下没有 `.git`（= 跑副本）时在**动任何东西之前**大声告警，点名「我在用副本路径 X 重启线上端口 Y」；③ 报告如实说明 **「恢复」= 新进程**（收尾打印原/现进程 CommandLine 对比，`restore_all` 也一并说明）。
17. **`normalizeProbeBudget` 上界分支零覆盖（P2）**：仓库内唯一调用方 `server.ts` 传的是 `positiveEnvMs` 归一后的值 ⇒ `osrmQuote.ts` 里 `> 2³¹−1` 那一支在仓库内**不可达**（env 边界由 `server.ts` 自己夹）。修法：① `scripts/verify-engine-probe.ts` 增**直调**用例（`probeEngine(2³²)` → 断言活引擎仍 `ok=true` + `console.warn` 含被拒原值与「超过上限」），并配一条**反向用例**（合法 5000ms 不得有任何告警，否则「有 warn 就算过」会被别处的告警蒙混）；② 删掉 `osrmQuote.ts` 里「调用方常写 `Number(process.env.OSRM_PROBE_TIMEOUT_MS)`」这句 —— 那个 env 在仓库里**根本不存在**，注释改为说明「该分支靠直调用例覆盖」，免得后人以为有 env 入口。
18. **假依赖端口必须避开动态端口范围（P2，假红源）**：本机 `netsh int ipv4 show dynamicport tcp` = 起始 1024、13977 个（→ **1024–15000**），而临时站点（node）的**出站连接也从这一段取源端口**。从副本跑时实测撞过一次：假依赖 bind 到 **4190**，站点侧对它一律 ECONNREFUSED → `reason='unreachable'`，并且 ⑦ 的「预算写 2³² 时活依赖被误报成不可达」跟着红两条 —— 看起来像产品缺陷，其实只是本机端口撞车。修法：`start_fake_dep` / `start_blackhole_dep` 改用 `dynamic_safe_port()`（在 16000–32000 里取一个**此刻真能 bind** 的端口，并排除 18000/18001/18123 等长驻端口）；一个都拿不到时记 fail 并退回 OS 自选（而不是静默）。

#### 运维配方（本机长驻三服务：站点侧真正依赖的 env 一个都不能少）

站点侧**不止** `OSRM_API_BASE`。缺下面任何一个，症状都与「配置无关的地方」长得一样，运维会查错方向：

| 服务 | env | 缺了会怎样（实测/代码依据） |
|---|---|---|
| 引擎 `127.0.0.1:18000` | — | AIOSRM++ 裸引擎（`run_server.py`），不带密钥 |
| 网关 `127.0.0.1:18001` | `ENGINE_API_KEY` | 未配置**拒绝启动**（`deploy/osrm-engine/server.py` 自己的硬约束） |
| 站点 `127.0.0.1:3300` | `OSRM_API_BASE=http://127.0.0.1:18001` | `engine.configured=false`、`lastProbe.reason='not_configured'` |
| 站点 `127.0.0.1:3300` | **`OSRM_ENGINE_KEY=<与 ENGINE_API_KEY 同值>`** | `/health` 照样 200 + `ok=true`，而**客户侧测算全 401**（假绿，规格 §4.1 的已知取舍）→ 验收脚本的 `①B 密钥门禁` 就是钉这条的 |
| 站点 `127.0.0.1:3300` | **`HEALTH_PROBE_MS=5000`** | 不设 = 后台探针间隔 **60s** ⇒ 依赖死后轻量档要 ~60s 才 degraded。脚本能实测间隔自适应（不会假红），但**本机配方统一设 5000**（实测 `lastProbe.at` 间隔 = 5.002s），验证才快且可预期 |
| 站点 `127.0.0.1:3300` | `HEALTH_DEEP_TIMEOUT_MS`(3000) / `HEALTH_PROBE_TIMEOUT_MS`(5000) | 有默认值；**写 2³² 会被夹到 2³¹−1 并告警**（写超上限会把活引擎误报 timeout） |
| 验收脚本 | `ENGINE_API_KEY`（或 `OSRM_ENGINE_KEY`） | **必填**，无默认值：不给就快速失败（给默认密钥会让「密钥不一致」变假绿） |
| 验收脚本 | `HEALTH_PROBE_WAIT` | 显式覆盖等待预算；**只接受有限正值**（nan/inf/0/负数/非数字 → 记 fail + 退出 2，见第 14 条） |
| 验收脚本 | `HEALTH_PROBE_MEASURE_CAP`(75) / `ENGINE_PY` / `ENGINE_CWD` | 采样上限 / 本机引擎运行时路径覆盖 |

```bash
# 1) 引擎 18000（PATH 里的 python 没 fastapi，必须用 AIOSRM++ 的 venv）
powershell -NoProfile -Command "Start-Process -FilePath 'D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe' -ArgumentList 'run_server.py','--port','18000' -WorkingDirectory 'D:/01_业务/立三方/AIOSRM++/backend' -WindowStyle Hidden"
# 2) 网关 18001（绝对路径启动 → CommandLine 可直接核身份）
powershell -NoProfile -Command "\$env:PORT='18001'; \$env:ENGINE_API_KEY='test-key-abc123'; Start-Process -FilePath 'D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe' -ArgumentList '<仓库绝对路径>/deploy/osrm-engine/server.py' -WindowStyle Hidden"
# 3) 站点 3300（HEALTH_PROBE_MS 与 OSRM_ENGINE_KEY 见上表）
powershell -NoProfile -Command "\$env:NODE_ENV='production'; \$env:PORT='3300'; \$env:OSRM_API_BASE='http://127.0.0.1:18001'; \$env:OSRM_ENGINE_KEY='test-key-abc123'; \$env:HEALTH_PROBE_MS='5000'; Start-Process -FilePath 'node' -ArgumentList 'dist/server.cjs' -WorkingDirectory '<仓库绝对路径>' -WindowStyle Hidden"
# 核验：每个端口**只有 1 行** LISTENING；再跑验收（约 60s，脚本自己会杀/恢复网关）
netstat -ano | grep LISTENING | grep -cE ':(18000|18001|3300) '
ENGINE_API_KEY=test-key-abc123 python scripts/verify-health.py
```

⚠️ 两个真踩过的坑：
- **命令行里必须是绝对路径**。以 cwd 方式启动（`python server.py`）时 Windows 的 `CommandLine` 里只剩 `server.py`，身份核验只能退到「弱标识 + 端口自证」；`start_port` 现在用 `abspath` 强制绝对路径，就是为了让 `CommandLine` 能直接认人。
- **别从副本跑验收脚本**：④⑤ 会**杀掉线上网关、再用脚本自己 ROOT 下的路径拉起来** —— 从副本跑等于用副本的 `deploy/osrm-engine/server.py` 顶替线上 18001，而「恢复」只是**新进程**（PID/命令行/进程内状态都变），不是还原原进程。脚本现在会在动任何东西之前把这件事打出来（`IS_REPO_ROOT` + 副本路径点名），但别拿它做这种实验。

---

## Task 3: `npm run stack` —— 三服务守护（本机崩溃自恢复）

**Files:**
- Create: `scripts/serve-stack.mjs`
- Modify: `package.json`（scripts 加 `"stack": "node scripts/serve-stack.mjs"`）
- Create: `scripts/verify-stack.py`
- Test: `scripts/verify-stack.py`

**Step 1: 先写会失败的验收脚本**

创建 `scripts/verify-stack.py`：

```python
"""守护验证：故意杀引擎 → 应自动重启 → 测算接口重新可用。用法：python scripts/verify-stack.py"""
import json, subprocess, sys, time

ROOT = "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4"
fails = []


def http(url, timeout=20):
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", str(timeout), "-w", "%{http_code}", url],
                       capture_output=True)
    return r.stdout.decode().strip()


def pid_on(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            return line.split()[-1]
    return None


print("启动守护（后台）…")
proc = subprocess.Popen(["node", "scripts/serve-stack.mjs"], cwd=ROOT,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        if all(http(f"http://127.0.0.1:{p}/health", 5) == "200" for p in (18000, 18001, 3300)):
            break
        time.sleep(2)
    else:
        print("守护启动后 120s 内三服务未全部就绪")
        sys.exit(1)

    before = pid_on(18000)
    print("引擎 PID(前):", before)
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {before} -Force"],
                   capture_output=True)

    recovered = False
    for _ in range(30):                      # 最多等 60s
        time.sleep(2)
        after = pid_on(18000)
        if after and after != before and http("http://127.0.0.1:18000/health", 5) == "200":
            recovered = True
            print("引擎 PID(后):", after)
            break
    if not recovered:
        fails.append("杀引擎后 60s 内未自动恢复")
    else:
        body = subprocess.run(["curl", "-s", "-m", "60", "-X", "POST", "http://127.0.0.1:3300/api/osrm-quote",
                               "-H", "Content-Type: application/json",
                               "--data-binary", "@-"],
                              input=json.dumps({"origin": "nanning", "destination": "hanoi", "border": "youyiguan",
                                                "weight_kg": 20000, "volume_m3": 60, "mode": "consolidated"}).encode(),
                              capture_output=True).stdout.decode("utf-8", "replace")
        print("恢复后测算:", body[:160])
        try:
            if json.loads(body).get("ok") is not True:
                fails.append(f"恢复后测算未成功：{body[:120]}")
        except Exception:
            fails.append("恢复后测算返回非 JSON")
finally:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { $_.CommandLine -like '*serve-stack*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)
    proc.terminate()

print()
print("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails))
sys.exit(1 if fails else 0)
```

> 注：把上面 `raise SystemExit_fail` 一行删掉，改为 `sys.exit(1)`（脚本首轮跑不通是**预期**：`scripts/serve-stack.mjs` 还不存在）。

**Step 2: 跑它，确认失败**

```bash
python scripts/verify-stack.py
```

Expected: FAIL —— 守护脚本不存在，三服务未就绪

**Step 3: 实现 `scripts/serve-stack.mjs`**

```js
#!/usr/bin/env node
/**
 * 本机三服务守护：引擎(18000) + 网关(18001) + 官网(3300)。
 * 任一进程退出即带退避重启（1/2/4/8/16s，每个服务最多 5 次），超过则全部停掉并明确报错 ——
 * 不无限重启掩盖真问题（2026-09-25 引擎在 Windows 上 2 次自行崩溃，需要这个兜底）。
 * 云上不用它：Render 平台自己有崩溃重启，避免两套重启打架。
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const PY = 'D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe';
const AIOSRM = 'D:/01_业务/立三方/AIOSRM++/backend';
const LOG_DIR = process.env.STACK_LOG_DIR || path.join(ROOT, '.stack-logs');
const MAX_RESTARTS = Number(process.env.STACK_MAX_RESTARTS ?? 5);
const BACKOFF = [1000, 2000, 4000, 8000, 16000];

const SERVICES = [
  { name: 'engine', port: 18000, cmd: PY, args: ['run_server.py', '--port', '18000'], cwd: AIOSRM, env: {} },
  {
    name: 'gateway', port: 18001, cmd: PY, args: ['server.py'],
    cwd: path.join(ROOT, 'deploy', 'osrm-engine'),
    env: { PORT: '18001', ENGINE_API_KEY: process.env.ENGINE_API_KEY || 'test-key-abc123' },
  },
  {
    name: 'site', port: 3300, cmd: process.execPath, args: [path.join(ROOT, 'dist', 'server.cjs')],
    cwd: ROOT,
    env: {
      NODE_ENV: 'production', PORT: '3300',
      AGENT_CHAT_DEMO: process.env.AGENT_CHAT_DEMO ?? '1',
      OSRM_API_BASE: process.env.OSRM_API_BASE ?? 'http://127.0.0.1:18001',
      OSRM_ENGINE_KEY: process.env.OSRM_ENGINE_KEY || 'test-key-abc123',
    },
  },
];

const portFree = (port) => new Promise((resolve) => {
  const srv = net.createServer();
  srv.once('error', () => resolve(false));
  srv.once('listening', () => srv.close(() => resolve(true)));
  srv.listen(port, '0.0.0.0');
});

fs.mkdirSync(LOG_DIR, { recursive: true });
const children = new Map();
let shuttingDown = false;
let restarts = 0;

function stopAll(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.error(`[stack] 停止：${reason}`);
  for (const child of children.values()) {
    try { child.kill(); } catch { /* 已退出 */ }
  }
  process.exit(1);
}

async function startOne(svc, attempt) {
  const log = fs.createWriteStream(path.join(LOG_DIR, `${svc.name}.log`), { flags: 'a' });
  log.write(`\n[stack] ${new Date().toISOString()} 启动 ${svc.name}（第 ${attempt} 次）\n`);
  const child = spawn(svc.cmd, svc.args, {
    cwd: svc.cwd,
    env: { ...process.env, ...svc.env },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  children.set(svc.name, child);
  console.log(`[stack] ${svc.name} 已启动 pid=${child.pid}，日志 ${path.join(LOG_DIR, svc.name + '.log')}`);

  child.on('exit', (code, signal) => {
    children.delete(svc.name);
    if (shuttingDown) return;
    restarts += 1;
    if (restarts > MAX_RESTARTS) {
      stopAll(`${svc.name} 重启超过 ${MAX_RESTARTS} 次（末次 code=${code} signal=${signal}），请查看 ${svc.name}.log 尾部`);
      return;
    }
    const wait = BACKOFF[Math.min(restarts - 1, BACKOFF.length - 1)];
    console.error(`[stack] ${svc.name} 退出（code=${code}），${wait}ms 后重启`);
    setTimeout(() => { void startOne(svc, attempt + 1); }, wait);
  });
}

// 端口前置检查：占用即明确报出并退出（taskkill 静默失败曾让所有验证跑在旧构建上）
for (const svc of SERVICES) {
  if (!(await portFree(svc.port))) {
    console.error(`[stack] 端口 ${svc.port} 已被占用（${svc.name}），先清掉再启动：`);
    console.error(`  netstat -ano | grep ":${svc.port} " | grep LISTENING   # 取 PID，再 powershell Stop-Process -Id <pid> -Force`);
    process.exit(1);
  }
}

if (!fs.existsSync(path.join(ROOT, 'dist', 'server.cjs'))) {
  console.error('[stack] 缺少 dist/server.cjs，先跑 npm run build');
  process.exit(1);
}

for (const svc of SERVICES) await startOne(svc, 1);
console.log(`[stack] 全部启动（最多每个服务重启 ${MAX_RESTARTS} 次）。Ctrl+C 停止。`);

process.on('SIGINT', () => stopAll('收到 Ctrl+C'));
```

`package.json` scripts 增加一行：

```json
    "stack": "node scripts/serve-stack.mjs",
```

**Step 4: 跑测试，确认通过**

```bash
npm run stack   # 另开一个终端观察；或直接跑下面的脚本
python scripts/verify-stack.py
```

Expected: `全部通过 ✅`（杀引擎 → 60s 内自动恢复 → 测算接口重新返回 ok=true）

**Step 5: 提交**

```bash
git add scripts/serve-stack.mjs scripts/verify-stack.py package.json
git commit -m "feat(stack): 本机三服务守护（退避重启 + 端口前置检查）"
```

---

## Task 4: `npm run engine:audit` —— 引擎参数体检导出

**Files:**
- Create: `scripts/engine-audit.mjs`
- Modify: `package.json`（加 `"engine:audit": "node scripts/engine-audit.mjs"`）
- Create: `scripts/verify-engine-audit.py`
- Test: `scripts/verify-engine-audit.py`

**Step 1: 先写会失败的验收脚本**

创建 `scripts/verify-engine-audit.py`：

```python
"""体检脚本验收：产出两表 + 缺项即失败。用法：python scripts/verify-engine-audit.py"""
import glob, json, os, subprocess, sys

ROOT = "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4"
fails = []
env = {**os.environ, "OSRM_API_BASE": "http://127.0.0.1:18000"}

print("=== 正常路径 ===")
r = subprocess.run(["node", "scripts/engine-audit.mjs"], cwd=ROOT, env=env, capture_output=True, timeout=900)
out = r.stdout.decode("utf-8", "replace")
print(out[-1200:])
if r.returncode != 0:
    fails.append(f"体检脚本正常路径应退出 0，实际 {r.returncode}")

md = sorted(glob.glob(os.path.join(ROOT, "docs/engine-audit/*-engine-audit.md")))
js = sorted(glob.glob(os.path.join(ROOT, "docs/engine-audit/engine-params.json")))
if not md:
    fails.append("未产出 *-engine-audit.md")
else:
    text = open(md[-1], encoding="utf-8").read()
    for section in ["费率", "汇率", "油价", "口岸费用", "税率口径对照"]:
        if section not in text:
            fails.append(f"体检表缺区块：{section}")
    if "source" not in text:
        fails.append("体检表未标注 source（无法判断数据真伪）")
if not js:
    fails.append("未产出 engine-params.json")

print("\n=== 缺项即失败路径（指向死端口）===")
bad_env = {**os.environ, "OSRM_API_BASE": "http://127.0.0.1:19999"}
r2 = subprocess.run(["node", "scripts/engine-audit.mjs"], cwd=ROOT, env=bad_env, capture_output=True, timeout=300)
print(r2.stdout.decode("utf-8", "replace")[-400:])
if r2.returncode == 0:
    fails.append("引擎不可达时体检脚本必须非 0 退出（不能出一张半空的表当成功）")

print()
print("全部通过 ✅" if not fails else "存在问题：\n  - " + "\n  - ".join(fails))
sys.exit(1 if fails else 0)
```

**Step 2: 跑它，确认失败**

```bash
python scripts/verify-engine-audit.py
```

Expected: FAIL —— `engine-audit.mjs` 不存在（`Cannot find module`）

**Step 3: 实现 `scripts/engine-audit.mjs`**

```js
#!/usr/bin/env node
/**
 * 引擎参数体检：只读拉取 → 出两张产物
 *   1) docs/engine-audit/<YYYY-MM-DD>-engine-audit.md  给业务方核对（每项带 source/updated）
 *   2) docs/engine-audit/engine-params.json            快照，便于下次 diff 发现参数漂移
 * 只读：绝不调用会改状态的端点（*/apply、*/fit、*/import、*/save、*/refresh、*/rollback、
 * batch/submit、quote/export、vehicles|templates 的写方法），也不调用花外部额度的 /api/v1/ai/*。
 * 引擎自带 IP 限流（实测 429），请求间隔 ≥1.6s 并对 429 退避重试。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const OUT_DIR = path.join(ROOT, 'docs', 'engine-audit');
const raw = (process.env.OSRM_API_BASE || '').trim().replace(/\/+$/, '');
const BASE = raw ? (/\/api\/v1$/.test(raw) ? raw : `${raw}/api/v1`) : '';
const SPACING_MS = 1600;

if (!BASE) {
  console.error('[audit] 缺 OSRM_API_BASE，无法体检');
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(url, { retries = 3 } = {}) {
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(url, { headers: { 'User-Agent': 'jiuneng-engine-audit' } });
      if (res.status === 429 && attempt < retries) {
        const wait = 2000 * (attempt + 1);
        console.warn(`[audit] 429 限流，${wait}ms 后重试 ${url}`);
        await sleep(wait);
        continue;
      }
      if (!res.ok) return { ok: false, status: res.status };
      return { ok: true, status: res.status, data: await res.json() };
    } catch (error) {
      if (attempt === retries) return { ok: false, status: 0, error: String(error?.message || error) };
      await sleep(800);
    }
  }
  return { ok: false, status: 0 };
}

const SECTIONS = [
  { key: 'rates_current', title: '费率主表（34 车型基准价）', path: '/rates/current', need: ['price_factor', 'models'] },
  { key: 'rates_samples', title: '费率样本（未校准时条数为 0）', path: '/rates/samples', need: ['stats'] },
  { key: 'rates_versions', title: '费率版本', path: '/rates/versions', need: ['versions'] },
  { key: 'exchange', title: '汇率', path: '/reference/exchange-rate', need: ['vnd_per_rmb', 'source'] },
  { key: 'fuel', title: '油价', path: '/reference/fuel-price', need: ['price_vnd', 'source'] },
  { key: 'border_reference', title: '口岸费用参数表', path: '/border/reference-fees', need: ['china_side'] },
  { key: 'border_cn', title: '中国端费用', path: '/border/china-side', need: ['items', 'subtotal'] },
  { key: 'border_vn', title: '越南端费用', path: '/border/vietnam-side', need: ['items', 'subtotal'] },
  { key: 'cargo_types', title: '货型系数', path: '/reference/cargo-types', need: [] },
  { key: 'cargo_estimates', title: '进出口费用估算', path: '/reference/cargo-estimates', need: [] },
  { key: 'vehicles', title: '车型库（role=internal，不下发客户）', path: '/vehicles', need: ['models'] },
];

const HS_SAMPLE = '730890';

const collected = {};
const problems = [];

for (const section of SECTIONS) {
  const res = await get(`${BASE}${section.path}`);
  if (!res.ok) {
    problems.push(`${section.title} (${section.path}) 拉取失败：status=${res.status}`);
  } else {
    for (const field of section.need) {
      if (!(field in res.data)) problems.push(`${section.title} 缺关键字段 ${field}`);
    }
    collected[section.key] = res.data;
  }
  await sleep(SPACING_MS);
}

// 税率口径对照：同一 HS 两种口径并列
const lookup = await get(`${BASE}/border/hs-lookup?hs_code=${HS_SAMPLE}`);
await sleep(SPACING_MS);
const tax = await get(`${BASE}/border/import-tax?cargo_value_rmb=500000&hs_code=${HS_SAMPLE}`);
await sleep(SPACING_MS);

// 取上次快照做 diff
const snapshotPath = path.join(OUT_DIR, 'engine-params.json');
let previous = null;
if (fs.existsSync(snapshotPath)) {
  try { previous = JSON.parse(fs.readFileSync(snapshotPath, 'utf8')); } catch { previous = null; }
}

const changes = [];
if (previous) {
  const flat = (obj, prefix = '') => Object.entries(obj || {}).reduce((acc, [k, v]) => {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) return { ...acc, ...flat(v, key) };
    return { ...acc, [key]: v };
  }, {});
  const a = flat(previous.sections);
  const b = flat(collected);
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    if (JSON.stringify(a[key]) !== JSON.stringify(b[key])) {
      changes.push(`- \`${key}\`：${JSON.stringify(a[key])} → ${JSON.stringify(b[key])}`);
    }
  }
}

// 生成 md
const today = new Date().toISOString().slice(0, 10);
fs.mkdirSync(OUT_DIR, { recursive: true });
const mdPath = path.join(OUT_DIR, `${today}-engine-audit.md`);
const row = (label, value) => `| ${label} | ${typeof value === 'object' ? '`' + JSON.stringify(value) + '`' : value} |`;

const md = [
  `# 引擎参数体检（${today}）`,
  '',
  `- 引擎地址：\`${new URL(BASE).host}\``,
  `- 用途：交给业务方核对哪些参数是真实数据、哪些需要校准（A4 输入）`,
  '',
  '## 关键数据状态',
  '',
  '| 项 | 值 |',
  '|---|---|',
  row('价格系数', collected.rates_current?.price_factor ?? '（拉取失败）'),
  row('费率样本条数', collected.rates_samples?.stats?.total ?? '（拉取失败）'),
  row('费率版本数', Array.isArray(collected.rates_versions?.versions) ? collected.rates_versions.versions.length : '（拉取失败）'),
  row('汇率', collected.exchange ? { vnd_per_rmb: collected.exchange.vnd_per_rmb, source: collected.exchange.source, updated: collected.exchange.updated } : '（拉取失败）'),
  row('油价', collected.fuel ? { price_vnd: collected.fuel.price_vnd, source: collected.fuel.source } : '（拉取失败）'),
  row('车型数', collected.vehicles?.count ?? '（拉取失败）'),
  '',
  '## 口岸费用',
  '',
  `- 中国端：\`${JSON.stringify(collected.border_cn?.items ?? {})}\`（小计 ${collected.border_cn?.subtotal ?? '?'}）`,
  `- 越南端：\`${JSON.stringify(collected.border_vn?.items ?? {})}\`（小计 ${collected.border_vn?.subtotal ?? '?'}）`,
  `- 参数表描述：${collected.border_reference?._description ?? '（拉取失败）'}（更新 ${collected.border_reference?._updated ?? '?'}）`,
  '',
  '## 货型系数',
  '',
  '```json',
  JSON.stringify(collected.cargo_types ?? {}, null, 2),
  '```',
  '',
  '## 进出口费用估算',
  '',
  '```json',
  JSON.stringify(collected.cargo_estimates ?? {}, null, 2),
  '```',
  '',
  `## 税率口径对照（HS ${HS_SAMPLE}）`,
  '',
  '| 口径 | 结果 | 来源 |',
  '|---|---|---|',
  `| hs-lookup（优惠/协定口径） | ${lookup.ok ? JSON.stringify({ rate: lookup.data.import_duty_rate, vat: lookup.data.vat_rate, desc: lookup.data.desc_en }) : '拉取失败'} | ${lookup.ok ? lookup.data.duty_source ?? '?' : '?'} |`,
  `| import-tax（含税测算） | ${tax.ok ? JSON.stringify({ duty_rate: tax.data.duty_rate, duty_rmb: tax.data.import_duty_rmb, vat_rmb: tax.data.vat_rmb }) : '拉取失败'} | ${tax.ok ? tax.data.duty_source ?? '?' : '?'} |`,
  '',
  '> **要业务方决定**：对客展示用哪个口径（两者不一致时不得同时展示）。',
  '',
  '## 与上次快照的差异',
  '',
  changes.length ? changes.join('\n') : '（无差异或首次体检）',
  '',
  '## 拉取问题',
  '',
  problems.length ? problems.map((p) => `- ${p}`).join('\n') : '（无）',
  '',
].join('\n');

fs.writeFileSync(mdPath, md, 'utf8');
fs.writeFileSync(snapshotPath, JSON.stringify({ at: new Date().toISOString(), sections: collected }, null, 2), 'utf8');

console.log(`[audit] 已写出 ${path.relative(ROOT, mdPath)} 与 ${path.relative(ROOT, snapshotPath)}`);
if (changes.length) console.log(`[audit] 参数变更 ${changes.length} 项：\n${changes.join('\n')}`);
if (problems.length) {
  console.error(`[audit] ${problems.length} 个问题（见表）：\n${problems.map((p) => '  - ' + p).join('\n')}`);
  process.exit(1);
}
console.log('[audit] 全部关键字段齐备 ✅');
```

`package.json` scripts 增加一行：

```json
    "engine:audit": "node scripts/engine-audit.mjs",
```

**Step 4: 跑测试，确认通过**

```bash
python scripts/verify-engine-audit.py
```

Expected: `全部通过 ✅`（含"死端口必须非 0 退出"的负向断言）

**Step 5: 提交**

```bash
git add scripts/engine-audit.mjs scripts/verify-engine-audit.py package.json
git commit -m "feat(audit): 引擎参数体检导出（只读、带 source、缺项即失败、快照 diff）"
```

---

## Task 5: 云上实跑对比（**前置：业务方先填 Render 环境变量**）

**Files:**
- Modify: `docs/engine-audit/<today>-engine-audit.md`（追加对比章节）

**Step 1: 确认前置是否完成（未完成就停在这里，不许编数据）**

```bash
curl -s -m 90 https://jiuneng-osrm-engine.onrender.com/health   # 期望 {"status":"ok"}（首次可能等 15–30s 冷启动）
curl -s -m 40 https://jiuneng-website.onrender.com/api/health   # 期望 status=ok 且 engine.configured=true
```

**Step 2: 同一条线路两侧复算**

```bash
# 本机
curl -s -X POST http://127.0.0.1:3300/api/osrm-quote -H "Content-Type: application/json" \
  -d '{"origin":"nanning","destination":"hanoi","border":"youyiguan","weight_kg":20000,"volume_m3":60,"mode":"consolidated"}'
# 生产
curl -s -X POST https://jiuneng-website.onrender.com/api/osrm-quote -H "Content-Type: application/json" \
  -d '{"origin":"nanning","destination":"hanoi","border":"youyiguan","weight_kg":20000,"volume_m3":60,"mode":"consolidated"}'
```

Expected: 两次都 `ok:true`；逐项对比 `distance_km` / `driving_h` / `vehicle_count` / `price_min_vnd` / `price_max_vnd` / `profile_honored`

**Step 3: 把对比写进体检文档**（差异必须能解释：汇率缓存时间、路网数据版本、参数是否同步）

**Step 4: 提交**

```bash
git add docs/engine-audit/
git commit -m "docs(audit): 记录生产 vs 本机同线路复算对比"
```

---

## Task 6: 文档增补 + 交表给业务方（A4 输入）

**Files:**
- Modify: `DEVELOPMENT.md`（新增小节：体检脚本 / 守护用法 / 健康检查字段）

**Step 1: 增补 DEVELOPMENT.md**（三块：`npm run engine:audit`、`npm run stack`、`/api/health` 两种模式与字段含义；并写明"轻量模式永远 200 用于保活，深探测用于排查"）

**Step 2: 交表**：把 `docs/engine-audit/<today>-engine-audit.md` 的**完整可点击路径**发给业务方，逐项说明哪些是"手动默认值/本机缓存"（油价 `manual_default`、汇率 `file_cache`、费率样本 0 条、`price_factor` inactive），请其标注需校准项

**Step 3: 回归复跑（确认本切片没弄坏既有能力）**

```bash
python scripts/probe-quote-api.py        # 区间算法 + 内部字段零泄漏，应全绿
python scripts/verify-agent-page.py --url http://127.0.0.1:3300/ai --widths 390 1440   # 退出码 0
```

**Step 4: 提交**

```bash
git add DEVELOPMENT.md
git commit -m "docs: 引擎体检/守护/健康检查用法增补"
```

---

## 完成定义（A 切片）

1. ✅ **已完成（2026-09-25）** `npx tsx scripts/verify-engine-probe.ts` → 三分支正确；已补上界直调用例 + 反向用例（`8d47ce3`），变异自证：去掉夹紧 → 红（活引擎被误报 timeout），还原 → 绿。
2. ✅ **已完成（2026-09-25）** `python scripts/verify-health.py` → 全绿（含杀引擎 → degraded → 自动恢复；含默认 60s 间隔站点全绿）。**三重审查闭环**：T2 双评审（规格符合 PASS + 代码质量 REQUEST_CHANGES）→ 修复子 agent → 助手亲跑 → 只读复核子 agent **REQUEST_CHANGES**（4 条 fail_item + 9 条新发现）→ 修复子 agent（`096a3cb`/`c243e6e`/`98b8431`）→ 助手亲跑 + 独立复现 + 只读复核子 agent **APPROVE**（4 条 fail_item 全部真闭环）→ D 组非阻塞项修复（`8d47ce3`）。提交历史：`2f49858` `f250f40` `096a3cb` `c243e6e` `98b8431` `8d47ce3`。
3. ✅ **已完成（2026-09-26）** `python scripts/verify-stack.py` → 全绿（含杀引擎 → 60s 内自恢复 → 测算可用）。助手亲跑 `EXIT=0`（107s，六段全绿：②端口前置检查报出占用 PID 并非 0 退出 / ③按身份清场 / ④三服务就绪且父进程=守护 / ⑤A 杀引擎 15.6s 自恢复且测算 ok / ⑤B 杀网关「先坏后好」/ ⑥`STACK_MAX_RESTARTS=1` 超限全停 + 非 0 退出 / ⑦收尾恢复）。子 agent 两组变异自证（去自动重启 → 红；超限停机判据失效 → 红）。提交 `7942439`。
4. ✅ **已完成（2026-09-26）** `python scripts/verify-engine-audit.py` → 全绿（含死端口必须非 0 退出）。助手亲跑 `EXIT=0`（52s；死端口 19999 → exit 3 + 「引擎不在，体检无法进行」+ **两份产物字节级未变**；缺 `OSRM_API_BASE` → exit 2 拒绝猜地址）。子 agent 两组变异自证（不可达静默 continue → 红；`tax_comparison.conflict` 写死 false → 红）。产物 `docs/engine-audit/` 含内部成本参数 → **已进 `.gitignore`，绝不入库**（public 仓库）。提交 `070ff2f`。

**T4 附带产出（诊断，不是猜测）**：悬了很久的「税率口径不一致」根因已定位在引擎侧 —— `backend/app/services/border_costs.py:501` 写的是 `tariff.import_duty_rate or _FIXED_FEES[...]["import_duty_fallback_pct"]`，**ACFTA 合法的 `0.0` 被 falsy 判假 → 静默回落 5% 兜底**；而同文件 `:243` 用的是正确的 `... if tariff else ...`。两侧都自称 `duty_source=atiga`。⇒ 这不是「两种业务口径」，是**引擎的 falsy-zero 缺陷**，应反馈 AIOSRM++ 侧修（本轮不改引擎，越界）。
5. ⏸ **前置未完成，未执行（2026-09-26）**：生产侧两处硬阻塞 —— ① 引擎 Render 服务**尚未创建**（`jiuneng-osrm-engine.onrender.com` → 404 + `x-render-routing: no-server`）→ 云上官网必然测算不可用；② `site.jiuneng.space` **DNS 无记录**（权威 NS 返回 NXDOMAIN）。两者都需业务方在面板操作（Render 建引擎服务 + GoDaddy 加 CNAME `site` → `jiuneng-website.onrender.com`）；根域 `jiuneng.space` / `www` 指向 Vercel 上的 OSRM++ 工具，**禁动**。
6. ✅ **已完成（2026-09-26）** 无回归复跑：
   - `python scripts/probe-quote-api.py` → **EXIT=0**（4s；拼车 深圳→河内 8t/25m³ → 1028.5 km / 1 车 / 区间 9,300,000–11,300,000 VND + **内部字段零泄漏**；`unknown_origin`/`bad_weight`/`bad_vehicle` 三分支 reason 全对）。
   - `python scripts/verify-agent-page.py`（六档视口 390/768/1024/1280/1440/1920）→ **EXIT=0**：无横向溢出、`opacity:0` 内容 = 0、汉堡菜单可展开、标签切换（同时仅 1 个 active）、轮播 1/4→2/4（`translateX(0%)`→`-100%`）、hero→表单预填、表单→API **两条分支**（失败分支如实回落文案含新邮箱；成功分支拦截放行后线路结论/单证清单均渲染）。
   - 亮度扫描补跑（脚本缺 PIL 时会**静默跳过**，按「跳过≠通过」用 `uv run --with pillow` 补做）：@1440px `min=73.2`，<120 的带 `[20,21,22,30,31,32,64]`；@390px `min=97.8`，`[39,87]`。**逐带归因**（两档一致）：`brain`(4000-4600) / `#system`(6000-6600) = 深色平台截图（`system-overview.jpg` 平均亮度 **34.0**、`system-tracking.jpg` **33.3**）套在浅色窗口框里 —— AGENTS.md 已记录的既定模式（待换浅色界面截图）；`cta`(12800-13000 / 390px 17420-17700) = `.jx-cta` 的**深蓝满幅渐变**（`linear-gradient(128deg,#001030,#0040c0 62%,#0b5cd6)`）—— 与 v0.6「全站浅色骨架」相悖，但属 `/ai` 页既有设计、非本切片引入，**是否改浅色待业务方定**。无未归因的暗区。
   - 该脚本三处短板（已记录，待业务方点头再修）：① 缺 PIL 时**静默跳过**亮度扫描却仍退 0；② `--only widths` 会**静默跳过**截图/亮度段（无任何提示）；③ 亮度数字只打印、**无断言**（"算不算回归"无人判）。
7. ✅ **已完成（2026-09-26）** 体检表已交业务方（对话内给出完整路径 + 6 条待处理 + 税率不一致的**真根因**：引擎 `border_costs.py:501` 的 falsy-zero 兜底）。**A4 校准输入待业务方提供真实成交价**（费率样本 0 条 → 费率无实测支撑）。

## 明确不做（YAGNI / 边界）

- 不改引擎参数值（业务方决定）、不改 AIOSRM++ 源码
- 不新增告警通道（复用 B 切片的邮件/飞书）
- 不做 CI 门禁（后续切片）
- 不在云上跑本机守护（交给 Render 平台重启）
- 不给客户暴露任何新端点或内部字段

---

## 上线门槛（用户 2026-09-25 指令：**开发 + 检查全部完成之后**，配置到官网与服务器）

**目标只有一个：`https://site.jiuneng.space`。**
⚠️ 根域 `jiuneng.space` 与 `www.jiuneng.space` 指向 Vercel 上的 OSRM++ 报价工具，**两个都不许动**（代码里 canonical / og:url / sitemap / robots / JSON-LD 已统一指向 site 子域，勿改回）。

### 放行条件（全绿才部署）

1. 完成定义 1–7 全绿
2. T2 / T3 / T4 每个任务都过了「实现 → 审查 → 修复 → 复核」闭环（严格串行，T2/T3 都要杀引擎）
3. `npm run lint` 0 错误；`dist/` 存在且含 `index.html`
4. 本机三服务（3300 / 18001 / 18000）验完一轮全绿，且 `18001` 的 `LISTENING` 行数为 1

### 必须**用户面板**做的两件事（我做不了）

- **GoDaddy**：加 CNAME `site` → `jiuneng-website.onrender.com`
  （现状 `site.jiuneng.space` 权威 NS 返回 NXDOMAIN，DNS 无记录）
- **Render**：创建引擎服务 `jiuneng-osrm-engine`（`render.yaml` 已声明，含 `healthCheckPath: /health`）
  并在站点服务 Environment 里确认：`NODE_ENV=production`、`GEMINI_API_KEY`、`OSRM_API_BASE`、`OSRM_ENGINE_KEY`（必须与引擎的 `ENGINE_API_KEY` 一致）
  ⚠️ 站点服务的 healthCheckPath **保持默认 `/`**，**不要**指到 `/api/health`——轻量档永远 200 正是为了不让 Render 把「降级但可用」判成不健康而反复重启

### 部署进展（2026-09-26 执行）

**已完成**（助手操作，均有验证）：

| 项 | 结果 |
|---|---|
| 代码入库 | `37459a0`（/ai 页 + 新服务端 + A 切片，22 文件 +7105/−10）→ `5484781`（`deploy/osrm-engine` 引擎部署件，63 文件 +13839）；均已 push 到 `miiinniam/jiuneng-website` |
| Render 自动部署 | push 后约 **40s** 完成；`/api/health` 已呈新形态：`{"status":"ok",...,"engine":{"configured":false,"base":null,"lastProbe":{"ok":false,"reason":"not_configured"}}}` → **新代码生效且如实降级** |
| `/ai` 页上线 | 真被服务（`<title>JIUNENG logistics \| 物流 AI 数字员工</title>` + `assets/ai-1DIpN__Q.js` / `ai-CmtM1ich.css`），非 SPA 兜底 |
| 生产复跑 | `verify-agent-page.py`（390/1440）**EXIT=0**：无横向溢出、`opacity:0` 内容 0、汉堡菜单可展开、标签切换、轮播 1/4→2/4、hero→表单预填；**表单 → `/api/logistics-consult` HTTP 200 `ok=True`** ⇒ 站点服务已配 `GEMINI_API_KEY`，线上 AI 询价可用；亮度 @1440 `min=73.2 [20,21,22,64]`、@390 `min=97.8 [39,87]` |
| 引擎部署件 | 已入库并**只带已公开的 4 份数据**（`exchange_rate`/`fixed_fees`/`hs_tariff_2026`/`osrm_plus.db`）；未公开的 `price_versions`/`calibration_samples`/`demand_periods` 已进 `.gitignore` + `sync-engine.mjs` 排除表（暂存门禁验证：0 个敏感文件、0 个 `__pycache__`）。实测去掉那三份后引擎仍能起 + 真算（2243.0265 km / 77,400,453 VND，与基线逐位一致） |

**未完成（需业务方面板操作）**：

1. **Render**：Blueprint → **Sync**（或 New → Web Service，repo `miiinniam/jiuneng-website`、rootDir `deploy/osrm-engine`、runtime Python、build `pip install -r requirements.txt`、start `python server.py`、healthCheckPath `/health`）→ 创建 `jiuneng-osrm-engine`
2. **引擎服务** Environment：`ENGINE_API_KEY`＝随机串（自定，勿提交仓库）
3. **站点服务** Environment：`OSRM_API_BASE=https://jiuneng-osrm-engine.onrender.com`、`OSRM_ENGINE_KEY`＝与上面**同一个值**（不一致时客户测算 401 而 `/health` 仍绿）、`NODE_ENV=production`（healthCheckPath 保持默认 `/`，**不要**指到 `/api/health`）
4. **GoDaddy**：CNAME `site` → `jiuneng-website.onrender.com`（根域/www 禁动）
5. （建议）UptimeRobot 每 5 分钟 ping `https://site.jiuneng.space/api/health` 保活（免费层 15 分钟休眠）

**待业务方完成上述后由助手续做**：`probe-quote-api.py` 打生产域名跑真实测算 → 记录「生产 vs 本机」同线路复算对比 → 写入当日 audit 文档。

### 拿到授权后我做的（原计划原文，保留备查）

1. `git push` 触发 Render 自动部署（**不自动 push：等用户明确点头**）
2. 按序验：
   - `curl https://site.jiuneng.space/api/health` → `configured:true` + `lastProbe.ok:true`
   - `python scripts/probe-quote-api.py` 打生产域名跑**真实测算**（健康 ok ≠ 密钥正确，必须另测测算）
   - `python scripts/verify-agent-page.py` 六档视口复跑（/ai 页无回归）
3. 记录「生产 vs 本机」同线路复算对比，写入同日期 audit 文档
4. 提醒用户配 UptimeRobot 每 5 分钟 ping `/api/health` 保活（免费层 15 分钟无请求会休眠）

### 红线复述

绝不打包 `resources/company_seal.png` / `company_sign.png`；绝不暴露引擎地址、`breakdown`/成本/利润字段；对客口径仍是「初步测算，非正式报价」。
