# 报价功能（Quote）· 架构与并行分工契约

> 目标：把 `jiuneng.space/quote`（OSRM++ Next.js 前端 + FastAPI 后端）搬进官网，**UI 按官网瑞士编辑风重做**，
> 代码独立成 `features/quote/` 一个功能目录，以后单独升级。
>
> 本文件是并行开发的唯一接口事实来源。**四个代理各自只看自己那份文件，接口冲突一律以本文为准。**

---

## 0. 现状（开工前必须知道）

| 事实 | 值 |
|---|---|
| 官网栈 | Vite 6 + React 19 + 纯 CSS（`src/styles/*.css` 令牌）+ Express（`server.ts`）多页 MPA |
| 官网已有引擎出口 | `server.ts` 里 `/api/osrm-quote`、`/api/quote-route`、`/api/customs/*`、`/api/fleet-match`，走 `server/osrmQuote.ts` 的白名单 |
| 引擎地址 | `process.env.OSRM_API_BASE`（官网），生产后端实测 `https://osrm-backend-m6zg.onrender.com/api/v1` |
| 报价站原始代码 | 已在 `features/quote/legacy/`（frontend/src 与 backend/app 全量，**只读参考，不参与构建**） |
| 对外口径 | **成本、毛利、分项成本一律不出现在公开页面**。公开页只出：里程、时长、车数、车型、参考价区间 |
| 内部版 | 同一套 UI，多「成本参数」一步 + 分项成本 + 模板 + 批量 Excel，需口令 |

## 1. 目录结构（最终形态）

```
features/quote/
  CONTRACT.md              ← 本文件
  README.md                ← 怎么改 / 怎么升 / 怎么验收（集成阶段写）
  legacy/                  ← 原始代码（只读）
  src/
    api.ts                 ← 唯一数据出口，浏览器只打 /api/quote/*
    engine/                ← 从 legacy 移植的纯函数（无 JSX、无 DOM）
      types.ts  format.ts  geometry.ts  trunkRoute.ts
    state/useQuoteForm.ts  ← 表单状态机（从 legacy 移植并收敛）
    pages/QuoteApp.tsx     ← 页面壳：步骤条 + 表单 + 面板编排
    components/
      wizard/              ← 步骤 1–5 的表单块（RouteStep / CargoClassStep / CargoStep / VehicleStep / CostStep / ReviewStep）
      results/             ← 结果面板
      map/MapPicker.tsx    ← 地图选点（leaflet）
      ai/ChatPanel.tsx     ← AI 助手
      batch/BatchPanel.tsx ← 批量 Excel
      templates/TemplateBar.tsx
    quote.css              ← 向导 + 结果（C 代理所有）
    panels.css             ← 地图/AI/批量/模板（D 代理所有）
  tests/                   ← 冒烟脚本
```

## 2. 页面入口与路由

| 路径 | 页面 | 口径 |
|---|---|---|
| `/quote` | 公开客户版（**5 步**：路线 → 货物分类 → 重量与明细 → 车型 → 提交测算 → 结果） | 不含成本参数；结果只有里程/时长/车数/车型 + 参考价区间 |
| `/quote/internal` | 内部版（**6 步**，提交前多「成本参数」） | 需口令；含分项成本、DDP、模板、批量 |

### 2.1 步骤口径（2026-11 改版，与 `useQuoteForm.ts` 的 `QuoteStep` 一一对应）

| step | 公开版 | 内部版 | 必填判据（`canNext`） |
|---|---|---|---|
| 0 | 路线 | 路线 | 起终点经纬度齐 |
| 1 | 货物分类 | 货物分类 | `cargoClass` 已选（默认 `normal`，等于默认通过） |
| 2 | 重量与明细 | 重量与明细 | `weightKg > 0`；拼货模式另需体积（公开版已无拼货） |
| 3 | 车型 | 车型 | 整车模式需 `vehicleModelId`（引擎推荐会自动预填） |
| 4 | **提交测算** | **成本参数** | 公开版此步只核对，不新增必填；内部版校验成本四项非负 |
| 5 | — | **提交测算** | 只核对 |

