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
      setError('车辆数需为大于等于 1 的整数（单位：台）。');
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
        setUnavailable(data.note || '线上暂不提供报关费测算，请联系项目经理');
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
          <p className="micro">线上测算暂停</p>
          <h2 className="t-h2">线上暂不提供报关费测算</h2>
          <p className="t-unavailable-note">{unavailable}</p>
          <p className="t-hint">
            两岸口岸费用随柜型、查验率与滞留天数变动，需要按票核算。请把起运地、柜型与预计车期发给项目经理，
            我们给书面口径。
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
          <p className="micro">输入</p>
          <h2 className="t-h2">柜型 · 车数 · 附加作业</h2>
        </div>

        <div className="t-fields">
          <label className="t-field">
            <span className="t-label">车辆数（台）</span>
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
              境内运费（RMB）<span className="t-opt">选填</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={100}
              placeholder="不计入时留空"
              value={domestic}
              onChange={(e) => setDomestic(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              柜数<span className="t-opt">选填</span>
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
              柜型<span className="t-opt">选填</span>
            </span>
            <select className="t-input" value={containerType} onChange={(e) => setContainerType(e.target.value)}>
              <option value="">未指定</option>
              <option value="20GP">20GP</option>
              <option value="40GP">40GP</option>
              <option value="40HQ">40HQ</option>
              <option value="45HQ">45HQ</option>
            </select>
          </label>

          <label className="t-field">
            <span className="t-label">
              滞留天数<span className="t-opt">选填</span>
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
              吊装吨位（吨）<span className="t-opt">选填</span>
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

        <p className="t-hint">金额与车数按常规作业条件测算；查验、滞留与特殊吊装以现场实际发生为准。</p>

        <ErrorLine text={error} testId="customs-error" />

        <div className="t-actions">
          <button type="submit" className="t-btn" data-testid="customs-submit" disabled={status === 'busy'}>
            {status === 'busy' ? '测算中…' : '测算两端费用'}
          </button>
        </div>
      </form>

      <section className="t-out" data-testid="customs-range" aria-live="polite">
        <div className="t-out-head">
          <p className="micro">结果</p>
          <h2 className="t-h2">中国端 · 越南端 · DDP</h2>
        </div>

        {status === 'busy' ? <p className="t-hint">正在向报关引擎取数…</p> : null}

        {status !== 'busy' && !ready ? (
          <p className="t-hint">填写左侧参数后点「测算两端费用」，先看区间；需要分项时再留公司信息。</p>
        ) : null}

        {status !== 'busy' && ready ? (
          <>
            <dl className="t-stats">
              <div className="t-stat">
                <dt>中国端（出口报关）</dt>
                <dd>
                  <span className="t-num">{fmtInt(ready.china.min_rmb)}</span>
                  <span className="t-dash">–</span>
                  <span className="t-num">{fmtInt(ready.china.max_rmb)}</span> RMB
                </dd>
              </div>
              <div className="t-stat">
                <dt>越南端（进口清关）</dt>
                <dd>
                  {ready.vietnam ? (
                    <>
                      <span className="t-num">{fmtInt(ready.vietnam.min_vnd)}</span>
                      <span className="t-dash">–</span>
                      <span className="t-num">{fmtInt(ready.vietnam.max_vnd)}</span> VND
                    </>
                  ) : (
                    '汇率暂不可用，越南端暂不折算'
                  )}
                </dd>
              </div>
              <div className="t-stat">
                <dt>DDP 合计（估）</dt>
                <dd>
                  {ready.ddp ? (
                    <>
                      <span className="t-num">{fmtInt(ready.ddp.min_vnd)}</span>
                      <span className="t-dash">–</span>
                      <span className="t-num">{fmtInt(ready.ddp.max_vnd)}</span> VND
                    </>
                  ) : (
                    '汇率暂不可用，DDP 暂不折算'
                  )}
                </dd>
              </div>
              {ready.ddp ? (
                <div className="t-stat">
                  <dt>折算汇率</dt>
                  <dd>
                    1 RMB = <span className="t-num">{fmtInt(ready.ddp.rate)}</span> VND
                  </dd>
                </div>
              ) : null}
            </dl>

            <p className="t-price-note">
              区间为对客口径的上下浮动，取整到 10 元 / 10 万越南盾；不含查验超额、临时仓储与特殊吊装。
            </p>

            <div className="t-actions">
              <button
                type="button"
                className="t-btn"
                data-testid="customs-unlock"
                onClick={() => setModalOpen(true)}
              >
                看分项明细
              </button>
              <span className="t-busy">需填写公司、联系人、联系方式三项</span>
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
