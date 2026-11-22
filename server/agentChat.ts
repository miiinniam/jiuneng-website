/**
 * /ai 页「AI 数字员工对话」的服务端实现：SSE 流式 + 函数调用（工具）。
 *
 * 与站内既有内容同一套口径约束（见 src/agent/content.ts 文件头）：
 * - 不承诺清关时效、运费价格、货损率、SLA；AI 输出统一为「初步整理 / 初步评估」。
 * - 越南侧能力一律「通过越南本地合作代理网络」。
 * - **价格口径（2026-09 业务确认）**：对客只给「参考价区间」= OSRM++ 引擎售价 ±10%（取整到 10 万 VND），
 *   统一标注「初步测算，非正式报价」。**内部成本明细（breakdown）、利润（profit_vnd）、毛利率（margin_rate）、
 *   两端口岸费用明细（border_fees）绝不出官网** —— 白名单重建在 `server/osrmQuote.ts` 一处完成，勿在别处另写一套。
 * - 工具查不到就如实说查不到，不允许模型自己编里程、编价格、编时效。
 *
 * 设计要点：
 * - 模型调用通过 `ChatModel` 接口注入 —— 生产用 Gemini，自测用 `scriptedModel()`。
 *   这样本机没有 GEMINI_API_KEY 也能验证「工具执行 → OSRM++ 转发 → SSE 事件契约」整条链路。
 * - OSRM++ 报价引擎通过 `OSRM_API_BASE` 环境变量接入；未配置时工具明确返回「未接入」，
 *   而不是抛错或让模型猜。
 */
import { GoogleGenAI } from '@google/genai';
import { agentI18n, type Lang, type Status } from '../src/agent/content';
import { runQuote } from './osrmQuote';
import { parseCustomsInput, publicRange as customsPublicRange } from './tools/customs';
import { matchFleet, parseFleetInput } from './tools/fleet';
import { quoteIntel } from '../src/agent/quoteIntel';

/* ── 类型 ──────────────────────────────────────────────── */

export type ChatTurn = { role: 'user' | 'assistant'; text: string };

export type ToolCall = { name: string; args: Record<string, unknown> };

export type ModelEvent = { text?: string; calls?: ToolCall[] };

export interface ChatModel {
  stream(
    contents: unknown[],
    opts: { system: string; tools: unknown[] },
  ): AsyncGenerator<ModelEvent, void, void>;
}

export type SseEvent =
  | { event: 'text'; data: { content: string } }
  | { event: 'tool_start'; data: { name: string; label: string } }
  | { event: 'tool_done'; data: { name: string; ok: boolean; summary: string } }
  /** 报价工具专用：把表单补丁下发前端（**单向流，不做 RPC**）。`patch` 里只放表单字段。 */
  | { event: 'form_patch'; data: { patch: Record<string, unknown>; reason: string } }
  /** 报价工具专用：确定性引擎的测算结果。**只含区间口径**，不许带 breakdown / cost_* */
  | { event: 'quote_result'; data: Record<string, unknown> }
  | { event: 'error'; data: { message: string } }
  | { event: 'done'; data: { tools: number; rounds: number; aborted?: boolean } };

export type ToolResult = {
  ok: boolean;
  summary: string;
  payload: Record<string, unknown>;
  /** 工具想额外下行给前端的事件（form_patch / quote_result）—— 编排器在 tool_done 之后转发 */
  events?: SseEvent[];
};

/* ── 工具声明（Gemini functionDeclarations 格式）────────── */

