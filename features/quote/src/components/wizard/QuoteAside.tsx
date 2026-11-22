/**
 * 右侧「当前填写」摘要卡 —— 设计稿 `docs/ai-inquiry/mockups/quote-form-5steps.html` 的 `.q-aside`。
 *
 * 规矩：**只读 `form`，不写任何状态**。摘要卡不能成为第二份真相 ——
 * 它的每一行都必须是表单里已有的值，算不出就显示「待填」而不是猜。
 * 许可档位取自 `form.fitPicks[0]`（第 4 步自动配车写入的引擎结果），没有就留空。
 */
import type { QuoteFormState } from '../../engine/types';

/** 分类名与 `CargoClassStep.tsx` 的 CLASSES 同源；改一处必须改两处（那边的 desc 更长，不适合摘要）。 */
const CLASS_NAME: Record<string, string> = {
  normal: '普通货物',
  equipment: '机械设备',
  heavy: '大型机械',
  oversized: '超大型超限',
  small: '小件货物',
};

function weightText(form: QuoteFormState): string {
  const raw = Number(form.weightKg);
  if (!Number.isFinite(raw) || raw <= 0) return '';
  // 表单里 weightKg 是「按 weightUnit 记的数值」，展示统一折成吨
  const tons = form.weightUnit === 'kg' ? raw / 1000 : raw;
  const rounded = Math.round(tons * 100) / 100;
  return `${rounded} 吨`;
}

function itemsText(form: QuoteFormState): string {
  if (!form.items?.length) return '';
  const pieces = form.items.reduce((sum, it) => {
    const n = Number(it.count);
    return sum + (Number.isFinite(n) && n > 0 ? n : 1);
  }, 0);
  return `${form.items.length} 行 / ${pieces} 件`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="q-kv">
      <span className="k">{label}</span>
      <span className={value ? 'v' : 'v empty'}>{value || '待填'}</span>
    </div>
  );
}

export default function QuoteAside({ form }: { form: QuoteFormState }) {
  const route =
    form.originLabel && form.destLabel ? `${form.originLabel} → ${form.destLabel}` : '';
  const pick = form.fitPicks?.[0];
  const permit =
    pick && pick.permit_tier
      ? `${pick.permit_tier} · ${pick.permit_workdays_local ?? '-'} 个工作日`
      : '';

  return (
    <aside className="q-aside" aria-label="当前填写">
      <div className="q-aside-hd">当前填写</div>
      <Row label="线路" value={route} />
      <Row label="货物分类" value={CLASS_NAME[form.cargoClass] ?? ''} />
      <Row label="总重量" value={weightText(form)} />
      <Row label="明细" value={itemsText(form)} />
      <Row label="车型" value={pick?.name ?? ''} />
      <Row label="许可" value={permit} />
      <div className="q-aside-ft">结果由配车引擎按真实口径计算，仅作参考价，不作为正式报价。</div>
    </aside>
  );
}
