import express, { Request, Response } from 'express';
import fs from 'fs';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
import {
  geminiModel,
  deepseekModel,
  runAgentChat,
  sanitizeHistory,
  parseLang,
  sseFormat,
  scriptedModel,
  type ChatModel,
  type ModelEvent,
} from './server/agentChat';
import { agentI18n, type Lang } from './src/agent/content';
import { runQuote, PLACES, VEHICLES, probeEngine } from './server/osrmQuote';

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT) || 3000;
const HMR_PORT = process.env.HMR_PORT ? Number(process.env.HMR_PORT) : 24679;

app.use(express.json());

// Lazy-initialize Gemini SDK Client
let aiClient: GoogleGenAI | null = null;
function getGeminiClient(): GoogleGenAI {
  if (!aiClient) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      throw new Error('GEMINI_API_KEY variable is missing. Please set it in the Settings panel.');
    }
    aiClient = new GoogleGenAI({
      apiKey,
      httpOptions: {
        headers: {
          'User-Agent': 'aistudio-build',
        },
      },
    });
  }
  return aiClient;
}

/* ── 右下角「AI 数字员工」对话的模型选择 ────────────────────────
   2026-09-26 拍板：**DeepSeek 优先**（model 默认 deepseek-flash，与主人 Hermes 同一入口
   https://api.deepseek.com/v1），没配或调用失败时**回退 Gemini**（线上本就配着 GEMINI_API_KEY）；
   两者都没有 → 如实报错，绝不假装答对。

   为什么回退要卡在「一个字都还没发出去」时才做：半途换模型会让客户看到两段自相矛盾的话，
   而且第一段的工具调用结果已经发出去了没法收回。回退必须**可追溯**（日志里写清楚谁失败、退到谁）。
   CHAT_PROVIDER=deepseek|gemini 可强制指定（强制时不回退，验收 C 段钉着这条）。 */

type ChatChoice = { label: string; model: ChatModel };

