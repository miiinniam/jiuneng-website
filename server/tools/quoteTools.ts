/**
 * 报价助手（`/quote` 专用）的站内工具层。
 *
 * 为什么要这一层：`/quote` 的 AI 原本是「引擎 SSE 原样透传」——工具跑在引擎进程里，
 * 我们既插不进自己的工具，也下不发表单补丁；而且引擎 `ai_chat_prompt.py` 要求模型输出
 * 「运费明细 + 口岸费明细 + DDP 总计」，工具 `_format_cost_result` 回 13 项 breakdown，
 * 客户能在**聊天正文**里看到成本结构（工作台卡干净 ≠ 页面干净，这是本项目唯一的红线漏洞）。
 *
 * 换成站内编排后：工具在本文件里跑，口径在这里收死。
 *
 * 口径（用户 2026-11-22 定）：**运费只给区间**，与工作台卡片一致；不给明细、不给成本项。
 *
 * 设计约束（照 `docs/ai-inquiry/03-AI表单工具层-MCP映射.md`）：
 *  · 单向流：工具只「校验 + 算补丁」，补丁以 `form_patch` 下行，前端 `patch(form)`；不做双向 RPC。
 *  · 表格**整表替换**，不做逐行索引（流式与并发下索引最容易错位，全量替换幂等）。
 *  · 坐标只认地址检索；解析不到就如实说找不到 —— 猜错的坐标等于给错价。
 */
import { matchFleet, parseFleetInput } from './fleet.ts';
import { specMap } from './vehicleModels.ts';
import type { SseEvent, ToolResult } from '../agentChat';
import type { Lang } from '../../src/shell/i18n';

/* ── 表单快照（与前端 QuoteFormState 的 camelCase 对齐，前端可直接 patch） ── */

export type QuoteFormItem = {
  id?: string;
  name?: string;
  lengthM?: number;
  widthM?: number;
  heightM?: number;
  weightKg?: number;
  count?: number;
  stackable?: boolean;
  divisible?: boolean;
};

export type QuoteFormSnapshot = {
  originLabel?: string;
  destLabel?: string;
  originLat?: number;
  originLng?: number;
  destLat?: number;
  destLng?: number;
  cargoClass?: string;
  cargoType?: string;
  weightKg?: number;
  weightUnit?: string;
  items?: QuoteFormItem[];
  vehicleModelId?: string;
  needLoading?: boolean;
  needUnloading?: boolean;
  needCrane?: boolean;
  allowOversized?: boolean;
};

export type GeocodeHit = { label: string; lat: number; lng: number };

export type QuoteToolDeps = {
  /** 地址检索（复用 quoteProxy 的 `/geocode` 上游，不另写一套） */
  geocode: (q: string) => Promise<GeocodeHit | null>;
  /** 跑一次确定性测算 —— **必须已过公开白名单**（只回区间口径，不含 breakdown/cost_*） */
  runQuote: (form: QuoteFormSnapshot) => Promise<Record<string, unknown> | null>;
  /** 当前表单快照（服务端从请求体拿到的，工具基于它算补丁） */
  form: QuoteFormSnapshot;
};

/* ── 工具声明（Gemini functionDeclarations 格式，与 agentChat 同构） ── */

const ITEM_SCHEMA = {
  type: 'object',
  description: '单件明细；长度的单位是米、重量是公斤',
  properties: {
    name: { type: 'string', description: '货物名称，例如 塔筒节' },
    length_m: { type: 'number', description: '单件长度（米）' },
    width_m: { type: 'number', description: '单件宽度（米）' },
    height_m: { type: 'number', description: '单件高度（米）' },
    weight_kg: { type: 'number', description: '单件重量（公斤）' },
    count: { type: 'number', description: '件数，默认 1' },
    stackable: { type: 'boolean', description: '是否可叠放，默认 false' },
    divisible: { type: 'boolean', description: '是否可拆解运输（客户说能拆成几段时置 true）' },
  },
  required: ['length_m', 'width_m', 'weight_kg'],
};

