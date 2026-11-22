/**
 * 公开版结果：里程 / 时长 / 车辆数 / 车型 + 参考价区间。
 * 口径（CONTRACT §2）：不出现成本、毛利、分项。
 * price_low_vnd / price_high_vnd 线上实测为 null —— 此时**不显示 0 或 —**，
 * 改为“参考价区间需项目经理核定” + 提交询价入口。
 */
import type { PublicQuoteResult } from '../../api';
import { StatRow, hours, km, money } from './ResultBits';
import { resultsText } from '../../i18n/results';
import { useLang } from '../../../../../src/shell/LangProvider';


export default function PublicResult({ result }: { result: PublicQuoteResult }) {
  const { lang } = useLang();
  const tx = resultsText(lang);
  const totalHours = result.timing?.total_duration_h ?? result.duration_h;
  const loading = result.timing?.loading_hours ?? 0;
  const rest = result.timing?.rest_hours ?? 0;

  const low = typeof result.price_low_vnd === 'number' ? result.price_low_vnd : null;
  const high = typeof result.price_high_vnd === 'number' ? result.price_high_vnd : null;
  const hasPrice = low !== null && high !== null;

  return (
    <div className="q-result">
      <p className="micro q-result-kicker">{tx.public.kicker}</p>

      <StatRow
        items={[
          { label: tx.public.distance, value: km(result.distance_km), unit: 'km' },
          { label: tx.public.duration, value: hours(totalHours), unit: 'h' },
          { label: tx.public.vehicles, value: String(result.vehicle_count), unit: tx.public.unitVehicles },
          {
            label: tx.public.vehicle,
            value: result.vehicle?.name ?? tx.public.autoMatch,
            unit: result.vehicle?.max_load_ton ? tx.public.payload(String(result.vehicle.max_load_ton)) : undefined,
          },
        ]}
      />

      {hasPrice ? (
        <div className="q-price">
          <p className="micro">{tx.public.priceRange}</p>
          <p className="q-price-v">
            {money(low)}
            <span className="q-price-dash" aria-label={tx.public.toAria}>
              –
            </span>
            {money(high)}
          </p>
          <p className="q-note">
            {tx.public.priceNote}
          </p>
        </div>
      ) : (
        <div className="q-price q-price--pending">
          <p className="micro">{tx.public.price}</p>
          <p className="q-price-pending">{tx.public.pendingRange}</p>
          <p className="q-note">
            {tx.public.pendingRangeBody}
          </p>
          <a className="btn q-price-cta" href="/contact">
            {tx.public.submitInquiry}
          </a>
        </div>
      )}

      {loading > 0 || rest > 0 ? (
        <p className="q-note micro">
          {tx.public.withLoading(hours(loading))}
          {rest > 0 ? tx.public.withRest(hours(rest)) : ''}
        </p>
      ) : null}

      <p className="q-note micro">
        {tx.public.footNote}
      </p>
    </div>
  );
}
