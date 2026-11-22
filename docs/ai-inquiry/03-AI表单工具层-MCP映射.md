# AI 询价助手 · 把流程变成「AI 能操作的工具」（含 MCP 映射）

> 你提的目标：**把优化后的表单流程映射到 AI 助手，让 AI 能通过 MCP 操作表格、算路径**。
> 本文先把这个目标落成可实现的架构，再给出工具清单与协议增量。

---

## 一、先说清一件事：`/quote` 现在的 AI 无法「操作」任何东西

现在 `/quote` 的 AI 是 **引擎（OSRM++）自己的 `/ai/chat`**，我们只做 SSE 透传（`quoteProxy.ts:783-860`）。

这意味着：

- 引擎 AI 的每一条工具调用都发生在**引擎进程里**，结果只回流给它自己；
- 我们的服务端**只能转发字节**，没有位置插入自己的工具，也没有位置给浏览器发「表单补丁」；
- 前端只能靠正则从回复文本里猜（`parseHints.ts` 86 行、`extractCoords.ts` 93 行）—— 这就是 R7/R8 的根因。

**结论：要让 AI 真正操作表格与计算，`/quote` 的 AI 必须换成我们自己的编排层**（就是站内 `/api/agent-chat` 那套 `runAgentChat` + `ChatModel` 接缝），引擎退回成「计算后端」。
这一步不是可选项，否则「AI 操作表格」在架构上不可能成立。

---

## 二、「MCP」的两种含义 —— 需要你确认要哪个

| | 含义 A：站内工具层（推荐先做） | 含义 B：真 MCP Server |
|---|---|---|
| 是什么 | 用 function calling 让**站内 AI** 调用我们定义的工具，工具能改表单、能算价 | 发布一个独立服务，把玖能的算价能力暴露成 MCP，给**外部客户端**（Claude Desktop / 内部 agent / 你的 Bot）连 |
| 谁在用 | 官网访客 | 你们内部同事、外部 AI 客户端 |
| 有没有「表格」 | 有（就是页面上的单件明细表 / 成本明细表） | 没有（外部没有页面） |
| 改动位置 | `server/agentChat.ts` 编排 + `features/quote` 前端 | 全新目录 `deploy/quote-mcp/` |
| 工期 | 主体工作 | 独立一期，可在 A 之后做 |

两者可以并存：A 是「客户在网页上跟 AI 改需求」，B 是「你的同事在自己电脑上用 Claude 算价」。**不冲突，但工作量和验收面完全不同**，所以必须分开定。

---

## 三、含义 A 的架构（推荐实现）

### 3.1 为什么用「单向 SSE + 表单补丁」，而不是双向 RPC

浏览器内执行工具（AI 说「我要改重量」→ 前端改 → 回传结果 → AI 继续）需要双向协议：浏览器得把工具结果再发回服务端，长连接要维持两轮，断线恢复、并发、超时全都要自己实现。

而现有编排（`runAgentChat`）已经在服务端执行工具。所以更省的做法是：

```
① 前端每次发送都把当前表单快照带上（现在 context 被丢弃，改成真用）
② 服务端工具只做两件事：校验参数 + 算出「补丁」，不碰浏览器
③ 补丁通过新的 SSE 事件 form_patch 下行
④ 前端收到就 patch(form) —— 用户看到表格自己变了
⑤ 计算类工具在服务端执行，结果通过 quote_result 事件下行，前端直接渲染结果面板
```

单向流、无需重连、与现有 SSE 契约兼容。**这就是「AI 操作表格」在浏览器里的落法。**

### 3.2 协议增量（3 处，都是加字段不是改结构）