`cargoClass`（5 类）→ 引擎 `cargo_type` 的映射在 `engine/types.ts` 的 `CARGO_CLASS_TO_TYPE`：
`normal→normal`、`equipment→heavy_equipment`、`heavy→heavy_equipment`、`oversized→oversized`、`small→normal`。
**引擎没有「大型机械」「小件」两档**，界面分类只决定字段要求与文案，不新增档位。

两个路径共用一个 HTML 入口 `quote.html`，由 `location.pathname.endsWith('/internal')` 决定 `scope`。
页面用官网既有 `mountPage(<QuoteApp scope={...} />)` 渲染 —— TopBar / Footer / 语言切换全部继承，**不许自建导航**。

## 3. 接口契约（A 代理实现，B/C/D 只调用）

浏览器只允许打 `/api/quote/*`。**不许**直连 Render 后端，**不许**在浏览器里出现引擎域名。

### 3.1 公开（无需口令）

```http
GET  /api/quote/reference
→ 200 { vehicle_models: VehicleModelsByCategory, cargo_types: Record<string, CargoTypeRate>,
        fuel_price: { price_vnd: number, source: string },
        exchange_rate: { usd_vnd: number, cny_vnd: number, updated_at: string } | null }

GET  /api/quote/geocode?q=<自由文本>
→ 200 { results: [{ label: string, lat: number, lng: number, kind?: 'city'|'address' }] }
   失败一律 200 + { results: [] }（地址搜索失败不是错误）

POST /api/quote/route   body: QuoteRequest（§4）
→ 200 公开口径：
  { ok: true, scope: 'public',
    distance_km: number, duration_h: number,
    vehicle_count: number,
    vehicle: { id: string, name: string, max_load_ton: number } | null,
    price_low_vnd: number, price_high_vnd: number,
    timing: { loading_hours: number, rest_hours: number, total_duration_h: number },
    geometry: RouteGeometry | null }
  { ok: false, reason: string, message: string }   // message 已是客户可读中文

POST /api/quote/ai      body: { messages: ChatMessage[], lang?: 'zh'|'vi'|'en', form?: QuoteFormSnapshot }
→ 200 text/event-stream（**站内编排，不是引擎透传**，2026-11-22 起）

事件（`event: <name>` + `data: <json>`）：
  text        { content }                     正文增量
  tool_start  { name, label }                 工具开始（read_form / set_route / set_cargo /
                                              set_vehicle / set_conditions / match_vehicles / run_quote）
  tool_done   { name, ok, summary }           工具结果
  form_patch  { patch, reason }               **AI 改了表单**：前端直接 patch(patch)（键为前端字段名 camelCase）
  quote_result{ ... }                         **确定性测算结果**（= 公开白名单出参：distance_km /
                                              duration_h / total_trucks / picks[] / note，**绝不含 breakdown**）
  error       { message }                     可读错误
  done        { tools, rounds, aborted? }     终止（任何失败路径都会发）

金额口径：**只给区间**（与工作台卡片一致）。成本项、单价、明细、利润率一个字都不许出现在正文。`context` 已不参与（后端只认 `form`）；消息体两种写法都收（`content` 或 `text`）。

GET  /api/quote/templates        → 200 { templates: [] }     // 公开版返回空数组，前端改用 localStorage
```

### 3.2 内部（请求头 `x-quote-key: <QUOTE_INTERNAL_KEY>`，缺失或错 → 401 `{ ok:false, reason:'unauthorized' }`）

```http
POST /api/quote/route       → 200 { ok: true, scope: 'internal', quote: QuoteResponse }   // 引擎原样
GET  /api/quote/templates   → 200 { templates: TemplateOut[] }
POST /api/quote/templates   → 200 TemplateOut        body: { name, config: QuoteFormState }
PATCH/DELETE /api/quote/templates/:id
POST /api/quote/batch       → 200 { results: BatchRowResult[] }   body: { rows: BatchRowInput[] }
POST /api/quote/ddp         → 200 DDPFullResult                   body: DDPFullParams
POST /api/quote/customs     → 200 BorderCostResult                body: BorderCostParams
```

