// features/quote/src/state/useQuoteForm.ts
// 表单状态机：从 legacy frontend/src/hooks/useQuoteForm.ts 移植并按 CONTRACT.md §6 收敛。
// 出口签名固定为 { form, patch, apply, reset, toRequest, problems, canNext }。
// 只用 useState/useCallback，不引入任何状态库（CONTRACT §6 / §11）。

import { useCallback, useState } from 'react';
import type { QuoteFormState, QuoteRequest } from '../engine/types';
import type { QuoteScope } from '../api';
import { validateText } from '../i18n/validation';
import { useLang } from '../../../../src/shell/LangProvider';

export type QuoteStep = 0 | 1 | 2 | 3 | 4 | 5;
/** 步骤口径（公开版 5 步 + 内部版多一步成本）：
 *  0 路线 · 1 货物分类 · 2 重量与明细 · 3 车型 · 4 提交确认 · 5 成本参数（仅内部版） */

export interface UseQuoteFormOptions {
  scope: QuoteScope;
  status: 'idle' | 'loading' | 'ok' | 'error';
  result?: unknown;
}

export interface UseQuoteFormResult {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  apply: (s: QuoteFormState) => void;
  reset: () => void;
  toRequest: () => QuoteRequest;
  problems: Partial<Record<keyof QuoteFormState, string>>;
  canNext: (step: QuoteStep) => boolean;
}

/** 改这些字段 ⇒ 旧配车推荐作废（见 patch 注释）。`fitStatus` 刻意不在内，避免自我触发。 */
const FIT_INPUT_KEYS = ['weightKg', 'weightUnit', 'items', 'cargoClass', 'cargoType'] as const;

/** 默认值照搬 legacy（buildDefaultForm），一个字段不改 */
function buildDefaultForm(): QuoteFormState {
  return {
    originLat: '',
    originLng: '',
    destLat: '',
    destLng: '',
    waypoints: [],
    cargoClass: 'normal' as const,
    weightKg: '',
    weightUnit: 'ton' as const,
    volumeM3: '',
    cargoType: 'normal',
    cargoValueVnd: '',
    cargoValueCurrency: 'RMB' as const,
    items: [],
    loadingMode: 'full_truck',
    vehicleModelId: '',
    emptyReturn: false,
    needLoading: false,
    needUnloading: false,
    needCrane: false,
    fitStatus: 'idle' as const,
    fitPicks: [],
    fitNote: '',
    fitTotalTrucks: 0,
    avoidRestrictedZones: false,
    avoidConstructionZones: false,
    viaMountainRoad: false,
    fuelPriceVnd: '',
    wageHourlyVnd: '',
    tollRateVndPerKm: '',
    miscCostVnd: '0',
  };
}

