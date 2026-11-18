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
  return (
    <div className="t-side">
      <p className="t-label">{title}</p>
      <ul className="t-lines">
        {lines.length === 0 ? <li className="t-line-empty">无分项</li> : null}
        {lines.map((line) => (
          <li key={`${line.label_zh}-${line.amount}`} className="t-line">
            <span>{line.label_zh}</span>
            <span className="t-num">
              {fmtInt(line.amount)} {line.unit}
            </span>
          </li>
        ))}
      </ul>
      <p className="t-line-total">
        <span>小计</span>
        <span className="t-num">
          {fmtInt(total)} {unit}
        </span>
      </p>
      <p className="t-side-note">口径注：含服务口径的对外金额，不是成本，也不含临时仓储与查验超额。</p>
    </div>
  );
}

export default function LeadModal({ open, params, onClose }: Props) {
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
      setError('请把公司、联系人、联系方式三项填写完整。');
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
            <p className="micro">分项明细</p>
            <h2 className="t-h2" id="lead-modal-title">
              {detail ? '中国端 / 越南端分项' : '留下公司信息，查看分项'}
            </h2>
          </div>
          <button type="button" className="t-close" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </header>

        {detail ? (
          <div className="t-modal-body" data-testid="customs-detail">
            <div className="t-sides">
              <Side
                title="中国端（出口报关）"
                lines={Array.isArray(detail.china_side) ? detail.china_side : []}
                total={detail.china_total_rmb}
                unit="RMB"
              />
              <Side
                title="越南端（进口清关）"
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
              <p className="t-hint">需要按本条参数出正式报价，请联系项目经理复核。</p>
              <button type="button" className="t-btn-ghost" onClick={onClose}>
                关闭
              </button>
            </div>
          </div>
        ) : (
          <form className="t-modal-body" onSubmit={submit} noValidate>
            <p className="t-hint">
              三项信息仅用于本次明细与后续对接，不建账号、不设密码；明细凭证 30 分钟后失效。
            </p>

            <label className="t-field">
              <span className="t-label">公司名称</span>
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
              <span className="t-label">联系人</span>
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
              <span className="t-label">联系方式（手机 / 微信 / 邮箱）</span>
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
                {busy ? '提交中…' : '查看分项明细'}
              </button>
              <button type="button" className="t-btn-ghost" onClick={onClose}>
                取消
              </button>
            </div>

            <Disclaim />
          </form>
        )}
      </div>
    </div>
  );
}
