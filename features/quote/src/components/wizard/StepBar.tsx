/**
 * 步骤条：公开版 01 路线 / 02 货物分类 / 03 重量与明细 / 04 车型 / 05 提交测算；
 * 内部版在「提交」前多一步「成本参数」，共 6 步（labels 由调用方传入，本组件只负责渲染）。
 * 编号用 micro 字阶；当前步实色，未到步 60% 灰；步骤间发丝线；已走过的步可回跳。
 */
import type { QuoteStep } from '../../state/useQuoteForm';
import { shell } from '../../i18n/shell';
import { useLang } from '../../../../../src/shell/LangProvider';


export default function StepBar({
  labels,
  current,
  onJump,
}: {
  labels: string[];
  current: QuoteStep;
  onJump: (s: QuoteStep) => void;
}) {
  const { lang } = useLang();
  const q = shell(lang);
  return (
    <nav className="q-stepbar" aria-label={q.app.stepAria}>
      <ol className="q-stepbar-list">
        {labels.map((label, i) => {
          const idx = i as QuoteStep;
          const state = idx === current ? 'is-current' : idx < current ? 'is-done' : 'is-todo';
          const clickable = idx < current;
          return (
            <li className={`q-step ${state}`} key={label}>
              <button
                type="button"
                className="q-step-btn"
                onClick={() => (clickable ? onJump(idx) : undefined)}
                disabled={!clickable}
                aria-current={idx === current ? 'step' : undefined}
              >
                <span className="q-step-n micro">{String(i + 1).padStart(2, '0')}</span>
                <span className="q-step-l">{label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
