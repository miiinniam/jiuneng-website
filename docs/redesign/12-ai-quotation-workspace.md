# 12 · AI 报价工作台（Quotation Workspace）拆解与实施计划

> 来源：用户提供的 ChatGPT 方案（把右侧「在线报价助手」从聊天框升级成模块化报价工作台）。
> 本文只保留**能在本站架构里落地**的部分，并标明为什么不照搬某几条。

## 1. 对方方案的骨架（拆成六件事）

| # | 模块 | 对方要的交互 | 本站能不能做 |
|---|---|---|---|
| A | 运输方案卡 TransportCard | 起终点/里程/时长/车型/车数/货物，可改路线、看地图 | ✅ 数据引擎已有，纯前端 |
| B | 费用明细表 CostBreakdownTable | 可编辑行、增删费用、小计合计、币种切换 | ⚠️ **仅内部版**（公开版没有分项成本，见 §3） |
| C | 车型选择器 VehicleSelector | 卡片选车型、改车数、自动重算 | ✅ 车型库已有（含载重/容积/适用货类） |
| D | 报价汇总卡 QuotationSummary | 大号总价 + 双币 + 状态（预估/确认） | ✅ 公开版出区间或「待核定」 |
| E | 快捷操作 QuickActions | 按状态给按钮，**必须接真实逻辑** | ✅ 全部映射到表单/引擎 |
| F | 方案版本 QuotationVersions | A/B/C 方案并存、切换、比价 | 🟡 二期（先做 A→B 的「另存」与切换） |

## 2. 对方最关键的一条判断（采纳）

> AI 不应该直接决定最终报价金额，真正的金额计算交给确定性引擎。

这条和本站现有口径完全一致，也决定了实现方式：

```
用户一句话 → AI 只做两件事：① 解析出起终点（已有 extractRoutePair）② 解释结果
                        ↓
              表单（useQuoteForm）+ /api/quote/route（引擎）
                        ↓
              结构化结果（PlanCard / Summary / 明细表）← 前端渲染，数字只来自引擎
```

**不做**的事：让模型输出 JSON 报价、前端信任模型给的金额。模型给的数字一律不落到卡片上。

## 3. 与本站「口径隔离」的冲突处理（不照搬的部分）

对方要求「费用明细表」公开可见。本站不这么做，原因不是保守：

- 公开接口的响应是服务端**重建的白名单**，根本没有 `breakdown`；引擎只返回成本，售价由项目经理定。
- 公开页出现「距离运费 4,676,246」等于把成本单价摊在客户面前，直接违反「不暴露成本/毛利」。

所以：

| 模块 | 公开版 (/quote) | 内部版 (/quote/internal) |
|---|---|---|
| 运输方案卡 | 里程/时长/车型/车数/货重 | 同左 |
| 费用明细 | ❌ 只给「参考价区间」或「待项目经理核定」 | ✅ 完整分项 + 可编辑 + 备注 |
| 汇总 | 区间 / 待核定 + 提交询价 | 成本合计 + 单车成本 + 已改标记 |
| 快捷操作 | 改路线 / 换车型 / 重算 / 复制 / 提交询价 | 再加 编辑费用 / 导出报价单 |

顺带修一个**真漏洞**：`GET /api/quote/reference` 原来把引擎的车型库原样外传，
里面含 `base_rate_vnd_per_km`、`fixed_surcharge_vnd`、`fuel_l_per_100km`、
`toll_rate_vnd_per_km` 和 `notes`（"源:DuyAnh报价…"）——公开接口能直接读到成本单价和供应商备注。
现改为公开只回展示字段；带 `x-quote-key` 的内部请求才拿到全量。

## 4. 分期

### Phase 1（本次做完）— 聊天窗模块化
1. `components/workspace/` 六件套：`PlanCard` `CostEditor` `SummaryCard` `QuickActions` `WorkspacePanel` `plan.ts`
2. `buildPlan(form, result, reference, scope)` 纯函数：把「表单 + 引擎结果」投影成卡片数据（可单测）
3. AI 一轮结束后，在最后一条回复下方挂 `WorkspacePanel`（不是拆解 markdown，而是挂**引擎算出来的**结构）
4. 所有按钮接真逻辑：改路线→跳步骤 0、换车型→跳步骤 2、重算→`runQuote()`、复制→剪贴板、提交询价→/contact
5. 内部版费用明细可编辑：改金额/增行/删行 → 本地重算合计 → 标「已修改」→ 可撤销（**不覆盖引擎结果**，另存 override）
6. 移动端：面板全屏、表格横向滚动、按钮 44px

### Phase 2（下一步）— 方案版本与比价
- `versions: Plan[]` 存 A/B/C，切换、复制、两列对比（车型/车数/里程/总价）
- 「换 17.5 米再看看」→ 引擎重算 → 存成方案 B

### Phase 3（再下一步）— 正式报价单与历史
- 生成中越双语报价单（复用 `jiuneng-quotation-html` 技能的 A4 模板）
- 报价记录落库（内部），同线路历史价参考

## 5. 组件与数据契约

```ts
// components/workspace/plan.ts
export type WsLine = { label: string; qty?: string; value: number; note?: string };
export type WsPlan = {
  scope: 'public' | 'internal';
  route: { from: string; to: string; km: number; hours: number };
  vehicle: { name: string; count: number; maxLoadTon: number | null };
  cargo: { weightTon: number | null; typeLabel: string; volumeM3: number | null };
  price: { low: number | null; high: number | null; cny: number | null; status: 'estimate' | 'pending' };
  cost: { lines: WsLine[]; total: number } | null;   // 仅内部
};
export function buildPlan(input): WsPlan | null;      // 缺坐标/缺结果一律 null，卡片不渲染
```

## 6. 验收（机器可判）

| 断言 | 手段 |
|---|---|
| AI 回复后出现 `.q-ws`（工作台卡） | `scripts/verify-chat-render.py` 扩展 |
| 卡片里程/车数与 `/api/quote/route` 返回一致 | 同上（比对 DOM 文本与接口 JSON） |
| 公开页 DOM 不含 `breakdown`/`cost_`/`毛利` | `scripts/verify-quote-page.py`（已有） |
| 公开 `/reference` 不含成本字段 | 新增断言：`base_rate_vnd_per_km` 不出现 |
| 内部版编辑一行金额 → 合计即时变化、出现「已修改」 | 新增断言（CDP 点表格） |
| 移动端 390 无横向滚动、按钮 ≥44 | `verify-quote-page.py`（已有） |

## 7. 不做的三件事（避免过度设计）

1. **不让 AI 输出结构化 JSON** 再来渲染——模型不稳定，且会把金额从「引擎」挪到「生成」。
2. **不做独立的后端报价工作台**——现有 `/api/quote/*` 已够，二期再加历史库。
3. **不在公开版做费用编辑**——公开版没有分项，编辑等于让客户自己编成本。
