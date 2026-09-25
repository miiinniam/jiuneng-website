#!/usr/bin/env node
/**
 * 本机三服务守护：真引擎(AIOSRM++ `run_server.py` @18000) + 窄暴露网关(`deploy/osrm-engine/server.py` @18001)
 * + 官网生产构建(`dist/server.cjs` @3300)。
 *
 * 为什么需要它：2026-09-25 引擎在 Windows 上 2 次自行崩溃（asyncio 平台缺陷，无规律），客户测算中途
 * 直接不可用，而没人知道它倒了。守护在崩溃时**自动带退避重启**，并把每次退出码 + 日志尾部留痕。
 *
 * 行为约定（都对应本轮踩过的坑）：
 *  1. **启动前端口前置检查**：三个端口任一**已有 LISTENING**（数**行数**，不是「端口在不在」——
 *     Windows 的 SO_REUSEADDR 允许同端口多监听者）→ 报出占用 PID + 命令行，以 **3** 退出，
 *     绝不在别人的进程上硬起（`taskkill` 静默失败曾让所有验证跑在旧构建上）。
 *  2. **退避重启**：1s/2s/4s/8s/16s，**每个服务各自**最多 `STACK_MAX_RESTARTS`(默认 5) 次
 *     （原实现用一个全局计数：A 服务崩 5 次会把 B 的额度也吃掉）。超限 → **停掉全部子进程**、
 *     打印「哪个服务、几次、去哪看日志」并以 **1** 退出 —— 不无限重启掩盖真问题。
 *  3. **不把引擎打爆**：健康检查只用 `GET /health`（免鉴权、不读业务端点），只在**启动就绪**期间与
 *     每 `STACK_HEALTH_MS`(默认 30s) 各一次；且**只有连接级失败**（连不上/超时）才计数，
 *     HTTP 非 2xx 只告警不判死。引擎自带 IP 限流（实测 429），高频轮询会把客户测算的额度吃光。
 *  4. **子进程一律用绝对路径 + 完整 env 启动**：事后 `CommandLine` 要能直接认出端口上是谁
 *     （以 cwd 方式启动时 Windows 的 CommandLine 里只剩 `server.py` 这种弱串，根本核不出身份）。
 *  5. **env 覆盖参数做有限性/正性校验**：非法值 → 打印明确错误并以 **2** 退出，**绝不静默回落**
 *     （`STACK_READY_WAIT_MS=nan` 会让就绪预算永不到期、脚本永不退出，这类坑已在验收脚本里踩过）。
 *  6. 云上**不用**它：Render 平台自带崩溃重启，两套重启会互相打架。
 *
 * 退出码：0 = 正常停止（Ctrl+C）；1 = 超限停机；2 = 参数/环境非法；3 = 端口被占用（前置检查）。
 * 用法：ENGINE_API_KEY=... npm run stack   （`STACK_MAX_RESTARTS`/`STACK_LOG_DIR` 等可覆盖）
 */
import { spawn, execFile } from 'node:child_process';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const ENGINE_PY = process.env.ENGINE_PY
  || 'D:/01_业务/立三方/AIOSRM++/.venv-build/Scripts/python.exe';
const ENGINE_CWD = path.resolve(process.env.ENGINE_CWD || 'D:/01_业务/立三方/AIOSRM++/backend');
const ENGINE_SCRIPT = path.resolve(ENGINE_CWD, 'run_server.py');
const GATEWAY_CWD = path.resolve(ROOT, 'deploy', 'osrm-engine');
const GATEWAY_SCRIPT = path.resolve(GATEWAY_CWD, 'server.py');
const SITE_ENTRY = path.resolve(ROOT, 'dist', 'server.cjs');

const EXIT_OK = 0;
const EXIT_LIMIT = 1;
const EXIT_CONFIG = 2;
const EXIT_PORT = 3;

class ConfigError extends Error {}

/** env 数值参数：只接受有限值且在区间内；非法 → ConfigError（调用处打印 + exit 2），**不静默回落**。 */
function numEnv(name, { fallback, min, max, integer = false }) {
  const raw = process.env[name];
  if (raw === undefined || String(raw).trim() === '') return fallback;
  const value = Number(String(raw).trim());
  if (!Number.isFinite(value)) {
    throw new ConfigError(`${name}=${JSON.stringify(raw)} 不是有限数值（nan/inf 会让定时器/等待预算失效）`);
  }
  if (integer && !Number.isInteger(value)) {
    throw new ConfigError(`${name}=${JSON.stringify(raw)} 必须是整数`);
  }
  if (value < min || value > max) {
    throw new ConfigError(`${name}=${JSON.stringify(raw)} 超出允许区间 [${min}, ${max}]`);
  }
  return value;
}

