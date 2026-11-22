/**
 * 步骤 03 · 重量与明细：总重（吨/公斤切换，提交统一 kg）+ 货值（选填，带币种）+ 单件明细。
 *
 * - 货类由第 2 步 cargoClass 决定：本步只用它决定提示文案，**不写 cargoType**（由第 2 步派生）。
 * - 体积（volumeM3）只在拼货模式需要，公开版已去掉拼货，本步不展示该字段（字段仍保留在 state 里）。
 */
import { QField, QInput, QSwitch, QUnit } from './fields';
import type { CargoClass, CargoItem, QuoteFormState } from '../../engine/types';
import type { ReferenceBundle } from '../../api';
import { shell } from '../../i18n/shell';
import { useLang } from '../../../../../src/shell/LangProvider';

const s = (n: number | null): string => (n === null || Number.isNaN(n) ? '' : String(n));
const nOrNull = (v: string): number | null => (v.trim() ? Number(v) : null);

/** 单件重量：引擎口径存 kg，界面按「吨」填（保留 3 位，12.5 t → 12500 kg 往返无损） */
const tonFromKg = (kg: number | null): string =>
  kg === null || !Number.isFinite(kg) ? '' : String(Number((kg / 1000).toFixed(3)));
const kgFromTon = (v: string): number | null => {
  if (!v.trim()) return null;
  const ton = Number(v);
  return Number.isFinite(ton) ? Math.round(ton * 1000) : null;
};

/** 货值币种（只影响展示与后续换算，引擎只认 value_vnd） */
const CURRENCIES: { value: QuoteFormState['cargoValueCurrency']; label: string }[] = [
  { value: 'RMB', label: 'RMB' },
  { value: 'USD', label: 'USD' },
  { value: 'VND', label: 'VND' },
];