export const AGENT_TOOLS = [
  {
    name: 'query_route_cost',
    description:
      '测算中越陆运线路的里程、预计行驶时长、车数与参考价区间，数据来自 OSRM++ 测算引擎（玖能自有）。'
      + '客户问到「多远 / 走哪个口岸 / 用什么车 / 大概多少钱」时调用。'
      + '起运地与目的地必须是以下城市/口岸之一：上海、宁波、深圳、广州、青岛、天津、义乌、南宁、凭祥、'
      + '友谊关口岸、东兴口岸、河口口岸、河内、北宁、海防、岘港、胡志明；不在清单内也不要猜坐标，'
      + '如实说明并引导客户走正式询价。'
      + '返回的金额一律是「参考价区间」，属于初步测算、非正式报价：转述时必须带上这一限定，'
      + '不得说成报价、不得承诺时效。'
      + '若工具返回 ok=false，必须如实告知客户该测算当前不可用，绝不可自行估算里程或金额。',
    parameters: {
      type: 'object',
      properties: {
        origin: { type: 'string', description: '起运地，例如 南宁 / 凭祥 / 上海' },
        destination: { type: 'string', description: '目的地，例如 河内 / 北宁 / 海防' },
        border: { type: 'string', description: '可选：指定口岸，例如 友谊关口岸 / 东兴口岸 / 河口口岸' },
        weight_kg: { type: 'number', description: '货物总重量（公斤），例如 20000 表示 20 吨' },
        volume_m3: { type: 'number', description: '可选：总体积（立方米）' },
        mode: {
          type: 'string',
          description: 'consolidated（拼车，默认）或 full_truck（整车，须同时给 vehicle_model_id）',
        },
        vehicle_model_id: {
          type: 'string',
          description: '整车时的车型：flatbed_13m / flatbed_low_17m5 / flatbed_low_13m / flatbed_12m5 / small_box_10t / small_box_5t',
        },
      },
      required: ['origin', 'destination', 'weight_kg'],
    },
  },
  {
    name: 'lookup_service_info',
    description:
      '查询玖能自身的服务能力、能力状态（已上线/内测中/建设中）、单证与流程要点、联系方式，'
      + '以及**报价口径**（报价要准备哪些资料、报价包含哪些费用）。'
      + '客户问「报价要准备什么资料 / 需要提供什么信息 / 价格里都含什么 / 运费之外还收什么 / 怎么联系」时调用；'
      + '答案必须来自本工具返回的站内内容，不要凭你自己的记忆回答。'
      + '三条默认问题的对应主题：报价资料用 quote_docs，费用构成用 quote_fees，联系方式用 contact。',
    parameters: {
      type: 'object',
      properties: {
        topic: {
          type: 'string',
          description:
            '查询主题：quote_docs（报价所需资料）/ quote_fees（报价费用构成）/ '
            + 'service（服务能力）/ documents（单证）/ process（流程）/ contact（联系方式）/ status（能力状态）',
        },
      },
      required: ['topic'],
    },
  },
  {
    name: 'quote_customs_range',
    description:
      '测算中国端与越南端的口岸费用**区间**（报关、口岸、装卸/换装、清关、滞留），并给出 DDP 合计区间。'
      + '客户问「报关费多少 / 清关怎么收 / 双边的费用 / 到门价」时调用。'
      + '返回的只是区间，**分项明细必须由客户在官网填写联系信息后解锁**：'
      + '不要在对话里承诺具体分项金额，也不要暗示可以在这里给到分项；'
      + '如实说明「区间可按参数测算，分项明细请在报关测算页填写公司与联系人后查看」。'
      + '金额一律为初步测算、非正式报价。若工具返回 available=false，说明线上暂不提供报关费测算，'
      + '请客户联系项目经理，绝不自行估算费用。',
    parameters: {
      type: 'object',
      properties: {
        vehicle_count: { type: 'number', description: '车辆数，≥1，默认 1' },
        domestic_transport_rmb: { type: 'number', description: '可选：中国境内段运费（人民币），不确定就不填' },
        container_count: { type: 'number', description: '可选：集装箱数量' },
        container_type: { type: 'string', description: '可选：箱型，例如 20GP / 40HQ / 40OT / 40FR' },
        detention_days: { type: 'number', description: '可选：口岸滞留天数' },
        heavy_lift_tons: { type: 'number', description: '可选：吊装吨位（大件装卸费按吨计）' },
      },
      required: ['vehicle_count'],
    },
  },
  {
    name: 'match_vehicles',
    description:
      '根据货物件数与单件尺寸重量推荐车型与车数，并判定是否超限（超长/超宽/超高/超重）与是否需要拆分。'
      + '客户问「用什么车 / 要几辆 / 这个尺寸能不能装 / 会不会超限」时调用。'
      + '本工具只回答车型、车数与超限，不返回任何价格；价格问题请改用 query_route_cost。'
      + '**车型名与参数一律取自车辆型号库，禁止自行推断或改写车型名**：'
      + '只许使用返回值里的 display_name 讲车型，库里没有的车型不要提；'
      + 'max_load_ton 与 length_m 原样转述，length_m 或 axle_config 为 null 时如实说「库内暂无该参数」，不得估算补齐。',
    parameters: {
      type: 'object',
      properties: {
        weight_kg: { type: 'number', description: '货物总重量（公斤）' },
        volume_m3: { type: 'number', description: '可选：总体积（立方米）' },
        cargo_type: { type: 'string', description: '可选：货类，默认 normal（普货）' },
        items: {
          type: 'array',
          description: '逐件货物；至少一行',
          items: {
            type: 'object',
            properties: {
              name: { type: 'string', description: '货物名称，例如 风机叶片' },
              length_m: { type: 'number', description: '单件长度（米）' },
              width_m: { type: 'number', description: '单件宽度（米）' },
              height_m: { type: 'number', description: '单件高度（米），可选' },
              weight_kg: { type: 'number', description: '单件重量（公斤）' },
              count: { type: 'number', description: '件数' },
              stackable: { type: 'boolean', description: '是否可叠放' },
            },
            required: ['length_m', 'width_m', 'weight_kg', 'count'],
          },
        },
      },
      required: ['weight_kg', 'items'],
    },
  },
];

/* ── 工具①：OSRM++ 测算（走 server/osrmQuote.ts 唯一出口） ──
   出口内部完成：真契约拼装（经纬度/route+cargo+vehicle）、X-API-Key、白名单出参、
   参考价区间（引擎售价 ±10% 取整）。这里只负责把结果转成给模型看的摘要与事实。 */

const vnd = (v: number) => v.toLocaleString('en-US');

/** TS 对跨模块判别联合的收窄在本项目 tsconfig 下不生效，用类型谓词显式收窄。 */
type CalcFail = { ok: false; reason: string; note: string; status?: number };
const isFail = (r: { ok: boolean }): r is CalcFail => r.ok === false;