let MAX_RESTARTS; let READY_WAIT_MS; let HEALTH_MS; let STABLE_MS; let MIN_HEALTH_MS;
let LOG_DIR;
try {
  MAX_RESTARTS = numEnv('STACK_MAX_RESTARTS', { fallback: 5, min: 0, max: 100, integer: true });
  READY_WAIT_MS = numEnv('STACK_READY_WAIT_MS', { fallback: 90000, min: 1000, max: 600000 });
  HEALTH_MS = numEnv('STACK_HEALTH_MS', { fallback: 30000, min: 0, max: 3600000 });
  MIN_HEALTH_MS = 5000;                                     // 周期性检查的硬下限：不许变成高频轮询
  if (HEALTH_MS > 0 && HEALTH_MS < MIN_HEALTH_MS) {
    throw new ConfigError(`STACK_HEALTH_MS=${JSON.stringify(process.env.STACK_HEALTH_MS)} 低于下限 ${MIN_HEALTH_MS}`
      + `（0 = 关闭周期性检查）；高频轮询会把引擎的 IP 限流额度吃光（实测 429）`);
  }
  STABLE_MS = numEnv('STACK_STABLE_MS', { fallback: 600000, min: 0, max: 86400000 });
  LOG_DIR = process.env.STACK_LOG_DIR || path.join(ROOT, '.stack-logs');
} catch (error) {
  if (!(error instanceof ConfigError)) throw error;
  console.error(`[stack] 参数非法：${error.message}`);
  console.error('[stack] 拒绝启动：env 覆盖参数只接受区间内的有限值，**不做静默回落**（静默回落会让运维'
    + '以为自己的设置生效了）。修正后重跑，或去掉该 env 用默认值。');
  process.exit(EXIT_CONFIG);
}

const KEY = (process.env.ENGINE_API_KEY || process.env.OSRM_ENGINE_KEY || '').trim();
if (!KEY) {
  // 不设默认密钥：默认值会让「网关密钥 / 官网密钥不一致」变成假绿（/health 照样 ok，客户测算全 401）。
  console.error('[stack] 缺 ENGINE_API_KEY：拒绝用默认密钥启动（网关会拒绝启动，且密钥不一致时'
    + '健康检查仍报 ok、客户测算全 401）。用法：ENGINE_API_KEY=... npm run stack');
  process.exit(EXIT_CONFIG);
}

const SERVICES = [
  {
    name: 'engine',
    port: 18000,
    exe: ENGINE_PY,
    args: [ENGINE_SCRIPT, '--port', '18000'],
    cwd: ENGINE_CWD,
    env: {},
    healthPath: '/health',
    identity: ENGINE_SCRIPT,
    checkHealth: (body) => body && body.status === 'ok',
  },
  {
    name: 'gateway',
    port: 18001,
    exe: ENGINE_PY,
    args: [GATEWAY_SCRIPT],
    cwd: GATEWAY_CWD,
    env: { PORT: '18001', ENGINE_API_KEY: KEY },
    healthPath: '/gateway/health',
    identity: GATEWAY_SCRIPT,
    // 端口自证：弱标识（只有 server.py）不足以认人，指纹才对
    checkHealth: (body) => body && body.gateway === 'jiuneng-osrm-gateway',
  },
  {
    name: 'site',
    port: 3300,
    exe: process.execPath,
    args: [SITE_ENTRY],
    cwd: ROOT,
    env: {
      NODE_ENV: 'production',
      PORT: '3300',
      HEALTH_PROBE_MS: process.env.HEALTH_PROBE_MS || '5000',
      AGENT_CHAT_DEMO: process.env.AGENT_CHAT_DEMO ?? '1',
      OSRM_API_BASE: process.env.OSRM_API_BASE || 'http://127.0.0.1:18001',
      OSRM_ENGINE_KEY: KEY,
    },
    healthPath: '/api/health',
    identity: SITE_ENTRY,
    // 轻量档永远 200：degraded 也算「进程活着」
    checkHealth: (body) => body && (body.status === 'ok' || body.status === 'degraded'),
  },
];

const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000];
const TAIL_LINES = 24;                                     // 每个服务留最后 24 行日志（崩溃时打出来）
const PS_UTF8 = '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; ';

