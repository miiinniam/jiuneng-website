/**
 * AI 报价工作台卡片（挂在助手回复下方）。
 *
 * 原则：**卡片上的数字只来自引擎**（buildPlan 投影自 /api/quote/route 的结果），
 * 模型只负责解析需求与解释结果。内部版允许人工改费用，但改动只存在本地 override 里，
 * 不覆盖引擎结果，随时可撤销 —— 否则下一次 AI 回复会把人工修改悄悄吃掉。
 *
 * 公开版没有分项成本（服务端白名单就没有 breakdown），所以只出方案 + 区间/待核定。
 */
import { useMemo, useState } from 'react';
import type { WsLine, WsPlan } from './plan';
import { strings, type Lang } from '../../i18n/strings';
import { workspaceText } from '../../i18n/workspace';

export type WsAction = 'edit-route' | 'edit-cargo' | 'edit-vehicle' | 'recalc' | 'copy' | 'contact' | 'map';

export type WorkspacePanelProps = {
  plan: WsPlan;
  /** 人民币汇率（VND / 1 CNY）；null = 不显示人民币折算 */
  cnyVnd?: number | null;
  /** 美元汇率（VND / 1 USD）；null = 不显示美元折算 */
  usdVnd?: number | null;
  /** 界面语言（卡片标题与字段跟着站点语言） */
  lang?: Lang;
  onAction: (action: WsAction) => void;
};

const vnd = (n: number): string => new Intl.NumberFormat('en-US').format(Math.round(n));
const cny = (n: number): string => new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
const hours = (h: number): string => (h >= 1.05 ? h.toFixed(1) : h.toFixed(2));

type Extra = WsLine;

