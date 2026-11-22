import { useEffect, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import HairlineTable from '../HairlineTable';
import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { PageHead } from '../ui';
import { getContact } from '../../content';
import { useLang } from '../../shell/LangProvider';
import { applyLangToDocument } from '../../shell/i18n';

type FormState = {
  name: string;
  company: string;
  inquiryType: string;
  loadingPort: string;
  dischargePort: string;
  weightEstimate: string;
  details: string;
};

type ConsultResult = {
  routeRecommendation?: string;
  documentChecklist?: string[];
  hsCodeAdvice?: string;
  riskMitigation?: string[];
  consultantStatement?: string;
};

type Status = 'idle' | 'loading' | 'ok' | 'fallback' | 'invalid';

export default function Contact() {
  const { lang } = useLang();
  const t = getContact(lang);
  const f = t.form;

  const [form, setForm] = useState<FormState>({
    name: '',
    company: '',
    inquiryType: t.form.types[0],
    loadingPort: '',
    dischargePort: '',
    weightEstimate: '',
    details: '',
  });
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<ConsultResult | null>(null);

  useEffect(() => {
    applyLangToDocument(lang, t.meta.title);
  }, [lang, t]);

  /* 语言切换后，已选业务类型若不在当前语言的清单里，回落到第一项，避免下拉框显示上次语言的词 */
  const inquiryType = f.types.includes(form.inquiryType) ? form.inquiryType : f.types[0];

  function onChange(e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (status === 'loading') return;

    if (!form.name.trim() || !form.details.trim()) {
      setResult(null);
      setStatus('invalid');
      return;
    }

    setStatus('loading');
    setResult(null);

    try {
      const res = await fetch('/api/logistics-consult', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          company: form.company,
          inquiryType,
          loadingPort: form.loadingPort,
          dischargePort: form.dischargePort,
          weightEstimate: form.weightEstimate,
          details: form.details,
        }),
      });

      const data = (await res.json().catch(() => null)) as ConsultResult | null;

      /* 只有拿到 routeRecommendation 才算成功；500 / 空响应 / 缺字段一律走站内兜底文案 */
      if (!res.ok || !data || typeof data.routeRecommendation !== 'string' || !data.routeRecommendation) {
        setResult(null);
        setStatus('fallback');
        return;
      }

      setResult(data);
      setStatus('ok');
    } catch {
      setResult(null);
      setStatus('fallback');
    }
  }

  const detailRows = t.details.map((d) => ({
    k: d.label,
    v:
      d.href ? (
        <a className="inline-link" href={d.href}>
          {d.value}
        </a>
      ) : d.pending ? (
        <span className="pending">{d.value}</span>
      ) : (
        d.value
      ),
  }));

  return (
    <>
      <PageHead no="05" kicker={t.eyebrow} title={t.title} lead={t.intro} />

      <section className="section">
        <div className="wrap">
          <SectionHeader no="01" title={t.detailsTitle} lead={t.detailsLead} />
          <div className="contact-grid">
            <HairlineTable head={t.tableHead} groups={[{ rows: detailRows }]} />
            <div className="contact-side">
              <p className="micro">{t.sideKicker}</p>
              <ul className="lines">
                {t.sideItems.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="section section-end" id="consult">
        <div className="wrap">
          <SectionHeader no="02" title={f.title} lead={f.lead} />

          <form className="cform" data-testid="contact-form" onSubmit={onSubmit} noValidate>
            <div className="form-grid">
              <label className="field" htmlFor="cf-name">
                <span className="field-label">{f.fields.name}</span>
                <input
                  id="cf-name"
                  name="name"
                  value={form.name}
                  onChange={onChange}
                  placeholder={f.placeholders.name}
                  autoComplete="name"
                  aria-required="true"
                  data-testid="field-name"
                />
              </label>

              <label className="field" htmlFor="cf-company">
                <span className="field-label">{f.fields.company}</span>
                <input
                  id="cf-company"
                  name="company"
                  value={form.company}
                  onChange={onChange}
                  placeholder={f.placeholders.company}
                  autoComplete="organization"
                />
              </label>

              <label className="field" htmlFor="cf-type">
                <span className="field-label">{f.fields.inquiryType}</span>
                <select id="cf-type" name="inquiryType" value={inquiryType} onChange={onChange} data-testid="field-type">
                  {f.types.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field" htmlFor="cf-weight">
                <span className="field-label">{f.fields.weightEstimate}</span>
                <input
                  id="cf-weight"
                  name="weightEstimate"
                  value={form.weightEstimate}
                  onChange={onChange}
                  placeholder={f.placeholders.weightEstimate}
                />
              </label>

              <label className="field" htmlFor="cf-loading">
                <span className="field-label">{f.fields.loadingPort}</span>
                <input
                  id="cf-loading"
                  name="loadingPort"
                  value={form.loadingPort}
                  onChange={onChange}
                  placeholder={f.placeholders.loadingPort}
                />
              </label>

              <label className="field" htmlFor="cf-discharge">
                <span className="field-label">{f.fields.dischargePort}</span>
                <input
                  id="cf-discharge"
                  name="dischargePort"
                  value={form.dischargePort}
                  onChange={onChange}
                  placeholder={f.placeholders.dischargePort}
                  data-testid="field-dest"
                />
              </label>

              <label className="field field-full" htmlFor="cf-details">
                <span className="field-label">{f.fields.details}</span>
                <textarea
                  id="cf-details"
                  name="details"
                  value={form.details}
                  onChange={onChange}
                  placeholder={f.placeholders.details}
                  rows={5}
                  aria-required="true"
                />
              </label>
            </div>

            <div className="submit-row">
              <button className="btn" type="submit" data-testid="contact-submit" disabled={status === 'loading'}>
                {status === 'loading' ? f.submitting : f.submit}
              </button>
              <p className="micro submit-note">{f.requiredNote}</p>
            </div>

            <div className="result" data-testid="contact-result" aria-live="polite">
              {status === 'idle' ? <p className="note">{f.disclaimer}</p> : null}

              {status === 'loading' ? <p className="note">{f.submitting}</p> : null}

              {status === 'invalid' ? (
                <div className="result-body">
                  <h3 className="result-title">{f.incompleteTitle}</h3>
                  <p>{f.incompleteBody}</p>
                  <p className="note">{f.disclaimer}</p>
                </div>
              ) : null}

              {status === 'fallback' ? (
                <div className="result-body">
                  <h3 className="result-title">{f.resultTitle}</h3>
                  <p>{f.fallback}</p>
                  <p className="result-error">{f.errorNote}</p>
                  <p className="note">{f.disclaimer}</p>
                </div>
              ) : null}

              {status === 'ok' && result ? (
                <div className="result-body">
                  <h3 className="result-title">{f.resultTitle}</h3>
                  <p className="result-route">{result.routeRecommendation}</p>

                  <div className="result-cols">
                    {result.documentChecklist && result.documentChecklist.length > 0 ? (
                      <div>
                        <p className="micro">{f.docTitle}</p>
                        <ul className="lines">
                          {result.documentChecklist.map((d) => (
                            <li key={d}>{d}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {result.riskMitigation && result.riskMitigation.length > 0 ? (
                      <div>
                        <p className="micro">{f.riskTitle}</p>
                        <ul className="lines">
                          {result.riskMitigation.map((d) => (
                            <li key={d}>{d}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>

                  {result.hsCodeAdvice ? (
                    <div className="result-block">
                      <p className="micro">{f.hsTitle}</p>
                      <p>{result.hsCodeAdvice}</p>
                    </div>
                  ) : null}

                  {result.consultantStatement ? (
                    <p className="result-quote">{result.consultantStatement}</p>
                  ) : null}

                  <p className="note">{f.disclaimer}</p>
                </div>
              ) : null}
            </div>
          </form>
        </div>
      </section>

      <PhotoFull src={t.photo.src} alt={t.photo.alt} caption={t.photo.caption} ratio="21/9" />
    </>
  );
}
