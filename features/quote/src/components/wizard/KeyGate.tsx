/**
 * 内部口令面板：内部接口 401 时出现，setInternalKey() 后由页面重试。
 * 不用遮罩弹窗，避免和 D 的 ChatPanel / TemplateBar 抢层级。
 */
import { useEffect, useRef, useState } from 'react';
import { gateText } from '../../i18n/gate';
import { useLang } from '../../../../../src/shell/LangProvider';


export default function KeyGate({
  onConfirm,
  onCancel,
  message,
}: {
  onConfirm: (key: string) => void;
  onCancel: () => void;
  message?: string;
}) {
  const { lang } = useLang();
  const g = gateText(lang);
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <section className="q-gate" aria-label={g.aria}>
      <p className="micro">{g.kicker}</p>
      <h2 className="q-gate-t">{g.title}</h2>
      <p className="q-note">
        {message ?? g.body}
      </p>
      <form
        className="q-gate-form"
        onSubmit={(e) => {
          e.preventDefault();
          const key = value.trim();
          if (key) onConfirm(key);
        }}
      >
        <input
          ref={inputRef}
          className="q-input"
          type="password"
          autoComplete="off"
          placeholder={g.placeholder}
          aria-label={g.aria}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <div className="q-gate-actions">
          <button type="submit" className="btn" disabled={!value.trim()}>
            {g.confirm}
          </button>
          <button type="button" className="btn btn-outline" onClick={onCancel}>
            {g.cancel}
          </button>
        </div>
      </form>
      <p className="q-note micro">{g.footNote}</p>
    </section>
  );
}