export async function queryRouteCost(args: Record<string, unknown>): Promise<ToolResult> {
  const res = await runQuote({
    origin: args.origin,
    destination: args.destination,
    border: args.border,
    weight_kg: args.weight_kg,
    volume_m3: args.volume_m3,
    mode: args.mode,
    vehicle_model_id: args.vehicle_model_id,
  });

  if (isFail(res)) {
    return {
      ok: false,
      summary: `测算不可用：${res.note}`,
      payload: { ok: false, available: false, reason: res.reason, note: res.note },
    };
  }

  const facts: string[] = [`${res.origin.label} → ${res.destination.label}${res.border ? `（经${res.border.label}）` : ''}`];
  if (res.distance_km !== null) facts.push(`约 ${res.distance_km} km`);
  if (res.driving_h !== null) facts.push(`预计行驶 ${res.driving_h} 小时`);
  if (res.vehicle_count !== null) facts.push(`${res.vehicle_count} 车`);
  if (res.vehicle_label) facts.push(res.vehicle_label);

  const hasPrice = res.price_min_vnd !== null && res.price_max_vnd !== null;
  const priceLine = hasPrice
    ? `参考价区间约 ${vnd(res.price_min_vnd as number)} – ${vnd(res.price_max_vnd as number)} VND（初步测算，非正式报价）`
    : '未取得参考价区间';

  return {
    ok: true,
    summary: `${facts.join('，')}；${priceLine}`,
    payload: {
      ok: true,
      available: true,
      origin: res.origin.label,
      destination: res.destination.label,
      border: res.border?.label ?? null,
      mode: res.mode,
      distance_km: res.distance_km,
      driving_h: res.driving_h,
      vehicle_count: res.vehicle_count,
      vehicle_label: res.vehicle_label,
      price_min_vnd: res.price_min_vnd,
      price_max_vnd: res.price_max_vnd,
      price_basis: '引擎售价 ±10% 区间，取整到 10 万 VND',
      profile_honored: res.profile_honored,
      suggestions: res.suggestions,
      /* 内部成本、利润、口岸费用明细、几何线路一律不出本函数（白名单重建已在出口完成）。 */
      usage_rule:
        '转述时必须说明这是「初步测算 / 参考价区间」，不构成报价或时效承诺；'
        + '不得提及成本、利润或任何内部费用结构；引导客户走正式询价以获得正式价格。'
        + '若 profile_honored=false，说明该次按通用货车规则算路、未按车型限高限重单独选路，可如实提醒超限货物以项目经理确认为准。',
    },
  };
}

/* ── 工具②：站内能力/单证/流程/联系方式 ────────────────── */

export function lookupServiceInfo(topic: string, lang: Lang): ToolResult {
  const t = agentI18n[lang] ?? agentI18n.zh;
  const labels = t.common.statusLabels as Record<Status, string>;
  const key = String(topic || '').toLowerCase();
  const hit = (re: RegExp) => re.test(key);

  const all = () => ({
    roles: t.team.roles.map((r) => ({ name: r.name, title: r.title, status: labels[r.status] })),
    services: t.services.items.map((s) => ({ title: s.title, status: labels[s.status], desc: s.desc, points: s.points })),
  });

  let payload: Record<string, unknown>;
  /** 默认问题①：报价要准备什么资料（设备信息 + 机电类附加项） */
  if (hit(/quote_docs|报价资料|资料清单|准备.{0,4}资料|资料准备|需要什么资料|what to prepare/)) {
    payload = { quoteDocs: quoteIntel[lang] ?? quoteIntel.zh };
  } else if (hit(/quote_fees|费用构成|包含.{0,6}费用|报价包含|费用包含|什么费用|what.*(cover|included)/)) {
    payload = { quoteFees: quoteIntel[lang] ?? quoteIntel.zh };
  } else if (hit(/contact|联系|邮箱|电话|email|liên/)) {
    payload = {
      contact: t.contact.items,
      email: t.common.email,
      phone: t.common.phone,
    };
  } else if (hit(/process|流程|步骤|step|流程/)) {
    payload = { process: t.consult.steps, consultIntro: t.consult.intro, consultDisclaimer: t.consult.disclaimer };
  } else if (hit(/doc|单证|单据|报关|文件|chứng từ/)) {
    payload = {
      documents: t.services.items.map((s) => ({ title: s.title, points: s.points })),
      apps: t.apps.tabs.map((a) => ({ label: a.label, title: a.title, bullets: a.bullets })),
    };
  } else if (hit(/status|状态|上线/)) {
    payload = { status: all().services, labels };
  } else {
    payload = all();
  }
  return { ok: true, summary: `站内内容已取到（${topic || 'service'}）`, payload };
}

/* ── 工具调度 ──────────────────────────────────────────── */

/* ── 工具③：双边口岸费用区间（走 server/tools/customs.ts 唯一出口） ──
   对客只给区间；分项必须留资解锁（/api/lead → /api/customs/detail），对话里绝不出现分项。 */

const wan = (v: number) => `${Math.round(v / 10_000).toLocaleString('en-US')} 万`;