const state = new Map();      // name → { child, restarts, startedAt, tail, ready, strikes, timer }
const starting = new Set();
let shuttingDown = false;

const stamp = () => new Date().toISOString();
const log = (msg) => console.log(`[stack] ${msg}`);
const elog = (msg) => console.error(`[stack] ${msg}`);

fs.mkdirSync(LOG_DIR, { recursive: true });

function st(svc) {
  if (!state.has(svc.name)) {
    state.set(svc.name, { child: null, restarts: 0, startedAt: 0, tail: [], ready: false, strikes: 0, timer: null });
  }
  return state.get(svc.name);
}

// ── 进程/端口小工具（带超时；失败一律**明确报出**，不静默）────────────────
function run(exe, args, timeout) {
  return new Promise((resolve) => {
    execFile(exe, args, { timeout, windowsHide: true, maxBuffer: 8 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) resolve({ ok: false, error: String(error.message || error), stdout: stdout || '', stderr: stderr || '' });
      else resolve({ ok: true, stdout: stdout || '', stderr: stderr || '' });
    });
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** netstat -ano → [{ port, pid, addr }]，只收 TCP LISTENING 行（**行数**才是判据）。 */
async function netstatListeners() {
  const res = await run('netstat', ['-ano'], 15000);
  if (!res.ok) {
    elog(`netstat 调用失败（${res.error}）—— 端口身份无法核对，按「未知」处理`);
    return null;
  }
  const rows = [];
  for (const line of res.stdout.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 5 || parts[0] !== 'TCP' || parts[3] !== 'LISTENING') continue;
    const m = /:(\d+)$/.exec(parts[1]);
    if (!m) continue;
    rows.push({ port: Number(m[1]), pid: parts[4], addr: parts[1] });
  }
  return rows;
}

async function listenersOn(port) {
  const rows = await netstatListeners();
  if (rows === null) return null;
  return rows.filter((r) => r.port === port);
}

/** 取某 PID 的 Name/CommandLine/ParentProcessId（PowerShell 输出统一 UTF-8，否则中文路径乱码）。 */
async function procInfo(pid) {
  const res = await run('powershell', ['-NoProfile', '-Command',
    `${PS_UTF8}Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}' | `
    + 'Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress'], 25000);
  if (!res.ok) return null;
  try {
    const obj = JSON.parse(res.stdout.trim() || '{}');
    return Array.isArray(obj) ? (obj[0] || null) : obj;
  } catch { return null; }
}

function portFree(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    const done = (value) => { try { srv.close(); } catch { /* 已关 */ } resolve(value); };
    srv.once('error', () => done(false));
    srv.once('listening', () => done(true));
    try { srv.listen(port, '0.0.0.0'); } catch { done(false); }
  });
}

async function healthOk(svc) {
  try {
    const res = await fetch(`http://127.0.0.1:${svc.port}${svc.healthPath}`,
      { signal: AbortSignal.timeout(4000) });
    if (!res.ok) return { ok: false, reason: `HTTP ${res.status}`, connected: true };
    const body = await res.json().catch(() => null);
    return { ok: svc.checkHealth(body), reason: svc.checkHealth(body) ? '' : '响应体指纹不匹配', connected: true, body };
  } catch (error) {
    // 连接级失败（连不上/超时）：这才是「服务没在服务」的证据，周期性检查只对这种失败计数
    return { ok: false, reason: String(error?.name || error?.message || error), connected: false };
  }
}

/** 端口上的监听者是不是「我起的这棵树」：监听 PID 就是子进程，或是子进程的直接子进程
 *  （本机 venv 的 `Scripts/python.exe` 是**跳板**：它再 spawn 出 uv 的 python 才真正 listen）。
 *  另外要求命令行里出现该服务的**绝对路径** —— 端口被别人的同名脚本顶掉时这里就会红。 */
