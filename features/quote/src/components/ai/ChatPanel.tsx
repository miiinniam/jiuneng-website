/**
 * AI 助手面板（SSE 流式）。
 * 签名见 features/quote/CONTRACT.md §9，C 代理按此签名调用，**不得改动原有必填 props**。
 * 新增的三个 props（form / onFormPatch / onQuoteResult）全部可选，不传即与改造前完全一致。
 *
 * 数据只走 api.ts 的 aiChat()：
 *   text        → onText 回调（这里逐段拼到当前助手消息上）
 *   form_patch  → onFormPatch（页面拿 useQuoteForm 的 patch() 写表单）
 *   quote_result→ onQuoteResult（页面用与「提交测算」同一个 setter 展示结果面板）
 *   error       → 抛 QuoteApiError（message 已是中文，直接显示）
 *   done        → Promise resolve
 *   tool_*      → api.ts 不回调，所以「正在计算…/已算完」这两行由本组件按
 *                 「等首个 token / 收到首个 token」近似呈现。
 */

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { aiChat, QuoteApiError, type ChatFormSnapshot, type ChatMessage } from '../../api';
import type { LatLng } from '../../engine/types';
import { extractRoutePair } from './extractCoords';
import RichText from './RichText';
import WorkspacePanel, { type WsAction } from '../workspace/WorkspacePanel';
import type { WsPlan } from '../workspace/plan';
import { strings, type Lang } from '../../i18n/strings';
import { panelsText } from '../../i18n/panels';

export type ChatPanelProps = {
  open: boolean;
  onClose: () => void;
  context: Record<string, unknown>;
  onPickRoute: (origin: LatLng, destination: LatLng) => void;
  /** 当前已算出的方案（引擎结果投影）。有值且不在流式中时，在回复下方挂工作台卡片。 */
  plan?: WsPlan | null;
  /** VND / 1 CNY，用于卡片上的人民币折算 */
  cnyVnd?: number | null;
  /** VND / 1 USD，用于卡片上的美元折算 */
  usdVnd?: number | null;
  onWorkspaceAction?: (action: WsAction) => void;
  /** 用户这句话里的业务参数（重量/车型/货类），页面据此更新表单 */
  onHints?: (text: string) => void;
  /** 界面语言：跟随站点（?lang= → localStorage:jiuneng-lang → 浏览器 → zh） */
  lang?: Lang;
  /** 当前表单快照（后端白名单键，见 api.ts 的 ChatFormSnapshot）。不传 = AI 看不到表单 */
  form?: ChatFormSnapshot;
  /** 服务端 form_patch：AI 改表单，页面用 useQuoteForm 的 patch() 落地 */
  onFormPatch?: (patch: Record<string, unknown>, reason: string) => void;
  /** 服务端 quote_result：确定性测算结果，页面走与「提交测算」同一个结果 setter */
  onQuoteResult?: (result: Record<string, unknown>) => void;
};

/** 首屏四个咨询入口由 i18n 提供（strings.welcome.entries），跟着站点语言走 */

function emptyReply(lang: Lang): string {
  return panelsText(lang).chat.emptyReply;
}

function isAbort(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { name?: string }).name === 'AbortError';
}

function errorText(e: unknown, lang: Lang): string {
  if (e instanceof QuoteApiError && e.message) return e.message;
  if (e instanceof Error && e.message) return e.message;
  return panelsText(lang).chat.unavailable;
}