export async function quoteCustomsRange(args: Record<string, unknown>): Promise<ToolResult> {
  let input;
  try {
    input = parseCustomsInput(args);
  } catch (error) {
    const note = error instanceof Error ? error.message : '参数不完整';
    return { ok: false, summary: `报关测算参数不完整：${note}`, payload: { ok: false, available: false, note } };
  }

  const range = await customsPublicRange(input).catch(() => null);
  if (!range) {
    return {
      ok: false,
      summary: '报关费用测算暂时不可用，请客户联系项目经理核算。',
      payload: { ok: false, available: false, note: 'engine_unavailable' },
    };
  }
  if (!range.available) {
    return { ok: false, summary: range.note, payload: { ok: false, available: false, note: range.note } };
  }

  const facts: string[] = [`中国端口径：${input.vehicle_count} 车`];
  facts.push(`中国端约 ¥${range.china.min_rmb.toLocaleString('en-US')} – ¥${range.china.max_rmb.toLocaleString('en-US')}（人民币）`);
  if (range.vietnam) {
    facts.push(`越南端约 ${wan(range.vietnam.min_vnd)} – ${wan(range.vietnam.max_vnd)} VND`);
  }
  if (range.ddp) {
    facts.push(`DDP 合计约 ${wan(range.ddp.min_vnd)} – ${wan(range.ddp.max_vnd)} VND（按 1 RMB ≈ ${range.ddp.rate} VND 折算）`);
  }
  return {
    ok: true,
    summary: `${facts.join('；')}（初步测算，非正式报价；分项明细需在报关测算页填写公司与联系人后查看）`,
    payload: { ok: true, ...range },
  };
}

/* ── 工具④：车辆匹配与超限（走 server/tools/fleet.ts 唯一出口） ── */

export async function matchVehicles(args: Record<string, unknown>): Promise<ToolResult> {
  // TS 在跨模块判别联合上不收窄（本项目 tsconfig 已知行为），这里显式标注两支形状。
  const parsed = parseFleetInput(args) as
    | { ok: true; value: import('./tools/fleet').FleetInput }
    | { ok: false; reason: string; note: string };
  if (parsed.ok === false) {
    return { ok: false, summary: parsed.note, payload: { ok: false, reason: parsed.reason, note: parsed.note } };
  }

  const result = (await matchFleet(parsed.value)) as
    | {
        ok: true;
        groups: {
          model: string;
          display_name: string;
          category: string;
          max_load_ton: number;
          vehicle_count: number;
          reason: string;
          flags: string[];
          spec: import('./tools/vehicleModels').VehicleSpec | null;
        }[];
        total_trucks: number;
        oversize: { blocked: boolean; basis: string };
      }
    | { ok: false; reason: string; note: string };
  if (result.ok === false) {
    return { ok: false, summary: result.note, payload: { ok: false, reason: result.reason, note: result.note } };
  }

  /* 只逐键挑库内 4 个字段给模型：spec 整块塞进去会连 width/height/volume/装载效率一起暴露。
     spec 为 null（车型库不可达）时，length_m / axle_config 显式给 null —— 键不许省，省了模型会自己猜。 */
  const groupsOut = result.groups.map((g) => ({
    display_name: g.display_name,
    max_load_ton: g.max_load_ton,
    length_m: g.spec?.length_m ?? null,
    axle_config: g.spec?.axle_config ?? null,
    vehicle_count: g.vehicle_count,
    reason: g.reason,
    flags: g.flags,
  }));

  const groups = groupsOut
    .map((g) => {
      const head = `${g.display_name} · 载 ${g.max_load_ton} 吨`;
      const len = g.length_m === null ? '' : ` · ${g.length_m} 米`;
      const axle = g.axle_config === null ? '' : `（${g.axle_config}）`;
      return `${head}${len}${axle} · ${g.vehicle_count} 辆`;
    })
    .join('；');
  const oversizeLine = result.oversize.blocked
    ? '该票货物按现有车型配不上车：存在超限件，需专项方案或拆分，请联系项目经理评估。'
    : '未触发超限拦截。';
  return {
    ok: true,
    summary: `${groups || '未能匹配到合适车型'}；共 ${result.total_trucks} 辆。${oversizeLine}`,
    payload: {
      ok: true,
      groups: groupsOut,
      total_trucks: result.total_trucks,
      oversize: result.oversize,
      usage_rule:
        '车型名只能原样使用 groups[].display_name，参数只能引用 max_load_ton / length_m / axle_config；'
        + '为 null 的参数如实说「库内暂无」，不得推断、补全或改写车型名。',
    },
  };
}

export async function executeTool(
  name: string,
  args: Record<string, unknown>,
  lang: Lang,
): Promise<ToolResult> {
  if (name === 'query_route_cost') return queryRouteCost(args);
  if (name === 'quote_customs_range') return quoteCustomsRange(args);
  if (name === 'match_vehicles') return matchVehicles(args);
  if (name === 'lookup_service_info') return lookupServiceInfo(String(args.topic ?? ''), lang);
  return { ok: false, summary: `未知工具 ${name}`, payload: { error: 'unknown_tool' } };
}

/** SSE 里给前端显示的「正在做什么」，用站内三语词条。 */
export function toolLabel(name: string, lang: Lang): string {
  const t = agentI18n[lang] ?? agentI18n.zh;
  const labels = t.chat?.toolLabels as Record<string, string> | undefined;
  return labels?.[name] ?? name;
}

