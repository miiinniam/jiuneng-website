import express, { Request, Response } from 'express';
import fs from 'fs';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
import {
  geminiModel,
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

// API: Health probe —— 如实反映依赖状态。
// 轻量模式必须永远快、永远 200（UptimeRobot 保活依赖它）；深探测只在 ?deep=1 时实时打引擎。
// 环境变量：HEALTH_PROBE_MS（后台探查间隔，默认 60s）、HEALTH_DEEP_TIMEOUT_MS（deep 预算，默认 3s）、
//          HEALTH_PROBE_TIMEOUT_MS（后台探查预算，默认 5s）。预算归一由 probeEngine 负责（NaN/0/负数回落默认）。
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

/** 只暴露 host，绝不带路径/查询串（避免把内部路径或密钥泄给监控页面）。 */
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

  // 轻量档：只读后台探针的缓存结果，绝不在这里实时探测（否则保活请求会被拖死）
  const degraded = snap.configured && snap.lastProbe !== null && !snap.lastProbe.ok;
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
    const model = demo ?? geminiModel(getGeminiClient());
    for await (const ev of runAgentChat({ history, model, lang })) {
      if (closed) break;
      res.write(sseFormat(ev));
    }
  } catch (error: any) {
    console.error('agent-chat failed:', error);
    if (!closed) {
      res.write(sseFormat({ event: 'error', data: { message: agentI18n[lang].chat.error } }));
    }
  } finally {
    res.end();
  }
});

// API: OSRM++ 测算（官网唯一出口，浏览器拿不到引擎地址）
// 出参白名单在 server/osrmQuote.ts 统一重建：只回里程/时长/车数/车型 + 参考价区间（售价 ±10%），
// 内部成本、利润、毛利率、口岸费用明细一律不出。对客口径：初步测算，非正式报价。
app.post('/api/osrm-quote', async (req: Request, res: Response) => {
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

    const steps: ModelEvent[] = scenario === 'info'
      ? [
          { calls: [{ name: 'lookup_service_info', args: { topic: 'service' } }] },
          { text: '(selftest) 站内能力清单已取到。' },
        ]
      : [
          { calls: [{ name: 'query_route_cost', args: { origin: '南宁', destination: '河内', border: '友谊关口岸', weight_kg: 20000, mode: 'full_truck', vehicle_model_id: 'flatbed_13m' } }] },
          { text: '(selftest) 线路测算已完成。' },
        ];

    const events: unknown[] = [];
    for await (const ev of runAgentChat({
      history: [{ role: 'user', text: question }],
      model: scriptedModel(steps),
      lang,
    })) {
      events.push(ev);
    }
    res.json({
      scenario,
      osrmConfigured: Boolean(process.env.OSRM_API_BASE),
      geminiKeyPresent: Boolean(process.env.GEMINI_API_KEY),
      events,
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
