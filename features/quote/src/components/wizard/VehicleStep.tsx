/**
 * 步骤 03 · 车型：引擎自动配车推荐（预填车型 + 许可档位/工作日）+ 车型选择（按类别分组）
 * + 装卸勾选（装车 / 卸车 / 随车吊）+ 四个路况开关。
 *
 * ⚠️ 公开版只做整车：`loadingMode` 保持默认 'full_truck'，页面不再提供整车/拼货选择器。
 * ⚠️ 推荐卡文案暂为中文（i18n 词条未入库），后续补词条时统一迁移，别直接照抄。
 */
import { useEffect, useState } from 'react';
import { QSwitch, QSwitchList } from './fields';
import type { CargoItem, QuoteFormState, VehicleModel } from '../../engine/types';
import type { FitCargoItem, InternalFitGroup, ReferenceBundle } from '../../api';
import { fitVehicles, getInternalKey } from '../../api';
import FitDetail from '../results/FitDetail';
import { shell, vehicleKind } from '../../i18n/shell';
import { detectLang } from '../../../../../src/shell/i18n';
import { useLang } from '../../../../../src/shell/LangProvider';


/**
 * 内部版判断：与 src/main.tsx 的 `resolveScope()` 同一口径 —— 只看 pathname，
 * 不看 query（避免客户改个参数就看到内部明细）。
 */
function isInternalPage(): boolean {
  if (typeof window === 'undefined') return false;
  return /\/internal\/?$/.test(window.location.pathname);
}


const CATEGORY_LABEL: Record<string, string> = {
  small_box: '小卡车',
  flatbed: '平板车',
  high_side: '高栏车',
  container: '集装箱车',
  cold_chain: '冷链车',
};

function categoryLabel(key: string): string {
  return vehicleKind(detectLang(), key) || CATEGORY_LABEL[key] || key;
}

function volumeOf(m: VehicleModel): string {
  const v = m.effective_volume_m3 ?? m.volume_capacity_m3;
  return v === null || v === undefined ? '—' : `${Math.round(v)} m³`;
}

/** 总重换算成公斤；空值/非数字/≤0 一律按 0（0 表示还没填够，不触发配车） */
function totalWeightKg(weightKg: string, unit: 'ton' | 'kg'): number {
  const n = Number(weightKg);
  if (!weightKg.trim() || !Number.isFinite(n) || n <= 0) return 0;
  return unit === 'ton' ? n * 1000 : n;
}

/** 明细里是否有可用于精确配车的条目（尺寸齐全 + 重量 > 0） */
function hasDetailItems(items: CargoItem[]): boolean {
  return items.some(
    (i) => i.lengthM > 0 && i.widthM > 0 && i.weightKg !== null && i.weightKg > 0,
  );
}

/**
 * 明细 → /fit 入参。
 * 只收合格明细；一条都没有时用总重造一条 12m 标准件兜底
 * （界面会标注「按标准件估算」，避免把估算当成客户真实数据）。
 */
function buildFitItems(items: CargoItem[], totalKg: number): FitCargoItem[] {
  const detail: FitCargoItem[] = [];
  for (const i of items) {
    if (!(i.lengthM > 0 && i.widthM > 0)) continue;
    if (i.weightKg === null || !(i.weightKg > 0)) continue;
    detail.push({
      name: i.name.trim() || undefined,
      length_m: i.lengthM,
      width_m: i.widthM,
      height_m: i.heightM ?? undefined,
      weight_kg: i.weightKg,
      count: i.count,
      stackable: i.stackable,
      divisible: i.divisible === true,
    });
  }
  if (detail.length > 0) return detail;
  return [
    {
      length_m: 12,
      width_m: 2.4,
      height_m: 2.5,
      weight_kg: totalKg,
      count: 1,
      stackable: false,
    },
  ];
}

