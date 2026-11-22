/**
 * 工作台数据投影：把「表单 + 引擎结果」压成卡片需要的结构（纯函数，可单测）。
 *
 * 为什么要这一层：卡片上的每个数字都必须来自确定性引擎，**不能**来自模型输出。
 * 模型只负责把「换成 17.5 米两辆」解析回表单，金额永远是 /api/quote/route 算出来的。
 * 所以这里只做投影与重命名，不做任何计算。
 */
import type { PublicQuoteResult, QuoteScope, ReferenceBundle } from '../../api';
import type { QuoteFormState, QuoteResponse } from '../../engine/types';
import { cargoName, strings } from '../../i18n/strings';
import { workspaceText } from '../../i18n/workspace';
import { detectLang } from '../../../../../src/shell/i18n';

export type WsLine = { key: string; label: string; value: number; note?: string };

export type WsPlan = {
  scope: QuoteScope;
  route: { from: string; to: string; km: number; hours: number };
  vehicle: { id: string; name: string; count: number; maxLoadTon: number | null };
  cargo: { weightTon: number | null; typeLabel: string; volumeM3: number | null };
  /** 公开版：区间（可能两端为 null = 待核定）；内部版：成本合计 */
  price: {
    low: number | null;
    high: number | null;
    costTotal: number | null;
    perVehicle: number | null;
    perKm: number | null;
    status: 'estimate' | 'pending' | 'cost';
  };
  cost: { lines: WsLine[]; total: number } | null; // 仅内部版
};

/** 货类键 → 中文（与 CargoStep 保持一致；未知键原样显示） */
export const CARGO_LABEL: Record<string, string> = {
  normal: '普通货物',
  cold_chain: '冷链',
  hazardous: '危险品',
  oversized: '超限货',
  heavy_equipment: '工程机械',
  other: '其他',
};

/** 成本分项 → 中文（顺序即展示顺序；0 值不显示） */
const COST_LABELS: { key: keyof QuoteResponse['breakdown']; label: string }[] = [
  { key: 'cost_distance', label: '距离运费' },
  { key: 'cost_time', label: '人工工时' },
  { key: 'cost_fuel', label: '燃油' },
  { key: 'cost_fixed', label: '固定调度费' },
  { key: 'cost_body_surcharge', label: '车型附加' },
  { key: 'cost_toll', label: '路桥费' },
  { key: 'cost_loading', label: '装卸' },
  { key: 'cost_insurance', label: '保险' },
  { key: 'cost_port', label: '口岸操作' },
  { key: 'cost_restricted_zone', label: '限行区' },
  { key: 'cost_construction_zone', label: '施工绕行' },
  { key: 'cost_mountain_road', label: '山路附加' },
  { key: 'cost_misc', label: '杂费' },
];

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function coordsOrLabel(lat: string, lng: string, label?: string): string {
  if (label && label.trim()) return label.trim();
  const a = Number(lat);
  const b = Number(lng);
  if (Number.isFinite(a) && Number.isFinite(b) && (a !== 0 || b !== 0)) {
    return `${a.toFixed(3)}, ${b.toFixed(3)}`;
  }
  return workspaceText(detectLang()).unfilled;
}

export function isInternalQuote(r: PublicQuoteResult | QuoteResponse): r is QuoteResponse {
  return typeof (r as QuoteResponse).breakdown === 'object' && (r as QuoteResponse).breakdown !== null;
}

