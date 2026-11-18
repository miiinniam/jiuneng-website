/**
 * 测算助手：全站悬浮入口（默认收起）+ 独立页共用的对话本体。
 *
 * 口径：只做初步整理与区间，不报价、不承诺时效、不出内部成本。
 * 协议：`POST /api/agent-chat` 的 SSE（text / tool_start / tool_done / error / done）。
 *
 * 版式约束：圆角 ≤2px、无阴影、无渐变、悬停不位移。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import '../styles/tools-assistant.css';
import { useLang } from '../shell/LangProvider';
import { chatFallbackError, streamChat } from './chat';

type Msg =
  | { id: number; kind: 'user'; text: string }
  | { id: number; kind: 'assistant'; text: string };

let seq = 0;
const nextId = () => (seq += 1);

const SUGGESTIONS = [
  '南宁到河内 20 吨整车，里程和车型怎么算？',
  '拼车测算需要我准备哪些货物参数？',
  '越南进口清关通常要哪些单证？',
];

const EMPTY_INTRO =
  '说明线路、货重与体积（拼车必须给体积），我按站内测算引擎给出里程、车数与参考区间。正式价格与时效由项目经理核定。';

/** 极简排版：**粗体** 与 `- ` 列表，够用就不引依赖。 */
function renderText(text: string) {
  return text.split('\n').map((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return <span key={index} className="tc-gap" />;
    const bullet = /^[-•*]\s+/.test(trimmed);
    const body = trimmed.replace(/^[-•*]\s+/, '');
    const parts = body.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, i) => {
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

export function AssistantChat({ variant }: { variant: 'page' | 'panel' }) {
  const { lang } = useLang();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('尚未调用测算工具');
  const [error, setError] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  useEffect(() => () => abortRef.current?.abort(), []);

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
      setStatus('正在解读问题…');
      setMsgs((prev) => [...prev, { id: nextId(), kind: 'user', text: question }]);

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let assistantId: number | null = null;
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
              setStatus(event.label ? `正在调用：${event.label}` : '正在调用测算工具…');
            } else if (event.type === 'tool_done') {
              setStatus(event.summary || '测算工具已返回结果');
            } else if (event.type === 'error') {
              setError(event.message || chatFallbackError);
            }
          },
        });
        if (assistantId === null) {
          setError(chatFallbackError);
        }
      } catch (err) {
        if (!(err instanceof Error && err.name === 'AbortError')) {
          setError(chatFallbackError);
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

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  };

  return (
    <div className={`tc ${variant === 'page' ? 'tc-page' : 'tc-embedded'}`}>
      <div className="tc-list" ref={listRef}>
        {msgs.length === 0 ? (
          <div className="tc-intro">
            <p className="tc-p">{EMPTY_INTRO}</p>
            <ul className="tc-sugs">
              {SUGGESTIONS.map((line) => (
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
            <div
              key={m.id}
              className={`tc-msg tc-${m.kind}`}
              data-testid="chat-bubble"
              data-kind={m.kind}
            >
              {m.text ? renderText(m.text) : <span className="tc-typing">正在整理…</span>}
            </div>
          ))
        )}
      </div>

      <p className="tc-status" data-testid="chat-tool-status" aria-live="polite">
        {status}
      </p>

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
          placeholder="例如：南宁 → 河内，20 吨，整车"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={busy}
          aria-label="向测算助手提问"
        />
        <button type="submit" className="t-btn tc-send" disabled={busy || !input.trim()}>
          {busy ? '整理中…' : '发送'}
        </button>
      </form>

      <p className="tc-note">初步测算 · 非正式报价 · 非时效承诺</p>
    </div>
  );
}

/** 全站悬浮入口：默认收起，展开时隐藏悬浮按钮。 */
export default function AssistantLauncher() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div className="tc-launcher">
      {open ? (
        <section className="tc-panel" role="dialog" aria-label="测算助手" data-testid="chat-panel">
          <header className="tc-head">
            <div>
              <p className="micro">测算助手</p>
              <p className="tc-sub">里程 · 车型 · 单证方向</p>
            </div>
            <button type="button" className="t-close" onClick={() => setOpen(false)} aria-label="收起助手">
              ✕
            </button>
          </header>
          <AssistantChat variant="panel" />
        </section>
      ) : null}

      {open ? null : (
        <button
          type="button"
          className="tc-fab"
          data-testid="chat-toggle"
          onClick={() => setOpen(true)}
          aria-expanded={open}
        >
          测算助手
        </button>
      )}
    </div>
  );
}