/* ── 系统提示词 ────────────────────────────────────────── */

export function systemPrompt(lang: Lang): string {
  const t = agentI18n[lang] ?? agentI18n.zh;
  const langRule = lang === 'vi'
    ? '回答语言：越南语。'
    : lang === 'en'
      ? '回答语言：英语。'
      : '回答语言：中文（客户用越南语/英语提问时跟随客户语言）。';

  return `你是 JIUNENG logistics（玖能国际）工程物流平台的「测算助手」，聚焦中越工程物流、进出口报关与国际贸易。
玖能定位「面向中国企业的工程物流平台」：中国侧由广西玖一进出口贸易有限公司提供进出口与报关支持，越南侧通过越南本地合作代理网络衔接业务。

${langRule}

必须遵守的口径（与官网一致，不得违反）：
- 你的输出是「初步整理 / 初步评估」，不是报价，也不是时效承诺。
- 不得承诺或估算清关时效、运费价格、货损率、任何 SLA 数字。**你自己不得给任何价格**；但工具 query_route_cost 返回的「参考价区间」**可以原样转达**，且必须同时标注「初步测算，非正式报价」。工具没给数字时不要编，引导客户提交正式询价，由项目经理按项目核算。
- 越南侧能力一律表述为「通过越南本地合作代理网络」，不得宣称自营报关公司、自营仓储或越南全境直营网点。
- 不得宣称全程 GPS 追踪或 7×24 小时客服。
- 能力状态必须如实：已上线的可以介绍，内测中/建设中的必须说明「正在建设 / 内测中」，不得当成已交付。
- 缺少关键信息时，直接列出需要客户补充的内容，不要臆测。

工具使用（重要）：
- 客户问到线路、里程、口岸、车型时，调用 query_route_cost；该工具未接入或失败时，如实告知「线路查询暂未接入，可由项目经理核算」，不要自行估算。
- 客户问到报关费、清关费、双边口岸费用、到门价时，调用 quote_customs_range。它只返回**区间**：可以转述区间，并明确告知「分项明细请在报关测算页填写公司与联系人后查看」；**不得在对话里给出分项金额或声称能在这里给到分项**。工具返回 available=false 时，如实说线上暂不提供报关费测算并请客户联系项目经理。
- 客户问到用什么车、几辆、能不能装、是否超限时，调用 match_vehicles；它只回答车型/车数/超限，不回答价格。
- 客户问到你们能做什么、要什么单证、流程怎么走、怎么联系时，调用 lookup_service_info，答案以工具返回为准。
- **三条高频默认问题按固定口径回答，不得自己发挥**：
  · 「报价需要准备什么资料」→ 调 lookup_service_info(quote_docs)：设备名称 / 设备说明 / 用途 / 品牌 / 型号 / 铭牌照片；机器设备与电器类另需功率、电压、工作原理、功能说明；再补件数、单件尺寸与重量、起运地与目的地、期望出运时间。
  · 「报价包含哪些费用」→ 调 lookup_service_info(quote_fees)：按「运费 + 中国端 + 越南端」分段列；中国端报关、堆场、换车（换装）、装卸、杂费；越南端清关、口岸、堆场、换车、装卸、查验/滞留/吊装按实计；关税增值税保险按贸易条款（EXW/DAP/DDP）另定。**只说构成，不给金额**。
  · 「客服联系方式」→ 调 lookup_service_info(contact)：以工具返回的邮箱、电话、地址为准，不要自己编号码。
- 严禁凭记忆编造单证清单、关税、编码、时效或价格。

语气：专业、克制、简洁。中文回答控制在 250 字以内；可用短列表；不要输出大段免责声明（站内已有固定说明）。公司邮箱：${t.common.email}；中国咨询电话：${t.common.phone}。`;
}

/* ── 模型适配器：Gemini ────────────────────────────────── */

export function geminiModel(ai: GoogleGenAI, modelName = 'gemini-3.1-flash-lite'): ChatModel {
  return {
    async *stream(contents, { system, tools }) {
      const stream = await ai.models.generateContentStream({
        model: modelName,
        contents: contents as never,
        config: {
          systemInstruction: system,
          temperature: 0.3,
          tools: [{ functionDeclarations: tools as never }],
        },
      });
      for await (const chunk of stream) {
        const calls = chunk.functionCalls;
        if (calls && calls.length) {
          yield { calls: calls.map((c) => ({ name: c.name ?? '', args: (c.args ?? {}) as Record<string, unknown> })) };
        }
        let text = '';
        try {
          text = chunk.text ?? '';
        } catch {
          text = '';
        }
        if (text) yield { text };
      }
    },
  };
}