function newItem(): CargoItem {
  return {
    id: `item_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    name: '',
    count: 1,
    lengthM: 0,
    widthM: 0,
    heightM: null,
    weightKg: null,
    stackable: true,
    divisible: false,
  };
}

/**
 * 按第 2 步选的货类给出本步填写口径。
 * shell 里暂无这些 key，本步先用中文字面量（不改 i18n）。
 * tone: error = 缺件提示（不阻断，校验在 useQuoteForm）、strong = 醒目一段、soft = 常规小字。
 */
function classHint(
  cargoClass: CargoClass,
  hasItems: boolean,
): { text: string; tone: 'error' | 'strong' | 'soft' } | null {
  if (cargoClass === 'oversized') {
    return hasItems
      ? { text: '超限货物请务必填写单件长宽高，否则无法判定许可档位与是否超限。', tone: 'strong' }
      : {
          text: '超限货物：单件明细为空，请添加一件并填写长宽高 —— 缺尺寸无法判定许可档位与是否超限（本步不阻断，可先继续）。',
          tone: 'error',
        };
  }
  if (cargoClass === 'equipment' || cargoClass === 'heavy') {
    return { text: '请填单件尺寸，系统按件配车。', tone: 'soft' };
  }
  if (cargoClass === 'small') {
    return { text: '多件零担请填件数，系统按体积与件数合并配车。', tone: 'soft' };
  }
  return null; // normal：回落到明细表通用说明
}

/** 提示文案 → 现有类名（不新增 CSS） */
function hintClassOf(tone: 'error' | 'strong' | 'soft' | 'plain'): string {
  if (tone === 'error') return 'q-field-error';
  if (tone === 'strong') return 'q-note';
  return 'q-note micro';
}

export default function CargoStep({
  form,
  patch,
  problems,
  // 保留入参：调用方固定传 4 个 props，本步已不需要参考数据
  reference: _reference,
}: {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  problems: Partial<Record<keyof QuoteFormState, string>>;
  reference: ReferenceBundle | null;
}) {
  const { lang } = useLang();
  const q = shell(lang);

  const switchUnit = (next: 'ton' | 'kg') => {
    if (next === form.weightUnit) return;
    const current = Number(form.weightKg);
    if (!form.weightKg.trim() || !Number.isFinite(current)) {
      patch({ weightUnit: next });
      return;
    }
    // 吨 ⇄ 公斤换算，保留可读精度（公斤取整，吨保留 3 位）
    const converted =
      next === 'kg' ? String(Math.round(current * 1000)) : String(Number((current / 1000).toFixed(3)));
    patch({ weightUnit: next, weightKg: converted });
  };

  const switchCurrency = (next: string) => {
    // QUnit 只回字符串，这里收窄到 state 的三个合法币种，避免非法值进 state
    patch({ cargoValueCurrency: next === 'USD' || next === 'VND' ? next : 'RMB' });
  };

  const updateItem = (id: string, p: Partial<CargoItem>) => {
    patch({ items: form.items.map((i) => (i.id === id ? { ...i, ...p } : i)) });
  };

  const hint = classHint(form.cargoClass, form.items.length > 0);
  const hintText = hint === null ? q.cargo.itemsHint : hint.text;
  const hintClass = hintClassOf(hint === null ? 'plain' : hint.tone);

  return (
    <div className="q-step-body">
      {/* 总重量（必填）/ 货值（选填 + 币种） */}
      <div className="q-grid q-grid-2">
        <div className="q-field">
          <p className="q-field-label micro">
            <span>
              {q.cargo.weight}<span className="q-req">*</span>
            </span>
          </p>
          <div className="q-inline">
            <QInput
              value={form.weightKg}
              onChange={(v) => patch({ weightKg: v })}
              placeholder={form.weightUnit === 'ton' ? q.cargo.weightPhTon : q.cargo.weightPhKg}
              ariaLabel={q.cargo.weight}
            />
            <QUnit
              value={form.weightUnit}
              onChange={(v) => switchUnit(v === 'kg' ? 'kg' : 'ton')}
              options={[
                { value: 'ton', label: q.cargo.unitTon },
                { value: 'kg', label: q.cargo.unitKg },
              ]}
            />
          </div>
          <p className="q-note micro">
            {form.weightUnit === 'ton' ? q.cargo.unitHintTon : q.cargo.unitHintKg}
          </p>
          {problems.weightKg ? <p className="q-field-error">{problems.weightKg}</p> : null}
        </div>

        <QField label="货值（选填·保险与关税参考）">
          <div className="q-inline">
            <QInput
              value={form.cargoValueVnd}
              onChange={(v) => patch({ cargoValueVnd: v })}
              placeholder="0.00"
              ariaLabel="货值"
            />
            <QUnit
              value={form.cargoValueCurrency}
              onChange={switchCurrency}
              options={CURRENCIES}
            />
          </div>
        </QField>
      </div>

      {/* 单件明细 */}
      <div className="q-items">
        <div className="q-sub-head">
          <p className="micro">{q.cargo.items(form.items.length)}</p>
          <button
            type="button"
            className="q-add"
            onClick={() => patch({ items: [...form.items, newItem()] })}
          >
            {q.cargo.addItem}
          </button>
        </div>

        {/* 按货类提示：超限=醒目一段 / 缺件=红字但不阻断 / 其余=小字说明 */}
        <p className={hintClass}>{hintText}</p>
        {problems.items ? <p className="q-field-error">{problems.items}</p> : null}

        {form.items.map((item, i) => (
          <div className="q-item" key={item.id}>
            <div className="q-item-head">
              <span className="micro">{q.cargo.itemNo(String(i + 1).padStart(2, '0'))}</span>
              <button
                type="button"
                className="q-x"
                onClick={() => patch({ items: form.items.filter((x) => x.id !== item.id) })}
                aria-label={q.cargo.removeItem(i + 1)}
              >
                {q.cargo.remove}
              </button>
            </div>

            <QField label={q.cargo.name}>
              <QInput
                kind="text"
                value={item.name}
                onChange={(v) => updateItem(item.id, { name: v })}
                placeholder={q.cargo.namePh}
                ariaLabel={q.cargo.name}
              />
            </QField>

            {/* 列：长 m / 宽 m / 高 m / 单重 t（存 kg） */}
            <div className="q-grid q-grid-4">
              <QField label={q.cargo.length} hint="m">
                <QInput
                  value={s(item.lengthM)}
                  onChange={(v) => updateItem(item.id, { lengthM: Number(v) || 0 })}
                  ariaLabel={q.cargo.length}
                />
              </QField>
              <QField label={q.cargo.width} hint="m">
                <QInput
                  value={s(item.widthM)}
                  onChange={(v) => updateItem(item.id, { widthM: Number(v) || 0 })}
                  ariaLabel={q.cargo.width}
                />
              </QField>
              <QField label={q.cargo.height} hint="m">
                <QInput
                  value={s(item.heightM)}
                  onChange={(v) => updateItem(item.id, { heightM: nOrNull(v) })}
                  ariaLabel={q.cargo.height}
                />
              </QField>
              <QField label="单重" hint="t">
                <QInput
                  value={tonFromKg(item.weightKg)}
                  onChange={(v) => updateItem(item.id, { weightKg: kgFromTon(v) })}
                  ariaLabel="单重（吨）"
                />
              </QField>
            </div>

            {/* 列：件数 / 可叠 / 可拆 */}
            <div className="q-grid q-grid-4">
              <QField label={q.cargo.qty}>
                <QInput
                  value={String(item.count)}
                  onChange={(v) => updateItem(item.id, { count: Math.max(1, parseInt(v, 10) || 1) })}
                  ariaLabel={q.cargo.qty}
                />
              </QField>
              <div className="q-field">
                <p className="q-field-label micro">
                  <span>可叠</span>
                </p>
                <QSwitch
                  checked={item.stackable}
                  onChange={(v) => updateItem(item.id, { stackable: v })}
                  label={item.stackable ? q.cargo.stackable : q.cargo.unstackable}
                  desc={item.stackable ? '' : q.cargo.unstackableDesc}
                />
              </div>
              <div className="q-field">
                <p className="q-field-label micro">
                  <span>可拆</span>
                </p>
                <label className="q-inline">
                  <input
                    type="checkbox"
                    checked={item.divisible === true}
                    onChange={(e) => updateItem(item.id, { divisible: e.target.checked })}
                    aria-label="可拆（可分件运输）"
                    // 原生复选框默认是浏览器蓝，这里只把勾选色拉到品牌墨色（不新增 CSS）
                    style={{ accentColor: 'var(--ink)' }}
                  />
                  <span className="q-note micro">可分件运输</span>
                </label>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
