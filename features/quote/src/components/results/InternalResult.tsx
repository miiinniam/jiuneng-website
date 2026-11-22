/**
 * 内部版结果：QuoteResponse.breakdown 全量分项，发丝线表格（不用卡片）。
 * 参考 src/site/HairlineTable.tsx 的做法：表头 micro + 上粗线，行间 1px。
 */
import type { QuoteResponse } from '../../engine/types';
import { StatRow, hours, km, money } from './ResultBits';
import { resultsText } from '../../i18n/results';
import { useLang } from '../../../../../src/shell/LangProvider';


type Row = { k: string; v: string; strong?: boolean };
type Group = { label?: string; rows: Row[] };

export default function InternalResult({ result }: { result: QuoteResponse }) {
  const { lang } = useLang();
  const tx = resultsText(lang);
  const b = result.breakdown;
  const vehicleCount = b.vehicle_count || result.vehicle_count || 1;

  const groups: Group[] = [
    {
      label: tx.internal.transport,
      rows: [
        { k: tx.internal.items.distance, v: money(b.cost_distance) },
        { k: tx.internal.items.time, v: money(b.cost_time) },
        { k: tx.internal.items.fuel, v: money(b.cost_fuel) },
        { k: tx.internal.items.loading, v: money(b.cost_loading) },
        { k: tx.internal.items.insurance, v: money(b.cost_insurance) },
        { k: tx.internal.items.toll, v: money(b.cost_toll) },
        { k: tx.internal.items.misc, v: money(b.cost_misc) },
      ],
    },
    {
      label: tx.internal.extra,
      rows: [
        { k: tx.internal.items.body, v: money(b.cost_body_surcharge) },
        { k: tx.internal.items.restricted, v: money(b.cost_restricted_zone) },
        { k: tx.internal.items.construction, v: money(b.cost_construction_zone) },
        { k: tx.internal.items.mountain, v: money(b.cost_mountain_road) },
        { k: tx.internal.items.port, v: money(b.cost_port) },
        { k: tx.internal.items.fixed, v: money(b.cost_fixed) },
      ],
    },
    {
      label: tx.internal.totals,
      rows: [
        { k: tx.internal.items.total, v: money(b.cost_total), strong: true },
        { k: tx.internal.items.perKm, v: money(b.cost_per_km) },
        { k: tx.internal.items.perTonKm, v: b.cost_per_ton_km === null ? '—' : money(b.cost_per_ton_km) },
        { k: tx.internal.items.perVehicle, v: b.cost_per_vehicle === null ? '—' : money(b.cost_per_vehicle) },
        {
          k: tx.internal.items.utilisation,
          v: Number.isFinite(b.capacity_ratio) ? `${Math.round(b.capacity_ratio * 100)}%` : '—',
        },
        { k: tx.internal.items.vehicles, v: tx.internal.unitVehicles(String(vehicleCount)) },
        { k: tx.internal.items.matched, v: b.matched_vehicle_model_name || b.matched_vehicle_model_id || '—' },
      ],
    },
  ];

  return (
    <div className="q-result q-result--internal">
      <p className="micro q-result-kicker">{tx.internal.kicker}</p>

      <StatRow
        items={[
          { label: tx.public.distance, value: km(result.route?.distance_km ?? 0), unit: 'km' },
          { label: tx.public.duration, value: hours(result.timing?.total_duration_h ?? 0), unit: 'h' },
          { label: tx.internal.items.vehicles, value: String(vehicleCount), unit: tx.public.unitVehicles },
          {
            label: tx.internal.items.total,
            value: Number.isFinite(b.cost_total) ? money(b.cost_total).replace(' VND', '') : '—',
            unit: 'VND',
          },
        ]}
      />

      <table className="q-table">
        <caption className="q-table-cap micro">{tx.internal.tableCap}</caption>
        <thead>
          <tr>
            <th scope="col">{tx.internal.thItem}</th>
            <th scope="col">{tx.internal.thValue}</th>
          </tr>
        </thead>
        {groups.map((g) => (
          <tbody key={g.label ?? 'g'}>
            {g.label ? (
              <tr className="q-tr-group">
                <th scope="colgroup" colSpan={2}>
                  {g.label}
                </th>
              </tr>
            ) : null}
            {g.rows.map((r) => (
              <tr key={r.k} className={r.strong ? 'is-strong' : undefined}>
                <th scope="row">{r.k}</th>
                <td>{r.v}</td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>

      <p className="q-note micro">
        {tx.internal.footNote}
      </p>
    </div>
  );
}
