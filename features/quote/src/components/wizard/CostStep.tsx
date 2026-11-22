/**
 * 步骤 04 · 成本参数（仅内部版）：油价 / 时薪 / 过路费率 / 杂费。
 * 留空 = 让引擎用内置默认值（form 里的空串会由 toRequest() 跳过，不塞 0）。
 */
import { QField, QInput } from './fields';
import type { QuoteFormState } from '../../engine/types';
import { shell } from '../../i18n/shell';
import { useLang } from '../../../../../src/shell/LangProvider';


export default function CostStep({
  form,
  patch,
  problems,
}: {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  problems: Partial<Record<keyof QuoteFormState, string>>;
}) {
  const { lang } = useLang();
  const q = shell(lang);
  return (
    <div className="q-step-body">
      <p className="q-note">
        {q.cost.intro}
      </p>

      <div className="q-grid q-grid-2">
        <QField label={q.cost.fuel} hint="VND/L" error={problems.fuelPriceVnd}>
          <QInput
            value={form.fuelPriceVnd}
            onChange={(v) => patch({ fuelPriceVnd: v })}
            placeholder={q.cost.phDefault}
            ariaLabel={q.cost.fuel}
          />
        </QField>

        <QField label={q.cost.wage} hint="VND/h" error={problems.wageHourlyVnd}>
          <QInput
            value={form.wageHourlyVnd}
            onChange={(v) => patch({ wageHourlyVnd: v })}
            placeholder={q.cost.phDefault}
            ariaLabel={q.cost.wage}
          />
        </QField>

        <QField label={q.cost.toll} hint="VND/km" error={problems.tollRateVndPerKm}>
          <QInput
            value={form.tollRateVndPerKm}
            onChange={(v) => patch({ tollRateVndPerKm: v })}
            placeholder={q.cost.phDefault}
            ariaLabel={q.cost.toll}
          />
        </QField>

        <QField label={q.cost.misc} hint="VND" error={problems.miscCostVnd}>
          <QInput
            value={form.miscCostVnd}
            onChange={(v) => patch({ miscCostVnd: v })}
            placeholder={q.cost.phZero}
            ariaLabel={q.cost.misc}
          />
        </QField>
      </div>

      <p className="q-note micro">
        {q.cost.footNote}
      </p>
    </div>
  );
}