/* ── 模型适配器：DeepSeek（OpenAI 兼容接口）─────────────────────
   为什么要在适配器内部做格式转换：编排循环（runAgentChat）里的 contents 是 **Gemini 私有形状**
   （{role, parts:[{text}|{functionCall}|{functionResponse}]}）。换 provider 最干净的做法是把循环改成
   中性消息，但那会动到**已验收**的 Gemini 路径与自测路由（AGENT_CHAT_SELFTEST）；所以这里把
   「知道 OpenAI 形状」这件事**只留在本适配器内部**：收循环给的 contents，发 OpenAI 的 messages。

   三个真实坑（都有 scripts/verify-chat-deepseek.py 钉着，别凭感觉改）：
   ① 工具参数在 OpenAI 协议里是**跨多片字符串拼接**的（delta.tool_calls[].function.arguments 逐片追加）
      → 必须**拼完再 JSON.parse**，拼一半就 parse 必炸；
   ② assistant.tool_calls[].id 与后续 role:'tool'.tool_call_id 必须配对 —— 而循环回填的
      functionResponse **不带 id**，这里按「同一轮内出现顺序」合成 id（call_1、call_2…），
      下一轮再按顺序（name 能对上优先按 name）把 functionResponse 翻成 role:'tool'；
   ③ HTTP 级错误（401/400）必须**在吐出任何 text 之前**抛出 —— 编排层据此干净回退到 Gemini，
      半途抛已经写出去的字就没法回退了。 */

type OpenAiToolDecl = { type: 'function'; function: { name: string; description: string; parameters: unknown } };
type OpenAiToolCall = { id: string; type: 'function'; function: { name: string; arguments: string } };
type OpenAiMessage =
  | { role: 'system' | 'user'; content: string }
  | { role: 'assistant'; content: string | null; tool_calls?: OpenAiToolCall[] }
  | { role: 'tool'; tool_call_id: string; content: string };
type OpenAiStreamDelta = { content?: string | null; tool_calls?: { index?: number; id?: string; function?: { name?: string; arguments?: string } }[] };

/** Gemini functionDeclarations → OpenAI tools（形状不同，字段同名）。 */
export function openAiTools(tools: unknown[]): OpenAiToolDecl[] {
  const list = tools as { name: string; description: string; parameters: unknown }[];
  return list.map((t) => ({
    type: 'function' as const,
    function: { name: t.name, description: t.description, parameters: t.parameters },
  }));
}

/** 循环给的 Gemini 形状 contents → OpenAI messages（配对见文件头 ②）。
 *  ⚠️ prevIds = **上一轮模型真给过的** tool_call id（来自流式 delta.id）。OpenAI 协议要求
 *  assistant.tool_calls[].id 与后续 role:'tool'.tool_call_id **完全一致** —— 自己合成 call_1
 *  会被真实 API 当成「无主结果」（这个坑就是验收脚本首跑抓出来的：实际发的是 'call_1'，
 *  而模型给的是 'call_fake_1'）。 */
export function toOpenAiMessages(
  system: string,
  contents: unknown[],
  prevIds: { id: string; name: string }[] = [],
): OpenAiMessage[] {
  const out: OpenAiMessage[] = [{ role: 'system', content: system }];
  let pending: { id: string; name: string }[] = [];

  for (const raw of contents) {
    const msg = raw as { role?: string; parts?: unknown[] };
    const parts = Array.isArray(msg.parts) ? msg.parts : [];
    const text = parts
      .map((p) => (p as { text?: unknown }).text)
      .filter((t): t is string => typeof t === 'string')
      .join('');
    const calls = parts
      .map((p) => (p as { functionCall?: { name?: unknown; args?: unknown } }).functionCall)
      .filter((c): c is { name?: unknown; args?: unknown } => Boolean(c));
    const responses = parts
      .map((p) => (p as { functionResponse?: { name?: unknown; response?: unknown } }).functionResponse)
      .filter((r): r is { name?: unknown; response?: unknown } => Boolean(r));

    if (calls.length) {
      // 优先沿用**模型真给过的** id（prevIds 与协议顺序一一对应），拿不到才合成兜底 ——
      // 自己合成 id 会被真实 API 当成「无主工具结果」（验收脚本 A 段钉着这条）。
      pending = calls.map((c, i) => prevIds[i] ?? { id: `call_${i + 1}`, name: String(c.name ?? '') });
      out.push({
        role: 'assistant',
        content: text || null,
        tool_calls: calls.map((c, i) => ({
          id: pending[i].id,
          type: 'function' as const,
          function: { name: String(c.name ?? ''), arguments: JSON.stringify(c.args ?? {}) },
        })),
      });
      continue;
    }

    if (responses.length) {
      for (const r of responses) {
        const name = String(r.name ?? '');
        const at = pending.findIndex((p) => p.name === name);
        const id = at >= 0 ? pending.splice(at, 1)[0].id : (pending.shift()?.id ?? `call_${out.length}`);
        out.push({ role: 'tool', tool_call_id: id, content: JSON.stringify(r.response ?? {}) });
      }
      continue;
    }

    if (text) out.push({ role: msg.role === 'model' ? 'assistant' : 'user', content: text });
  }
  return out;
}