/** 空串或非数字 → null；用于区分“没填”和“填了 0” */
function num(v: string): number | null {
  if (v === undefined || v === null) return null;
  const s = String(v).trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function useQuoteForm(opts: UseQuoteFormOptions): UseQuoteFormResult {
  const { lang } = useLang();
  const vt = validateText(lang);
  // status / result 由页面持有（loading 态、错误提示、结果面板），
  // 状态机本身不消费；保留在签名里是为了让页面传参一致（CONTRACT §6）。
  const { scope } = opts;
  const [form, setForm] = useState<QuoteFormState>(buildDefaultForm);

  const patch = useCallback((p: Partial<QuoteFormState>) => {
    setForm((f) => {
      const next: QuoteFormState = { ...f, ...p };
      // 🆕 配车输入变了 ⇒ 旧推荐立刻作废（fitStatus 回 'idle'），
      //    第 4 步的 effect 会按新货量重新请求。
      //    ⚠️ 'fitStatus' 本身不在下面这组键里，所以「loading/ok/error」的写入不会自我触发。
      if (FIT_INPUT_KEYS.some((k) => k in p) && next.fitStatus !== 'loading') {
        next.fitStatus = 'idle';
        next.fitPicks = [];
        next.fitNote = '';
        next.fitTotalTrucks = 0;
      }
      return next;
    });
  }, []);

  const apply = useCallback((s: QuoteFormState) => {
    // 以默认值为底，避免模板缺字段时出现 undefined
    setForm({ ...buildDefaultForm(), ...s });
  }, []);

  const reset = useCallback(() => {
    setForm(buildDefaultForm());
  }, []);

  const toRequest = useCallback((): QuoteRequest => {
    const fm = form;

    // 成本参数：公开版一律不传用户填的成本，只给引擎一个 0 的占位（CONTRACT §6）
    const costParams: QuoteRequest['cost_params'] =
      scope === 'public'
        ? { misc_cost_vnd: 0 }
        : (() => {
            const p: QuoteRequest['cost_params'] = {
              misc_cost_vnd: num(fm.miscCostVnd) ?? 0,
            };
            const fuel = num(fm.fuelPriceVnd);
            if (fuel !== null) p.fuel_price_vnd = fuel;
            const wage = num(fm.wageHourlyVnd);
            if (wage !== null) p.wage_hourly_vnd = wage;
            const toll = num(fm.tollRateVndPerKm);
            if (toll !== null) p.toll_rate_vnd_per_km = toll;
            return p;
          })();

    // weightUnit 是显示单位，提交一律 kg（legacy 口径，保留）
    const rawWeight = num(fm.weightKg) ?? 0;
    const weightKg = fm.weightUnit === 'ton' ? rawWeight * 1000 : rawWeight;

    const volume = num(fm.volumeM3);
    const value = num(fm.cargoValueVnd);

    return {
      route: {
        // 没填时给 NaN（JSON 序列化成 null），让服务端明确报“参数不正确”，
        // 而不是悄悄按 (0,0) 出价。canNext(0) 已经拦在前面。
        origin: { lat: num(fm.originLat) ?? NaN, lng: num(fm.originLng) ?? NaN },
        destination: { lat: num(fm.destLat) ?? NaN, lng: num(fm.destLng) ?? NaN },
        waypoints: fm.waypoints.filter((w) => Number.isFinite(w.lat) && Number.isFinite(w.lng)),
      },
      cargo: {
        weight_kg: weightKg,
        volume_m3: volume === null ? undefined : volume,
        type: fm.cargoType,
        value_vnd: value === null ? undefined : value,
        // 单件明细：过滤无效行，转 snake_case（与 legacy 一致）
        items: fm.items
          .filter((i) => i.lengthM > 0 && i.widthM > 0)
          .map((i) => ({
            name: i.name || undefined,
            count: i.count,
            length_m: i.lengthM,
            width_m: i.widthM,
            height_m: i.heightM === null ? undefined : i.heightM,
            weight_kg: i.weightKg === null ? undefined : i.weightKg,
            stackable: i.stackable,
            divisible: i.divisible === true ? true : undefined,
          })),
      },
      vehicle: {
        loading_mode: fm.loadingMode,
        vehicle_model_id:
          fm.loadingMode === 'full_truck' ? fm.vehicleModelId || undefined : undefined,
        empty_return: fm.emptyReturn,
        need_loading: fm.needLoading,
        avoid_restricted_zones: fm.avoidRestrictedZones,
        avoid_construction_zones: fm.avoidConstructionZones,
        via_mountain_road: fm.viaMountainRoad,
      },
      cost_params: costParams,
    };
  }, [form, scope]);

  /* ── 校验：字段级中文提示（problems） ───────────────────────────── */

  const problems: Partial<Record<keyof QuoteFormState, string>> = {};

  if (num(form.originLat) === null) problems.originLat = vt.originPin;
  if (num(form.originLng) === null) problems.originLng = vt.originPin;
  if (num(form.destLat) === null) problems.destLat = vt.destPin;
  if (num(form.destLng) === null) problems.destLng = vt.destPin;

  const weight = num(form.weightKg);
  if (weight === null) problems.weightKg = vt.weight;
  else if (weight <= 0) problems.weightKg = vt.weightPositive;

  const volume = num(form.volumeM3);
  if (volume !== null && volume <= 0) problems.volumeM3 = vt.volumePositive;
  else if (form.loadingMode === 'consolidated' && volume === null)
    problems.volumeM3 = vt.volumeRequired;

  if (!form.cargoType.trim()) problems.cargoType = vt.cargoType;

  if (form.loadingMode === 'full_truck' && !form.vehicleModelId)
    problems.vehicleModelId = vt.vehicle;

  const badItem = form.items.find(
    (i) => i.count < 1 || i.lengthM < 0 || i.widthM < 0 || (i.lengthM > 0) !== (i.widthM > 0),
  );
  if (badItem) problems.items = vt.items;

  for (const [k, label] of [
    ['fuelPriceVnd', vt.fuel],
    ['wageHourlyVnd', vt.wage],
    ['tollRateVndPerKm', vt.toll],
    ['miscCostVnd', vt.misc],
  ] as const) {
    const v = num(form[k]);
    if (v !== null && v < 0) problems[k] = vt.negative(label);
  }

  /**
   * 逐步放行。步骤口径按 CONTRACT §2：
   *   0 = 路线（起点 + 终点）
   *   1 = 货物（重量 / 体积 / 货物类型）
   *   2 = 车型（整车需选车型）
   *   3 = 成本参数（仅内部版有这一步）
   * 只判定“当前这一步”是否填够，不重复校验前序步骤（与 legacy validateStep 同思路）。
   */
  const canNext = useCallback(
    (step: QuoteStep): boolean => {
      if (step === 0) {
        return (
          num(form.originLat) !== null &&
          num(form.originLng) !== null &&
          num(form.destLat) !== null &&
          num(form.destLng) !== null
        );
      }
      if (step === 1) {
        // 货物分类（5 类）：有默认值 normal，等于默认通过；超大件会在第 2/3 步强制尺寸
        return !!form.cargoClass;
      }
      if (step === 2) {
        const w = num(form.weightKg);
        if (w === null || w <= 0) return false;
        if (!form.cargoType.trim()) return false;
        if (form.loadingMode === 'consolidated') {
          const v = num(form.volumeM3);
          if (v === null || v <= 0) return false;
        }
        return true;
      }
      if (step === 3) {
        // 拼货模式由引擎按体积/重量配车，不需要选车型
        if (form.loadingMode === 'full_truck') return !!form.vehicleModelId;
        return true;
      }
      // step 4：公开版 = 提交确认（无需额外校验）；内部版 = 成本参数
      if (step === 4 && scope === 'public') return true;
      for (const k of ['fuelPriceVnd', 'wageHourlyVnd', 'tollRateVndPerKm', 'miscCostVnd'] as const) {
        const v = num(form[k]);
        if (v !== null && v < 0) return false;
      }
      return true;   // step 5 = 提交确认（仅内部版）
    },
    [form, scope],
  );

  return { form, patch, apply, reset, toRequest, problems, canNext };
}