export const QUOTE_TOOLS = [
  {
    name: 'read_form',
    description:
      '读取客户当前已经填好的报价表单（路线、货物分类、重量、单件明细、车型）以及还缺哪些必填项。'
      + '客户问「还差什么」「我这样填对吗」或者你不确定当前状态时，先调它，不要凭空猜。',
    parameters: { type: 'object', properties: {} },
  },
  {
    name: 'set_route',
    description:
      '把起运地/目的地写进表单。地名会由系统做地址检索转成坐标；'
      + '解析不到时**必须如实告诉客户找不到并请其补充省份或附近城市**，绝不许自己编经纬度（猜错的坐标等于给错价）。'
      + '两个参数至少给一个。',
    parameters: {
      type: 'object',
      properties: {
        origin: { type: 'string', description: '起运地，例如 南宁 / 凭祥 / 上海' },
        destination: { type: 'string', description: '目的地，例如 河内 / 北宁 / 海防' },
      },
    },
  },
  {
    name: 'set_cargo',
    description:
      '设置货物信息：总重量（**单位公斤**）、货物分类、单件明细。'
      + '明细是**整表替换**（不是追加）—— 要保留原有行就把它们一起传回来。'
      + '货类取值只能是 normal / heavy_equipment / oversized / cold_chain / hazardous / other。',
    parameters: {
      type: 'object',
      properties: {
        weight_kg: { type: 'number', description: '货物总重量（公斤），例如 25000 表示 25 吨' },
        cargo_type: {
          type: 'string',
          description: '货类：normal 普通货物 / heavy_equipment 机械设备 / oversized 超限 / cold_chain 冷链 / hazardous 危险品 / other 其他',
        },
        items: { type: 'array', description: '单件明细（整表替换）', items: ITEM_SCHEMA },
      },
    },
  },
  {
    name: 'set_vehicle',
    description:
      '指定运输车型。model_id 必须来自车型库（可从 match_vehicles 的返回里取），'
      + '不许自行编造或改写车型名。',
    parameters: {
      type: 'object',
      properties: {
        model_id: { type: 'string', description: '车型库 model_id，例如 flatbed_low_17m5' },
      },
      required: ['model_id'],
    },
  },
  {
    name: 'set_conditions',
    description:
      '设置附加条件：含装车、含卸车、需随车吊、允许超限运输配车。'
      + '只改这些开关，**不能改运输模式**（公开版固定整车）。',
    parameters: {
      type: 'object',
      properties: {
        need_loading: { type: 'boolean', description: '是否含装车/吊装' },
        need_unloading: { type: 'boolean', description: '是否含卸车' },
        need_crane: { type: 'boolean', description: '是否需要随车吊' },
        allow_oversized: { type: 'boolean', description: '是否允许超限运输配车' },
      },
    },
  },
  {
    name: 'match_vehicles',
    description:
      '按货物自动匹配车型与车数，返回库内车型名（display_name）、载重、车长、轴型与许可档位。'
      + '结果里的车型名与参数一律来自车辆型号库，转述时原样使用，禁止推断或改写。',
    parameters: {
      type: 'object',
      properties: {
        weight_kg: { type: 'number', description: '货物总重量（公斤）' },
        cargo_type: { type: 'string', description: '货类（同 set_cargo）' },
        allow_oversized: { type: 'boolean', description: '是否允许超限配车' },
        items: { type: 'array', description: '单件明细（与表单一致）', items: ITEM_SCHEMA },
      },
      required: ['weight_kg', 'items'],
    },
  },
  {
    name: 'run_quote',
    description:
      '用当前表单跑一次确定性测算，返回里程、预计时长、车数、车型与**参考价区间**。'
      + '缺路线或重量时不会跑，会告诉你缺什么。'
      + '返回的金额只有区间，**只能照抄，不得改写、不得换算、不得补出明细项**；'
      + '转述时必须说明这是初步测算、非正式报价。',
    parameters: { type: 'object', properties: {} },
  },
];

const LABELS: Record<string, Record<Lang, string>> = {
  read_form: { zh: '正在读取表单…', vi: 'Đang đọc biểu mẫu…', en: 'Reading the form…' },
  set_route: { zh: '正在写入路线…', vi: 'Đang điền tuyến đường…', en: 'Setting the route…' },
  set_cargo: { zh: '正在写入货物…', vi: 'Đang điền hàng hóa…', en: 'Setting the cargo…' },
  set_vehicle: { zh: '正在选择车型…', vi: 'Đang chọn loại xe…', en: 'Selecting the vehicle…' },
  set_conditions: { zh: '正在更新附加条件…', vi: 'Đang cập nhật điều kiện…', en: 'Updating conditions…' },
  match_vehicles: { zh: '正在匹配车型…', vi: 'Đang khớp loại xe…', en: 'Matching vehicles…' },
  run_quote: { zh: '正在测算运费…', vi: 'Đang tính cước…', en: 'Running the estimate…' },
};

export function quoteToolLabel(name: string, lang: Lang): string {
  return LABELS[name]?.[lang] ?? LABELS[name]?.zh ?? name;
}