async function ownedByPort(svc, childPid) {
  const rows = await listenersOn(svc.port);
  if (rows === null) return { ok: false, why: 'netstat 失败' };
  if (rows.length !== 1) return { ok: false, why: `${svc.port} 上 LISTENING 行数 = ${rows.length}（应为 1）` };
  const pid = rows[0].pid;
  const info = await procInfo(pid);
  if (!info) return { ok: false, why: `PID ${pid} 查不到进程信息` };
  const cmd = String(info.CommandLine || '');
  // 斜杠归一：Start-Process / cwd 混用会把同一路径写成 `...\a\b`、`.../a/b` 或 `...\a/b` 三种形态
  const norm = (s) => String(s).replace(/\\/g, '/');
  if (!norm(cmd).includes(norm(svc.identity))) {
    return { ok: false, why: `PID ${pid} 的命令行里没有绝对路径 ${svc.identity}（可能是别人的进程）` };
  }
  if (String(pid) !== String(childPid)) {
    const parent = await procInfo(String(info.ParentProcessId || ''));
    if (!parent || String(parent.ProcessId) !== String(childPid)) {
      return { ok: false, why: `PID ${pid} 既不是子进程 ${childPid} 也不是它的直接子进程（跳板链不符）` };
    }
  }
  return { ok: true, why: `PID ${pid}（我起的进程树）`, pid };
}

function appendTail(entry, chunk) {
  for (const line of String(chunk).split(/\r?\n/)) {
    if (line === '') continue;
    entry.tail.push(line);
  }
  while (entry.tail.length > TAIL_LINES) entry.tail.shift();
}

function writeLog(svc, text) {
  try {
    fs.appendFileSync(path.join(LOG_DIR, `${svc.name}.log`), text);
  } catch (error) {
    elog(`写日志失败（${path.join(LOG_DIR, `${svc.name}.log`)}）：${error.message}`);
  }
}

/** 杀**我自己的子进程**及其整棵树。身份依据 = 我自己 spawn 出来的 PID（不扫端口号段）。
 *  /T 很关键：venv python 是跳板，只杀跳板可能留下真正 listen 的孙子进程占着端口。 */
function killTree(pid, label) {
  return new Promise((resolve) => {
    const child = spawn('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true });
    let out = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { out += d; });
    child.on('error', (error) => {
      elog(`杀 ${label} PID ${pid} 失败：${error.message}`);
      resolve(false);
    });
    child.on('exit', (code) => {
      log(`已停 ${label} PID ${pid}（taskkill exit=${code}）`);
      resolve(code === 0 || /not found|没有找到/i.test(out));
    });
    setTimeout(() => { try { child.kill(); } catch { /* 已退 */ } resolve(false); }, 20000);
  });
}

async function waitReady(svc, child) {
  const deadline = Date.now() + READY_WAIT_MS;
  let delay = 300;
  let last = '未知';
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      return { ok: false, why: `进程已退出（code=${child.exitCode}）` };
    }
    const rows = await listenersOn(svc.port);
    if (rows && rows.length === 1) {
      const h = await healthOk(svc);
      if (h.ok) {
        const own = await ownedByPort(svc, child.pid);
        if (own.ok) return { ok: true, why: `${own.why} ${svc.healthPath} 200` };
        return { ok: false, why: own.why };
      }
      last = h.reason || '健康检查未通过';
    } else if (rows) {
      last = `${svc.port} 上 LISTENING 行数 = ${rows.length}（应为 1）`;
    } else {
      last = 'netstat 失败';
    }
    await sleep(delay);
    delay = Math.min(Math.ceil(delay * 1.6), 2000);      // 退避：就绪检查也不做高频轮询
  }
  return { ok: false, why: `${Math.round(READY_WAIT_MS / 1000)}s 内未就绪（末次：${last}）` };
}

async function stopAll(reason, code) {
  if (shuttingDown) return;
  shuttingDown = true;
  elog(`停止管控：${reason}`);
  for (const svc of SERVICES) {
    const entry = st(svc);
    entry.ready = false;
    if (entry.timer) clearTimeout(entry.timer);
    if (entry.child) {
      const pid = entry.child.pid;
      entry.child.removeAllListeners('exit');
      await killTree(pid, svc.name);
      entry.child = null;
    }
  }
  // 收尾核对：三个端口都不该再有 LISTENING（别人的进程不算我的责任，但要如实报出来）
  const rows = await netstatListeners();
  if (rows) {
    for (const svc of SERVICES) {
      const left = rows.filter((r) => r.port === svc.port);
      if (left.length) elog(`注意：${svc.name}(${svc.port}) 仍有 ${left.length} 行 LISTENING（PID ${left.map((r) => r.pid).join(',')}）`
        + '—— 可能不是本守护的子进程，需人工确认');
    }
  }
  elog('全部子进程已停止。');
  process.exit(code);
}

