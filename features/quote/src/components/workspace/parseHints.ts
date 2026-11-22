/**
 * 从用户的一句话里抽业务参数（纯函数）。
 *
 * 为什么前端也要抽：模型已经会把「13 米平板车、25 吨、从友谊关到河内」算得清清楚楚，
 * 但那是**对话里的文字**，不是表单。要让工作台卡片和向导同步，必须在本地把话变成参数。
 * 这里只认确定性规则（数字 + 单位 + 车型长度），不猜到的一律不动。
 */
import type { ReferenceBundle } from '../../api';

export type CargoHints = {
  weightKg?: string;
  vehicleModelId?: string;
  cargoType?: string;
};

const CARGO_KEYWORDS: { re: RegExp; key: string }[] = [
  { re: /冷链|冷藏|冷冻|冷柜/, key: 'cold_chain' },
  { re: /危险品|危化|爆炸|易燃|hazmat/i, key: 'hazardous' },
  { re: /超限|超宽|超长|超高|超重/, key: 'oversized' },
  { re: /工程机械|挖机|挖掘机|装载机|泵车|吊车|旋挖|成槽机/, key: 'heavy_equipment' },
  { re: /普通货|整车|普货|设备|钢材|货物/, key: 'normal' },
];

/** 13 米 / 17.5 米 / 9.6 米 …… */
const LEN_RE = /(\d{1,2}(?:\.\d)?)\s*米/;
/** 25 吨 / 25t / 25000 公斤 / 25T */
const TON_RE = /(\d+(?:\.\d+)?)\s*(吨|t(?![a-z])|T(?![A-Z]))/;
const KG_RE = /(\d{3,6})\s*(公斤|kg|KG|Kg)/;

export type RouteHints = { from: string; to: string };

/**
 * 「从友谊关到河内」「凭祥 → 北宁」里的起终点。
 * 只认显式的「从…到…」结构：宁可不出，也不要从一句话里猜一个地名（猜错等于给错价）。
 */
export function parseRouteText(text: string): RouteHints | null {
  const src = String(text ?? '');
  const m =
    /从\s*([^，,。；;\s]{2,20}?)\s*(?:出发)?\s*(?:到|至|→|->|去)\s*([^，,。；;\s]{2,20})/.exec(src) ??
    /([^，,。；;\s]{2,20}?)\s*(?:→|->)\s*([^，,。；;\s]{2,20})/.exec(src);
  if (!m) return null;
  const from = m[1].trim();
  const to = m[2].trim();
  if (!from || !to || from === to) return null;
  return { from, to };
}

export function parseHints(text: string, reference: ReferenceBundle | null): CargoHints {
  const hints: CargoHints = {};
  const src = String(text ?? '');

  const ton = TON_RE.exec(src);
  if (ton) {
    const v = Number(ton[1]);
    if (Number.isFinite(v) && v > 0 && v < 200) hints.weightKg = String(v); // 表单默认单位是 ton
  } else {
    const kg = KG_RE.exec(src);
    if (kg) {
      const v = Number(kg[1]);
      if (Number.isFinite(v) && v > 0) hints.weightKg = String(v / 1000);
    }
  }

  const len = LEN_RE.exec(src);
  if (len && reference) {
    const want = len[1]; // "13" / "17.5" / "9.6"
    for (const list of Object.values(reference.vehicle_models)) {
      const hit = (list || []).find(
        (m) => m.display_name.includes(`${want}米`) || m.display_name.includes(`${want} 米`),
      );
      if (hit) {
        hints.vehicleModelId = hit.model_id;
        break;
      }
    }
  }

  for (const { re, key } of CARGO_KEYWORDS) {
    if (re.test(src)) {
      hints.cargoType = key;
      break;
    }
  }

  return hints;
}