/** 逐行解析 OpenAI SSE：只认 `data:` 行；`[DONE]` 与坏片跳过（流以 EOF 结束）。 */
async function* openAiSseChunks(body: unknown): AsyncGenerator<{ choices?: { delta?: OpenAiStreamDelta }[] }, void, void> {
  const decoder = new TextDecoder();
  let buf = '';
  // Node 的 fetch 响应体是 web stream，可直接 for-await（as unknown 只为绕开 tsconfig 无 DOM lib）
  for await (const chunk of body as AsyncIterable<Uint8Array>) {
    buf += decoder.decode(chunk, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).replace(/\r$/, '');
      buf = buf.slice(idx + 1);
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === '[DONE]') continue;
      try {
        yield JSON.parse(payload) as { choices?: { delta?: OpenAiStreamDelta }[] };
      } catch {
        /* 单行坏片忽略：不让一行垃圾打断整条流 */
      }
    }
  }
}

export type DeepSeekOptions = { apiKey: string; baseUrl?: string; model?: string; fetchImpl?: typeof fetch };

/** DeepSeek（OpenAI 兼容）适配器。baseUrl **必须含 /v1**（官方入口 https://api.deepseek.com/v1）。 */
export function deepseekModel(opts: DeepSeekOptions): ChatModel {
  const base = (opts.baseUrl || 'https://api.deepseek.com/v1').replace(/\/+$/, '');
  const model = opts.model || 'deepseek-flash';
  const doFetch = opts.fetchImpl ?? fetch;
  /** 上一轮流式给出的**真实** tool_call id —— 下一轮必须原样带回去（见 toOpenAiMessages 注释）。 */
  let lastIds: { id: string; name: string }[] = [];

  return {
    async *stream(contents, { system, tools }) {
      const res = await doFetch(`${base}/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${opts.apiKey}` },
        body: JSON.stringify({
          model,
          stream: true,
          temperature: 0.3,
          messages: toOpenAiMessages(system, contents, lastIds),
          tools: openAiTools(tools),
          tool_choice: 'auto',
        }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => '');
        throw new Error(`deepseek_http_${res.status}:${detail.slice(0, 300)}`);
      }
      if (!res.body) throw new Error('deepseek_no_body');

      const acc = new Map<number, { id: string; name: string; args: string }>();
      for await (const chunk of openAiSseChunks(res.body)) {
        const delta = chunk.choices?.[0]?.delta;
        if (!delta) continue;
        if (typeof delta.content === 'string' && delta.content) yield { text: delta.content };
        for (const tc of delta.tool_calls ?? []) {
          const i = typeof tc.index === 'number' ? tc.index : 0;
          const cur = acc.get(i) ?? { id: `call_${i + 1}`, name: '', args: '' };
          if (tc.id) cur.id = tc.id;
          if (tc.function?.name) cur.name = tc.function.name;
          if (tc.function?.arguments) cur.args += tc.function.arguments;   // ← 坑 ①：逐片拼接
          acc.set(i, cur);
        }
      }

      const entries = [...acc.entries()].sort((a, b) => a[0] - b[0]);
      lastIds = entries.map(([, v]) => ({ id: v.id, name: v.name }));      // ← 坑 ②：记下来配对
      const calls = entries
        .map(([, v]) => {
          let args: Record<string, unknown> = {};
          try {
            args = v.args ? (JSON.parse(v.args) as Record<string, unknown>) : {};
          } catch {
            throw new Error('deepseek_bad_tool_args');
          }
          return { name: v.name, args };
        });
      if (calls.length) yield { calls };
    },
  };
}

/** 自测用假模型：按脚本**逐次**吐出「调用工具」或「文本」，不依赖任何外部 API。
 *  注意必须一次性消费脚本（游标），不能每次调用 stream() 都从头重放 —— 编排循环会多轮
 *  调用 stream()，重放会让同一轮工具调用跑满 MAX_ROUNDS（这个坑是自测自己抓出来的）。 */
export function scriptedModel(steps: ModelEvent[]): ChatModel {
  let cursor = 0;
  return {
    async *stream() {
      if (cursor >= steps.length) return;
      yield steps[cursor++];
    },
  };
}

/* ── 编排循环 ──────────────────────────────────────────── */

const MAX_ROUNDS = 4;

/**
 * 兜底文案：模型一个字都没吐出来时用（工具失败后上游断流、空回复、模型抛错）。
 * 为什么必须有：2026-09-26 线上实测 —— 客户问「上海到河内 20 吨多少钱」，工具调完
 * 模型第二轮抛错，SSE 只有 tool_start/tool_done 就断了：**0 字正文、连 done 都没有**，
 * 客户点了发送什么都看不到。宁可出一句诚实的兜底，也绝不静默。
 * （本函数 + server.ts 的终止事件双保险；scripts/verify-chat-robust.py 的 E1/E2/E4/E5 钉着。）
 */
const FALLBACK_TEXT: Record<Lang, string> = {
  zh: '这次没能把结果整理出来（线路测算引擎可能正在唤醒，通常需要半分钟左右）。请再发一次，或直接把起运地、目的地、货重／体积发我；也可以提交正式询价，由项目经理核算。',
  vi: 'Lần này chưa tổng hợp được kết quả (hệ thống tính toán tuyến đường có thể đang khởi động, thường mất khoảng nửa phút). Vui lòng gửi lại, hoặc cho tôi điểm đi, điểm đến, trọng lượng/thể tích. Cũng có thể gửi yêu cầu báo giá chính thức để quản lý dự án tính toán.',
  en: 'I could not put the result together this time (the route engine may be waking up, usually about half a minute). Please send it again, or give me the origin, destination and weight/volume. You can also submit a formal inquiry for a project manager to work out.',
};

