/**
 * 报价助手（`/quote` · `/quote/internal`）的站内编排端点。
 *
 * 取代原先「把引擎 `/ai/chat` 的 SSE 原样透传」的做法。原做法有三个治不好的问题：
 *  ① 工具在引擎进程内跑 —— 我们既插不进自己的工具，也下不发表单补丁；
 *  ② 引擎 `ai_chat_prompt.py` 要求模型输出「运费明细 + 口岸费明细 + DDP 总计」，
 *     工具回 13 项 breakdown ⇒ **客户能在聊天正文看到成本结构**（工作台卡干净 ≠ 页面干净）；
 *  ③ AI 看不到当前表单（`body.context` 从未下传），客户填完表再问只能被反问。
 *
 * 现在：工具在本服务跑（`server/tools/quoteTools.ts`），金额只从 `run_quote` 拿**区间**，
 * 表单改动通过 `form_patch` 单向下发。引擎退回成纯计算后端。
 */
import type { Request, RequestHandler, Response } from 'express';
import { GoogleGenAI } from '@google/genai';
import {
  deepseekModel,
  geminiModel,
  parseLang,
  runAgentChat,
  sanitizeHistory,
  sseFormat,
  type ChatModel,
} from './agentChat';
import {
  QUOTE_TOOLS,
  createQuoteExecutor,
  quoteSystemPrompt,
  quoteToolLabel,
  type QuoteFormSnapshot,
  type QuoteFormItem,
} from './tools/quoteTools';

export type QuoteAiDeps = {
  /** 地址检索（复用 quoteProxy 的上游，不另写一套） */
  geocode: (q: string) => Promise<{ label: string; lat: number; lng: number } | null>;
  /** 跑一次确定性测算 —— **必须已过公开白名单**（只回区间口径） */
  runQuote: (form: QuoteFormSnapshot) => Promise<Record<string, unknown> | null>;
};

const MAX_ITEMS = 100;

const numOr = (v: unknown, dflt: number): number => {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : dflt;
};

const boolOr = (v: unknown): boolean | undefined => (typeof v === 'boolean' ? v : undefined);

const str = (v: unknown, max = 80): string | undefined => {
  if (typeof v !== 'string') return undefined;
  const s = v.trim().slice(0, max);
  return s || undefined;
};

/** 表单快照白名单：只收前端 form 里这些键，逐键校验类型（不 spread 客户端对象）。 */
export function sanitizeQuoteForm(raw: unknown): QuoteFormSnapshot {
  const f = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const out: QuoteFormSnapshot = {};

  const originLabel = str(f.originLabel, 120);
  const destLabel = str(f.destLabel, 120);
  if (originLabel) out.originLabel = originLabel;
  if (destLabel) out.destLabel = destLabel;

  const coords: Array<[string, number]> = [
    ['originLat', 90], ['originLng', 180], ['destLat', 90], ['destLng', 180],
  ];
  for (const [key, limit] of coords) {
    const v = numOr(f[key], NaN);
    if (Number.isFinite(v) && Math.abs(v) <= limit) (out as Record<string, unknown>)[key] = v;
  }

  const cargoClass = str(f.cargoClass, 40);
  const cargoType = str(f.cargoType, 40);
  if (cargoClass) out.cargoClass = cargoClass;
  if (cargoType) out.cargoType = cargoType;

  const weightKg = numOr(f.weightKg, NaN);
  if (Number.isFinite(weightKg) && weightKg > 0) out.weightKg = weightKg;
  const weightUnit = str(f.weightUnit, 8);
  if (weightUnit) out.weightUnit = weightUnit;

  const vehicleModelId = str(f.vehicleModelId, 60);
  if (vehicleModelId) out.vehicleModelId = vehicleModelId;

  for (const key of ['needLoading', 'needUnloading', 'needCrane', 'allowOversized'] as const) {
    const v = boolOr(f[key]);
    if (v !== undefined) out[key] = v;
  }

  if (Array.isArray(f.items)) {
    const items: QuoteFormItem[] = [];
    for (const entry of f.items.slice(0, MAX_ITEMS)) {
      const it = (entry && typeof entry === 'object' ? entry : {}) as Record<string, unknown>;
      const lengthM = numOr(it.lengthM, NaN);
      const widthM = numOr(it.widthM, NaN);
      const weightKgItem = numOr(it.weightKg, NaN);
      const row: QuoteFormItem = {
        name: str(it.name, 60) ?? '货件',
        lengthM: Number.isFinite(lengthM) ? lengthM : 0,
        widthM: Number.isFinite(widthM) ? widthM : 0,
        heightM: numOr(it.heightM, 0),
        weightKg: Number.isFinite(weightKgItem) ? weightKgItem : 0,
        count: Math.max(1, Math.round(numOr(it.count, 1))),
        stackable: boolOr(it.stackable) ?? false,
        divisible: boolOr(it.divisible) ?? false,
      };
      const id = str(it.id, 60);
      if (id) row.id = id;
      items.push(row);
    }
    if (items.length) out.items = items;
  }

  return out;
}