```ts
// ① 请求体（POST /api/quote/assistant）
{
  messages: ChatMessage[],
  lang: 'zh'|'vi'|'en',
  form: QuoteFormState,        // 新增：当前表单快照
  reference?: { vehicle_models, cargo_types, exchange_rate }  // 新增（可选）：车型库，供工具选型
}

// ② SSE 事件（现有 5 种 → 7 种）
{ event:'text' } | { event:'tool_start' } | { event:'tool_done' }
| { event:'form_patch',  data:{ patch: Partial<QuoteFormState>; note: string } }   // 新增
| { event:'quote_result', data:{ quote: PublicQuoteResult } }                       // 新增
| { event:'error' } | { event:'done' }

// ③ 前端回调（QuoteApp → ChatPanel）
onFormPatch?(patch: Partial<QuoteFormState>): void
onQuoteResult?(quote: PublicQuoteResult): void
```

### 3.3 工具清单（8 个，全部由 `server/tools/quoteTools.ts` 单一出口）

| # | 工具 | 入参 | 服务端做什么 | 下行事件 | 公开/内部 |
|---|---|---|---|---|---|
| 1 | `read_form` | — | 读请求里的 form，返回「已填/缺项/已有结果」摘要 | — | 都可用 |
| 2 | `set_route` | `origin_text, dest_text, border?` | `geocode()` 解析成坐标（**不接受模型自造经纬度**）；解析不到就返回 `ok:false` + 候选 | `form_patch` | 公开 |
| 3 | `set_cargo` | `weight_kg?, volume_m3?, cargo_type?, items[]?` | 单位归一（吨→kg）、items 全量替换、越界拦截 | `form_patch` | 公开 |
| 4 | `set_vehicle` | `vehicle_model_id` | 校验 id 在车型库内，返回补丁 | `form_patch` | 公开 |
| 5 | `set_conditions` | `empty_return/need_loading/avoid_*` | 布尔开关补丁 | `form_patch` | 公开 |
| 6 | `match_vehicles` | `weight_kg, volume_m3?, items[]?` | **复用** `server/tools/fleet.ts` → `/reference/fit-vehicles` | 回模型（车型/车数/超限） | 公开 |
| 7 | `run_quote` | —（读当前 form） | 调 `/api/quote/route` 同一套逻辑 → 白名单结果 | `quote_result` | 公开 |
| 8 | `set_cost_line` | `key, value` / `add{label,value}` / `remove{key}` | 只写内部版 override，不动引擎结果 | `form_patch` | **仅内部** |

**复用而非重写**：③④的站内工具 `query_route_cost` / `match_vehicles` / `quote_customs_range` / `lookup_service_info` 已在 `server/agentChat.ts` 里，且都把口径约束写在工具描述里。新的 `quoteTools.ts` 只补「表单补丁」能力，计算一律调既有出口。

### 3.4 「操作表格」具体指什么

| 表格 | 在哪个版本 | AI 怎么操作 |
|---|---|---|
| 单件明细表（名称/件数/长/宽/高/单件重量/可堆叠） | 公开 + 内部 | `set_cargo(items:[...])` 全量替换。**不做逐行索引增删** —— 索引在并发/流式下最容易错位，全量替换是幂等的 |
| 成本明细表（13 项成本） | 仅内部 | `set_cost_line` 写本地 override，标「已修改」，可撤销；引擎结果不被覆盖 |

### 3.5 红线（写死，不靠提示词）

1. **数字只能来自引擎**：`run_quote` 的返回是白名单重建后的结果；模型不得在任何工具里「算」金额。
2. **成本/毛利/分项绝不出现在公开工具结果里**：`quoteTools.ts` 里公开分支只投影白名单字段（与 `buildPublicQuote` 同一套），grep 断言 `cost_|breakdown|margin|profit` = 0。
3. **坐标只认 geocode**：模型给的地名必须过 `geocode()`，失败就如实说「这个地名我找不到，请补充省份或附近城市」，不许猜坐标。
4. **失败必须有终止事件**：沿用现有 `error + done(aborted)` / `FALLBACK_TEXT + done` 双保险。

### 3.6 前端改动面（最小集）

| 文件 | 改什么 |
|---|---|
| `QuoteApp.tsx` | 传 `form` 与 `reference`；接 `onFormPatch` / `onQuoteResult` |
| `ChatPanel.tsx` | 解析两种新事件；把补丁转回调；把结果转渲染 |
| `api.ts` | `aiChat` 增加 `onEvent`（现在只给 `onText`，工具事件被吞） |
| 结果面板 | 与路径 1 共用一个组件（避免 F9/F10 又长成两套） |