/* ── 系统提示词：只给区间的口径 ── */

export function quoteSystemPrompt(): string {
  return [
    '你是玖能国际（JIUNENG International）官网报价页的「报价助手」，只负责中越工程物流的运输测算。',
    '',
    '【身份与边界】',
    '- 只做运输测算：路线、里程、时长、车型、车数、参考价。',
    '- 服务咨询、流程、单证、报关细则请引导客户去官网右下角的「咨询助手」或 /contact。',
    '- 你**不能**给正式报价、不能承诺时效、不能承诺舱位。',
    '',
    '【金额口径（最重要，违反即事故）】',
    '- 金额**只给区间**，且只能来自 run_quote 工具返回的区间原文。',
    '- **禁止**输出费用明细、成本项、单价、每公里成本、利润率、DDP 分解 —— 一个字都不许。',
    '- 禁止自行估算、换算汇率或补齐缺失金额；工具没给就说「以正式询价为准」。',
    '- 每次给金额都必须带上「初步测算，非正式报价」。',
    '',
    '【事实来源】',
    '- 车型名与参数一律取自工具返回的车辆型号库字段（display_name / max_load_ton / length_m / axle_config），',
    '  禁止自行推断、改写或补充车型名；参数为 null 就说「库内暂无该参数」。',
    '- 经纬度只能来自 set_route 的地址检索结果；检索不到就如实说找不到，请客户补充省份或附近城市。',
    '- 不确定的事就说不知道，不要编。',
    '',
    '【怎么工作】',
    '- 客户描述需求 → 用 set_route / set_cargo / set_conditions 写进表单（缺什么先问或先补），',
    '  需要车型就用 match_vehicles，要金额就用 run_quote。',
    '- 工具返回 ok=false 时，如实告诉客户当前不可用，并给出可行下一步（补充信息 / 走正式询价）。',
    '- 改完表单后用一两句话说明你改了什么、还差什么，不要把表单字段逐条念一遍。',
  ].join('\n');
}

/* ── 工具执行器 ── */

const num = (v: unknown): number | null => {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
};

const bool = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null);

function patchEvent(patch: Record<string, unknown>, reason: string): SseEvent {
  return { event: 'form_patch', data: { patch, reason } };
}

/** 把模型给的 items 规范化成前端表单字段（整表替换） */
function normalizeItems(raw: unknown): QuoteFormItem[] {
  if (!Array.isArray(raw)) return [];
  const out: QuoteFormItem[] = [];
  for (const entry of raw.slice(0, 100)) {
    const it = (entry && typeof entry === 'object' ? entry : {}) as Record<string, unknown>;
    const lengthM = num(it.length_m);
    const widthM = num(it.width_m);
    const weightKg = num(it.weight_kg);
    if (lengthM === null || widthM === null || weightKg === null) continue;
    out.push({
      id: `ai-${out.length + 1}-${Date.now().toString(36)}`,
      name: typeof it.name === 'string' ? it.name.slice(0, 60) : `货件 ${out.length + 1}`,
      lengthM,
      widthM,
      heightM: num(it.height_m) ?? 0,
      weightKg,
      count: Math.max(1, Math.round(num(it.count) ?? 1)),
      stackable: bool(it.stackable) ?? false,
      divisible: bool(it.divisible) ?? false,
    });
  }
  return out;
}

/** 表单缺项（与前端 canNext 同口径，只用于回答「还缺什么」） */
function missingOf(form: QuoteFormSnapshot): string[] {
  const missing: string[] = [];
  if (!(Number.isFinite(form.originLat) && Number.isFinite(form.originLng))) missing.push('起运地');
  if (!(Number.isFinite(form.destLat) && Number.isFinite(form.destLng))) missing.push('目的地');
  if (!num(form.weightKg)) missing.push('总重量');
  return missing;
}