### 3.3 服务端实现要点（A）

- 新文件 `server/quoteProxy.ts`：一个 `proxyQuote(path, { method, body, headers })`，统一
  「OSRM_API_BASE 未配置 → `{ok:false, reason:'engine_not_configured'}`」「超时 75s」「HTTP 非 2xx 归一」。
- 公开 route 的响应**由服务端重建**（白名单搬运）：里程/时长/车数/车型/时长拆分 + 参考价区间。
  参考价区间算法复用 `server/osrmQuote.ts` 里已有的售价公式，**不要另写一套**。
- `QUOTE_INTERNAL_KEY` 从环境变量读；未配置时内部接口一律 503 `{reason:'internal_disabled'}`。
- 路由注册写在 `server.ts` 的 `// ==== v7 API ROUTES ====` 段之后，用 `app.use('/api/quote', quoteRouter)`。
- `quote.html` 的静态路由（`/quote`、`/quote/internal` → `quote.html`）也由 A 在 `server.ts` 的
  `PAGE_ROUTES` 里登记（表在 858–880 行附近，dev/prod 两处分支都要加）。

### 3.4 公开端点 `POST /api/quote/fit`（货物 → 自动配车）

与 §3.1 同一分级：**公开，无 `x-quote-key` 校验**，浏览器可直接调用。作用是把「货物明细」交给引擎自动配车，
返回推荐车型与车数 —— 这是 `/quote` 工作台从「人工选车型」改为「引擎推荐 + 人工可改」的入口。

```http
POST /api/quote/fit     body: FitRequest
→ 200 { ok: true, scope: 'public', total_trucks, needs_split, split_note, picks[], note }
→ 失败 { ok: false, reason, message }        // 与 /route 同一口径（§3.1），message 已是客户可读中文
```

请求体：

```json
{
  "items": [
    { "name": "塔筒第三节", "length_m": 30, "width_m": 3.2, "height_m": 3.2,
      "weight_kg": 42000, "count": 1, "stackable": false, "divisible": false }
  ],
  "cargo_type": "wind_tower",
  "distance_km": 720,
  "allow_oversized": true
}
```

| 请求字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `items[]` | ✅ | array | 货物明细，**至少 1 行、最多 200 行** |
| `items[].name` | 否 | string | 品名，只用于 `picks` / `note` 的可读提示 |
| `items[].length_m` | ✅ | number | 单件长（米），**必须为正数** |
| `items[].width_m` | ✅ | number | 单件宽（米），**必须为正数** |
| `items[].height_m` | 否 | number | 单件高（米）；缺省时不作高度约束的输入 |
| `items[].weight_kg` | ✅ | number | 单件重（公斤），**必须为正数** |
| `items[].count` | 否 | number | 件数，缺省 1 |
| `items[].stackable` | 否 | boolean | 可否叠装 |
| `items[].divisible` | 否 | boolean | 可否解体运输（影响「一件一车」判定） |
| `cargo_type` | 否 | string | 货物类型标识，键与 `/api/quote/reference` 的 `cargo_types` 一致 |
| `distance_km` | 否 | number | 有距离时引擎按总价比选多方案；缺省只按费率排序 |
| `allow_oversized` | 否 | boolean | 允许超限（需许可）方案，缺省 false |

响应 200：

| 响应字段 | 类型 | 说明 |
|---|---|---|
| `ok` | `true` | 成功恒为 true |
| `scope` | `'public'` | 与 `/route` 公开口径一致 |
| `total_trucks` | number | 全票合计车数 |
| `needs_split` | boolean | 该票是否需拆多车/多趟 |
| `split_note` | `string \| null` | 拆分原因（客户可读中文）；不需拆分时为 null |
| `picks[]` | array | 推荐方案，**最多 3 个**；`picks[0]` 为推荐主选 |
| `picks[].model_id` / `picks[].name` | string | 车型标识与显示名（与 `/reference` 的 `vehicle_models` 同源） |
| `picks[].max_load_ton` | number | 该车型额定载重（吨） |
| `picks[].vehicle_count` | number | 该方案车数 |
| `picks[].oversize` | boolean | 该方案是否属超限运输 |
| `picks[].permit_tier` | `'一类' \| '二类' \| '三类' \| null` | 中国超限运输许可档位；不需要许可时 null |
| `picks[].permit_workdays_local` | `number \| null` | 省内许可办理工作日；不需要许可时 null |
| `picks[].permit_note` | `string \| null` | 许可说明（客户可读中文） |
| `note` | string | 整票说明：为什么这样配 |

