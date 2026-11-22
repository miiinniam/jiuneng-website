# features/quote — 报价功能（客户版 + 内部版）

官网里的**独立功能目录**：把 `jiuneng.space/quote`（OSRM++ 报价工具）搬进本站，UI 按官网瑞士编辑风重做。
以后这个功能单独升级，只动这个目录 + `server/quoteProxy.ts`，不影响官网其它页面。

---

## 目录

```
features/quote/
  README.md          本文件：怎么改、怎么升、怎么验收
  CONTRACT.md        架构与并行分工契约（接口/类型/样式/文件归属的唯一事实来源）
  legacy/            原始代码存档(frontend/src + backend/app)，只读参考，不参与构建
  src/
    main.tsx         页面引导：判定 scope(public/internal) → mountPage(<QuoteApp/>)
    api.ts           唯一数据出口，浏览器只打本站 /api/quote/*
    engine/          纯逻辑：types / format / geometry / trunkRoute（含 node 测试）
    state/           表单状态机 useQuoteForm
    pages/           QuoteApp（步骤条 + 表单 + 面板编排）
    components/      wizard / results / map / ai / batch / templates
    quote.css        向导与结果样式（.q- 前缀，只用 tokens.css 变量）
    panels.css       地图 / AI / 批量 / 模板样式
```

## 两个入口

| 路径 | 面向 | 步骤 | 能看到的数 |
|---|---|---|---|
| `/quote` | 客户 | 路线 → 货物 → 车型 → 结果 | 里程、时长、车辆数、车型、**参考价区间** |
| `/quote/internal` | 内部（口令保护） | 以上 + 成本参数 | 完整分项成本、DDP、模板、批量 Excel |

口令：服务端环境变量 `QUOTE_INTERNAL_KEY`。前端把口令存在 `sessionStorage['jn-quote-key']`，
每个内部请求带 `x-quote-key` 头。**这不是账号体系**，是"共享口令门"，够用但别当权限系统。

## 数据链路

```
浏览器 → /api/quote/*（本站 Express） → OSRM_API_BASE（报价引擎） → OSRM 路由
```

- 浏览器永远拿不到引擎地址；`OSRM_API_BASE` 只在服务端。
- **公开口径由服务端强制**：`POST /api/quote/route` 在无 `x-quote-key` 时，响应由服务端重建，
  只回里程/时长/车数/车型/参考价区间；`breakdown`、`cost_*`、`margin`、`profit` 一个都不出。
- 内部口径需要 key，响应透传引擎原始 `QuoteResponse`。

## 怎么改

| 想改什么 | 改哪里 | 注意 |
|---|---|---|
| 文案 | `src/content.ts`（如未建则在 `src/pages/QuoteApp.tsx` 顶部常量） | 只用可核对事实，不写形容词 |
| 计算规则/价格 | **不要动** `legacy/`；改后端 `backend/app/services/**`（原始仓库）或在 `server/quoteProxy.ts` 调整口径 | 引擎是唯一真相，前端不重算 |
| 表单字段 | `src/state/useQuoteForm.ts` + `engine/types.ts`（字段名与后端一致） | 加字段必须后端同版本支持 |
| 步骤/版式 | `src/pages/QuoteApp.tsx` + `src/quote.css` | 类名 `.q-` 前缀；只用 tokens 变量 |
| 地图 / AI / 批量 | `src/components/{map,ai,batch}/` + `src/panels.css` | 不给图上叠字、不给面板加圆角/阴影 |
| 新增接口 | `server/quoteProxy.ts` + `CONTRACT.md` §3 同步更新 | 公开端点必须过白名单 |

## 怎么升级

1. 从原始仓库（`JIUNENG 数字平台/02_报价站`）拉最新 `frontend/src` 与 `backend/app`，覆盖 `legacy/`；
2. `git diff` 看 `legacy/` 变了什么，只把**逻辑变更**搬进 `src/`（UI 变更不搬，UI 以官网风格为准）；
3. 跑下面四条验收。

## 验收

```bash
cd "D:/01_业务/JIUNENG 公司【总文件夹】/JIUNENG 官方网站-源代码"
npm run lint
npm run build
NODE_ENV=production PORT=3300 node dist/server.cjs &
curl -s localhost:3300/api/quote/reference | head -c 300
node --test --experimental-strip-types features/quote/src/engine/*.test.ts
```

公开口径硬断言（必须为 0 命中）：

```bash
curl -s -X POST localhost:3300/api/quote/route -H 'content-type: application/json' -d @features/quote/tests/sample-request.json \
  | grep -Eo 'breakdown|cost_[a-z_]+|margin|profit' | sort -u
```

## 依赖

`leaflet` + `react-leaflet`（地图选点）、`xlsx`（批量 Excel，内部版）。
其余一律用仓库已有的 React 19 / Vite 6，不引 UI 库。

## 助手回复的渲染（v10.1）

回复不再是一坨纯文字。渲染链路：

```
SSE 文本增量 → ChatPanel 累积到 m.content
             → <RichText text>  (UI 组件，只产出 React 元素)
             → parseBlocks / parseInline  (纯函数，可 node 测试)
```

支持的块：段落（保留作者换行）· 无序/有序列表 · 标题 · 引用 · 表格 · 代码块；
行内：`**加粗**` · `` `代码` `` · `[文字](url)` · 裸链接。
样式全在 `panels.css` 的 `.q-rt*`：15px/1.78、发丝线表格、`—` 列表号、tabular-nums、`text-wrap: pretty`。
未闭合的 `**`、半截表格、流式断在词中间都不会闪成结构（有测试钉着）。

| 想改什么 | 改哪里 |
|---|---|
| 新的块类型（比如任务列表） | `components/ai/parseRichText.ts` 加一种 `Block`，再在 `RichText.tsx` 的 `BlockView` 加一个 case |
| 行内语法 | `parseInline` 的正则与 `RichText.tsx` 的 `InlineRun` |
| 排版（字号/间距/表格线） | `panels.css` 的 `.q-rt` 段 |
| 复制按钮文案 | `ChatPanel.tsx` 里 `复制 / 已复制` |

验收（会真发一个问题给引擎，看回复有没有被渲染成结构）：

```bash
env -u PYTHONPATH python scripts/verify-chat-render.py --url http://127.0.0.1:3300/quote \
  --shot shots/chat.png
# 断言：出现 .q-rt、正文残留 ** = 0、有 strong/列表/表格、有复制按钮 → CHAT-RENDER: PASS
```

纯函数测试（不联网、秒级）：

```bash
node --test --experimental-strip-types features/quote/src/components/ai/parseRichText.test.ts
```

> 注：官网站内那个全站悬浮「测算助手」（`src/tools/AssistantLauncher.tsx`）走的是另一套更简单的
> 渲染（只认加粗与 `-` 列表）。要统一，把这个解析器挪到共享位置再两处复用即可。

## 已知边界

- 引擎在 Render 免费层会休眠，首次测算可能要 30–60 秒；前端超时 90s 并在文案里说明。
- 模板：内部版存引擎；客户版存浏览器 localStorage（`jn-quote-templates`）。
- 批量 Excel 只在内部版开放。
