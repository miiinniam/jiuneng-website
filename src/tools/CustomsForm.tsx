/**
 * 报关与税费：参数 → `GET /api/customs/range` → 两端区间 → 留资解锁分项。
 *
 * `available:false` 是**预期状态**（服务端未配置对外系数时 fail-closed）：
 * 一旦命中就整块换成「请联系项目经理」并**隐藏输入区**，不让客户白填一遍。
 */
import { useState } from 'react';
import type { FormEvent } from 'react';
import common from '../content/zh/common';
import {
  errorText,
  fetchCustomsRange,
  fmtInt,
  type CustomsParams,
  type CustomsRange,
} from './api';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';
import { Disclaim, ErrorLine } from './parts';
import LeadModal from './LeadModal';

type Status = 'idle' | 'busy';

function optInt(raw: string): number | undefined {
  const value = Number(raw);
  if (!raw.trim() || !Number.isFinite(value) || value < 0) return undefined;
  return Math.round(value);
}

function optFloat(raw: string): number | undefined {
  const value = Number(raw);
  if (!raw.trim() || !Number.isFinite(value) || value < 0) return undefined;
  return value;
}

export default function CustomsForm() {
  const { lang } = useLang();
  const t = getTools(lang);
  const [vehicles, setVehicles] = useState('1');
  const [domestic, setDomestic] = useState('');
  const [containers, setContainers] = useState('');
  const [containerType, setContainerType] = useState('');
  const [detention, setDetention] = useState('');
  const [lift, setLift] = useState('');

  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState('');
  const [range, setRange] = useState<CustomsRange | null>(null);
  const [unavailable, setUnavailable] = useState('');
  const [lockedParams, setLockedParams] = useState<CustomsParams | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (status === 'busy') return;

    const count = Number(vehicles);
    if (!Number.isFinite(count) || count < 1) {
      setError(t.customs.errVehicles);
      setRange(null);
      return;
    }

    const params: CustomsParams = {
      vehicle_count: Math.round(count),
      domestic_transport_rmb: optInt(domestic),
      container_count: optInt(containers),
      container_type: containerType || null,
      detention_days: optInt(detention),
      heavy_lift_tons: optFloat(lift),
    };

    setError('');
    setStatus('busy');
    try {
      const data = await fetchCustomsRange(params);
      if (data.available === false) {
        setUnavailable(data.note || t.customs.noteFallback);
        setRange(null);
        setLockedParams(null);
      } else {
        setUnavailable('');
        setRange(data);
        setLockedParams(params);
      }
    } catch (err) {
      setError(errorText(err));
      setRange(null);
    } finally {
      setStatus('idle');
    }
  };

  if (unavailable) {
    return (
      <div className="t-grid">
        <section className="t-unavailable">
          <p className="micro">{t.customs.pausedKicker}</p>
          <h2 className="t-h2">{t.customs.pausedTitle}</h2>
          <p className="t-unavailable-note">{unavailable}</p>
          <p className="t-hint">
            {t.customs.pausedBody}
          </p>
          <ul className="t-contact">
            <li>{common.footer.contactLines[0]}</li>
            <li>{common.footer.contactLines[1]}</li>
            <li>{common.footer.contactLines[2]}</li>
          </ul>
          <Disclaim />
        </section>
      </div>
    );
  }

  const ready = range && range.available ? range : null;

  return (
    <div className="t-grid">
      <form className="t-form" onSubmit={submit} noValidate>
        <div className="t-form-head">
          <p className="micro">{t.customs.inputKicker}</p>
          <h2 className="t-h2">{t.customs.inputTitle}</h2>
        </div>

        <div className="t-fields">
          <label className="t-field">
            <span className="t-label">{t.customs.vehicles}</span>
            <input
              className="t-input"
              data-testid="customs-vehicles"
              type="number"
              inputMode="numeric"
              min={1}
              step={1}
              value={vehicles}
              onChange={(e) => setVehicles(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              {t.customs.inland}<span className="t-opt">{t.customs.inlandOpt}</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={100}
              placeholder={t.customs.inlandPh}
              value={domestic}
              onChange={(e) => setDomestic(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              {t.customs.containers}<span className="t-opt">{t.customs.opt}</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={containers}
              onChange={(e) => setContainers(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              {t.customs.containerType}<span className="t-opt">{t.customs.opt}</span>
            </span>
            <select className="t-input" value={containerType} onChange={(e) => setContainerType(e.target.value)}>
              <option value="">{t.customs.containerNone}</option>
              <option value="20GP">20GP</option>
              <option value="40GP">40GP</option>
              <option value="40HQ">40HQ</option>
              <option value="45HQ">45HQ</option>
            </select>
          </label>

          <label className="t-field">
            <span className="t-label">
              {t.customs.dwell}<span className="t-opt">{t.customs.opt}</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={detention}
              onChange={(e) => setDetention(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              {t.customs.lift}<span className="t-opt">{t.customs.opt}</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="decimal"
              min={0}
              step={0.5}
              value={lift}
              onChange={(e) => setLift(e.target.value)}
            />
          </label>
        </div>

        <p className="t-hint">{t.customs.note}</p>

        <ErrorLine text={error} testId="customs-error" />

        <div className="t-actions">
          <button type="submit" className="t-btn" data-testid="customs-submit" disabled={status === 'busy'}>
            {status === 'busy' ? t.customs.submitBusy : t.customs.submit}
          </button>
        </div>
      </form>

      <section className="t-out" data-testid="customs-range" aria-live="polite">
        <div className="t-out-head">
          <p className="micro">{t.customs.resultKicker}</p>
          <h2 className="t-h2">{t.customs.resultTitle}</h2>
        </div>

        {status === 'busy' ? <p className="t-hint">{t.customs.fetching}</p> : null}

        {status !== 'busy' && !ready ? (
          <p className="t-hint">{t.customs.empty}</p>
        ) : null}

        {status !== 'busy' && ready ? (
          <>
            <dl className="t-stats">
              <div className="t-stat">
                <dt>{t.customs.rowChina}</dt>
                <dd>
                  <span className="t-num">{fmtInt(ready.china.min_rmb)}</span>
                  <span className="t-dash">–</span>
                  <span className="t-num">{fmtInt(ready.china.max_rmb)}</span> RMB
                </dd>
              </div>
              <div className="t-stat">
                <dt>{t.customs.rowVietnam}</dt>
                <dd>
                  {ready.vietnam ? (
                    <>
                      <span className="t-num">{fmtInt(ready.vietnam.min_vnd)}</span>
                      <span className="t-dash">–</span>
                      <span className="t-num">{fmtInt(ready.vietnam.max_vnd)}</span> VND
                    </>
                  ) : (
                    t.customs.fxUnavailable
                  )}
                </dd>
              </div>
              <div className="t-stat">
                <dt>{t.customs.rowDdp}</dt>
                <dd>
                  {ready.ddp ? (
                    <>
                      <span className="t-num">{fmtInt(ready.ddp.min_vnd)}</span>
                      <span className="t-dash">–</span>
                      <span className="t-num">{fmtInt(ready.ddp.max_vnd)}</span> VND
                    </>
                  ) : (
                    t.customs.fxUnavailableDdp
                  )}
                </dd>
              </div>
              {ready.ddp ? (
                <div className="t-stat">
                  <dt>{t.customs.rowFx}</dt>
                  <dd>
                    1 RMB = <span className="t-num">{fmtInt(ready.ddp.rate)}</span> VND
                  </dd>
                </div>
              ) : null}
            </dl>

            <p className="t-price-note">
              {t.customs.rangeNote}
            </p>

            <div className="t-actions">
              <button
                type="button"
                className="t-btn"
                data-testid="customs-unlock"
                onClick={() => setModalOpen(true)}
              >
                {t.customs.detailCta}
              </button>
              <span className="t-busy">{t.customs.detailNeed}</span>
            </div>
          </>
        ) : null}

        <Disclaim />
      </section>

      <LeadModal
        open={modalOpen && !!lockedParams}
        params={lockedParams ?? { vehicle_count: 1 }}
        onClose={() => setModalOpen(false)}
      />
    </div>
  );
}