`permit_tier` / `permit_workdays_local` 来自引擎 `permit_flags` 的
「中国许可：X 类（省内 N 个工作日…）」条目（依据《超限运输车辆行驶公路管理规定》62 号令第十五条）；
解析不出该条目时两者为 `null`，不做猜测。

**配不出车**（单件超出所有车型的尺寸/载重上限、或 `allow_oversized` 为 false 而只能超限）不是接口错误：
仍返回 200 + `ok: true`，`picks` 为空数组、`total_trucks` 为 0、`note` 说明原因。前端据此提示并允许人工选车型。

失败口径（与 `/route` 同一口径，响应体固定 `{ ok: false, reason, message }`）：

| `reason` | 触发条件 |
|---|---|
| `bad_request` | 入参不合法：`items` 为空或超 200 行、`length_m`/`width_m`/`weight_kg` 非正数、字段类型错 |
| `engine_not_configured` | 服务端未配置 `OSRM_API_BASE` |
| `engine_timeout` | 引擎超时 |
| `engine_unreachable` | 连不上引擎（DNS/连接失败） |
| `engine_error` | 引擎 5xx 或返回体无法解析 |
| `http_4xx` | 引擎以 4xx 拒绝该请求 |

**禁止字段（公开版红线）**：响应里**不许出现** `breakdown`、`count_doctrine`、`axle_lines`、`pairs`、`items`，
以及任何键名含 `cost` / `rate` / `price` / `margin` / `profit` 的字段（大小写不敏感）；也不回显请求里的 `items`。
验收方式：对 200 响应体 grep 上述词，零命中。

为什么这样设计：

- **不与 `/route` 合并**：`/route` 回答「多少钱」，前提是车型已定；`/fit` 只回答「配什么车、几辆、要不要许可、要等几天」，不解价、不返金额。拆开后售价公式仍只有 `server/osrmQuote.ts` 一份（§3.3），不会在配车链路上出现第二套价格口径。
- **必须逐件传尺寸，不只传总重**：引擎的载重 / 尺寸 / 装载长度 / 并排四约束靠单件长宽高；只给总重就退化成「按载重升序挑一个」，选错车型是错价的最大来源。
- **带 `distance_km` 才比较多方案总价**：引擎有距离时按总价比选，没距离只按费率排序；`/quote` 本来就有距离，传下去才不让配车算法降级。
- **`picks` 最多 3 个**：避免选择过载，主选 + 「查看其他方案」折叠即可；车型最终仍由人确认（引擎推荐 + 人工可改，不阻止改，只提示）。
- **公开给许可档位与工作日**：交期是客户最关心的变量，且不涉及成本，是引擎配车改进唯一对客户可见的出口。
- **服务端白名单重建，不透传引擎响应**：引擎原样返回带 breakdown / 轴荷 / 件数口径 / 费率，属成本口径红线；重建后即使引擎新增字段也不会漏到公开页。
- **无状态纯计算**：不写模板、不落库，同一入参得同一结果，前端可在「货物 → 车型」这一步静默预取而不产生副作用；`/fit` 不可用时退回人工选车型，页面不许因此卡住。

## 4. 类型契约（B 代理从 legacy 原样移植，字段名不许改）

`features/quote/src/engine/types.ts` 直接取
`features/quote/legacy/frontend/src/lib/types.ts` 全文（299 行），**不做字段重命名**。
唯一改动：顶部加一行注释说明来源。

`QuoteRequest`（§3.1 提交体）字段：`route{origin,destination,waypoints}`、`cargo{weight_kg,volume_m3?,type,value_vnd?,items?}`、
`vehicle{loading_mode,vehicle_model_id?,empty_return,need_loading,avoid_restricted_zones,avoid_construction_zones,via_mountain_road}`、
`cost_params{fuel_price_vnd?,wage_hourly_vnd?,toll_rate_vnd_per_km?,misc_cost_vnd}`。