/**
 * 模型优先级：DeepSeek 优先（OpenAI 兼容、带 function calling）→ Gemini 回退。
 * 都没有则返回空数组，调用方如实回 503（**绝不能让模型绕开工具自己编金额**）。
 */
function formModels(): ChatModel[] {
  const out: ChatModel[] = [];
  const dsKey = (process.env.DEEPSEEK_API_KEY || '').trim();
  if (dsKey) {
    out.push(
      deepseekModel({
        apiKey: dsKey,
        baseUrl: (process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1').trim(),
        model: (process.env.DEEPSEEK_MODEL || 'deepseek-flash').trim(),
      }),
    );
  }
  const gemKey = (process.env.GEMINI_API_KEY || '').trim();
  if (gemKey) {
    out.push(geminiModel(new GoogleGenAI({ apiKey: gemKey })));
  }
  return out;
}

/**
 * `/quote` 的前端沿用引擎协议（消息体是 `content`），而站内编排器用 `text`。
 * 在这里归一，而不是去改两头的协议 —— 前端不动、全站助手的 `sanitizeHistory` 也不动。
 */
function normalizeMessages(input: unknown): unknown[] {
  if (!Array.isArray(input)) return [];
  return input.map((m) => {
    const rec = (m && typeof m === 'object' ? m : {}) as Record<string, unknown>;
    if (typeof rec.text === 'string') return rec;
    return typeof rec.content === 'string' ? { role: rec.role, text: rec.content } : rec;
  });
}

export function createQuoteAiHandler(deps: QuoteAiDeps): RequestHandler {
  return async function handleQuoteAi(req: Request, res: Response): Promise<void> {
    const body = (req.body && typeof req.body === 'object' ? req.body : {}) as Record<string, unknown>;
    // 只认 user/assistant：tool_status 是前端展示行，发给模型会污染上下文
    const history = sanitizeHistory(normalizeMessages(body.messages));
    if (!history.length) {
      res.status(400).json({ ok: false, reason: 'bad_request', message: '请先输入要咨询的问题。' });
      return;
    }

    const models = formModels();
    if (!models.length) {
      res.status(503).json({
        ok: false,
        reason: 'ai_not_configured',
        message: 'AI 助手尚未配置，请稍后再试或直接联系我们。',
      });
      return;
    }

    const lang = parseLang(body.lang);
    const form = sanitizeQuoteForm(body.form);
    const execute = createQuoteExecutor({ geocode: deps.geocode, runQuote: deps.runQuote, form });

    res.status(200).set({
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    res.flushHeaders?.();

    // 断连守卫必须用 res.on('close')：req.on('close') 在 Node 16+ 请求体读完就触发，
    // 会在首个事件前把标志置 true，导致 SSE 一个字节都发不出去（线上事故形态）。
    let closed = false;
    res.on('close', () => { closed = true; });

    const write = (chunk: string): void => {
      if (closed || res.writableEnded) return;
      res.write(chunk);
    };

    let emitted = false;
    let sawQuoteResult = false;
    let textAcc = '';
    let finished = false;
    const finish = (aborted: boolean): void => {
      if (finished) return;
      finished = true;
      write(sseFormat({ event: 'done', data: { tools: 0, rounds: 0, ...(aborted ? { aborted: true } : {}) } }));
      if (!res.writableEnded) res.end();
    };

    for (const model of models) {
      try {
        for await (const ev of runAgentChat({
          history,
          model,
          lang,
          tools: QUOTE_TOOLS,
          execute,
          label: quoteToolLabel,
          system: quoteSystemPrompt(),
        })) {
          if (closed) break;
          // 编排器自己会发 done；这里只记「已发过事件」，用于决定能否回退
          if (ev.event !== 'done') emitted = true;
          if (ev.event === 'text') textAcc += ev.data.content;
          if (ev.event === 'quote_result') sawQuoteResult = true;
          write(sseFormat(ev));
        }
        // 合规话术不能靠模型自觉：本轮给过金额区间而正文没带限定语，由服务端补一句。
        // （客户会截图当报价用；「初步测算、非正式报价」是硬要求，不能概率性满足。）
        if (sawQuoteResult && !/初步|非正式|参考/.test(textAcc)) {
          write(sseFormat({
            event: 'text',
            data: { content: '\n\n（以上为初步测算，非正式报价；最终以书面确认为准。）' },
          }));
        }
        finish(false);
        return;
      } catch (error) {
        // 回退只允许在「一个字都还没发出去」时发生：半途换模型会让客户看到两段自相矛盾的话
        if (emitted) {
          console.error('[quote-ai] 编排中断（已吐出事件，就地收尾）：', (error as Error)?.message ?? error);
          write(sseFormat({
            event: 'text',
            data: { content: '抱歉，这次回答中断了。请再问一次，或直接把需求填进左侧表单测算。' },
          }));
          finish(true);
          return;
        }
        console.warn('[quote-ai] 模型调用失败，尝试下一个：', (error as Error)?.message ?? error);
      }
    }

    console.error('[quote-ai] 所有模型均不可用');
    write(sseFormat({ event: 'error', data: { message: 'AI 助手暂时不可用，请稍后再试。' } }));
    finish(true);
  };
}