function chatChoice(which: 'deepseek' | 'gemini'): ChatChoice | null {
  if (which === 'deepseek') {
    const key = (process.env.DEEPSEEK_API_KEY || '').trim();
    if (!key) return null;
    const baseUrl = (process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1').trim();
    const model = (process.env.DEEPSEEK_MODEL || 'deepseek-flash').trim();
    return { label: `DeepSeek(${model})`, model: deepseekModel({ apiKey: key, baseUrl, model }) };
  }
  if (!(process.env.GEMINI_API_KEY || '').trim()) return null;
  return { label: 'Gemini(gemini-3.1-flash-lite)', model: geminiModel(getGeminiClient()) };
}

function chatPlan(): { primary: ChatChoice; fallback: ChatChoice | null } | null {
  const forced = (process.env.CHAT_PROVIDER || '').trim().toLowerCase();
  if (forced === 'deepseek' || forced === 'gemini') {
    const only = chatChoice(forced);
    return only ? { primary: only, fallback: null } : null;
  }
  const ds = chatChoice('deepseek');
  const gem = chatChoice('gemini');
  if (ds) return { primary: ds, fallback: gem };
  return gem ? { primary: gem, fallback: null } : null;
}

/** 日志/自测用的一句话描述（**不含任何密钥值**）。 */
function chatPlanLabel(): string {
  const forced = (process.env.CHAT_PROVIDER || '').trim().toLowerCase();
  const plan = chatPlan();
  if (!plan) return `未配置（需 DEEPSEEK_API_KEY 或 GEMINI_API_KEY${forced ? `；已强制 CHAT_PROVIDER=${forced} 但没配对应密钥` : ''}）`;
  return plan.fallback
    ? `${plan.primary.label}（失败回退 ${plan.fallback.label}）`
    : `${plan.primary.label}${forced ? '（CHAT_PROVIDER 强制指定，不回退）' : ''}`;
}

console.info(`[chat] 数字员工对话模型：${chatPlanLabel()}`);

// API: Health probe —— 如实反映依赖状态。
// 轻量模式必须永远快、永远 200（UptimeRobot 保活依赖它）；深探测只在 ?deep=1 时实时打引擎。
// 环境变量：HEALTH_PROBE_MS（后台探查间隔，**默认 0 = 关闭周期探查**，见 probeIntervalMs）、
//          HEALTH_DEEP_TIMEOUT_MS（deep 预算，默认 3s）、HEALTH_PROBE_TIMEOUT_MS（后台探查预算，默认 5s）。
// ⚠️ 为什么默认关闭：Render 免费层「每工作区 750 实例小时/月」，用光则当月暂停**全部**免费服务。
//    周期探查（旧默认 60s）会 24/7 把引擎叫醒 → 两个常驻服务 ≈1440h/月，必然超额被暂停。
//    改为按需唤醒后，引擎只在有真实请求（或显式 ?deep=1）时才醒，实例小时只剩站点自身。
//    需要常驻探查的场景（本地联调、监控曲线）显式设 HEALTH_PROBE_MS=60000 即可，机制不变。
// ⚠️ 取数必须归一 + 夹下限 + **夹上界**：`Number('abc')`/`Number('')` 分别得到 NaN/0，直接喂给 setInterval 会退化成
//    1ms 忙循环——实测 3 秒内把引擎打了 1600+ 次，把引擎自带的 IP 限流额度吃光，**客户点「快速测算」就会吃 429**。
//    所以：非有限值或 ≤0 → 回落默认；再按下限夹紧（间隔最低 1s，预算最低 200ms）。
// ⚠️ **上界同样必须夹**：`setTimeout`/`setInterval` 的延迟参数在 Node 里按 32 位有符号整数存储，
//    超过 2³¹−1 会**回绕成很小的正数**（实测 `HEALTH_PROBE_MS=4294967296`（2³²）→ 回绕成 1ms，
//    3 秒上千次探针，两方独立复现 1639 次/3s 与 399 次/3s；`HEALTH_PROBE_TIMEOUT_MS=2³²` 则让**活引擎
//    被误报成 `{ok:false, ms:13, reason:'timeout'}` 的假告警**）。原来只夹下限，这类值会**静默**变成忙循环，
//    正是 T2 要防的「吃光引擎限流额度」。
const MAX_TIMER_MS = 2_147_483_647;                        // 2³¹−1：Node 定时器延迟的 32 位有符号上界
function positiveEnvMs(name: string, fallback: number, min: number): number {
  const rawStr = process.env[name];
  if (rawStr === undefined) return fallback;                 // 未配置：用默认值，不必告警
  const raw = Number(rawStr);
  if (!Number.isFinite(raw) || raw <= 0) {
    // 不静默回落：把被拒的原始字符串打出来，运维才知道自己写的值没生效、实际用的是哪个
    console.warn(`[health] 环境变量 ${name}=${JSON.stringify(rawStr)} 不是有限正值，回落到默认 ${fallback}ms`);
    return fallback;
  }
  if (raw < min) {
    console.warn(`[health] 环境变量 ${name}=${JSON.stringify(rawStr)} 低于下限，夹紧到 ${min}ms`);
    return min;
  }
  if (raw > MAX_TIMER_MS) {
    // 不静默夹紧：回绕成 1ms 的后果是「静默忙循环」，运维必须能从日志看出自己的值被拒了
    console.warn(`[health] 环境变量 ${name}=${JSON.stringify(rawStr)} 超过上限 ${MAX_TIMER_MS}ms`
      + `（超过会被 Node 定时器回绕成极小值，实测退化成千次/3s 忙循环），夹紧到 ${MAX_TIMER_MS}ms`);
    return MAX_TIMER_MS;
  }
  return raw;
}

/**
 * 后台探查间隔（ms）：**默认 0 = 不周期探查**（按需唤醒引擎，省免费层实例小时；理由见文件头）。
 * 语义边界必须明确：
 *   未设 / 空串 | 显式 0 → 0（关闭，**不告警**——这是新默认，不是写错）；
 *   非数字/负数 → 告警 + 0；>0 但低于下限 → 夹到 1000ms + 告警；> 2³¹−1 → 夹到上限 + 告警。
 * ⚠️ 这里**不能复用** positiveEnvMs：它把 0 当非法值回落成默认值，而 0 现在是合法且默认的取值；
 *    强行复用会让「默认关闭」变成「默认 60s」，本轮的省额度改动整套失效（且是静默失效）。
 */
function probeIntervalMs(): number {
  const rawStr = process.env.HEALTH_PROBE_MS;
  if (rawStr === undefined || rawStr.trim() === '') return 0;
  const raw = Number(rawStr);
  if (raw === 0) return 0;
  if (!Number.isFinite(raw) || raw < 0) {
    console.warn(`[health] 环境变量 HEALTH_PROBE_MS=${JSON.stringify(rawStr)} 不是有限非负值，回落到默认 0（关闭周期探查）`);
    return 0;
  }
  if (raw < 1_000) {
    console.warn(`[health] 环境变量 HEALTH_PROBE_MS=${JSON.stringify(rawStr)} 低于下限，夹紧到 1000ms`);
    return 1_000;
  }
  if (raw > MAX_TIMER_MS) {
    console.warn(`[health] 环境变量 HEALTH_PROBE_MS=${JSON.stringify(rawStr)} 超过上限 ${MAX_TIMER_MS}ms`
      + `（超过会被 Node 定时器回绕成极小值，实测退化成千次/3s 忙循环），夹紧到 ${MAX_TIMER_MS}ms`);
    return MAX_TIMER_MS;
  }
  return raw;
}

const PROBE_INTERVAL_MS = probeIntervalMs();
const DEEP_TIMEOUT_MS = positiveEnvMs('HEALTH_DEEP_TIMEOUT_MS', 3_000, 200);
const PROBE_TIMEOUT_MS = positiveEnvMs('HEALTH_PROBE_TIMEOUT_MS', 5_000, 200);

/**
 * ok/at/ms 在**首个探针回包之前**一律为 null —— 规格 §4 要求 lastProbe 是对象、字段可空，
 * 不得整体为 null（否则「还没探过」和「没这个字段」不可区分）。
 * ok 只允许 boolean | null，绝不用 0/'' 之类拿真值混淆「未知」与「结果」。
 */
/**
 * 探测结果**来源**：启动自检 / 周期探查 / deep 实时探测 / 真实测算请求。
 * 为什么要有这个字段：周期探查默认关闭后，lastProbe 可能**很久没更新**（陈旧）——
 * 运维与监控必须能区分「引擎坏了」和「最近没人探过」，否则会把陈旧状态误读成当前故障。
 */
type ProbeSource = 'startup' | 'periodic' | 'deep' | 'quote';
type LastProbe = { ok: boolean | null; at: string | null; ms: number | null; reason?: string; source?: ProbeSource };
let lastProbe: LastProbe = { ok: null, at: null, ms: null };
/** 只在状态跳变时打日志，避免刷屏（运维/告警靠日志看依赖状态）。 */
let lastLoggedOk: boolean | null = null;

/**
 * 「陈旧」判定窗口（ms，可用 HEALTH_STALE_MS 覆盖，默认 15 分钟）：
 * 超过 max(2×探查间隔, 该窗口) 没更新的结果**不**参与 degraded 判定 —— 否则一次瞬时 502
 * （Render 免费层实例轮换/部署期间很常见，实测 496ms 就回了 status_502）会让 /api/health
 * 一直挂着 degraded，保活监控（UptimeRobot）报假警、运维从此不再相信这个端点。
 */
const STALE_AFTER_MS = positiveEnvMs('HEALTH_STALE_MS', 900_000, 1_000);
function probeStale(): boolean {
  if (!lastProbe.at) return false;
  const age = Date.now() - Date.parse(lastProbe.at);
  if (!Number.isFinite(age)) return false;
  return age > Math.max(2 * PROBE_INTERVAL_MS, STALE_AFTER_MS);
}

async function tickProbe(source: ProbeSource): Promise<void> {
  const r = await probeEngine(PROBE_TIMEOUT_MS);
  lastProbe = { ok: r.ok, at: new Date().toISOString(), ms: r.ms, source, ...(r.reason ? { reason: r.reason } : {}) };
  if (lastLoggedOk === null || lastLoggedOk !== r.ok) {
    lastLoggedOk = r.ok;
    console.info(`[health] 引擎探测结果变化：${r.ok ? '可达' : '不可达'}（reason=${r.reason ?? 'none'} ms=${r.ms} source=${source}）`);
  }
}

/**
 * 真实测算请求的**引擎级**结果也写进探测状态（来源标 quote）。
 * 按需唤醒下这是最新鲜的健康信号：有客户在用，/api/health 就自动跟着更新，不必为了保活去唤醒引擎。
 * ⚠️ 只记引擎级失败（engine_timeout/unreachable/error）；入参校验类失败（未知城市/缺货重…）说明引擎活着，
 *    由调用方按 ok:true 处理，别把「客户填错」记成「引擎故障」。
 */
function noteQuoteOutcome(ok: boolean, ms: number, reason?: string): void {
  lastProbe = { ok, at: new Date().toISOString(), ms, source: 'quote', ...(reason ? { reason } : {}) };
}

/**
 * ⚠️ 后台 tick **必须**兜底 catch：`probeEngine` 不抛异常只是实现承诺，不是类型约束
 * （返回类型 `Promise<{...}>` 不排除 reject）。定时器回调里未捕获的异步抛错会直接要了进程的命
 * ——Node ≥15 默认 unhandledRejection 致命，实测 node 26 下整个进程 exit 1，
 * 官网连同保活端点 /api/health 一起挂掉，监控却看不出原因。
 */
const tick = (source: 'startup' | 'periodic'): void => {
  void tickProbe(source).catch((e) => console.error('[health] 探针 tick 失败：', e));
};
/**
 * 启动时**只**打一次：给 /api/health 一个初值（否则 lastProbe.ok=null 会一直被读成「还没探过」），
 * 顺带让发布后立刻能看出引擎可达性。代价是每次部署唤醒引擎约 1 分钟，可忽略。
 */
tick('startup');
/**
 * 周期探查**默认不启用**（PROBE_INTERVAL_MS === 0）：否则会把免费层的引擎 24/7 钉在醒着状态，
 * 两个常驻服务 ≈1440 实例小时/月 > 免费额度 750h/月，月中会被暂停**全部**免费服务。
 * 需要常驻探查（本地联调 / 监控曲线）时显式设 HEALTH_PROBE_MS，机制与旧版完全一致。
 * 引擎改由真实请求按需唤醒：休眠时首个测算要等冷启动，由 OSRM_QUOTE_TIMEOUT_MS（默认 75s）兜住。
 */
if (PROBE_INTERVAL_MS > 0) setInterval(() => tick('periodic'), PROBE_INTERVAL_MS).unref?.();

/** 只暴露 host，绝不带路径/查询串（避免把内部路径或密钥泄给监控页面）。 */
function engineSnapshot(): { configured: boolean; base: string | null; lastProbe: LastProbe; probeMode: 'periodic' | 'on_demand'; probeIntervalMs: number; stale: boolean } {
  const raw = (process.env.OSRM_API_BASE || '').trim();
  let host: string | null = null;
  try { host = raw ? new URL(raw).host : null; } catch { host = null; }
  return {
    configured: Boolean(raw),
    base: host || null,
    lastProbe,
    // 自描述：监控侧看到 probeMode='on_demand' 就知道 lastProbe 可能陈旧，不会把旧失败读成当前故障。
    probeMode: PROBE_INTERVAL_MS > 0 ? 'periodic' : 'on_demand',
    probeIntervalMs: PROBE_INTERVAL_MS,
    stale: probeStale(),
  };
}

// 启动即打印一次归一后的实际参数——运维写错 env 时能立刻从日志看出（而不是靠猜频率）
console.info(`[health] 后台周期探查 ${PROBE_INTERVAL_MS > 0
  ? `${PROBE_INTERVAL_MS}ms`
  : '已关闭（按需唤醒引擎，省免费层实例小时；需要常驻探查请设 HEALTH_PROBE_MS）'}`
  + `（deep 预算 ${DEEP_TIMEOUT_MS}ms / 后台预算 ${PROBE_TIMEOUT_MS}ms）；引擎 base = ${engineSnapshot().base ?? '未配置'}`);

type ProbeResult = { ok: boolean; ms: number; reason?: string };
/** deep 结果 + **结果时刻**（语义：探测拿到结果的时刻，不是请求进来的时刻）。 */
type DeepProbe = ProbeResult & { at: string };

/**
 * deep 档单飞合并：同一时刻只允许一个在飞探测，后来的请求 await 同一个 promise。
 * **不做时间缓存（不设 TTL）**：结算后立刻失效，所以「杀掉依赖后 deep 必须立刻 degraded」不受影响
 * （时间缓存会返回陈旧状态、把验收做假）。
 * 起因：`/api/health` 按规格 §4.1 必须保持免鉴权，于是 30 个匿名并发 `?deep=1` 会被 1:1 放大成
 * 30 次引擎请求 —— 官网成了打自己引擎的放大器。
 */
let inFlightDeep: Promise<DeepProbe> | null = null;

function deepProbe(): Promise<DeepProbe> {
  if (!inFlightDeep) {
    inFlightDeep = probeEngine(DEEP_TIMEOUT_MS)
      // at 在 await 之后取：探针真拿到结果的时刻（原先取的是请求时刻，比结果早一整个预算，实测早 3s）
      .then((r) => ({ ...r, at: new Date().toISOString() }))
      .finally(() => { inFlightDeep = null; });
  }
  return inFlightDeep;
}

app.get('/api/health', async (req: Request, res: Response) => {
  const snap = engineSnapshot();
  const now = new Date().toISOString();   // 请求时刻（顶层 time 的语义）

  if (req.query.deep === '1') {
    let probe: LastProbe;
    const deepStarted = Date.now();
    try {
      const r = await deepProbe();
      probe = { ok: r.ok, at: r.at, ms: r.ms, source: 'deep', ...(r.reason ? { reason: r.reason } : {}) };
      // deep 是**真实探测** → 顺手刷新共享状态，让轻量档也吃到这份新鲜结果
      // （按需唤醒下若不刷新，下一份「最新信号」要等到客户真的点一次测算）
      lastProbe = probe;
    } catch (e) {
      // 与后台 tick 同一类风险：express 4 不接管 async 处理器的 rejection，未捕获即进程级致命
      // ms 用**实测耗时**（原先硬编码 0）：0ms 在语义上是「未测量」（not_configured 专用），
      // 拿它当「探测失败耗时」会让运维误以为这条路径根本没发请求。
      // reason 仍留 'unreachable'（spec §4.1 的 reason 是封闭枚举，不轻易新增取值），
      // 但日志文本明确区分「探测内部异常」与「依赖连不上」——否则代码 bug 会被伪装成依赖不可达。
      console.error('[health] deep 探测内部异常（不是「依赖不可达」，请查代码/运行时）：', e);
      probe = { ok: false, at: new Date().toISOString(), ms: Date.now() - deepStarted, reason: 'unreachable' };
    }
    res.json({
      status: snap.configured && probe.ok === false ? 'degraded' : 'ok',
      time: now,
      // deep 是**当场**探测 → stale 恒为 false（覆盖快照里那份可能陈旧的标记）
      engine: { ...snap, lastProbe: probe, stale: false },
    });
    return;
  }

  // 轻量档：只读后台探针的缓存结果，绝不在这里实时探测（否则保活请求会被拖死）。
  // lastProbe.ok === null 表示首个探针还没回包 → 不判 degraded（status 只有 ok|degraded 两值，
  // 不能因为「未知」把保活端点打红）；「还没探过」由 lastProbe.ok=null 如实表达，不再谎报 ok。
  // ⚠️ **陈旧失败也不判 degraded**：按需唤醒下 lastProbe 可能几小时没更新（引擎睡着、没人在用），
  //    把那时的一次旧失败一直当当前故障，保活监控（UptimeRobot）会永久报假警、运维从此不信这个端点
  //    （实测：部署期间引擎瞬时 502 → 端点一直挂着 degraded）。新鲜度由 probeMode / stale 自描述。
  const degraded = snap.configured && snap.lastProbe.ok === false && !snap.stale;
  res.json({ status: degraded ? 'degraded' : 'ok', time: now, engine: snap });
});

// API: Server-side Gemini AI logistics risk risk consulting proxy
app.post('/api/logistics-consult', async (req: Request, res: Response) => {
  try {
    const { name, company, inquiryType, loadingPort, dischargePort, weightEstimate, details } = req.body;

    if (!name || !details) {
      res.status(400).json({ error: 'Please submit name and project details' });
      return;
    }

    const ai = getGeminiClient();

    const systemPrompt = `你是 JIUNENG logistics（玖能国际）工程物流平台的在线询价顾问，聚焦中越工程物流、进出口报关与国际贸易。
玖能定位为"面向中国企业的工程物流平台"：中国侧由广西玖一进出口贸易有限公司提供进出口与报关支持，越南侧通过本地合作代理网络衔接业务。
你的任务是根据客户提交的项目需求，给出专业、可落地的"初步评估"，帮助整理沟通信息，便于项目经理跟进正式方案。

合规约束（必须遵守）：
- 这是初步评估，不是正式报价，也不是时效承诺。
- 不得编造或承诺具体清关时效、报价金额、运费价格、货损率或任何 SLA 数字。
- 越南侧能力统一表述为"通过越南本地合作代理提供服务支持"，不得宣称越南自营报关公司、自营仓储或越南全境直营网点。
- 不得宣称全程 GPS 追踪或 7×24 小时客服。
- 缺少关键信息时，明确列出需要客户补充的内容，而不是臆测。
- 语气专业、克制，引导客户走平台正式询价流程。
- 输出语言：根据客户提交内容所用语言（中文/越南语/英文）回应。

你必须使用以下JSON格式返回响应：
{
  "routeRecommendation": "针对该项目的线路与运输方案方向（如口岸/干线/换装/现场交付要点），不承诺时效，专业克制",
  "documentChecklist": [
    "中方出口及越方进口可能涉及的关键单证清单（如 Form E 原产地证、大件超限许可、装箱清单、设备技术资料等），并标注需客户确认的项目"
  ],
  "hsCodeAdvice": "关于该品类的可能HS编码归类方向及中越自贸协定关税筹划提醒（仅作方向性提示，需正式核定）",
  "riskMitigation": [
    "项目物理运力与合规层面需提前关注的事项（如桥梁限高限重、雨季路况、吊装条件、单证完整性等），以及建议补充的资料"
  ],
  "consultantStatement": "一小段克制专业的寄语，说明这是初步评估，引导客户通过平台提交正式询价并由项目经理跟进，150字以内"
}`;

    const userPrompt = `
客户姓名: ${name}
公司名称: ${company || '未提供'}
咨询类别: ${inquiryType}
起运点/港: ${loadingPort || '中国主要口岸'}
目的地/港: ${dischargePort || '越南派送点'}
预估体积/重量: ${weightEstimate || '未明确大件规格'}
项目细节描述: ${details}
`;

    const response = await ai.models.generateContent({
      model: 'gemini-3.1-flash-lite',
      contents: userPrompt,
      config: {
        systemInstruction: systemPrompt,
        responseMimeType: 'application/json',
        temperature: 0.2,
      }
    });

    const replyText = response.text || '{}';
    res.json(JSON.parse(replyText));

  } catch (error: any) {
    console.error('Logistics inquiry assessment failed:', error);
    res.status(500).json({
      error: 'The online inquiry assessment is temporarily unavailable. Please submit your project details and our team will follow up by email.',
      details: error.message
    });
  }
});

// API: /ai 页的 AI 数字员工对话（SSE 流式 + 函数调用）
// 口径与 /api/logistics-consult 一致：只给初步整理，不报价、不承诺时效；工具查不到就如实说查不到。
app.post('/api/agent-chat', async (req: Request, res: Response) => {
  const history = sanitizeHistory(req.body?.messages);
  const lang = parseLang(req.body?.lang);

  if (!history.length) {
    res.status(400).json({ error: 'messages is required' });
    return;
  }

  res.status(200).set({
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  res.flushHeaders?.();

  let closed = false;
  // 必须监听 res 的 close（响应结束/客户端断开），**不能**监听 req 的：
  // Node 16+ 把请求体读完就会 close 掉 request 流，req.on('close') 会立刻触发，
  // 导致下面的事件循环第一轮就 break、SSE 一个事件都发不出去（已踩过）。
  res.on('close', () => { closed = true; });

  try {
    const demo = demoModel(req.body?.messages, lang);
    if (demo) console.info('[agent-chat] 本地演示模型（AGENT_CHAT_DEMO=1）');
    const plan = chatPlan();

    /** 已吐出过**实质内容**（text/工具事件）→ 不许再换模型重放，否则客户看到两段自相矛盾的话。 */
    let produced = false;
    const pump = async (model: ChatModel): Promise<void> => {
      for await (const ev of runAgentChat({ history, model, lang })) {
        if (closed) break;
        if (ev.event !== 'error') produced = true;
        res.write(sseFormat(ev));
      }
    };

    if (demo) {
      await pump(demo);
    } else if (!plan) {
      console.error('[agent-chat] 未配置任何模型密钥（DEEPSEEK_API_KEY / GEMINI_API_KEY）');
      if (!closed) {
        res.write(sseFormat({ event: 'error', data: { message: agentI18n[lang].chat.error } }));
        res.write(sseFormat({ event: 'done', data: { tools: 0, rounds: 0, aborted: true } }));
      }
    } else {
      try {
        await pump(plan.primary.model);
      } catch (primaryError: any) {
        const reason = String(primaryError?.message ?? primaryError);
        /* ⚠️ 任何失败路径都必须给客户端「终止事件」（error + done）。2026-09-26 线上就是在这里
           静默断流的：已吐过 tool_start/tool_done、模型第二轮抛错 → 原代码只打日志、不写事件 →
           客户 0 字正文、连 done 都没有，「思考中」永远不结束。验收 E2/E5 钉着这条。 */
        const failOut = () => {
          if (closed) return;
          res.write(sseFormat({ event: 'error', data: { message: agentI18n[lang].chat.error } }));
          res.write(sseFormat({ event: 'done', data: { tools: 0, rounds: 0, aborted: true } }));
        };
        if (produced) {
          console.error('[agent-chat] 流中途失败（已吐出内容，不再回退）：', primaryError);
          failOut();
        } else if (plan.fallback) {
          console.warn(`[agent-chat] ${plan.primary.label} 调用失败，回退 ${plan.fallback.label}：${reason}`);
          try {
            await pump(plan.fallback.model);
          } catch (fallbackError: any) {
            console.error(`[agent-chat] 回退 ${plan.fallback.label} 也失败：`, fallbackError);
            failOut();
          }
        } else {
          // 这条日志同时点出 DeepSeek 与 Gemini：回退这件事必须可追溯（验收 B 段钉着）
          console.error(`[agent-chat] ${plan.primary.label} 调用失败，且没有可回退的 Gemini`
            + `（未配 GEMINI_API_KEY 或已用 CHAT_PROVIDER 强制指定）：${reason}`);
          failOut();
        }
      }
    }
  } catch (error: any) {
    console.error('agent-chat failed:', error);
    if (!closed) {
      res.write(sseFormat({ event: 'error', data: { message: agentI18n[lang].chat.error } }));
      res.write(sseFormat({ event: 'done', data: { tools: 0, rounds: 0, aborted: true } }));
    }
  } finally {
    res.end();
  }
});

// API: OSRM++ 测算（官网唯一出口，浏览器拿不到引擎地址）
// 出参白名单在 server/osrmQuote.ts 统一重建：只回里程/时长/车数/车型 + 参考价区间（售价 ±10%），
// 内部成本、利润、毛利率、口岸费用明细一律不出。对客口径：初步测算，非正式报价。
/** 引擎级失败（≠ 客户填错）：只有这几种说明「引擎本身有问题」，要写进健康状态。 */
const ENGINE_LEVEL_REASONS = new Set(['engine_timeout', 'engine_unreachable', 'engine_error']);

app.post('/api/osrm-quote', async (req: Request, res: Response) => {
  const startedAt = Date.now();
  try {
    const result = await runQuote({
      origin: req.body?.origin,
      destination: req.body?.destination,
      border: req.body?.border,
      weight_kg: req.body?.weight_kg,
      volume_m3: req.body?.volume_m3,
      mode: req.body?.mode,
      vehicle_model_id: req.body?.vehicle_model_id,
    });
    // 按需唤醒下，**真实流量就是最新鲜的健康信号**：把引擎级结果记进 lastProbe（source='quote'）——
    // 这样 /api/health 不必为了保活去唤醒引擎，客户一用就自动刷新（否则一次瞬时 502 会挂很久）。
    // ⚠️ 入参校验类失败（未知城市/缺货重/整车没给车型…）说明引擎**活着**，不记，别把客户填错当引擎故障。
    const reason = (result as { reason?: string }).reason;
    if (result.ok) {
      noteQuoteOutcome(true, Date.now() - startedAt);
    } else if (reason && ENGINE_LEVEL_REASONS.has(reason)) {
      noteQuoteOutcome(false, Date.now() - startedAt, reason);
    }
    res.status(result.ok ? 200 : 200).json(result);
  } catch (error: any) {
    console.error('osrm-quote failed:', error);
    res.status(500).json({ ok: false, reason: 'server_error', note: '测算服务暂时不可用，请走正式询价。' });
  }
});

// 测算用的可选城市/车型清单（与 server/osrmQuote.ts 同一份白名单，前端不重复维护）
app.get('/api/osrm-quote/places', (_req: Request, res: Response) => {
  res.json({
    places: Object.entries(PLACES).map(([id, p]) => ({ id, kind: p.kind, zh: p.zh, vi: p.vi, en: p.en })),
    vehicles: Object.entries(VEHICLES).map(([id, v]) => ({ id, max_load_ton: v.max_load_ton, zh: v.zh, vi: v.vi, en: v.en })),
  });
});

// 本地评审用的脚本化模型：只有显式设 AGENT_CHAT_DEMO=1 才生效（生产不设该变量 → 走真 Gemini）。
// 工具调用是**真的**（会打到真实测算引擎），只有措辞是预置的；回复末尾带本机演示标记，避免评审时被误导。
const DEMO_REPLY: Record<Lang, { route: string; other: string }> = {
  zh: {
    route: '上面那份初步测算里，里程、车型车数与参考价区间都来自测算引擎（区间为内部测算售价 ±10%，取整到 10 万 VND），属于初步测算，不构成报价或时效承诺。要拿正式价格，把这条条件带到下方「在线询价」提交即可，项目经理会按实际核算。',
    other: '我是玖能的工程物流数字员工。可以问我中越线路的里程与车型建议、报关单证方向、或者报价需要先准备哪些信息。正式价格与时效由项目经理核定——本机演示模式下我只做初步整理。',
  },
  en: {
    route: 'In the estimate above, the distance, vehicle count and indicative price range all come from our costing engine (range = internal selling price ±10%, rounded to the nearest 100,000 VND). It is a preliminary estimate, not a quotation or a transit-time commitment. For a firm price, send these details through the inquiry form below and our project manager will confirm.',
    other: 'I am JIUNENG’s engineering-logistics digital employee. Ask me about China–Vietnam route distances and vehicle suggestions, customs document direction, or what to prepare before requesting a price. Firm prices and transit times are confirmed by our project manager — in this local demo mode I only organise information.',
  },
  vi: {
    route: 'Trong phần ước tính ở trên, quãng đường, số xe và khoảng giá tham khảo đều lấy từ công cụ tính toán của chúng tôi (khoảng giá = giá bán nội bộ ±10%, làm tròn 100.000 VND). Đây là ước tính ban đầu, không phải báo giá hay cam kết thời gian. Để có giá chính thức, hãy gửi thông tin qua biểu mẫu yêu cầu báo giá bên dưới, quản lý dự án sẽ xác nhận.',
    other: 'Tôi là nhân viên số về logistics công trình của JIUNENG. Bạn có thể hỏi tôi về quãng đường và loại xe cho tuyến Trung Quốc – Việt Nam, hướng chứng từ thông quan, hoặc cần chuẩn bị gì trước khi yêu cầu báo giá. Giá và thời gian chính thức do quản lý dự án xác nhận — ở chế độ demo nội bộ này tôi chỉ sắp xếp thông tin.',
  },
};

const DEMO_TAG = '\n\n（本机演示：以上措辞为预置文本，测算数据为真实引擎结果）';

function demoModel(rawMessages: unknown, lang: Lang): ChatModel | null {
  if (process.env.AGENT_CHAT_DEMO !== '1') return null;
  const rows = Array.isArray(rawMessages) ? rawMessages : [];
  const lastUser = [...rows].reverse().find((m) => (m as { role?: unknown })?.role !== 'assistant');
  const ask = String((lastUser as { text?: unknown })?.text ?? '');
  const wantsRoute = /价|多少|钱|费|测算|报价|距离|公里|车|route|price|cost|rate|km|giá|tính|bao nhiêu|xe/i.test(ask);
  const steps: ModelEvent[] = wantsRoute
    ? [
        { calls: [{ name: 'query_route_cost', args: { origin: '南宁', destination: '河内', border: '友谊关口岸', weight_kg: 20000, volume_m3: 60, mode: 'consolidated' } }] },
        { text: DEMO_REPLY[lang].route + DEMO_TAG },
      ]
    : [{ text: DEMO_REPLY[lang].other + DEMO_TAG }];
  return scriptedModel(steps);
}

// 自测路由：用脚本化假模型跑真实编排 + 真实工具执行（不调用外部模型，不花钱），
// 用来在没有 GEMINI_API_KEY 的机器上验证「工具 → OSRM++ 转发 → 事件契约」。
// 仅在 AGENT_CHAT_SELFTEST=1 时挂载，默认不存在。
if (process.env.AGENT_CHAT_SELFTEST === '1') {
  app.post('/api/agent-chat/selftest', async (req: Request, res: Response) => {
    const lang = parseLang(req.body?.lang);
    const scenario = String(req.body?.scenario ?? 'route');
    const question = typeof req.body?.question === 'string' && req.body.question
      ? req.body.question
      : '友谊关到河内，25 吨设备用什么车？';

    // 线路参数与 route 脚本同一份：真实工具会打到 OSRM++（或验收脚本的假引擎）
    const routeArgs: Record<string, unknown> = {
      origin: '南宁', destination: '河内', border: '友谊关口岸',
      weight_kg: 20000, mode: 'full_truck', vehicle_model_id: 'flatbed_13m',
    };

    // 两个**模型异常**场景（钉住「静默」这类线上事故，见 scripts/verify-chat-robust.py）：
    //   empty：模型一个事件都不吐（连工具都不调）→ 客户端必须仍收到兜底正文 + done；
    //   abort：先吐一个工具调用（真工具会跑完），**第二次被调用时抛错** —— 复现线上
    //          「tool_start/tool_done 之后模型挂掉 → 0 字正文、连 done 都没有」。
    // ⚠️ abort 不能用 scriptedModel：它按脚本逐次吐事件，表达不了「抛错」这个动作，
    //    所以这里内联一个 ChatModel，用游标计数（第 1 次给工具调用，第 2 次抛错）。
    let model: ChatModel;
    if (scenario === 'empty') {
      model = scriptedModel([]);
    } else if (scenario === 'abort') {
      let cursor = 0;
      model = {
        async *stream() {
          cursor += 1;
          if (cursor === 1) {
            yield { calls: [{ name: 'query_route_cost', args: routeArgs }] };
            return;
          }
          throw new Error('selftest_abort');
        },
      };
    } else {
      const steps: ModelEvent[] = scenario === 'info'
        ? [
            { calls: [{ name: 'lookup_service_info', args: { topic: 'service' } }] },
            { text: '(selftest) 站内能力清单已取到。' },
          ]
        : [
            { calls: [{ name: 'query_route_cost', args: routeArgs }] },
            { text: '(selftest) 线路测算已完成。' },
          ];
      model = scriptedModel(steps);
    }

    const events: unknown[] = [];
    // ⚠️ 这里**兜住**模型异常（而不是让它冒泡出去）：Express 4 不接管 async 处理器的拒绝
    //    → unhandledRejection 会直接打死临时站点，验收脚本就只剩「连接被重置」，
    //    看不到「抛错前其实已经吐了 tool_start/tool_done」。异常如实记进响应；
    //    断言仍然要求「兜底正文 + done 都在」——缺陷不会被这层兜底掩盖。
    let modelError: string | null = null;
    try {
      for await (const ev of runAgentChat({
        history: [{ role: 'user', text: question }],
        model,
        lang,
      })) {
        events.push(ev);
      }
    } catch (error: any) {
      modelError = String(error?.message ?? error);
    }
    res.json({
      scenario,
      osrmConfigured: Boolean(process.env.OSRM_API_BASE),
      geminiKeyPresent: Boolean(process.env.GEMINI_API_KEY),
      chatProvider: chatPlanLabel(),
      events,
      ...(modelError ? { modelError } : {}),
    });
  });
}

// Serve the AI-agent page (/ai) for both dev and production.
let viteDev: Awaited<ReturnType<typeof createViteServer>> | null = null;

async function serveAgentPage(res: Response) {
  if (process.env.NODE_ENV !== 'production' && viteDev) {
    const raw = fs.readFileSync(path.join(process.cwd(), 'ai.html'), 'utf-8');
    const html = await viteDev.transformIndexHtml('/ai', raw);
    res.status(200).set({ 'Content-Type': 'text/html' }).end(html);
    return;
  }
  res.sendFile(path.join(process.cwd(), 'dist', 'ai.html'));
}

// Configure Vite middleware or static server
async function setupServer() {
  if (process.env.NODE_ENV !== 'production') {
    viteDev = await createViteServer({
      server: {
        middlewareMode: true,
        hmr: {
          port: HMR_PORT,
        },
      },
      appType: 'spa',
    });
    app.get(['/ai', '/ai/'], (req: Request, res: Response) => { void serveAgentPage(res); });
    app.use(viteDev.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.get(['/ai', '/ai/'], (req: Request, res: Response) => { void serveAgentPage(res); });
    app.use(express.static(distPath));
    app.get('*', (req: Request, res: Response) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[Server] JIUNENG nexus server listening on http://localhost:${PORT}`);
  });
}

setupServer();
