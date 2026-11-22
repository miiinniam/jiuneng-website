/**
 * 测算助手：全站悬浮入口（默认收起）+ 独立页共用的对话本体。
 *
 * 口径：只做初步整理与区间，不报价、不承诺时效、不出内部成本。
 * 协议：`POST /api/agent-chat` 的 SSE（text / tool_start / tool_done / error / done）。
 *
 * v7.1 交互改动（用户指定）：
 *  1) 面板可拉高（拖顶部把手，高度记忆），宽度放大到 560px；
 *  2) 关闭面板**不清空**对话（localStorage 持久化，仅「清空对话」可清）；
 *  3) 每条回答后给「下一步」：看分项明细 / 换车型重算 / 打开车辆匹配 / 提交正式询价。
 *
 * 版式约束：圆角 ≤2px、无阴影、无渐变、悬停不位移。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import '../styles/tools-assistant.css';
import { useLang } from '../shell/LangProvider';
import { getAssistant, getCommon } from '../content';
import type { AssistantCopy } from '../content/zh/assistant';
import { chatFallbackError, streamChat } from './chat';

type Action = { label: string; href?: string; prompt?: string };

type Msg =
  | { id: number; kind: 'user'; text: string }
  | { id: number; kind: 'assistant'; text: string; actions?: Action[] };

let seq = 0;
const nextId = () => (seq += 1);

const STORE_KEY = 'jn-assistant-v1';
const HEIGHT_KEY = 'jn-assistant-h';
const MAX_KEPT = 40;

/** 每条回答后能点的「下一步」——按本轮真正调用过的工具决定，不猜。 */
function actionsFor(tools: Set<string>, a: AssistantCopy): Action[] {
  const acts: Action[] = [];
  if (tools.has('quote_customs_range')) acts.push({ label: a.actions.docDetail, href: '/platform/customs' });
  if (tools.has('query_route_cost')) acts.push({ label: a.actions.reMatch, prompt: a.actions.reMatchPrompt });
  if (tools.has('match_vehicles')) acts.push({ label: a.actions.vehicleMatch, href: '/platform/fleet' });
  acts.push({ label: a.actions.submitQuote, href: '/contact' });
  return acts;
}

/** 极简排版：**粗体** 与 `- ` 列表，够用就不引依赖。 */
function renderText(text: string) {
  return text.split('\n').map((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return <span key={index} className="tc-gap" />;
    const bullet = /^[-•*]\s+/.test(trimmed);
    const body = trimmed.replace(/^[-•*]\s+/, '');
    const parts = body
      .split(/(\*\*[^*]+\*\*)/g)
      .filter(Boolean)
      .map((part, i) => {
        if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
        return <span key={i}>{part}</span>;
      });
    return bullet ? (
      <span key={index} className="tc-li">
        {parts}
      </span>
    ) : (
      <span key={index} className="tc-p">
        {parts}
      </span>
    );
  });
}

function loadMsgs(): Msg[] {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((m): m is Msg => {
        const o = m as Msg;
        return (
          !!o &&
          typeof o.id === 'number' &&
          (o.kind === 'user' || o.kind === 'assistant') &&
          typeof o.text === 'string'
        );
      })
      .slice(-MAX_KEPT);
  } catch {
    return [];
  }
}

type StatusState =
  | { key: 'idle' | 'reading' | 'callingGeneric' | 'none' }
  | { key: 'calling'; label?: string }
  | { key: 'summary'; text?: string };

