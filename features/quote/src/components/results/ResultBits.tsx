/**
 * 结果面板共用零件：数字排版、事实行、内部结果类型守卫。
 * 全部走 .q- 前缀（CONTRACT §7），不用卡片阴影，只有发丝线。
 */
import type { QuoteResponse } from '../../engine/types';

/** 内部结果守卫：公开口径里根本没有 breakdown 键（CONTRACT §10 硬断言） */
export function isInternalResult(r: unknown): r is QuoteResponse {
  return !!r && typeof r === 'object' && 'breakdown' in (r as Record<string, unknown>);
}

export function StatRow({
  items,
}: {
  items: { label: string; value: string; unit?: string }[];
}) {
  return (
    <dl className="q-stat-row">
      {items.map((it) => (
        <div className="q-stat" key={it.label}>
          <dt className="q-stat-l micro">{it.label}</dt>
          <dd className="q-stat-v">
            {it.value}
            {it.unit ? <span className="q-stat-u"> {it.unit}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function km(n: number): string {
  return Number.isFinite(n) ? n.toFixed(0) : '—';
}

export function hours(n: number): string {
  return Number.isFinite(n) ? n.toFixed(1) : '—';
}

export function money(n: number): string {
  return Number.isFinite(n) ? `${n.toLocaleString('vi-VN', { maximumFractionDigits: 0 })} VND` : '—';
}
