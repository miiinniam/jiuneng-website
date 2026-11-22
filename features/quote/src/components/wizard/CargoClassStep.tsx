/**
 * 步骤 02 · 货物分类（5 类用户口径）。
 *
 * 为什么分类要单独一步：用户不认引擎的 cargo_type（6 个内部枚举），
 * 只认「我这批货是什么」—— 分类决定后续必填字段（单件尺寸 / 件数）与许可口径，
 * 所以先分类、再填参数，避免在第 3 页用一堆字段吓退用户。
 *
 * ⚠️ 点击时必须同时写 cargoClass 与 cargoType：引擎只认 cargoType（CARGO_CLASS_TO_TYPE 派生），
 *    只写 cargoClass 会出现「界面选了大型机械、引擎按普通货物报价」的静默错价。
 */
import { CARGO_CLASS_TO_TYPE } from '../../engine/types';
import type { CargoClass, QuoteFormState } from '../../engine/types';

type ClassDef = {
  value: CargoClass;
  name: string;
  desc: string;
  /** 超大型 / 小件独占一整行：前者是「例外路径」，后者是「零担路径」，视觉上要脱离 2×2 网格的并列感 */
  fullRow?: boolean;
};

const CLASSES: ClassDef[] = [
  {
    value: 'normal',
    name: '普通货物',
    desc: '包装成件的工业品、日用品；外廓不超 18m × 2.55m × 4.0m',
  },
  {
    value: 'equipment',
    name: '机械设备',
    desc: '成套设备、机床、发电机组；需填单件尺寸',
  },
  {
    value: 'heavy',
    name: '大型机械',
    desc: '挖掘机、履带设备、工程车；需尺寸 + 自重',
  },
  {
    value: 'oversized',
    name: '超大型超限货物',
    desc: '风电叶片、塔筒、变压器、模块车货；系统自动判定许可档位',
    fullRow: true,
  },
  {
    value: 'small',
    name: '小件货物',
    desc: '多件零担、配件、样品；按件数与体积合并配车',
    fullRow: true,
  },
];

/** 选中后的业务后果提示：写的都是「接下来会发生什么」，不是「您已选择」 */
const NOTES: Record<CargoClass, string> = {
  normal:
    '外廓不超 18m × 2.55m × 4.0m 无需超限许可，可直接按普通平板/厢车配车；若有单件明显偏长，请在下页填单件尺寸。',
  equipment:
    '下一步请填单件长宽高；缺尺寸时系统只能按总重估算，配车精度下降、可能少算车。',
  heavy:
    '下一步请填单件长宽高与自重；自重决定轴荷与是否需低平板，漏填会低估运费。',
  oversized:
    '系统将自动判定许可档位（一类约 2 天 / 二类约 5 天 / 三类约 15 天）与是否需轮廓图、护送方案；档位由外廓尺寸决定，交期从受理起算。',
  small:
    '按件数与体积合并配车；建议填清件数与总体积，否则零担会被按整车计价。',
};

export default function CargoClassStep({
  form,
  patch,
  problems,
}: {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  problems: Partial<Record<keyof QuoteFormState, string>>;
}) {
  // 被模板/旧存档带进来的未知值找不到定义时不崩，只是不高亮
  const active = CLASSES.find((c) => c.value === form.cargoClass) ?? null;

  return (
    <div className="q-step-body">
      <p className="q-field-label micro">
        货物分类<span className="q-req">*</span>
      </p>

      <div className="q-classes">
        {CLASSES.map((c) => {
          const on = c.value === form.cargoClass;
          return (
            <button
              key={c.value}
              type="button"
              className={`q-class${c.fullRow ? ' q-class-more' : ''}${on ? ' is-on' : ''}`}
              aria-pressed={on}
              onClick={() => patch({ cargoClass: c.value, cargoType: CARGO_CLASS_TO_TYPE[c.value] })}
            >
              <span className="q-class-n">
                {c.name}
                {c.value === 'oversized' ? (
                  <span
                    className="q-class-d"
                    style={{ display: 'inline', marginTop: 0, fontStyle: 'italic', color: 'var(--accent)' }}
                  >
                    {' '}超重 / 超高 / 超宽
                  </span>
                ) : null}
              </span>
              <span className="q-class-d">{c.desc}</span>
            </button>
          );
        })}
      </div>

      {problems.cargoClass ? <p className="q-field-error">{problems.cargoClass}</p> : null}

      {active ? <p className="q-classnote">{NOTES[active.value]}</p> : null}
    </div>
  );
}
