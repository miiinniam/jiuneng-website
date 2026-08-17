import express, { Request, Response } from 'express';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';

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

// API: Health probe
app.get('/api/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', time: new Date().toISOString() });
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
      model: 'gemini-2.5-flash',
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

// Configure Vite middleware or static server
async function setupServer() {
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        hmr: {
          port: HMR_PORT,
        },
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
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