async function accountExit(svc, { code, signal, why }) {
  const entry = st(svc);
  entry.child = null;
  entry.ready = false;
  if (entry.stream) { try { entry.stream.end(); } catch { /* 已关 */ } entry.stream = null; }
  if (shuttingDown) return;
  const uptime = entry.startedAt ? Date.now() - entry.startedAt : 0;
  const tail = entry.tail.slice(-8).join('\n');
  elog(`${svc.name} 退出（code=${code} signal=${signal}${why ? ` ${why}` : ''}），运行 ${(uptime / 1000).toFixed(1)}s`);
  if (tail) elog(`${svc.name} 最后日志：\n${tail}`);
  if (entry.restarts > 0 && uptime >= STABLE_MS) {
    log(`${svc.name} 已稳定运行 ${(uptime / 1000).toFixed(0)}s ≥ ${Math.round(STABLE_MS / 1000)}s → 重启计数归零`
      + '（否则一个长期健壮的服务会因为几天里零星崩几次被误判成「崩溃风暴」）');
    entry.restarts = 0;
  }
  entry.restarts += 1;
  if (entry.restarts > MAX_RESTARTS) {
    await stopAll(`${svc.name} 重启已达上限 ${MAX_RESTARTS} 次（第 ${entry.restarts} 次退出 code=${code} signal=${signal}）；`
      + `日志：${path.join(LOG_DIR, `${svc.name}.log`)} —— 不再重启，避免把真 bug 藏起来`, EXIT_LIMIT);
    return;
  }
  const wait = BACKOFF_MS[Math.min(entry.restarts - 1, BACKOFF_MS.length - 1)];
  elog(`${svc.name} 将在 ${wait}ms 后重启（第 ${entry.restarts}/${MAX_RESTARTS} 次）`);
  entry.timer = setTimeout(() => {
    if (!shuttingDown) void startService(svc);
  }, wait);
}