export function AssistantChat({ variant }: { variant: 'page' | 'panel' }) {
  const { lang } = useLang();
  const a = getAssistant(lang);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<StatusState>({ key: 'idle' });
  const [error, setError] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 首屏恢复上次对话（关闭面板不再丢历史）
  useEffect(() => {
    const saved = loadMsgs();
    if (saved.length) {
      setMsgs(saved);
      seq = Math.max(seq, ...saved.map((m) => m.id));
    }
  }, []);

  // 只在空闲时落盘，避免流式过程中频繁写
  useEffect(() => {
    if (busy) return;
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(msgs.slice(-MAX_KEPT)));
    } catch {
      /* 隐私模式忽略 */
    }
  }, [msgs, busy]);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  useEffect(() => () => abortRef.current?.abort(), []);

  // 恢复历史后不要把「尚未调用测算工具」一直挂在状态条上
  useEffect(() => {
    if (msgs.length > 0) setStatus({ key: 'none' });
  }, [msgs.length]);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    setMsgs([]);
    setStatus({ key: 'idle' });
    setError('');
    try {
      window.localStorage.removeItem(STORE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const send = useCallback(
    async (raw: string) => {
      const question = raw.trim();
      if (!question || busy) return;

      const history = [
        ...msgs.map((m) => ({ role: m.kind === 'user' ? ('user' as const) : ('assistant' as const), text: m.text })),
        { role: 'user' as const, text: question },
      ];

      setInput('');
      setError('');
      setBusy(true);
      setStatus({ key: 'reading' });
      setMsgs((prev) => [...prev, { id: nextId(), kind: 'user', text: question }]);

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let assistantId: number | null = null;
      const usedTools = new Set<string>();
      const ensure = () => {
        if (assistantId === null) {
          assistantId = nextId();
          const id = assistantId;
          setMsgs((prev) => [...prev, { id, kind: 'assistant', text: '' }]);
        }
        return assistantId;
      };

      try {
        await streamChat({
          messages: history,
          lang,
          signal: ctrl.signal,
          onEvent: (event) => {
            if (event.type === 'text') {
              if (!event.content) return;
              const id = ensure();
              setMsgs((prev) =>
                prev.map((m) => (m.id === id && m.kind === 'assistant' ? { ...m, text: m.text + event.content } : m)),
              );
            } else if (event.type === 'tool_start') {
              if (event.name) usedTools.add(event.name);
              setStatus(event.label ? { key: 'calling', label: event.label } : { key: 'callingGeneric' });
            } else if (event.type === 'tool_done') {
              if (event.name) usedTools.add(event.name);
              setStatus({ key: 'summary', text: event.summary });
            } else if (event.type === 'error') {
              setError(event.message || chatFallbackError(lang));
            }
          },
        });
        if (assistantId === null) {
          setError(chatFallbackError(lang));
        } else {
          // 回答结束就挂上「下一步」：指向真正用得上的那一页/那一次重算
          const id = assistantId;
          const actions = actionsFor(usedTools, a);
          setMsgs((prev) => prev.map((m) => (m.id === id && m.kind === 'assistant' ? { ...m, actions } : m)));
        }
      } catch (err) {
        if (!(err instanceof Error && err.name === 'AbortError')) {
          setError(chatFallbackError(lang));
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, lang, msgs],
  );

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  const statusText =
    status.key === 'idle'
      ? a.status.idle
      : status.key === 'reading'
        ? a.status.reading
        : status.key === 'calling'
          ? a.status.calling.replace('{label}', status.label ?? '')
          : status.key === 'callingGeneric'
            ? a.status.callingGeneric
            : status.key === 'summary'
              ? status.text || a.status.done
              : '';

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  };

  return (
    <div className={`tc ${variant === 'page' ? 'tc-page' : 'tc-embedded'}`}>
      {msgs.length > 0 ? (
        <div className="tc-tools">
          <button type="button" className="t-link" onClick={clear} data-testid="chat-clear">
            {a.ui.clear}
          </button>
        </div>
      ) : null}

      <div className="tc-list" ref={listRef}>
        {msgs.length === 0 ? (
          <div className="tc-intro">
            <p className="tc-p">{a.intro}</p>
            <ul className="tc-sugs">
              {a.suggestions.map((line) => (
                <li key={line}>
                  <button type="button" className="tc-sug" onClick={() => void send(line)} disabled={busy}>
                    {line}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          msgs.map((m) => (
            <div key={m.id} className="tc-row">
              <div className={`tc-msg tc-${m.kind}`} data-testid="chat-bubble" data-kind={m.kind}>
                {m.text ? renderText(m.text) : <span className="tc-typing">{a.ui.typing}</span>}
              </div>
              {m.kind === 'assistant' && m.actions?.length ? (
                <div className="tc-acts" data-testid="chat-actions">
                  {m.actions.map((a) =>
                    a.href ? (
                      <a key={a.label} className="tc-act" href={a.href}>
                        {a.label}
                      </a>
                    ) : (
                      <button
                        key={a.label}
                        type="button"
                        className="tc-act"
                        disabled={busy}
                        onClick={() => void send(a.prompt ?? '')}
                      >
                        {a.label}
                      </button>
                    ),
                  )}
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>

      {msgs.length > 0 ? (
        <p className="tc-status" data-testid="chat-tool-status" aria-live="polite">
          {statusText}
        </p>
      ) : null}

      {error ? (
        <p className="tc-error" role="alert">
          {error}
        </p>
      ) : null}

      <form className="tc-inputbar" onSubmit={onSubmit}>
        <textarea
          className="tc-input"
          rows={2}
          value={input}
          placeholder={a.ui.placeholder}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={busy}
          aria-label={a.ui.askAria}
        />
        <button type="submit" className="t-btn tc-send" disabled={busy || !input.trim()}>
          {busy ? a.ui.sending : a.ui.send}
        </button>
      </form>

      <p className="tc-note">{a.ui.note}</p>
    </div>
  );
}

/** 全站悬浮入口：默认收起，展开时隐藏悬浮按钮。面板高度可拖拽并记忆。 */
export default function AssistantLauncher() {
  const { lang } = useLang();
  const c = getCommon(lang).assistant;
  const [open, setOpen] = useState(false);
  const [height, setHeight] = useState(620);
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);

  // 深链：?chat=1 直接展开（用于「联系我们/报价」页外链与内部验收）
  useEffect(() => {
    try {
      const want = new URLSearchParams(window.location.search).get('chat');
      if (want === '1') setOpen(true);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    try {
      const saved = Number(window.localStorage.getItem(HEIGHT_KEY));
      if (Number.isFinite(saved) && saved >= 420) {
        setHeight(Math.min(saved, Math.round(window.innerHeight * 0.92)));
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const onGripDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = { startY: event.clientY, startH: height };
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
  };

  const onGripMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const next = Math.min(Math.max(drag.startH + (drag.startY - event.clientY), 420), Math.round(window.innerHeight * 0.92));
    setHeight(next);
  };

  const onGripUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    try {
      (event.target as HTMLElement).releasePointerCapture(event.pointerId);
      window.localStorage.setItem(HEIGHT_KEY, String(height));
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="tc-launcher">
      {open ? (
        <section
          className="tc-panel"
          role="dialog"
          aria-label={c.fab}
          data-testid="chat-panel"
          style={{ height: `${height}px` }}
        >
          <div
            className="tc-grip"
            role="separator"
            aria-label={c.grip}
            onPointerDown={onGripDown}
            onPointerMove={onGripMove}
            onPointerUp={onGripUp}
            onPointerCancel={onGripUp}
          />
          <header className="tc-head">
            <div>
              <p className="micro">{c.title}</p>
              <p className="tc-sub">{c.sub}</p>
            </div>
            <button type="button" className="t-close" onClick={() => setOpen(false)} aria-label={c.close}>
              ✕
            </button>
          </header>
          <AssistantChat variant="panel" />
        </section>
      ) : null}

      {open ? null : (
        <button type="button" className="tc-fab" data-testid="chat-toggle" onClick={() => setOpen(true)} aria-expanded={open}>
          {c.fab}
        </button>
      )}
    </div>
  );
}
