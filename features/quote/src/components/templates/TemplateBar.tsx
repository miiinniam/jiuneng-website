/**
 * 模板条：一行微字工具条（下拉选模板 + 另存为 + {tp.tpl.del}），不做卡片。
 * 签名见 features/quote/CONTRACT.md §9，C 代理按此签名调用，**不得改动签名**。
 *
 * 口径差异（契约 §3.1）：
 *   scope='internal' → 走 api.ts 的 listTemplates / saveTemplate / deleteTemplate
 *   scope='public'   → 不联网，读写 localStorage['jn-quote-templates']（{id,name,config}[]，上限 20）
 */

import { useCallback, useEffect, useState } from 'react';
import type { QuoteScope } from '../../api';
import { deleteTemplate, listTemplates, saveTemplate, QuoteApiError } from '../../api';
import type { QuoteFormState } from '../../engine/types';
import { panelsText } from '../../i18n/panels';
import { useLang } from '../../../../../src/shell/LangProvider';


export type TemplateBarProps = {
  scope: QuoteScope;
  form: QuoteFormState;
  onApply: (s: QuoteFormState) => void;
};

type LocalTemplate = { id: string; name: string; config: QuoteFormState };

const LOCAL_KEY = 'jn-quote-templates';
const LOCAL_LIMIT = 20;

function readLocal(): LocalTemplate[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (t): t is LocalTemplate =>
        typeof t === 'object' &&
        t !== null &&
        typeof (t as LocalTemplate).id === 'string' &&
        typeof (t as LocalTemplate).name === 'string' &&
        typeof (t as LocalTemplate).config === 'object' &&
        (t as LocalTemplate).config !== null,
    );
  } catch {
    return [];
  }
}

function writeLocal(list: LocalTemplate[]): boolean {
  try {
    window.localStorage.setItem(LOCAL_KEY, JSON.stringify(list.slice(0, LOCAL_LIMIT)));
    return true;
  } catch {
    return false;
  }
}