export function buildPlan(input: {
  form: QuoteFormState;
  result: PublicQuoteResult | QuoteResponse | null;
  reference: ReferenceBundle | null;
  scope: QuoteScope;
  /** 界面语言：货类名按语言显示（缺省中文） */
  lang?: 'zh' | 'vi' | 'en';
}): WsPlan | null {
  const { form, result, reference, scope, lang = 'zh' } = input;
  if (!result) return null;

  const internal = isInternalQuote(result);
  const route = internal ? result.route : result;
  const km = num(route.distance_km) ?? 0;
  const hours = internal
    ? (num(result.timing?.total_duration_h) ?? num(result.route?.duration_h) ?? 0)
    : (num(result.timing?.total_duration_h) ?? num(result.duration_h) ?? 0);

  // 车型：公开版在 result.vehicle，内部版在 breakdown；都缺就用表单里选的 id 查参考库
  const modelId = internal
    ? (result.breakdown.matched_vehicle_model_id || form.vehicleModelId)
    : (result.vehicle?.id || form.vehicleModelId);
  let modelName = internal ? result.breakdown.matched_vehicle_model_name : result.vehicle?.name;
  let maxLoadTon = internal ? null : (result.vehicle?.max_load_ton ?? null);
  if ((!modelName || maxLoadTon === null) && reference && modelId) {
    for (const list of Object.values(reference.vehicle_models)) {
      const hit = (list || []).find((m) => m.model_id === modelId);
      if (hit) {
        modelName = modelName || hit.display_name;
        maxLoadTon = maxLoadTon ?? (num(hit.max_load_ton) ?? null);
        break;
      }
    }
  }

  const rawWeight = Number(form.weightKg);
  const weightTon =
    Number.isFinite(rawWeight) && rawWeight > 0
      ? form.weightUnit === 'ton'
        ? rawWeight
        : rawWeight / 1000
      : null;
  const volume = Number(form.volumeM3);

  const plan: WsPlan = {
    scope,
    route: {
      from: coordsOrLabel(form.originLat, form.originLng, form.originLabel),
      to: coordsOrLabel(form.destLat, form.destLng, form.destLabel),
      km,
      hours,
    },
    vehicle: {
      id: modelId || '',
      name: modelName || workspaceText(detectLang()).autoMatch,
      count: internal ? (num(result.breakdown.vehicle_count) ?? result.vehicle_count ?? 0) : (num(result.vehicle_count) ?? 0),
      maxLoadTon,
    },
    cargo: {
      weightTon,
      typeLabel: cargoName(lang, form.cargoType),
      volumeM3: Number.isFinite(volume) && volume > 0 ? volume : null,
    },
    price: { low: null, high: null, costTotal: null, perVehicle: null, perKm: null, status: 'pending' },
    cost: null,
  };

  if (internal) {
    const b = result.breakdown;
    const dict = strings(lang).costLabels;
    const lines: WsLine[] = COST_LABELS.map(({ key, label }) => ({
      key: String(key),
      label: dict[String(key)] ?? label,
      value: num(b[key]) ?? 0,
    })).filter((l) => l.value !== 0);

    // 引擎的 legacy 遗留：`cost_fixed` 与 `cost_body_surcharge` 常常是同一个金额，
    // 但 `cost_total` 只算一次。两行都列出来，明细合计会比引擎合计多出一倍。
    // 值相同就合并成一行；值不同（真的两个费用）就都保留。
    const fixed = lines.find((l) => l.key === 'cost_fixed');
    const body = lines.find((l) => l.key === 'cost_body_surcharge');
    let merged = lines;
    if (fixed && body && Math.abs(fixed.value - body.value) < 1) {
      merged = lines
        .map((l) =>
          l.key === 'cost_fixed'
            ? { ...l, label: `${dict.cost_body_surcharge ?? '车型附加'} / ${dict.cost_fixed ?? '固定调度费'}` }
            : l,
        )
        .filter((l) => l.key !== 'cost_body_surcharge');
    }

    plan.cost = { lines: merged, total: num(b.cost_total) ?? merged.reduce((s, l) => s + l.value, 0) };
    plan.price = {
      low: null,
      high: null,
      costTotal: plan.cost.total,
      perVehicle: num(b.cost_per_vehicle),
      perKm: num(b.cost_per_km),
      status: 'cost',
    };
  } else {
    const low = num(result.price_low_vnd);
    const high = num(result.price_high_vnd);
    const has = low !== null && high !== null;
    plan.price = {
      low,
      high,
      costTotal: null,
      perVehicle: null,
      perKm: null,
      status: has ? 'estimate' : 'pending',
    };
  }

  return plan;
}
