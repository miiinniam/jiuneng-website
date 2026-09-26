/**
 * /ai 页的「AI 数字员工」对话面板。
 *
 * - 按钮先行（默认只有右下角一个胶囊按钮），点开才展开面板，不给页面添视觉噪音。
 * - 流式消费服务端 SSE（/api/agent-chat）：text / tool_start / tool_done / error / done。
 * - 服务端没配 GEMINI_API_KEY 时返回 error 事件，这里如实显示站内的兜底文案，不假装成功。
 * - 不用任何入场动画：动效不许有能力让内容消失（站内既有规矩），这里干脆不加。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentContent, Lang } from './content';

type Msg =
  | { id: number; kind: 'user'; text: string }
  | { id: number; kind: 'assistant'; text: string }
  | { id: number; kind: 'tool'; text: string; done: boolean; ok: boolean };

let seq = 0;
const nextId = () => (seq += 1);

/** 极简 markdown：**粗体**、`代码`、- 列表、段落。够用就不引依赖。 */
function renderText(text: string): React.ReactNode {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return <span key={i} className="jx-chat-gap" />;
    const isBullet = /^[-•*]\s+/.test(trimmed);
    const content = trimmed.replace(/^[-•*]\s+/, '');
    const parts = content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((p, j) => {
      if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={j}>{p.slice(2, -2)}</strong>;
      if (/^`[^`]+`$/.test(p)) return <code key={j}>{p.slice(1, -1)}</code>;
      return <React.Fragment key={j}>{p}</React.Fragment>;
    });
    return isBullet
      ? <span key={i} className="jx-chat-li">{parts}</span>
      : <span key={i} className="jx-chat-p">{parts}</span>;
  });
}

export const ChatPanel: React.FC<{ t: AgentContent; lang: Lang }> = ({ t, lang }) => {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, open]);

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;

    setInput('');
    setBusy(true);

    const history = [
      ...msgs.filter((m) => m.kind !== 'tool').map((m) => ({ role: m.kind === 'user' ? 'user' : 'assistant', text: m.text })),
      { role: 'user' as const, text: question },
    ];

    const toolId = nextId();
    setMsgs((prev) => [...prev, { id: nextId(), kind: 'user', text: question }]);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch('/api/agent-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history, lang }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error(`http ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let assistantId: number | null = null;
      let sawError = false;

      const ensureAssistant = () => {
        if (assistantId === null) {
          assistantId = nextId();
          setMsgs((prev) => [...prev, { id: assistantId as number, kind: 'assistant', text: '' }]);
        }
        return assistantId;
      };
      const appendAssistant = (chunk: string) => {
        const id = ensureAssistant();
        setMsgs((prev) => prev.map((m) => (m.id === id && m.kind === 'assistant' ? { ...m, text: m.text + chunk } : m)));
      };

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          const evLine = frame.split('\n').find((l) => l.startsWith('event:'));
          const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
          if (!evLine || !dataLine) continue;
          const event = evLine.slice(6).trim();
          let data: Record<string, unknown> = {};
          try { data = JSON.parse(dataLine.slice(5).trim()); } catch { continue; }

          if (event === 'text' && typeof data.content === 'string') {
            appendAssistant(data.content);
          } else if (event === 'tool_start') {
            setMsgs((prev) => [...prev, { id: toolId, kind: 'tool', text: String(data.label ?? ''), done: false, ok: true }]);
          } else if (event === 'tool_done') {
            const ok = data.ok !== false;
            const done = typeof data.summary === 'string' && data.summary ? data.summary : String(data.label ?? '');
            setMsgs((prev) => prev.map((m) => (m.id === toolId && m.kind === 'tool'
              ? { ...m, done: true, ok, text: done }
              : m)));
          } else if (event === 'error') {
            sawError = true;
            appendAssistant(typeof data.message === 'string' ? data.message : t.chat.error);
          }
        }
      }

      if (assistantId === null && !sawError) appendAssistant(t.chat.emptyReply);
    } catch (err) {
      if ((err as { name?: string })?.name !== 'AbortError') {
        setMsgs((prev) => [...prev, { id: nextId(), kind: 'assistant', text: t.chat.error }]);
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [busy, msgs, lang, t.chat.error, t.chat.emptyReply]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send(input);
    }
  };

  return (
    <div className="jx-chat">
      {open ? (
        <section className="jx-chat-panel" role="dialog" aria-label={t.chat.title}>
          <header className="jx-chat-head">
            <div>
              <p className="jx-chat-title">{t.chat.title}</p>
              <p className="jx-chat-sub">{t.chat.subtitle}</p>
            </div>
            <button type="button" className="jx-chat-close" onClick={() => setOpen(false)} aria-label={t.chat.close}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </header>

          <div className="jx-chat-list" ref={listRef}>
            {msgs.length === 0 ? (
              <div className="jx-chat-intro">
                <p className="jx-chat-intro-text">{t.chat.empty}</p>
                <div className="jx-chat-sugs">
                  {t.chat.suggestions.map((s) => (
                    <button type="button" key={s} className="jx-chat-sug" onClick={() => void send(s)} disabled={busy}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              msgs.map((m) => (
                m.kind === 'tool' ? (
                  <p key={m.id} className={`jx-chat-tool ${m.done ? (m.ok ? 'is-done' : 'is-off') : 'is-live'}`}>{m.text}</p>
                ) : (
                  <div key={m.id} className={`jx-chat-msg is-${m.kind}`}>
                    {m.text ? renderText(m.text) : <span className="jx-chat-typing">{t.chat.thinking}</span>}
                  </div>
                )
              ))
            )}
          </div>

          <div className="jx-chat-inputbar">
            <textarea
              ref={inputRef}
              className="jx-chat-input"
              rows={1}
              value={input}
              placeholder={t.chat.placeholder}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
            />
            <button
              type="button"
              className="jx-chat-send"
              onClick={() => void send(input)}
              disabled={busy || !input.trim()}
              aria-label={t.chat.send}
            >
              {busy ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
                  <path d="M12 3v18" opacity="0" />
                  <circle cx="12" cy="12" r="8" strokeDasharray="38 12" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M4 12l16-8-6.5 16L11 14l-7-2z" />
                </svg>
              )}
            </button>
          </div>
          <p className="jx-chat-disclaimer">{t.chat.disclaimer}</p>
        </section>
      ) : null}

      {open ? null : (
        <button
          type="button"
          className="jx-chat-fab"
          onClick={() => setOpen(true)}
          aria-expanded={open}
          aria-label={t.chat.open}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 11.5a8.4 8.4 0 01-9 8.4 9.6 9.6 0 01-2.9-.4L4 21l1.3-3.6A8.2 8.2 0 013 11.5 8.4 8.4 0 0112 3a8.4 8.4 0 019 8.5z" />
          </svg>
          <span>{t.chat.open}</span>
        </button>
      )}
    </div>
  );
};