## 5. `api.ts` 契约（B 代理实现，C/D 只 import 这些）

```ts
export type QuoteScope = 'public' | 'internal';
export function setInternalKey(key: string | null): void;   // sessionStorage 'jn-quote-key'
export function getInternalKey(): string | null;
export function hasInternalKey(): boolean;

export class QuoteApiError extends Error { reason: string; status: number; }

export function fetchReference(): Promise<ReferenceBundle>;
export function geocode(q: string): Promise<GeoResult[]>;
export function quoteRoute(req: QuoteRequest, scope: QuoteScope): Promise<PublicQuoteResult | QuoteResponse>;
export function aiChat(payload: ChatPayload, onText: (t: string) => void, signal?: AbortSignal): Promise<void>;
export function listTemplates(): Promise<TemplateOut[]>;          // 内部才真数据
export function saveTemplate(name: string, config: QuoteFormState): Promise<TemplateOut>;
export function deleteTemplate(id: string): Promise<void>;
export function batchQuote(rows: BatchRowInput[]): Promise<BatchRowResult[]>;
export function ddpCosts(p: DDPFullParams): Promise<DDPFullResult>;
export function customsCosts(p: BorderCostParams): Promise<BorderCostResult>;
```

`PublicQuoteResult` 见 §3.1。失败一律抛 `QuoteApiError`，**`message` 必须是中文**（reason 只进日志）。

## 6. 表单状态契约（B 代理）

`state/useQuoteForm.ts` 从 legacy 的 `hooks/useQuoteForm.ts`（326 行）移植，出口签名固定：

```ts
export type QuoteStep = 0 | 1 | 2 | 3;     // 公开版只用 0..2 + 结果
export function useQuoteForm(opts: { scope: QuoteScope; status: 'idle'|'loading'|'ok'|'error'; result?: unknown }): {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  apply: (s: QuoteFormState) => void;
  reset: () => void;
  toRequest: () => QuoteRequest;            // 公开版会剔除 cost_params
  problems: Partial<Record<keyof QuoteFormState, string>>;
  canNext: (step: QuoteStep) => boolean;
};
```

## 7. 样式契约（C/D 共同遵守）

- 类名一律 `.q-` 前缀（`q-app`、`q-stepbar`、`q-field`…），**不许**复用 `.tool-*`、`.cat-*` 这些别的段的类名。
- 颜色/间距/字号只用 `src/styles/tokens.css` 的变量：`--paper --paper-2 --ink --ink-2 --ink-3 --rule --accent --sp-1..10 --fs-* --dur-hover --ease-enter`。**不许出现 #hex**。
- 圆角 0，`box-shadow: none`，无渐变。悬停只变色/变色线，不位移（`.q-*:hover` 只允许颜色、`box-shadow` 用简边线代替）。
- 可以复用全局类：`.wrap .btn .btn-outline .micro .arrow-link .section`（`src/styles/site.css` 已有）。
- 触屏目标 ≥44px；`:hover` 包在 `@media (hover:hover) and (pointer:fine)` 里。
- `prefers-reduced-motion: reduce` 下不许有过渡。

## 8. 并行分工与文件归属（**只写自己那几份，别碰别人的**）

| 代理 | 只允许改这些文件 | 交付 |
|---|---|---|
| **A 后端** | `server/quoteProxy.ts`(新)、`server.ts`（只加路由与静态页登记） | §3 全部端点可用；`curl` 证据 |
| **B 引擎与状态** | `features/quote/src/engine/*`、`features/quote/src/state/useQuoteForm.ts`、`features/quote/src/api.ts` | 类型移植 + api.ts + 状态 hook；`npx tsc --noEmit` 过 |
| **C 向导与结果** | `features/quote/src/pages/QuoteApp.tsx`、`components/wizard/*`、`components/results/*`、`quote.css` | 3/4 步向导 + 结果面板，视觉与官网一致 |
| **D 地图/AI/批量/模板** | `components/map/*`、`components/ai/*`、`components/batch/*`、`components/templates/*`、`panels.css` | 见 §9 的组件签名 |
| **E 集成（本人）** | `quote.html`、`vite.config.ts`、`package.json`、`src/shell/*`、`public/sitemap.xml`、`README.md`、`docs/` | 构建通过 + 全站验收 |

