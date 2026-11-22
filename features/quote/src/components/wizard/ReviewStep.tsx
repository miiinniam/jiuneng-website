/**
 * 步骤 05 · 提交前核对。
 *
 * 为什么要有这一步：提交后引擎才返回运价区间与许可档位，一旦漏填单件尺寸或选错车型，
 * 用户要重填整条链路 —— 所以提交前把「线路 / 货物 / 车型」三件决定报价的事摊开，
 * 每行末尾给一个「改」直接跳回对应步骤（只跳转、不重复收集数据）。
 *
 * 本组件不接 reference：车型名优先取 fitPicks 里同名 model_id 的 name，
 * 取不到就回落到 model_id —— 宁可显示内部编号，也不显示空白。
 */
import type { QuoteFormState } from '../../engine/types';

const CLASS_LABEL: Record<string, string> = {
  normal: '普通货物',
  equipment: '机械设备',
  heavy: '大型机械',
  oversized: '超大型超限货物',
  small: '小件货物',
};

/** 去尾零 + 最多 3 位小数：吨位 0.8 与 12.5 都要好读，避免 12.500000001 */
function num(n: number): string {
  return String(Number(n.toFixed(3)));
}

/** 地名优先；没选地名（手填坐标）就显示坐标，保留 4 位小数（≈11m，够表达装卸点） */
function place(label: string | undefined, lat: string, lng: string): string {
  const named = (label ?? '').trim();
  if (named) return named;
  const la = Number(lat);
  const ln = Number(lng);
  if (!Number.isFinite(la) || !Number.isFinite(ln)) return '—';
  return `${la.toFixed(4)}, ${ln.toFixed(4)}`;
}

/** 表单重量是「显示单位」口径，这里统一折成吨再展示 */
function tonText(weight: string, unit: 'ton' | 'kg'): string | null {
  const raw = Number(weight);
  if (!weight.trim() || !Number.isFinite(raw)) return null;
  return num(unit === 'kg' ? raw / 1000 : raw);
}

export default function ReviewStep({
  form,
  onEdit,
}: {
  form: QuoteFormState;
  onEdit?: (step: number) => void;
}) {
  const origin = place(form.originLabel, form.originLat, form.originLng);
  const dest = place(form.destLabel, form.destLat, form.destLng);

  const ton = tonText(form.weightKg, form.weightUnit);
  const pieces = form.items.reduce((sum, i) => sum + (Number.isFinite(i.count) ? i.count : 0), 0);
  const cargoParts = [
    CLASS_LABEL[form.cargoClass] ?? form.cargoClass,
    ton ? `总重 ${ton} t` : '总重未填',
    pieces > 0 ? `${pieces} 件` : '件数未填',
  ];

  // 不传 reference，所以车型名只能从自动推荐结果里按 model_id 反查
  const picked = form.fitPicks.find((p) => p.model_id === form.vehicleModelId);
  const vehicleName = (picked?.name ?? '').trim() || form.vehicleModelId || '—';

  const first = form.fitPicks[0];
  const tier = first?.permit_tier ?? null;
  const permitDays = first?.permit_workdays_local ?? null;

  const handling = [
    form.needLoading ? '含装车' : '',
    form.needUnloading ? '含卸车' : '',
    form.needCrane ? '需随车吊' : '',
  ]
    .filter(Boolean)
    .join(' · ');

  const pickTrucks = form.fitPicks.reduce((sum, p) => sum + (p.vehicle_count || 0), 0);
  const trucks =
    form.fitTotalTrucks > 0
      ? `系统配车 ${form.fitTotalTrucks} 台（明细合计 ${pickTrucks} 台）`
      : '未采用自动配车，按手选车型核算';

  /** 「改」是次级动作：样式沿用链接式按钮，靠内联 margin 抹掉 .q-fit-alt 的块级上边距 */
  const edit = (step: number) =>
    onEdit ? (
      <button
        type="button"
        className="q-fit-alt micro"
        style={{ marginTop: 0, marginLeft: 'var(--sp-3)' }}
        onClick={() => onEdit(step)}
      >
        改
      </button>
    ) : null;

  return (
    <div className="q-step-body">
      <table className="q-review">
        <tbody>
          <tr>
            <th scope="row">线路</th>
            <td>
              {origin} → {dest}
              {edit(0)}
            </td>
          </tr>
          <tr>
            <th scope="row">货物</th>
            <td>
              {cargoParts.join(' · ')}
              {edit(1)}
            </td>
          </tr>
          <tr>
            <th scope="row">车型</th>
            <td>
              {vehicleName}
              {edit(3)}
            </td>
          </tr>
          <tr>
            <th scope="row">许可</th>
            <td>
              {tier ? (
                <span className="q-review-key">
                  {tier}
                  {permitDays ? ` · 省内 ${permitDays} 个工作日` : ''}
                </span>
              ) : (
                '—'
              )}
            </td>
          </tr>
          <tr>
            <th scope="row">装卸</th>
            <td>{handling || '不含装卸（发货方自装、收货方自卸）'}</td>
          </tr>
          <tr>
            <th scope="row">备注</th>
            <td>{trucks}</td>
          </tr>
        </tbody>
      </table>

      <p className="q-note micro">提交后返回运价区间、许可档位与预计交期；如需调整，点上面每行的「改」。</p>
    </div>
  );
}
