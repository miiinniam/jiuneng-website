// ChatPanel 依赖的 SSE 契约 —— 用假 fetch 在 node 里跑，不需要浏览器/网络。
// 跑法：npx tsx --test features/quote/src/components/ai/chatStream.test.ts
//
// 为什么 D 代理要测这里：面板只拿到 api.ts 的 onText 回调，所以必须确认
// （1）text 增量是逐段到的；（2）done 会 resolve；（3）error 抛中文 message；
// （4）tool_start / tool_done 不会被当成正文（api.ts 丢弃，面板另按「首个 token」近似状态行）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { aiChat, QuoteApiError } from '../../api';

function stubFetch(frames: string[]): () => void {
  const original = globalThis.fetch;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
  globalThis.fetch = (async () =>
    new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

test('顺序收：三段 text → 拼接顺序与分段都对，done 后 resolve', async () => {
  const restore = stubFetch([
    sse('tool_start', { name: 'calculate_freight_cost', params: {} }),
    sse('text', { content: '从友谊关' }),
    sse('tool_done', { name: 'calculate_freight_cost', result: { distance_km: 172.4 } }),
    sse('text', { content: '到河内约 ' }),
    sse('text', { content: '172 公里。' }),
    sse('done', { usage: {} }),
  ]);
  const pieces: string[] = [];
  try {
    await aiChat({ messages: [{ role: 'user', content: 'hi' }] }, (t) => pieces.push(t));
  } finally {
    restore();
  }
  assert.deepEqual(pieces, ['从友谊关', '到河内约 ', '172 公里。']);
  // tool_* 不产生正文 —— 面板因此只能按「首个 token」近似「正在计算…/已算完」
  assert.equal(pieces.join(''), '从友谊关到河内约 172 公里。');
});

test('error 事件：抛 QuoteApiError，message 原样是中文', async () => {
  const restore = stubFetch([sse('error', { message: '上游模型繁忙，请稍后再试' })]);
  try {
    await assert.rejects(
      () => aiChat({ messages: [{ role: 'user', content: 'hi' }] }, () => undefined),
      (e: unknown) => e instanceof QuoteApiError && e.message === '上游模型繁忙，请稍后再试',
    );
  } finally {
    restore();
  }
});

test('半截 JSON 不打断流（畸形帧直接丢）', async () => {
  const restore = stubFetch([
    'event: text\ndata: {"content":"前段"\n\n',
    sse('text', { content: '后段' }),
    sse('done', {}),
  ]);
  const pieces: string[] = [];
  try {
    await aiChat({ messages: [{ role: 'user', content: 'hi' }] }, (t) => pieces.push(t));
  } finally {
    restore();
  }
  assert.deepEqual(pieces, ['后段']);
});

test('没有 done 但流结束：正常 resolve（面板不会卡在转圈）', async () => {
  const restore = stubFetch([sse('text', { content: '短答' })]);
  const pieces: string[] = [];
  try {
    await aiChat({ messages: [{ role: 'user', content: 'hi' }] }, (t) => pieces.push(t));
  } finally {
    restore();
  }
  assert.deepEqual(pieces, ['短答']);
});