## 9. 跨代理组件签名（C 用这些，D 实现这些，**签名不许改**）

```ts
// features/quote/src/components/map/MapPicker
type MapPickerProps = {
  origin: LatLng | null;
  destination: LatLng | null;
  waypoints: LatLng[];
  geometry?: RouteGeometry | null;
  onPick: (p: { origin?: LatLng; destination?: LatLng; waypoints?: LatLng[] }) => void;
};
export default function MapPicker(props: MapPickerProps): JSX.Element;

// features/quote/src/components/ai/ChatPanel
type ChatPanelProps = { open: boolean; onClose: () => void; context: Record<string, unknown>;
                        onPickRoute: (origin: LatLng, destination: LatLng) => void };
export default function ChatPanel(props: ChatPanelProps): JSX.Element;

// features/quote/src/components/templates/TemplateBar
type TemplateBarProps = { scope: QuoteScope; form: QuoteFormState;
                          onApply: (s: QuoteFormState) => void };
export default function TemplateBar(props: TemplateBarProps): JSX.Element;

// features/quote/src/components/batch/BatchPanel
type BatchPanelProps = { scope: QuoteScope };
export default function BatchPanel(props: BatchPanelProps): JSX.Element;
```

## 10. 验收（E 阶段跑，四个代理交付前各自先跑）

```bash
cd "D:/01_业务/JIUNENG 公司【总文件夹】/JIUNENG 官方网站-源代码"
npm run lint                     # tsc --noEmit，必须 0 错
npm run build                    # 必须产出 dist/quote.html
NODE_ENV=production PORT=3300 node dist/server.cjs &
curl -s localhost:3300/api/quote/reference | head -c 300
curl -s -X POST localhost:3300/api/quote/route -H 'content-type: application/json' -d '{"route":{"origin":{"lat":22.8,"lng":106.7},"destination":{"lat":21.03,"lng":105.85},"waypoints":[]},"cargo":{"weight_kg":25000,"type":"general"},"vehicle":{"loading_mode":"full_truck","vehicle_model_id":"","empty_return":false,"need_loading":false,"avoid_restricted_zones":false,"avoid_construction_zones":false,"via_mountain_road":false},"cost_params":{"misc_cost_vnd":0}}'
env -u PYTHONPATH python scripts/verify-v10-motion.py http://127.0.0.1:3300/   # 首页动效不能回退
```

公开口径的硬断言：`/api/quote/route` 的公开响应里**不许出现** `breakdown`、`cost_`、`margin`、`profit` 任何一个键。

## 11. 不许做的事

- 不许把引擎域名、内部成本、毛利写进前端代码或响应。
- 不许改 `src/styles/tokens.css`（配色锁定）与 `02-视觉规范-瑞士编辑风.md` 的规则。
- 不许在 `features/quote/src` 里 import `motion`/`tailwind`/`next/*`。
- 不许删改 `legacy/`（那是原始代码存档）。
- 不许为了过检查去改 `AGENTS.md`、`server/osrmQuote.ts` 的白名单口径。

## 12. 变更记录

| 日期 | 章节 | 变更 |
|---|---|---|
| 2026-11-22 | §3.4 | 新增公开端点 `POST /api/quote/fit`（货物 → 自动配车）。`/quote` 工作台由此从「人工选车型」改为「引擎推荐 + 人工可改」，`/fit` 是这一步的入口。 |

`/fit` 与 `/route` 的分工：`/fit` 只回答「配什么车、几辆、要不要许可、要等几天」；`/route` 回答「多少钱」。
前端先 `/fit` 定车型，再拿定下的车型调 `/route` 出价，两边的口径不许互相混入（`/fit` 不返任何金额，`/route` 不返配车候选）。