export default function ChatPanel({
  open,
  onClose,
  context,
  onPickRoute,
  plan = null,
  cnyVnd = null,
  usdVnd = null,
  onWorkspaceAction,
  onHints,
  lang = 'zh',
  form,
  onFormPatch,
  onQuoteResult,
}: ChatPanelProps) {
  const t = strings(lang);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);

  /** 复制一条助手回复的原文（markdown 原样，粘到微信/邮件不失真）。 */
  const copyMessage = useCallback(async (index: number, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // http:// 或旧浏览器没有 clipboard API：退回 textarea 选区法
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } catch {
        /* 复制失败就静默——不打断对话 */
      }
      document.body.removeChild(ta);
    }
    setCopied(index);
    window.setTimeout(() => setCopied((cur) => (cur === index ? null : cur)), 1600);
  }, []);

  const bodyRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const messagesRef = useRef<ChatMessage[]>([]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // 只滚聊天容器内部，别用 scrollIntoView（会把整页带着跳）
  useEffect(() => {
    const node = bodyRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, error]);

  // 关闭即中止：面板收起后还在流的请求没有出口
  useEffect(() => {
    if (!open) abortRef.current?.abort();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 60);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const setStatusDone = useCallback((label: string) => {
    setMessages((prev) => {
      const copy = prev.slice();
      for (let i = copy.length - 1; i >= 0; i -= 1) {
        if (copy[i].role === 'tool_status' && copy[i].toolStatus === 'running') {
          copy[i] = { ...copy[i], content: label, toolStatus: 'done' };
          break;
        }
      }
      return copy;
    });
  }, []);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busyRef.current) return;

      // 先把这句里的业务参数抽出来喂给表单/工作台（13 米、25 吨、冷链…），
      // 这样卡片的数字来自引擎而不是聊天文字。
      onHints?.(text);

      setInput('');
      setError(null);

      const history: ChatMessage[] = messagesRef.current
        .filter((m) => m.role !== 'tool_status')
        .map((m) => ({ role: m.role, content: m.content }))
        .filter((m) => m.content.trim() !== '');

      const userMsg: ChatMessage = { role: 'user', content: text };
      const payloadMessages: ChatMessage[] = [...history, userMsg];

      setMessages((prev) => [
        ...prev,
        userMsg,
        { role: 'tool_status', content: panelsText(lang).chat.computing, toolStatus: 'running' },
        { role: 'assistant', content: '' },
      ]);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      busyRef.current = true;
      setBusy(true);

      let accum = '';
      let firstToken = false;

      try {
        // context 原样进请求体（C 传什么就传什么，这里不做映射）；
        // form 是后端白名单里的表单快照（不传时 JSON.stringify 会丢掉该键，请求体与改造前一致）；
        // 后两个回调不传时 form_patch / quote_result 与其它未知事件一样被忽略。
        await aiChat({ messages: payloadMessages, context, form, lang }, (piece) => {
          accum += piece;
          if (!firstToken) {
            firstToken = true;
            setStatusDone(panelsText(lang).chat.done);
          }
          setMessages((prev) => {
            const copy = prev.slice();
            for (let i = copy.length - 1; i >= 0; i -= 1) {
              if (copy[i].role === 'assistant') {
                copy[i] = { ...copy[i], content: copy[i].content + piece };
                break;
              }
            }
            return copy;
          });
        }, controller.signal, { onFormPatch, onQuoteResult });

        if (!firstToken) setStatusDone(panelsText(lang).chat.failed);
        if (!accum.trim()) {
          setMessages((prev) => {
            const copy = prev.slice();
            for (let i = copy.length - 1; i >= 0; i -= 1) {
              if (copy[i].role === 'assistant' && !copy[i].content) {
                copy[i] = { ...copy[i], content: emptyReply(lang) };
                break;
              }
            }
            return copy;
          });
        }

        // 只有真的识别出成对的 lat/lng 才动地图，且一轮只动一次
        const pair = extractRoutePair(accum);
        if (pair) onPickRoute(pair[0], pair[1]);
      } catch (e) {
        if (!isAbort(e)) {
          setError(errorText(e, lang));
          // 失败的这一轮不留在对话里（空的助手占位 + 还在转的状态行都清掉）
          setMessages((prev) =>
            prev.filter(
              (m) =>
                !(m.role === 'assistant' && m.content === '') &&
                !(m.role === 'tool_status' && m.toolStatus === 'running'),
            ),
          );
        }
      } finally {
        busyRef.current = false;
        setBusy(false);
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [context, form, onPickRoute, onFormPatch, onQuoteResult, setStatusDone],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    busyRef.current = false;
    setBusy(false);
    setStatusDone(panelsText(lang).chat.aborted);
  }, [setStatusDone]);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    busyRef.current = false;
    setBusy(false);
    setError(null);
    setMessages([]);
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  return (
    <aside className="q-chat" data-open={open ? 'true' : 'false'} aria-hidden={!open} inert={!open} aria-label={panelsText(lang).chat.panelAria}>
      <div className="q-chat-head">
        <div className="q-chat-headtext">
          <p className="micro">{t.header.online}</p>
          <p className="q-chat-title">{t.header.title}</p>
        </div>
        <div className="q-chat-headtools">
          <button
            type="button"
            className="q-chat-new"
            onClick={() => {
              clear();
              inputRef.current?.focus();
            }}
            disabled={messages.length === 0 && !error}
          >
            {t.header.newChat}
          </button>
          <button type="button" className="q-chat-close" onClick={onClose} aria-label={t.header.close}>
            <span aria-hidden="true">×</span>
          </button>
        </div>
      </div>

      <div className="q-chat-body" ref={bodyRef}>
        {messages.length === 0 && (
          <div className="q-chat-empty">
            <p className="q-chat-welcome-t">{t.welcome.title}</p>
            <p className="q-chat-lede">{t.welcome.lede}</p>
            <p className="q-chat-vs">{t.welcome.vs}</p>
            <p className="micro q-chat-welcome-h">{t.welcome.quick}</p>
            <ul className="q-chat-entries">
              {t.welcome.entries.map((e) => (
                <li key={e.n}>
                  <button type="button" className="q-chat-entry" onClick={() => void send(e.q)}>
                    <span className="q-chat-entry-n">{e.n}</span>
                    <span className="q-chat-entry-t">{e.t}</span>
                    <span className="q-chat-entry-s">{e.s}</span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="q-chat-welcome-note">{t.welcome.note}</p>
          </div>
        )}

        {messages.map((m, i) => {
          if (m.role === 'tool_status') {
            return (
              <p
                key={`tool-${i}`}
                className="q-chat-tool"
                data-status={m.toolStatus === 'running' ? 'running' : 'done'}
              >
                <span aria-hidden="true">{m.toolStatus === 'running' ? '▸' : '·'}</span>
                <span>{m.content || panelsText(lang).chat.computing}</span>
              </p>
            );
          }
          const isUser = m.role === 'user';
          const streaming = !isUser && busy && i === messages.length - 1;
          return (
            <div key={`${m.role}-${i}`} className={`q-chat-msg${isUser ? ' q-chat-msg--user' : ''}`}>
              <p className="q-chat-role">{isUser ? t.role.you : t.role.assistant}</p>
              {isUser ? (
                <p className="q-chat-text">{m.content}</p>
              ) : (
                <div className="q-chat-rich">
                  {m.content ? (
                    <RichText text={m.content} />
                  ) : (
                    <p className="q-chat-text">{t.composer.thinking}</p>
                  )}
                  {streaming && <span className="q-chat-caret" aria-hidden="true" />}
                  {!streaming && m.content ? (
                    <button
                      type="button"
                      className="q-chat-copy"
                      onClick={() => void copyMessage(i, m.content)}
                    >
                      {copied === i ? t.msg.copied : t.msg.copy}
                    </button>
                  ) : null}
                </div>
              )}
            </div>
          );
        })}

        {error && <p className="q-chat-err">{error}</p>}

        {/* 工作台卡片：数字来自引擎，不是模型生成的文字。
            只在「有结果 + 不在流式中」时出现，避免边算边跳。 */}
        {messages.length > 0 && plan && !busy ? (
          <div className="q-chat-ws">
            <WorkspacePanel
              plan={plan}
              cnyVnd={cnyVnd}
              usdVnd={usdVnd}
              lang={lang}
              onAction={(a) => onWorkspaceAction?.(a)}
            />
          </div>
        ) : null}
      </div>

      <div className="q-chat-composer">
        <textarea
          ref={inputRef}
          className="q-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t.composer.placeholder}
          rows={3}
          aria-label={t.composer.placeholder}
        />
        <div className="q-chat-foot">
          <button type="button" className="q-chat-btn q-chat-btn--ghost" onClick={clear} disabled={messages.length === 0 && !error}>
            {t.composer.clear}
          </button>
          {busy ? (
            <button type="button" className="q-chat-btn q-chat-btn--stop" onClick={stop}>
              {t.composer.stop}
            </button>
          ) : (
            <button type="button" className="q-chat-btn" onClick={() => void send(input)} disabled={!input.trim()}>
              {t.composer.send}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