---

## 四、含义 B：真 MCP Server（可选，独立一期）

```
deploy/quote-mcp/
  server.py            # 单文件，标准库 http + JSON-RPC，零依赖
  暴露工具：route_cost / fit_vehicles / customs_range / vehicle_models
  鉴权：X-API-Key（独立密钥，不复用 QUOTE_INTERNAL_KEY）
  不含：表单、成本、留资
```

- 用途：你或同事在 Claude Desktop / 自己的 agent 里直接问「南宁到河内 20 吨什么价」。
- 与官网的关系：**读同一套引擎**，但它是**另一条出口**，必须自己再做一次白名单（不能因为「内部用」就透传成本）。
- 不做的事：不暴露 `/ai/chat`、不暴露成本、不写线索库。

---

## 五、验收断言

| 断言 | 手段 |
|---|---|
| AI 说「改成 25 吨」→ 表单重量真的变成 25 | CDP：发送后读 `.q-cargo input` 的值 |
| AI 说「从凭祥到河内」→ 起终点被填上且地图画出线 | CDP：读 label + `geometry` |
| AI 说「用 17.5 米平板」→ 车型被选中（结果页可换） | CDP 读选中项 |
| `run_quote` 后结果面板出现且车数/里程与 `/api/quote/route` 一致 | 比对 DOM 与接口 JSON |
| 公开链路 DOM 与 SSE 文本中 `成本/breakdown/毛利` 出现 0 次 | 抓 SSE 原文断言 |
| 引擎不可用时 AI 如实说不可用，且不出现任何金额 | 黑洞依赖 |
| 三语：`?lang=vi` 下工具补丁与回复都是越南语 | 点击探针 |

---

## 六、分期建议（确认后再排）

| 期 | 内容 | 依赖 |
|---|---|---|
| P1 | 路径 1 表单优化（2 步 + 推荐车型 + 结果页 + 留资） | E1/E2/E3 |
| P2 | `/quote` AI 换自己的编排（DeepSeek 直连）+ 表单补丁协议 | P1 的表单形态定型 |
| P3 | 工具 1–7 全量 + 前端新事件 | P2 |
| P4 | 内部版 `set_cost_line`（AI 改成本明细） | P3 |
| P5 | 真 MCP Server（若你要 B） | 独立 |

> P2 是分水岭：**它决定 `/quote` 从此有自己的 AI，不再转发引擎 AI**。也顺带修掉 R1（成本泄漏）—— 因为那条链路的 prompt 不再被使用。

---

## 七、决策记录与待定项

**已定（2026-11-22）**

| 项 | 决定 |
|---|---|
| MCP 范围 | **A + B 都要**：先做站内工具层（A），再做对外 MCP Server（B） |
| 公开版运输模式 | 只保留整车 → `set_conditions` 不得修改 `loadingMode`（固定 `full_truck`）；`run_quote` 永远带 `vehicle_model_id` |
| 车型 | 必选但预填推荐值 → `match_vehicles` 的输出要能被 `set_vehicle` 直接采纳为补丁 |

**还需要你定（影响 P3 的实现细节）**

| # | 问题 | 选项 |
|---|---|---|
| Q1 | `/quote` 的 AI 换成站内编排后，**是否接受失去引擎 AI 的「多方案对比」与「实时汇率查询」** | 接受（汇率用 `reference.exchange_rate`，不必调 AI） / 补齐这两个工具（多约 1 天） |
| Q2 | AI 改表单**要不要用户确认** | ① 直接生效 + 顶部「已按你的话填好：25 吨 / 凭祥→河内」+ 撤销按钮（推荐）② 弹确认再填 |
| Q3 | AI 与表单**谁先**：客户填到一半问 AI，AI 是接着补全，还是重新问一遍？ | 接着补全（读 `form` 快照后只补缺项，推荐） / 重新确认全部 |
