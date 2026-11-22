/**
 * 测算助手 SSE 客户端（`POST /api/agent-chat`）。
 *
 * 服务端事件（契约）：`text` / `tool_start` / `tool_done` / `error` / `done`。
 * 不引第三方库：`fetch` + `ReadableStream` 手解 SSE 帧。
 *
 * 已知坑（沿用旧站实现的经验）：
 *  - 帧分隔符必须同时容忍 `\n\n` 与 `\r\n\r\n`；
 *  - `data:` 只取单行，多行 data 的 SSE 本服务端不产出，不实现；
 *  - 流结束但一个字都没有时，由调用方补一句兜底文案（这里不编话术）。
 */

import { getTools } from '../content';

export type ChatMessage = { role: 'user' | 'assistant'; text: string };

export type ChatStreamEvent =
  | { type: 'text'; content: string }
  | { type: 'tool_start'; name: string; label: string }
  | { type: 'tool_done'; name: string; label: string; ok: boolean; summary: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type ChatStreamOptions = {
  messages: ChatMessage[];
  lang: 'zh' | 'vi' | 'en';
  signal?: AbortSignal;
  onEvent: (event: ChatStreamEvent) => void;
};

export class ChatStreamError extends Error {
  readonly reason: string;

  constructor(reason: string, message: string) {
    super(message);
    this.name = 'ChatStreamError';
    this.reason = reason;
  }
}

export function chatFallbackError(lang: 'zh' | 'vi' | 'en'): string {
  return getTools(lang).api.chatFallback;
}

function parseFrame(frame: string, fallback: string): ChatStreamEvent | null {
  const lines = frame.split(/\r?\n/);
  const eventLine = lines.find((line) => line.startsWith('event:'));
  const dataLine = lines.find((line) => line.startsWith('data:'));
  if (!eventLine) return null;

  const event = eventLine.slice(6).trim();
  let data: Record<string, unknown> = {};
  if (dataLine) {
    try {
      const parsed = JSON.parse(dataLine.slice(5).trim()) as unknown;
      if (parsed && typeof parsed === 'object') data = parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  const str = (value: unknown): string => (typeof value === 'string' ? value : '');

  switch (event) {
    case 'text':
      return { type: 'text', content: str(data.content) };
    case 'tool_start':
      return { type: 'tool_start', name: str(data.name), label: str(data.label) };
    case 'tool_done':
      return {
        type: 'tool_done',
        name: str(data.name),
        label: str(data.label),
        ok: data.ok !== false,
        summary: str(data.summary) || str(data.label),
      };
    case 'error':
      return { type: 'error', message: str(data.message) || fallback };
    case 'done':
      return { type: 'done' };
    default:
      return null;
  }
}

export async function streamChat({ messages, lang, signal, onEvent }: ChatStreamOptions): Promise<void> {
  const fallback = chatFallbackError(lang);
  let res: Response;
  try {
    res = await fetch('/api/agent-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ messages, lang }),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') throw err;
    throw new ChatStreamError('network', fallback);
  }

  if (!res.ok || !res.body) {
    throw new ChatStreamError(`status_${res.status}`, fallback);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // 统一换行后再切帧，`\r\n\r\n` 与 `\n\n` 都能命中
      buffer = buffer.replace(/\r\n/g, '\n');
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        const event = parseFrame(frame, fallback);
        if (event) onEvent(event);
      }
    }
    const tail = parseFrame(buffer.replace(/\r\n/g, '\n'), fallback);
    if (tail) onEvent(tail);
  } finally {
    reader.releaseLock();
  }
}