export default function WorkspacePanel({ plan, cnyVnd, usdVnd, lang = 'zh', onAction }: WorkspacePanelProps) {
  const t = strings(lang);
  const w = workspaceText(lang);
  const internal = plan.scope === 'internal';
  const [editing, setEditing] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [extras, setExtras] = useState<Extra[]>([]);
  const [removed, setRemoved] = useState<string[]>([]);
  const [currency, setCurrency] = useState<'VND' | 'CNY' | 'USD'>('VND');

  const baseLines = plan.cost?.lines ?? [];
  const lines = useMemo(
    () =>
      baseLines
        .filter((l) => !removed.includes(l.key))
        .map((l) => ({ ...l, value: overrides[l.key] ?? l.value }))
        .concat(extras),
    [baseLines, overrides, extras, removed],
  );

  const total = useMemo(() => lines.reduce((s, l) => s + (Number.isFinite(l.value) ? l.value : 0), 0), [lines]);
  const dirty = Object.keys(overrides).length > 0 || extras.length > 0 || removed.length > 0;
  /** 未修改时以引擎合计为准；改过就用明细重算（否则人工改的钱看不出来） */
  const engineTotal = plan.price.costTotal ?? plan.cost?.total ?? total;
  const shownTotal = dirty ? total : engineTotal;
  const drift = !dirty && Math.abs(engineTotal - total) > 1;
  const money = (n: number) => {
    if (currency === 'CNY' && cnyVnd && cnyVnd > 0) return `¥${cny(n / cnyVnd)}`;
    if (currency === 'USD' && usdVnd && usdVnd > 0) return `$${cny(n / usdVnd)}`;
    return `${vnd(n)} đ`;
  };

  const resetEdits = () => {
    setOverrides({});
    setExtras([]);
    setRemoved([]);
    setEditing(false);
  };

  const addLine = () => {
    setExtras((prev) => [...prev, { key: `extra-${Date.now()}`, label: w.newFee, value: 0 }]);
  };

  const editLine = (key: string, patch: Partial<WsLine>) => {
    if (key.startsWith('extra-')) {
      setExtras((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
      return;
    }
    if (typeof patch.value === 'number') setOverrides((prev) => ({ ...prev, [key]: patch.value as number }));
  };

  return (
    <section className="q-ws" aria-label={w.boardAria}>
      {/* 01 运输方案 */}
      <div className="q-ws-block">
        <div className="q-ws-head">
          <p className="micro">{t.ws.plan}</p>
          <span className="q-ws-badge" data-tone="ok">
            {t.ws.computed}
          </span>
        </div>
        <dl className="q-ws-grid">
          <div>
            <dt>{t.ws.from}</dt>
            <dd title={plan.route.from}>{plan.route.from}</dd>
          </div>
          <div>
            <dt>{t.ws.to}</dt>
            <dd title={plan.route.to}>{plan.route.to}</dd>
          </div>
          <div>
            <dt>{t.ws.km}</dt>
            <dd className="q-ws-num">
              {plan.route.km.toFixed(1)}
              <span className="q-ws-unit">km</span>
            </dd>
          </div>
          <div>
            <dt>{t.ws.hours}</dt>
            <dd className="q-ws-num">
              {hours(plan.route.hours)}
              <span className="q-ws-unit">h</span>
            </dd>
          </div>
          <div>
            <dt>{t.ws.vehicle}</dt>
            <dd>{plan.vehicle.name}</dd>
          </div>
          <div>
            <dt>{t.ws.count}</dt>
            <dd className="q-ws-num">
              {plan.vehicle.count}
              <span className="q-ws-unit">{w.unitVehicles}</span>
            </dd>
          </div>
          <div>
            <dt>{t.ws.cargo}</dt>
            <dd>{plan.cargo.typeLabel}</dd>
          </div>
          <div>
            <dt>{t.ws.weight}</dt>
            <dd className="q-ws-num">
              {plan.cargo.weightTon === null ? '—' : plan.cargo.weightTon.toFixed(1)}
              <span className="q-ws-unit">t</span>
            </dd>
          </div>
        </dl>
        <div className="q-ws-links">
          <button type="button" className="q-ws-link" onClick={() => onAction('map')}>
            {t.ws.viewMap}
          </button>
          <button type="button" className="q-ws-link" onClick={() => onAction('edit-route')}>
            {t.ws.editRoute}
          </button>
        </div>
      </div>

      {/* 02 费用明细：仅内部版（公开版没有分项成本） */}
      {internal && plan.cost ? (
        <div className="q-ws-block">
          <div className="q-ws-head">
            <p className="micro">{t.ws.cost}</p>
            <div className="q-ws-head-tools">
              <button
                type="button"
                className="q-ws-chip"
                data-on={currency === 'VND'}
                onClick={() => setCurrency('VND')}
              >
                VND
              </button>
              <button
                type="button"
                className="q-ws-chip"
                data-on={currency === 'CNY'}
                onClick={() => setCurrency('CNY')}
                disabled={!cnyVnd}
              >
                CNY
              </button>
              <button
                type="button"
                className="q-ws-chip"
                data-on={currency === 'USD'}
                onClick={() => setCurrency('USD')}
                disabled={!usdVnd}
              >
                USD
              </button>
            </div>
          </div>

          <table className="q-ws-table">
            <thead>
              <tr>
                <th scope="col">{t.ws.item}</th>
                <th scope="col">{t.ws.amount}</th>
                {editing ? <th scope="col" className="q-ws-col-op">{w.action}</th> : null}
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.key}>
                  <td>
                    {editing && l.key.startsWith('extra-') ? (
                      <input
                        className="q-ws-in q-ws-in--text"
                        value={l.label}
                        aria-label={w.feeName}
                        onChange={(e) => editLine(l.key, { label: e.target.value })}
                      />
                    ) : (
                      l.label
                    )}
                  </td>
                  <td className="q-ws-num">
                    {editing ? (
                      <input
                        className="q-ws-in"
                        type="number"
                        inputMode="decimal"
                        value={Number.isFinite(l.value) ? l.value : 0}
                        aria-label={w.feeAmount(l.label)}
                        onChange={(e) => editLine(l.key, { value: Number(e.target.value) })}
                      />
                    ) : (
                      money(l.value)
                    )}
                  </td>
                  {editing ? (
                    <td className="q-ws-col-op">
                      <button type="button" className="q-ws-del" onClick={() => {
                        if (l.key.startsWith('extra-')) setExtras((prev) => prev.filter((x) => x.key !== l.key));
                        else setRemoved((prev) => [...prev, l.key]);
                      }}>
                        {w.remove}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
              <tr className="q-ws-total-row">
                <td>{t.ws.total}</td>
                <td className="q-ws-num q-ws-total">{money(shownTotal)}</td>
                {editing ? <td /> : null}
              </tr>
            </tbody>
          </table>

          {drift ? (
            <p className="q-ws-drift">
              {w.drift(money(total), money(engineTotal - total))}
            </p>
          ) : null}

          <div className="q-ws-links">
            {editing ? (
              <>
                <button type="button" className="q-ws-link" onClick={addLine}>
                  {t.ws.addFee}
                </button>
                <button type="button" className="q-ws-link" onClick={() => setEditing(false)}>
                  {t.ws.done}
                </button>
                <button type="button" className="q-ws-link" onClick={resetEdits}>
                  {t.ws.undo}
                </button>
              </>
            ) : (
              <button type="button" className="q-ws-link" onClick={() => setEditing(true)}>
                {t.ws.editDetail}
              </button>
            )}
            {dirty ? (
              <span className="q-ws-badge" data-tone="warn">
                {t.ws.modified}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* 03 汇总 */}
      <div className="q-ws-block">
        <div className="q-ws-head">
          <p className="micro">{internal ? t.ws.costTotal : t.ws.scopeEstimate}</p>
          <span className="q-ws-badge" data-tone={plan.price.status === 'estimate' ? 'ok' : 'muted'}>
            {plan.price.status === 'cost' ? t.ws.internalOnly : plan.price.status === 'estimate' ? t.ws.estimate : t.ws.pending}
          </span>
        </div>

        {internal ? (
          <>
            <p className="q-ws-amount">
              {money(shownTotal)}
              <span className="q-ws-unit">{currency === 'CNY' ? '' : 'VND'}</span>
            </p>
            <p className="q-ws-meta">
              {w.perVehicle} {(plan.price.perVehicle ?? 0) > 0 ? money(plan.price.perVehicle as number) : '—'}
              {plan.price.perKm ? ` · ${vnd(plan.price.perKm)} đ/km` : ''}
              {cnyVnd ? w.fx(vnd(cnyVnd)) : ''}
            </p>
          </>
        ) : plan.price.status === 'estimate' ? (
          <>
            <p className="q-ws-amount">
              {vnd(plan.price.low as number)}
              <span className="q-ws-dash">–</span>
              {vnd(plan.price.high as number)}
              <span className="q-ws-unit">VND</span>
            </p>
            <p className="q-ws-meta">
              {cnyVnd ? w.approxCny(cny((plan.price.low as number) / cnyVnd), cny((plan.price.high as number) / cnyVnd)) : w.fuelNote}
            </p>
          </>
        ) : (
          <>
            <p className="q-ws-pending">{t.ws.pendingMsg}</p>
            <p className="q-ws-meta">{t.ws.pendingDetail}</p>
          </>
        )}
      </div>

      {/* 04 重要说明：单独成块，不混在正文里 */}
      <div className="q-ws-block">
        <div className="q-ws-head">
          <p className="micro">{internal ? t.ws.noticeTitleInternal : t.ws.noticeTitle}</p>
        </div>
        <ul className="q-ws-notice">
          {(internal ? t.ws.noticeInternal : t.ws.noticePublic).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      {/* 05 联系顾问：只有真入口，不编造电话与邮箱 */}
      <div className="q-ws-contact">
        <p className="q-ws-contact-t">{internal ? t.ws.contactInternalT : t.ws.contactPublicT}</p>
        <p className="q-ws-contact-d">{internal ? t.ws.contactInternalD : t.ws.contactPublicD}</p>
        <button type="button" className="btn q-ws-btn" onClick={() => onAction('contact')}>
          {internal ? t.ws.contactCtaInternal : t.ws.contactCtaPublic}
        </button>
      </div>

      {/* 操作：每个按钮都接真实业务 */}
      <div className="q-ws-actions">
        {plan.price.status === 'pending' ? (
          <button type="button" className="btn q-ws-btn" onClick={() => onAction('contact')}>
            {t.ws.requestQuote}
          </button>
        ) : (
          <button type="button" className="btn q-ws-btn" onClick={() => onAction('recalc')}>
            {t.ws.recalc}
          </button>
        )}
        <button type="button" className="btn btn-outline q-ws-btn" onClick={() => onAction('edit-vehicle')}>
          {t.ws.changeVehicle}
        </button>
        <button type="button" className="btn btn-outline q-ws-btn" onClick={() => onAction('copy')}>
          {t.ws.copyQuote}
        </button>
      </div>

      <p className="q-ws-note">
        {internal
          ? t.ws.internalNote
          : t.ws.publicNote}{' '}
        {t.ws.baseNote}
      </p>
    </section>
  );
}

export function planToText(plan: WsPlan, cnRate?: number | null, lang: Lang = 'zh'): string {
  const w = workspaceText(lang);
  const rows: string[] = [];
  rows.push(`${w.copy.header}${plan.route.from} → ${plan.route.to}`);
  rows.push(w.copy.km(plan.route.km.toFixed(1), hours(plan.route.hours)));
  rows.push(w.copy.vehicle(plan.vehicle.name, plan.vehicle.count));
  rows.push(w.copy.cargo(plan.cargo.typeLabel, plan.cargo.weightTon ? plan.cargo.weightTon.toFixed(1) : ''));
  if (plan.scope === 'internal' && plan.cost) {
    rows.push(w.copy.costDetail);
    for (const l of plan.cost.lines) rows.push(`${l.label}\t${vnd(l.value)}`);
    rows.push(w.copy.total(vnd(plan.cost.total), cnRate ? cny(plan.cost.total / cnRate) : ''));
  } else if (plan.price.status === 'estimate') {
    rows.push(w.copy.priceRange(vnd(plan.price.low as number), vnd(plan.price.high as number)));
  } else {
    rows.push(w.copy.pricePending);
  }
  rows.push(w.copy.disclaimer);
  return rows.join('\n');
}