async function startService(svc) {
  const entry = st(svc);
  if (shuttingDown || entry.child || starting.has(svc.name)) return;
  starting.add(svc.name);
  try {
    const argv = [svc.exe, ...svc.args];
    writeLog(svc, `\n[stack] ${stamp()} 启动 ${svc.name}（第 ${entry.restarts + 1} 次）\n`);
    // 绝对路径 + 完整 env：事后用 CommandLine 就能认出端口上是谁（弱标识核不出身份）
    const child = spawn(svc.exe, svc.args, {
      cwd: svc.cwd,
      env: { ...process.env, ...svc.env },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    entry.child = child;
    entry.startedAt = Date.now();
    entry.ready = false;
    entry.strikes = 0;
    entry.tail = [];
    log(`启动 ${svc.name}（第 ${entry.restarts + 1} 次）pid=${child.pid}：${argv.join(' ')}  [cwd=${svc.cwd}]`);
    log(`  ${svc.name} 日志 → ${path.join(LOG_DIR, `${svc.name}.log`)}`);
    const stream = fs.createWriteStream(path.join(LOG_DIR, `${svc.name}.log`), { flags: 'a' });
    entry.stream = stream;
    child.stdout.pipe(stream);
    child.stderr.pipe(stream);
    child.stdout.on('data', (d) => appendTail(entry, d));
    child.stderr.on('data', (d) => appendTail(entry, d));
    // 一次退出只记一次账（'error' 与 'exit' 可能都来；就绪失败那条路也会记一次）
    let fired = false;
    child.on('error', (error) => {
      if (fired) return;
      fired = true;
      elog(`${svc.name} 启动失败：${error.message}`);
      void accountExit(svc, { code: null, signal: null, why: `spawn 失败：${error.message}` });
    });
    child.on('exit', (code, signal) => {
      if (fired) return;
      fired = true;
      void accountExit(svc, { code, signal, why: '' });
    });
    const ready = await waitReady(svc, child);
    if (ready.ok) {
      entry.ready = true;
      log(`${svc.name} 就绪：${ready.why}`);
    } else if (!shuttingDown && !fired && entry.child === child) {
      fired = true;
      elog(`${svc.name} 未就绪：${ready.why} —— 停掉它并按失败重启（就绪失败同样要消耗重启额度）`);
      child.removeAllListeners('exit');
      await killTree(child.pid, svc.name);          // /T：跳板进程要连孙子一起收掉，否则端口不放
      await accountExit(svc, { code: null, signal: 'not-ready', why: `就绪失败：${ready.why}` });
    }
  } finally {
    starting.delete(svc.name);
  }
}

/** 周期性轻量健康检查：只对**连接级**失败计数；3 次连续失败才判「活着但不服务」→ 停掉重启。 */
async function periodicCheck() {
  if (shuttingDown) return;
  for (const svc of SERVICES) {
    const entry = st(svc);
    if (!entry.child || !entry.ready) continue;            // 正在启动/重启的服务不查，避免误判
    const h = await healthOk(svc);
    if (h.ok) { entry.strikes = 0; continue; }
    if (!h.connected) {
      entry.strikes += 1;
      elog(`${svc.name} 健康检查失败（${entry.strikes}/3）：${h.reason}`);
      if (entry.strikes >= 3) {
        elog(`${svc.name} 连续 3 次连不上 —— 进程还在但不服务，停掉它并重启`);
        entry.ready = false;
        await killTree(entry.child.pid, svc.name);
        await accountExit(svc, { code: null, signal: 'unhealthy', why: '连续 3 次健康检查连不上' });
      }
    } else {
      elog(`${svc.name} 健康检查返回异常（${h.reason}）—— 只告警不判死（HTTP 层报错可能只是限流/瞬时负载）`);
    }
  }
}

// ── 前置检查：三个端口都必须空闲（含占用 PID 报出）──────────────────────
async function precheck() {
  const rows = await netstatListeners();
  const occupied = [];
  for (const svc of SERVICES) {
    const hits = rows ? rows.filter((r) => r.port === svc.port) : [];
    const free = await portFree(svc.port);
    if (hits.length || !free) {
      const details = [];
      for (const hit of hits) {
        const info = await procInfo(hit.pid);
        details.push(`PID ${hit.pid}${info ? ` ${info.Name} :: ${String(info.CommandLine).slice(0, 160)}` : '（查不到进程信息）'}`);
      }
      occupied.push({ svc, hits, free, details });
    }
  }
  if (!occupied.length) return true;
  elog('端口前置检查未通过：下面这些端口已被占用，**拒绝**在别人的进程上硬起服务（taskkill 静默失败'
    + '曾让所有验证跑在旧构建上）：');
  for (const o of occupied) {
    elog(`  端口 ${o.svc.port}（${o.svc.name}）：LISTENING ${o.hits.length} 行；bind 测试 ${o.free ? '可绑（Windows 允许同端口多监听者，以 netstat 为准）' : '失败'}`);
    for (const d of o.details) elog(`    ${d}`);
    elog(`    清掉：netstat -ano | findstr ":${o.svc.port} " | findstr LISTENING  然后  powershell Stop-Process -Id <PID> -Force`);
  }
  return false;
}

// ── 主流程 ──────────────────────────────────────────────────────────
log(`守护三服务：${SERVICES.map((s) => `${s.name}@${s.port}`).join(' + ')}`);
log(`  ROOT=${ROOT}`);
log(`  日志目录=${LOG_DIR}`);
log(`  重启上限=${MAX_RESTARTS} 次/服务，退避 ${BACKOFF_MS.join('/')}ms；就绪预算 ${READY_WAIT_MS}ms；`
  + `周期健康检查 ${HEALTH_MS ? `${HEALTH_MS}ms` : '关闭'}`);
log(`  密钥：已提供（长度 ${KEY.length}，前 4 位 ${KEY.slice(0, 4)}…，不回显全文）`);

if (!fs.existsSync(SITE_ENTRY)) {
  elog(`缺 ${SITE_ENTRY}，先跑 npm run build（拒绝在没有构建产物时假装启动成功）`);
  process.exit(EXIT_CONFIG);
}
if (!fs.existsSync(ENGINE_SCRIPT)) {
  elog(`缺引擎入口 ${ENGINE_SCRIPT}（检查 ENGINE_CWD / AIOSRM++ 安装位置）`);
  process.exit(EXIT_CONFIG);
}
if (!fs.existsSync(GATEWAY_SCRIPT)) {
  elog(`缺网关入口 ${GATEWAY_SCRIPT}`);
  process.exit(EXIT_CONFIG);
}
if (!(await precheck())) process.exit(EXIT_PORT);

process.on('SIGINT', () => { void stopAll('收到 Ctrl+C', 130); });
process.on('SIGTERM', () => { void stopAll('收到 SIGTERM', 130); });

await Promise.all(SERVICES.map((svc) => startService(svc)));
log(`全部启动（每个服务最多重启 ${MAX_RESTARTS} 次）。Ctrl+C 停止。`);

if (HEALTH_MS > 0) {
  setInterval(() => { void periodicCheck().catch((e) => elog(`健康检查 tick 失败：${e}`)); }, HEALTH_MS);
}