export async function* runAgentChat(opts: {
  history: ChatTurn[];
  model: ChatModel;
  lang: Lang;
  /** 工具集：默认全站助手那 4 个。报价助手传自己的工具表 —— 同一编排器，不另写一套循环。 */
  tools?: unknown[];
  /** 工具执行器：默认 executeTool。报价工具用它做「校验 + 算补丁」。 */
  execute?: (name: string, args: Record<string, unknown>, lang: Lang) => Promise<ToolResult>;
  /** 工具状态条文案：默认 toolLabel。 */
  label?: (name: string, lang: Lang) => string;
  /** 系统提示词：默认 systemPrompt(lang)。报价助手要一套「只给区间」的口径。 */
  system?: string;
}): AsyncGenerator<SseEvent, void, void> {
  const { history, model, lang } = opts;
  const tools = opts.tools ?? AGENT_TOOLS;
  const exec = opts.execute ?? executeTool;
  const labelOf = opts.label ?? toolLabel;
  const system = opts.system ?? systemPrompt(lang);

  const contents: unknown[] = history.map((turn) => ({
    role: turn.role === 'user' ? 'user' : 'model',
    parts: [{ text: turn.text }],
  }));

  let rounds = 0;
  let toolCount = 0;
  let anyText = false;
  const fallback = FALLBACK_TEXT[lang] ?? FALLBACK_TEXT.zh;

  try {
    for (let round = 0; round < MAX_ROUNDS; round++) {
      rounds = round + 1;
      const calls: ToolCall[] = [];
      let streamedText = false;

      for await (const ev of model.stream(contents, { system, tools })) {
        if (ev.text) {
          streamedText = true;
          anyText = true;
          yield { event: 'text', data: { content: ev.text } };
        }
        if (ev.calls?.length) calls.push(...ev.calls);
      }

      if (!calls.length) {
        if (!streamedText) {
          yield { event: 'error', data: { message: agentI18n[lang]?.chat?.emptyReply ?? 'empty reply' } };
        }
        break;
      }

      contents.push({ role: 'model', parts: calls.map((c) => ({ functionCall: { name: c.name, args: c.args } })) });

      const responses: unknown[] = [];
      for (const call of calls) {
        toolCount += 1;
        yield { event: 'tool_start', data: { name: call.name, label: labelOf(call.name, lang) } };
        const result = await exec(call.name, call.args ?? {}, lang);
        yield { event: 'tool_done', data: { name: call.name, ok: result.ok, summary: result.summary } };
        // 工具下行的副作用事件（报价工具用它改表单 / 回测算结果）：放在 tool_done **之后** ——
        // 前端先看到「工具完成」再收补丁，不会出现「表单已变但工具还没报完」的错序。
        for (const extra of result.events ?? []) yield extra;
        responses.push({ functionResponse: { name: call.name, response: result.payload } });
      }
      contents.push({ role: 'user', parts: responses });
    }
  } catch (error: any) {
    // 模型调用中途抛错（上游 4xx/断流、换 provider 的适配器异常等）。
    // 分两种情况，不能一刀切：
    //  ① 还没发出任何事件（典型：主模型密钥无效/欠费、接口 4xx）→ **原样抛出**，
    //     交给 server.ts 走「DeepSeek 失败 → 回退 Gemini」链路（回退必须可追溯，验收 B 段钉着）。
    //  ② 已经吐过工具/正文事件（线上事故形态：工具跑完、第 2 轮模型挂掉）→ 不能再换模型重放
    //     （客户会看到两段自相矛盾的话），必须**就地收尾**：补兜底正文 + done，绝不静默。
    if (!anyText && toolCount === 0) throw error;
    console.error('[agent-chat] 编排中断（已吐出事件，就地收尾）：', error);
    if (!anyText) {
      anyText = true;
      yield { event: 'text', data: { content: fallback } };
    }
    yield { event: 'done', data: { tools: toolCount, rounds, aborted: true } };
    return;
  }

  if (!anyText) {
    // 工具跑了但模型一个字没回（线上真出现过）：补一句诚实的兜底，保证客户端一定拿到正文 + done。
    yield { event: 'text', data: { content: fallback } };
  }

  yield { event: 'done', data: { tools: toolCount, rounds } };
}

/* ── 请求体校验 ────────────────────────────────────────── */

export function sanitizeHistory(input: unknown): ChatTurn[] {
  if (!Array.isArray(input)) return [];
  return input
    .slice(-12)
    .map((m) => {
      const rec = (m ?? {}) as Record<string, unknown>;
      const role = rec.role === 'assistant' ? 'assistant' : 'user';
      const text = typeof rec.text === 'string' ? rec.text.slice(0, 2000) : '';
      return { role, text } as ChatTurn;
    })
    .filter((m) => m.text.trim().length > 0);
}

export function parseLang(input: unknown): Lang {
  return input === 'vi' || input === 'en' ? input : 'zh';
}

export function sseFormat(ev: SseEvent): string {
  return `event: ${ev.event}\ndata: ${JSON.stringify(ev.data)}\n\n`;
}