function newId(): string {
  return `tpl_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function isFormLike(value: unknown): value is QuoteFormState {
  return typeof value === 'object' && value !== null && typeof (value as QuoteFormState).originLat === 'string';
}

export default function TemplateBar({ scope, form, onApply }: TemplateBarProps) {
  const { lang } = useLang();
  const tp = panelsText(lang);
  const [items, setItems] = useState<{ id: string; name: string; config: QuoteFormState }[]>([]);
  const [selected, setSelected] = useState('');
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'error' | 'ok'; text: string } | null>(null);

  const refresh = useCallback(async () => {
    if (scope === 'public') {
      setItems(readLocal());
      return;
    }
    try {
      const list = await listTemplates();
      setItems(list.map((t) => ({ id: t.id, name: t.name, config: t.config })));
    } catch (e) {
      setItems([]);
      const text = e instanceof QuoteApiError ? e.message : tp.tpl.loadFail;
      setMsg({ kind: 'error', text });
    }
  }, [scope]);

  useEffect(() => {
    void refresh();
    // 只在口径变化时重读；refresh 依赖 scope，已经是稳定引用
  }, [refresh]);

  // 换口径/重新拉取后，选中项可能已经不存在
  useEffect(() => {
    if (selected && !items.some((t) => t.id === selected)) setSelected('');
  }, [items, selected]);

  const apply = (id: string) => {
    const found = items.find((t) => t.id === id);
    if (!found) return;
    if (!isFormLike(found.config)) {
      setMsg({ kind: 'error', text: tp.tpl.incomplete });
      return;
    }
    onApply(found.config);
    setMsg({ kind: 'ok', text: tp.tpl.applied(found.name) });
  };

  const startSave = () => {
    setName('');
    setNaming(true);
    setMsg(null);
    setConfirmId(null);
  };

  const doSave = async () => {
    const cleaned = name.trim();
    if (!cleaned) {
      setMsg({ kind: 'error', text: tp.tpl.needName });
      return;
    }
    if (scope === 'public') {
      const list = readLocal();
      if (list.length >= LOCAL_LIMIT) {
        setMsg({ kind: 'error', text: tp.tpl.limit(LOCAL_LIMIT) });
        return;
      }
      const next = [{ id: newId(), name: cleaned, config: form }, ...list];
      if (!writeLocal(next)) {
        setMsg({ kind: 'error', text: tp.tpl.storageWrite });
        return;
      }
      setItems(readLocal());
      setNaming(false);
      setMsg({ kind: 'ok', text: tp.tpl.savedLocal(cleaned) });
      return;
    }

    setBusy(true);
    try {
      await saveTemplate(cleaned, form);
      await refresh();
      setNaming(false);
      setMsg({ kind: 'ok', text: tp.tpl.savedAs(cleaned) });
    } catch (e) {
      setMsg({ kind: 'error', text: e instanceof QuoteApiError ? e.message : tp.tpl.saveFail });
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (id: string) => {
    const target = items.find((t) => t.id === id);
    if (scope === 'public') {
      if (!writeLocal(readLocal().filter((t) => t.id !== id))) {
        setMsg({ kind: 'error', text: tp.tpl.storageDelete });
        return;
      }
      setItems(readLocal());
      setConfirmId(null);
      setSelected('');
      setMsg({ kind: 'ok', text: tp.tpl.deleted(target ? target.name : null) });
      return;
    }

    setBusy(true);
    try {
      await deleteTemplate(id);
      setConfirmId(null);
      setSelected('');
      await refresh();
      setMsg({ kind: 'ok', text: tp.tpl.deleted(target ? target.name : null) });
    } catch (e) {
      setMsg({ kind: 'error', text: e instanceof QuoteApiError ? e.message : tp.tpl.deleteFail });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="q-tpl" role="group" aria-label={tp.tpl.groupAria}>
      <span className="q-tpl-label">{scope === 'internal' ? tp.tpl.labelTpl : tp.tpl.labelLocal}</span>

      <span className="q-tpl-selectwrap">
        <select
          className="q-tpl-select"
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setConfirmId(null);
            if (e.target.value) apply(e.target.value);
          }}
          aria-label={tp.tpl.selectAria}
          disabled={items.length === 0 || busy}
        >
          <option value="">{items.length === 0 ? tp.tpl.empty : tp.tpl.selectPh}</option>
          {items.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </span>

      {naming ? (
        <span className="q-tpl-save">
          <input
            className="q-tpl-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void doSave();
              }
              if (e.key === 'Escape') setNaming(false);
            }}
            placeholder={tp.tpl.namePh}
            maxLength={40}
            aria-label={tp.tpl.namePh}
            autoFocus
          />
          <button type="button" className="q-tpl-btn" onClick={() => void doSave()} disabled={busy}>
            {busy ? tp.tpl.saving : tp.tpl.save}
          </button>
          <button type="button" className="q-tpl-btn q-tpl-btn--quiet" onClick={() => setNaming(false)}>
            {tp.tpl.cancel}
          </button>
        </span>
      ) : (
        <button type="button" className="q-tpl-btn" onClick={startSave} disabled={busy}>
          {tp.tpl.saveAs}
        </button>
      )}

      {confirmId ? (
        <span className="q-tpl-confirm">
          <span className="q-tpl-note">{tp.tpl.confirmDelete}</span>
          <button type="button" className="q-tpl-btn q-tpl-btn--danger" onClick={() => void doDelete(confirmId)} disabled={busy}>
            {tp.tpl.del}
          </button>
          <button type="button" className="q-tpl-btn q-tpl-btn--quiet" onClick={() => setConfirmId(null)}>
            {tp.tpl.cancel}
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="q-tpl-btn q-tpl-btn--quiet"
          onClick={() => setConfirmId(selected || null)}
          disabled={busy || !selected}
        >
          {tp.tpl.del}
        </button>
      )}

      {msg && <span className={`q-tpl-msg q-tpl-msg--${msg.kind}`}>{msg.text}</span>}
    </div>
  );
}