export default function VehicleStep({
  form,
  patch,
  problems,
  reference,
}: {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  problems: Partial<Record<keyof QuoteFormState, string>>;
  reference: ReferenceBundle | null;
}) {
  const { lang } = useLang();
  const q = shell(lang);
  const groups = reference
    ? Object.entries(reference.vehicle_models).filter(([, list]) => Array.isArray(list) && list.length > 0)
    : [];

  const totalKg = totalWeightKg(form.weightKg, form.weightUnit);
  const usingFallback = !hasDetailItems(form.items);
  const [showAlt, setShowAlt] = useState(false);

  const first = form.fitPicks[0];
  /** 客户手选过、且与推荐不同 —— 只提示，不强改客户选择 */
  const mismatch = !!first && !!form.vehicleModelId && form.vehicleModelId !== first.model_id;

  // 🆕 46 款车全平铺会让本页高到 4000px+（实测 4483px），默认收起。
  //    推荐没预填车型、或自动匹配失败时必须自动展开 —— 否则客户不知道还要手选。
  const [showAllVehicles, setShowAllVehicles] = useState(false);
  const vehicleTotal = groups.reduce((n, [, list]) => n + list.length, 0);
  const vehiclesExpanded = showAllVehicles || form.fitStatus === 'error' || !form.vehicleModelId;

  /* ── 自动配车：进入本步骤静默请求一次；失败只降级，绝不弹窗打断手选 ── */
  useEffect(() => {
    // fitStatus 只当一次性闸门：idle 之外的任何状态都不重复请求
    if (form.fitStatus !== 'idle') return;
    if (totalKg <= 0) return;
    // 🆕 超限货物必须先有单件尺寸。无明细时兜底成「12m 标准件」会把超限货误配成普通平板
    //    —— 实测：选「超大型超限货物」+ 只填 25t，推荐出「普通平板 13 米」，与实际形态不符。
    const validItems = form.items.filter((i) => i.lengthM > 0 && i.widthM > 0);
    if (form.cargoClass === 'oversized' && validItems.length === 0) {
      patch({
        fitStatus: 'error',
        fitNote: '超限货物请先在第 3 步填写单件长宽高 —— 没有尺寸就判不了许可档位，也配不出车型。',
      });
      return;
    }

    let alive = true;
    patch({ fitStatus: 'loading' });

    const run = async () => {
      try {
        const res = await fitVehicles({
          items: buildFitItems(form.items, totalKg),
          cargo_type: form.cargoType,
          allow_oversized: form.cargoClass === 'oversized',
        });
        if (!alive) return;
        patch({
          fitStatus: 'ok',
          fitPicks: res.picks,
          fitNote: res.note,
          fitTotalTrucks: res.total_trucks,
          // 推荐只做预填：下方车型列表仍可点击，客户随时能改
          ...(res.picks[0] ? { vehicleModelId: res.picks[0].model_id } : {}),
        });
      } catch (err) {
        if (!alive) return;
        // 引擎未配置 / 网络不可用都是常态，静默降级到手选
        console.warn('[VehicleStep] 自动配车不可用，已降级为手动选车：', err);
        patch({ fitStatus: 'error' });
      }
    };
    void run();

    return () => {
      alive = false;
    };
    // 依赖刻意不含 fitStatus / patch：前者在函数体内判断（写进依赖会自触发），
    // 后者来自 useCallback，引用恒定
  }, [form.cargoClass, form.cargoType, form.weightKg, form.weightUnit, form.items]);

  /* ── 内部版配车明细：四约束分解 / 轴荷线 / 共车组合（公开版永不请求） ──
   * 刻意独立成第二个请求，不改动上面的公开自动配车 effect —— 公开路径必须零变化。
   * 只在「公开配车已成功（fitStatus='ok'）+ 有内部口令」时补一次带 x-quote-key 的
   * 同一请求；拿不到（无口令 / 401 / 形状不对）就整块不渲染，不影响手选车型。
   */
  const internalPage = isInternalPage();
  const [fitGroups, setFitGroups] = useState<InternalFitGroup[]>([]);

  useEffect(() => {
    if (!internalPage) return;
    if (form.fitStatus !== 'ok') return;
    const key = getInternalKey();
    if (!key) return;

    // 输入变了就先清掉旧明细，别让上一次货物的数字留在屏幕上
    setFitGroups([]);

    let alive = true;
    const run = async () => {
      try {
        const res = await fitVehicles(
          {
            items: buildFitItems(form.items, totalKg),
            cargo_type: form.cargoType,
            allow_oversized: form.cargoClass === 'oversized',
          },
          key,
        );
        if (!alive) return;
        setFitGroups(Array.isArray(res.groups) ? res.groups : []);
      } catch (err) {
        if (!alive) return;
        console.warn('[VehicleStep] 内部配车明细不可用，已隐藏明细块：', err);
        setFitGroups([]);
      }
    };
    void run();

    return () => {
      alive = false;
    };
    // 依赖与公开 effect 同源；fitStatus 只当「公开配车已成功」的闸门（同一原因不写进依赖）
  }, [internalPage, form.fitStatus, form.cargoClass, form.cargoType, form.weightKg, form.weightUnit, form.items]);

  return (
    <div className="q-step-body">
      {/* ① 推荐卡：loading / ok（有方案）/ ok（配不出车）/ error 四态 */}
      {form.fitStatus === 'loading' ? (
        <p className="q-note micro">正在按货物匹配车型…</p>
      ) : null}

      {form.fitStatus === 'error' ? (
        // fitNote 可能是「超限货物请先填单件尺寸」这类**可行动**提示，必须优先于通用降级文案
        <p className="q-note micro">{form.fitNote || '自动匹配暂不可用，请手动选择车型。'}</p>
      ) : null}

      {form.fitStatus === 'ok' && first ? (
        <div className="q-fit">
          <div className="q-fit-tag">◎ 引擎推荐</div>
          <div className="q-fit-name">{first.name}</div>
          <div className="q-fit-chips">
            <span className="q-chip">{first.vehicle_count} 辆</span>
            {first.oversize ? <span className="q-chip is-warn">超限件</span> : null}
            {first.permit_tier ? (
              <span className="q-chip is-warn">
                {first.permit_tier}许可 · 省内 {first.permit_workdays_local ?? '—'} 个工作日
              </span>
            ) : null}
          </div>

          {form.fitPicks.length > 1 ? (
            <button
              type="button"
              className="q-fit-alt"
              aria-expanded={showAlt}
              onClick={() => setShowAlt((v) => !v)}
            >
              {showAlt ? '收起其他方案' : `查看其他方案（${form.fitPicks.length - 1}）`}
            </button>
          ) : null}

          {showAlt && form.fitPicks.length > 1 ? (
            <ul className="q-vlist">
              {form.fitPicks.slice(1).map((p) => {
                const on = form.vehicleModelId === p.model_id;
                return (
                  <li key={p.model_id}>
                    <button
                      type="button"
                      className={`q-vrow${on ? ' is-on' : ''}`}
                      aria-pressed={on}
                      onClick={() => patch({ vehicleModelId: p.model_id })}
                    >
                      <span className="q-vrow-mark micro" aria-hidden="true">
                        {on ? '●' : '○'}
                      </span>
                      <span className="q-vrow-name">
                        {p.name}
                        {p.oversize ? <span className="q-vrow-fit micro">超限</span> : null}
                      </span>
                      <span className="q-vrow-spec micro">{p.vehicle_count} 辆</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}

          {form.fitNote ? <p className="q-fit-note">{form.fitNote}</p> : null}
          {usingFallback ? (
            <p className="q-fit-note">未填单件明细，按总重 1 件 12m 标准件估算。</p>
          ) : null}
          {mismatch ? (
            <p className="q-fit-note">当前手动选择与推荐不符，可能影响合规性。</p>
          ) : null}
        </div>
      ) : null}

      {form.fitStatus === 'ok' && !first ? (
        <div className="q-fit">
          <div className="q-fit-tag">◎ 引擎推荐</div>
          <p className="q-note">{form.fitNote || '按当前货物信息未能配出合适车型。'}</p>
          <p className="q-fit-note">可手动选择，或补充单件明细后重试。</p>
        </div>
      ) : null}

      {/* ①.5 内部版配车明细：公开版不渲染（fitGroups 只会在内部口径下被填充） */}
      {internalPage && fitGroups.length > 0 ? <FitDetail groups={fitGroups} /> : null}

      {/* ② 车型列表：按类别分组、点击单选；推荐只是预填，这里永远可改 */}
      <div className="q-vehicles">
        <div className="q-sub-head">
          <p className="micro">
            {q.vehicle.type}<span className="q-req">*</span>
          </p>
          <p className="micro q-sub-note">
            {groups.length > 0 ? q.vehicle.typeCount(groups.reduce((n, [, l]) => n + l.length, 0)) : q.vehicle.refLoading}
          </p>
        </div>

        {problems.vehicleModelId ? (
          <p className="q-field-error">{problems.vehicleModelId}</p>
        ) : null}

        {groups.length === 0 ? (
          <p className="q-note micro">
            {reference ? q.vehicle.fleetEmpty : q.vehicle.fleetLoading}
          </p>
        ) : null}

        <button
          type="button"
          className="q-fit-alt"
          aria-expanded={vehiclesExpanded}
          onClick={() => setShowAllVehicles((v) => !v)}
        >
          {vehiclesExpanded ? '收起车型列表' : `手动选择车型（共 ${vehicleTotal} 款）`}
        </button>

        {vehiclesExpanded ? groups.map(([cat, list]) => (
          <div className="q-vgroup" key={cat}>
            <p className="q-vgroup-t micro">{categoryLabel(cat)}</p>
            <ul className="q-vlist">
              {list.map((m) => {
                const on = form.vehicleModelId === m.model_id;
                const fit = m.suitable_cargo_types.includes(form.cargoType);
                return (
                  <li key={m.model_id}>
                    <button
                      type="button"
                      className={`q-vrow${on ? ' is-on' : ''}`}
                      aria-pressed={on}
                      onClick={() => patch({ vehicleModelId: on ? '' : m.model_id })}
                    >
                      <span className="q-vrow-mark micro" aria-hidden="true">
                        {on ? '●' : '○'}
                      </span>
                      <span className="q-vrow-name">
                        {m.display_name}
                        {fit ? <span className="q-vrow-fit micro">{q.vehicle.fits}</span> : null}
                      </span>
                      <span className="q-vrow-spec micro">
                        {q.vehicle.load(String(m.max_load_ton))}
                        <span className="q-vrow-sep" aria-hidden="true">
                          /
                        </span>
                        {q.vehicle.volume(volumeOf(m))}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )) : null}
      </div>

      {/* ③ 装卸勾选：needLoading 在这里出现，下面的开关列表不再重复收它 */}
      <p className="q-field-label micro">装卸需求</p>
      <div className="q-checkrow">
        <label className="q-check">
          <input
            type="checkbox"
            checked={form.needLoading}
            onChange={(e) => patch({ needLoading: e.target.checked })}
          />
          含装车 · 吊装
        </label>
        <label className="q-check">
          <input
            type="checkbox"
            checked={form.needUnloading}
            onChange={(e) => patch({ needUnloading: e.target.checked })}
          />
          含卸车
        </label>
        <label className="q-check">
          <input
            type="checkbox"
            checked={form.needCrane}
            onChange={(e) => patch({ needCrane: e.target.checked })}
          />
          需随车吊
        </label>
      </div>

      <QSwitchList>
        <p className="q-field-label micro">附加条件</p>
        <QSwitch
          checked={form.emptyReturn}
          onChange={(v) => patch({ emptyReturn: v })}
          label={q.vehicle.conds.returnEmpty.label}
          desc={q.vehicle.conds.returnEmpty.desc}
        />
        <QSwitch
          checked={form.avoidRestrictedZones}
          onChange={(v) => patch({ avoidRestrictedZones: v })}
          label={q.vehicle.conds.avoidRestricted.label}
          desc={q.vehicle.conds.avoidRestricted.desc}
        />
        <QSwitch
          checked={form.avoidConstructionZones}
          onChange={(v) => patch({ avoidConstructionZones: v })}
          label={q.vehicle.conds.avoidConstruction.label}
          desc={q.vehicle.conds.avoidConstruction.desc}
        />
        <QSwitch
          checked={form.viaMountainRoad}
          onChange={(v) => patch({ viaMountainRoad: v })}
          label={q.vehicle.conds.mountain.label}
          desc={q.vehicle.conds.mountain.desc}
        />
      </QSwitchList>
    </div>
  );
}