export function createQuoteExecutor(deps: QuoteToolDeps) {
  // 本轮对话内的**可变表单**：工具写进去的补丁必须立刻对后续工具可见 ——
  // 否则「set_route / set_cargo 之后紧接着 run_quote」会读到旧的初始快照、
  // 判定「缺路线/缺重量」而拒绝测算（实测：同一轮里 set_cargo 成功、run_quote 却说缺重量）。
  const form: QuoteFormSnapshot = { ...deps.form };

  return async function execute(
    name: string,
    args: Record<string, unknown>,
    _lang: Lang,
  ): Promise<ToolResult> {

    switch (name) {
      /* ── 读表单 ── */
      case 'read_form': {
        const missing = missingOf(form);
        const summary = missing.length
          ? `已填：${[
              form.originLabel ? `起点 ${form.originLabel}` : '',
              form.destLabel ? `终点 ${form.destLabel}` : '',
              num(form.weightKg) ? `重量 ${Math.round(num(form.weightKg)! / 1000)} 吨` : '',
              form.items?.length ? `明细 ${form.items.length} 行` : '',
              form.vehicleModelId ? `车型 ${form.vehicleModelId}` : '',
            ].filter(Boolean).join('、') || '（还没有内容）'}；还缺：${missing.join('、')}`
          : '路线与重量已齐，可以直接测算。';
        return {
          ok: true,
          summary,
          payload: { form, missing, ready: missing.length === 0 },
        };
      }

      /* ── 写路线（地名必须过地址检索） ── */
      case 'set_route': {
        const patch: Record<string, unknown> = {};
        const notes: string[] = [];
        const jobs: Array<[string, unknown, string, string]> = [
          ['origin', args.origin, 'originLat', 'originLabel'],
          ['destination', args.destination, 'destLat', 'destLabel'],
        ];
        for (const [key, raw, latKey, labelKey] of jobs) {
          const q = typeof raw === 'string' ? raw.trim() : '';
          if (!q) continue;
          const hit = await deps.geocode(q);
          if (!hit) {
            notes.push(`「${q}」检索不到坐标`);
            continue;
          }
          patch[latKey] = hit.lat;
          patch[labelKey === 'originLabel' ? 'originLng' : 'destLng'] = hit.lng;
          patch[labelKey] = hit.label;
          notes.push(`${key === 'origin' ? '起点' : '终点'} → ${hit.label}`);
        }
        if (!Object.keys(patch).length) {
          return {
            ok: false,
            summary: notes.length ? `${notes.join('；')}。请让客户补充省份或附近城市。` : '没有给出地名。',
            payload: { ok: false, reason: 'geocode_failed', notes },
          };
        }
        Object.assign(form, patch);
        return {
          ok: true,
          summary: notes.join('；'),
          payload: { ok: true, applied: Object.keys(patch) },
          events: [patchEvent(patch, 'set_route')],
        };
      }
      /* ── 写货物（明细整表替换） ── */
      case 'set_cargo': {
        const patch: Record<string, unknown> = {};
        const weight = num(args.weight_kg);
        if (weight !== null) {
          patch.weightKg = weight;
          patch.weightUnit = 'kg';
        }
        const cargoType = typeof args.cargo_type === 'string' ? args.cargo_type.trim() : '';
        if (cargoType) patch.cargoType = cargoType;
        const items = normalizeItems(args.items);
        if (items.length) patch.items = items;
        if (!Object.keys(patch).length) {
          return { ok: false, summary: '没有可写入的货物字段（需要 weight_kg 或 items）。', payload: { ok: false, reason: 'bad_input' } };
        }
        const bits: string[] = [];
        if (weight !== null) bits.push(`总重 ${Math.round(weight / 1000)} 吨`);
        if (cargoType) bits.push(`货类 ${cargoType}`);
        if (items.length) bits.push(`明细 ${items.length} 行（整表替换）`);
        Object.assign(form, patch);
        return {
          ok: true,
          summary: `已写入：${bits.join('、')}`,
          payload: { ok: true, applied: Object.keys(patch) },
          events: [patchEvent(patch, 'set_cargo')],
        };
      }

      /* ── 选车型（必须在库内） ── */
      case 'set_vehicle': {
        const modelId = typeof args.model_id === 'string' ? args.model_id.trim() : '';
        if (!modelId) return { ok: false, summary: '没有给 model_id。', payload: { ok: false, reason: 'bad_input' } };
        const specs = await specMap();
        const spec = specs.get(modelId);
        if (!spec) {
          return {
            ok: false,
            summary: `车型 ${modelId} 不在车辆型号库中，请先用 match_vehicles 匹配。`,
            payload: { ok: false, reason: 'unknown_model', model_id: modelId },
          };
        }
        form.vehicleModelId = modelId;
        return {
          ok: true,
          summary: `已选车型：${spec.display_name}（载 ${spec.max_load_ton} 吨）`,
          payload: { ok: true, model_id: modelId, display_name: spec.display_name, max_load_ton: spec.max_load_ton },
          events: [patchEvent({ vehicleModelId: modelId }, 'set_vehicle')],
        };
      }

      /* ── 附加条件 ── */
      case 'set_conditions': {
        const patch: Record<string, unknown> = {};
        const map: Array<[string, string]> = [
          ['need_loading', 'needLoading'],
          ['need_unloading', 'needUnloading'],
          ['need_crane', 'needCrane'],
          ['allow_oversized', 'allowOversized'],
        ];
        for (const [from, to] of map) {
          const v = bool(args[from]);
          if (v !== null) patch[to] = v;
        }
        if (!Object.keys(patch).length) {
          return { ok: false, summary: '没有可设置的附加条件。', payload: { ok: false, reason: 'bad_input' } };
        }
        Object.assign(form, patch);
        return {
          ok: true,
          summary: `已更新：${Object.keys(patch).join('、')}`,
          payload: { ok: true, applied: Object.keys(patch) },
          events: [patchEvent(patch, 'set_conditions')],
        };
      }

      /* ── 配车（复用 server/tools/fleet.ts，车型名来自库） ── */
      case 'match_vehicles': {
        const parsed = parseFleetInput({
          weight_kg: args.weight_kg,
          cargo_type: typeof args.cargo_type === 'string' ? args.cargo_type : 'normal',
          items: Array.isArray(args.items) ? args.items : [],
          allow_oversized: bool(args.allow_oversized) ?? undefined,
        });
        if (!parsed.ok) {
          // TS 判别联合在本项目跨模块不收窄（已知坑）：在调用处显式标注失败支形状
          const bad = parsed as { ok: false; reason: string; note: string };
          return { ok: false, summary: bad.note, payload: { ok: false, reason: bad.reason, note: bad.note } };
        }
        const result = await matchFleet(parsed.value);
        if (!result.ok) {
          const bad = result as { ok: false; reason: string; note: string };
          return { ok: false, summary: bad.note, payload: { ok: false, reason: bad.reason, note: bad.note } };
        }
        const groups = result.groups.map((g) => ({
          model_id: g.model,
          display_name: g.display_name,
          max_load_ton: g.max_load_ton,
          length_m: g.spec?.length_m ?? null,
          axle_config: g.spec?.axle_config ?? null,
          vehicle_count: g.vehicle_count,
          reason: g.reason,
          flags: g.flags,
        }));
        return {
          ok: true,
          summary: groups
            .map((g) => `${g.display_name} · 载 ${g.max_load_ton} 吨${g.length_m ? ` · ${g.length_m} 米` : ''} · ${g.vehicle_count} 辆`)
            .join('；') + `；共 ${result.total_trucks} 辆。`,
          payload: {
            ok: true,
            groups,
            total_trucks: result.total_trucks,
            oversize: result.oversize,
            usage_rule:
              '车型名只能原样使用 groups[].display_name，参数只能引用 max_load_ton / length_m / axle_config；'
              + '为 null 的参数如实说「库内暂无」，不得推断、补全或改写车型名。',
          },
        };
      }

      /* ── 测算（只回区间） ── */
      case 'run_quote': {
        const missing = missingOf(form);
        if (missing.length) {
          return {
            ok: false,
            summary: `还不能测算，缺少：${missing.join('、')}。`,
            payload: { ok: false, reason: 'form_incomplete', missing },
          };
        }
        const result = await deps.runQuote(form);
        if (!result) {
          return {
            ok: false,
            summary: '测算引擎暂时不可用，请稍后再试或走正式询价。',
            payload: { ok: false, reason: 'engine_unavailable' },
          };
        }
        const picks = Array.isArray(result.picks) ? (result.picks as Array<Record<string, unknown>>) : [];
        const first = picks[0];
        const bits: string[] = [];
        if (typeof result.distance_km === 'number') bits.push(`里程约 ${result.distance_km} 公里`);
        if (typeof result.duration_h === 'number') bits.push(`约 ${result.duration_h} 小时`);
        if (typeof result.total_trucks === 'number') bits.push(`${result.total_trucks} 辆`);
        if (first && typeof first.name === 'string') bits.push(`车型 ${first.name}`);
        return {
          ok: true,
          summary: bits.length ? `${bits.join(' · ')}（参考价区间见结果）` : '测算完成。',
          payload: {
            ok: true,
            result,
            usage_rule:
              '金额只许照抄 result 里的区间原文，禁止换算、拆分、补明细；'
              + '转述时必须说明「初步测算，非正式报价」。',
          },
          events: [{ event: 'quote_result', data: result }],
        };
      }

      default:
        return { ok: false, summary: `未知工具 ${name}。`, payload: { ok: false, reason: 'unknown_tool' } };
    }
  };
}
