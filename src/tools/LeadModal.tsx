/**
 * 留资弹层：三字段 → `POST /api/lead` → `POST /api/customs/detail` → 同层展开分项明细。
 *
 * 口径（契约 §3.3–3.4）：
 *  - 只收公司 / 联系人 / 联系方式三项，不建账号、不设密码。
 *  - 明细令牌与参数指纹绑定：参数一变即失效，这里每次都用「当前参数」重新换 token。
 *  - 分项每行只显示 `label_zh / amount / unit`，额外口径注写在区块上，不混进金额行。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  errorText,
  fmtInt,
  postCustomsDetail,
  postLead,
  type CustomsDetail,
  type CustomsParams,
  type CustomsLine,
} from './api';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';
import { Disclaim, ErrorLine } from './parts';

type Props = {
  open: boolean;
  params: CustomsParams;
  onClose: () => void;
};

function Side({
  title,
  lines,
  total,
  unit,
}: {
  title: string;
  lines: CustomsLine[];
  total: number;
  unit: 'RMB' | 'VND';
}) {
  const { lang } = useLang();
  const t = getTools(lang);
  return (
    <div className="t-side">
      <p className="t-label">{title}</p>
      <ul className="t-lines">
        {lines.length === 0 ? <li className="t-line-empty">{t.lead.emptyLine}</li> : null}
        {lines.map((line) => (
          <li key={`${line.label_zh}-${line.amount}`} className="t-line">
            <span>{t.customsLines[line.label_zh] ?? line.label_zh}</span>
            <span className="t-num">
              {fmtInt(line.amount)} {line.unit}
            </span>
          </li>
        ))}
      </ul>
      <p className="t-line-total">
        <span>{t.lead.subtotal}</span>
        <span className="t-num">
          {fmtInt(total)} {unit}
        </span>
      </p>
      <p className="t-side-note">{t.lead.sideNote}</p>
    </div>
  );
}

export default function LeadModal({ open, params, onClose }: Props) {
  const { lang } = useLang();
  const t = getTools(lang);
  const [company, setCompany] = useState('');
  const [contact, setContact] = useState('');
  const [reach, setReach] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<CustomsDetail | null>(null);
  const firstRef = useRef<HTMLInputElement | null>(null);

  const paramsKey = useMemo(() => JSON.stringify(params), [params]);

  useEffect(() => {
    if (!open) return;
    setError('');
    setDetail(null);
    const timer = window.setTimeout(() => firstRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [open, paramsKey]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (!company.trim() || !contact.trim() || !reach.trim()) {
      setError(t.lead.errRequired);
      return;
    }
    setError('');
    setBusy(true);
    try {
      const lead = await postLead({
        company: company.trim(),
        contact: contact.trim(),
        reach: reach.trim(),
        params,
      });
      const data = await postCustomsDetail({ leadId: lead.leadId, token: lead.token, params });
      setDetail(data);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="t-modal-root">
      <div className="t-scrim" onClick={onClose} aria-hidden="true" />
      <div
        className="t-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lead-modal-title"
        data-testid="lead-modal"
      >
        <header className="t-modal-head">
          <div>
            <p className="micro">{t.lead.kicker}</p>
            <h2 className="t-h2" id="lead-modal-title">
              {detail ? t.lead.titleDetail : t.lead.titleGate}
            </h2>
          </div>
          <button type="button" className="t-close" onClick={onClose} aria-label={t.lead.closeAria}>
            ✕
          </button>
        </header>

        {detail ? (
          <div className="t-modal-body" data-testid="customs-detail">
            <div className="t-sides">
              <Side
                title={t.lead.chinaTitle}
                lines={Array.isArray(detail.china_side) ? detail.china_side : []}
                total={detail.china_total_rmb}
                unit="RMB"
              />
              <Side
                title={t.lead.vietnamTitle}
                lines={Array.isArray(detail.vietnam_side) ? detail.vietnam_side : []}
                total={detail.vietnam_total_vnd}
                unit="VND"
              />
            </div>

            {Array.isArray(detail.notes) && detail.notes.length > 0 ? (
              <ul className="t-list">
                {detail.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}

            <Disclaim />

            <div className="t-modal-foot">
              <p className="t-hint">{t.lead.needFormal}</p>
              <button type="button" className="t-btn-ghost" onClick={onClose}>
                {t.lead.close}
              </button>
            </div>
          </div>
        ) : (
          <form className="t-modal-body" onSubmit={submit} noValidate>
            <p className="t-hint">
              {t.lead.privacy}
            </p>

            <label className="t-field">
              <span className="t-label">{t.lead.company}</span>
              <input
                ref={firstRef}
                className="t-input"
                data-testid="lead-company"
                type="text"
                autoComplete="organization"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              />
            </label>

            <label className="t-field">
              <span className="t-label">{t.lead.contact}</span>
              <input
                className="t-input"
                data-testid="lead-contact"
                type="text"
                autoComplete="name"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
              />
            </label>

            <label className="t-field">
              <span className="t-label">{t.lead.contactWay}</span>
              <input
                className="t-input"
                data-testid="lead-reach"
                type="text"
                autoComplete="tel"
                value={reach}
                onChange={(e) => setReach(e.target.value)}
              />
            </label>

            <ErrorLine text={error} testId="lead-error" />

            <div className="t-actions">
              <button type="submit" className="t-btn" data-testid="lead-submit" disabled={busy}>
                {busy ? t.lead.submitBusy : t.lead.submit}
              </button>
              <button type="button" className="t-btn-ghost" onClick={onClose}>
                {t.lead.cancel}
              </button>
            </div>

            <Disclaim />
          </form>
        )}
      </div>
    </div>
  );
}
