# 玖能国际官网 — 开发文档 (v0.6)

> 面向开发者与 AI agent 的技术参考手册。部署操作步骤见 [`DEPLOY.md`](DEPLOY.md)；给 AI agent 的项目上下文见 [`AGENTS.md`](AGENTS.md)。
>
> 本文档记录 v0.5 升级后的实际状态（设计系统重构 + SEO + 性能优化），所有数据均为实测值。

---

## 1. 项目概览

玖能国际（JIUNENG International）官方门户网站，面向中国企业的中越工程物流平台。

| 项目 | 值 |
|---|---|
| 定位 | 面向中国企业的工程物流平台（中越工程物流 / 进出口报关 / 国际贸易） |
| 技术栈 | React 19 + Vite 6 + TailwindCSS 4 + motion 12 + Express 4 |
| 语言 | 中文 / 越南语 / 英文 三语切换 |
| 前端入口 | `src/main.tsx`（单文件 SPA） |
| 样式入口 | `src/styles.css`（品牌视觉系统） |
| 后端入口 | `server.ts`（Express，含 Gemini AI 询价代理） |
| 生产运行 | `node dist/server.cjs`（Express 静态服务 `dist/`） |
| 部署目标 | Render 免费层 Node 服务（`render.yaml` 声明式配置） |
| 仓库 | `https://github.com/miiinniam/jiuneng-website` |
| 站点域名 | `https://jiuneng.space`（根域，**注意**：当前根域 DNS 指向 Vercel 的 OSRM++ 项目，勿动） |

### 项目来源

由 Google AI Studio 导出（`metadata.json` 标记 `MAJOR_CAPABILITY_SERVER_SIDE_GEMINI_API`），后经多轮改造。`README.md` 仍是 AI Studio 原始模板，未更新。

---

## 2. 目录结构

```
开发版v0.4/
├── index.html              # HTML 骨架：SEO meta、OG、JSON-LD、字体预加载
├── server.ts               # Express 服务：静态托管 + /api/health + /api/logistics-consult
├── render.yaml             # Render 声明式部署配置
├── package.json
├── tsconfig.json
├── vite.config.ts
├── AGENTS.md               # AI agent 项目上下文
├── DEPLOY.md               # 部署操作手册
├── DEVELOPMENT.md          # ← 本文件
├── metadata.json           # AI Studio 元数据
├── design-system/
│   └── jiuneng-logistics/
│       └── MASTER.md       # 品牌视觉规范（唯一事实来源，勿用通用工具重新生成）
├── public/                 # 静态资源（直接拷贝到 dist/）
│   ├── robots.txt          # ← v0.5 新增
│   ├── sitemap.xml         # ← v0.5 新增
│   ├── favicon.png
│   ├── favicon-64.png      # ← v0.5 新增
│   ├── apple-touch-icon.png# ← v0.5 新增
│   └── assets/             # 图片资源（v0.5 已全部转为 JPEG 压缩）
└── src/
    ├── main.tsx            # 全部 UI 组件 + 三语翻译数据（单文件，1633 行）
    └── styles.css          # 品牌视觉系统 CSS（1015 行）
```

---

## 3. 常用命令

```bash
npm install          # 安装依赖
npm run dev          # 本地开发：tsx server.ts（Vite 中间件模式，HMR 端口 24679）
npm run build        # 生产构建：vite build → dist/ + esbuild server.ts → dist/server.cjs
npm start            # 生产运行：node dist/server.cjs
npm run lint         # 类型检查：tsc --noEmit
```

### 构建产物（v0.5 实测）

```
dist/index.html                   4.48 kB │ gzip:   1.63 kB
dist/assets/index-*.css          22.49 kB │ gzip:   5.21 kB
dist/assets/index-*.js          381.53 kB │ gzip: 120.47 kB
dist/server.cjs                   8.30 kB
dist/ 总计                        6.4 MB（含图片资源）
```

> `npm run build` 必须同时产出**前端静态文件**和 `dist/server.cjs`，两者缺一不可 —— `npm start` 只认 `dist/`。

---

## 4. 架构说明

### 4.1 请求链路

```
浏览器
  │
  ├─ GET /               → Express static(dist/) → dist/index.html → React SPA
  ├─ GET /assets/*       → Express static(dist/assets/)
  ├─ GET /robots.txt     → Express static(dist/robots.txt)
  ├─ GET /sitemap.xml    → Express static(dist/sitemap.xml)
  ├─ GET /api/health     → JSON { status: "ok", time }
  └─ POST /api/logistics-consult → Gemini API → JSON 初步评估
```

### 4.2 运行模式切换（关键）

`server.ts` 通过 `NODE_ENV` 决定运行模式：

| `NODE_ENV` | 行为 | 用途 |
|---|---|---|
| `production` | `express.static(dist)` + `app.get('*')` 回退 index.html | **生产必须** |
| 其他/未设 | 启动 Vite 中间件（HMR 端口 24679） | 仅本地开发 |

> ⚠️ **Render 上必须显式设 `NODE_ENV=production`**，否则走 dev 中间件模式，生产静态文件不生效，页面白屏或样式全乱。`render.yaml` 已配置。

### 4.3 前端结构

`src/main.tsx` 是单文件 SPA，包含：

- **图标组件**：手写 SVG（`Icon` 包装器 + 20 个图标组件）
- **类型定义**：`Translation` 类型定义完整的三语数据结构
- **翻译数据**：`translations: Record<Lang, Translation>`，含 `zh` / `vi` / `en` 三套完整文案
- **动画组件**：`Section`（滚动入场）、`StaggerItem`（列表错峰）、`AnimatedCounter`
- **主组件**：`App`，含导航、10 个 section、页脚

语言检测优先级：`localStorage('jiuneng-lang')` → `navigator.language` → 默认 `zh`。

---

## 5. 功能清单

### 5.1 页面区块（10 个）

| # | 锚点 | 区块 | 内容 |
|---|---|---|---|
| 1 | — | Hero | 主标题、引导语、双 CTA、平台流程面板、4 项统计 |
| 2 | `#about` | 关于玖能 | 公司介绍、使命/愿景、4 项核心价值观、两个主体信息卡 |
| 3 | `#platform` | 平台系统 | 12 步业务流程图、5 个系统模块、2 张系统截图 |
| 4 | `#services` | 核心业务 | 工程物流 / 进出口报关 / 国际贸易，各含 3 个要点 |
| 5 | `#solutions` | 解决方案 | 轨道交通 / 基建 / 电力 / 新能源，4 张行业卡 |
| 6 | `#vehicles` | 设备资源 | 风机运输特种车、叶片举升车、配套资源 |
| 7 | `#cases` | 代表项目 | 胡志明二号线、河内地铁 1 号线、越南风电项目 |
| 8 | `#network` | 中越协同网络 | 中国侧 / 越南侧双栏对比 + 合规声明 |
| 9 | `#qual` | 企业信息 | 越南主体 + 中国侧主体正式登记信息 |
| 10 | `#consult` | 在线询价 | AI 询价表单（深色背景 CTA 高潮区） |
| 11 | `#contact` | 联系我们 | 邮箱、电话、地址、微信/WhatsApp（待补充） |

### 5.2 交互功能

- **三语切换**：导航栏右上角，切换时同步更新 `<html lang>`、`document.title`、`meta[description]`
- **响应式导航**：滚动超过 40px 时导航栏从透明渐变变为白色毛玻璃；宽度 ≤980px 时折叠为汉堡菜单
- **滚动动画**：所有 section 进入视口时淡入上移；列表项错峰入场（50ms 间隔）
- **图片悬停**：卡片图片放大 1.045 倍，卡片上浮 3px
- **无障碍**：Skip link、`:focus-visible` 焦点环、`aria-label`、`prefers-reduced-motion` 支持

---

## 6. AI 助手应用（在线询价顾问）

### 6.1 概述

网站的 AI 功能是一个**服务端代理的 Gemini 询价顾问**，把客户提交的项目需求转成结构化的「初步评估」。

| 项 | 值 |
|---|---|
| 接口 | `POST /api/logistics-consult` |
| 模型 | `gemini-3.1-flash-lite` |
| SDK | `@google/genai`（服务端调用，密钥不出后端） |
| 温度 | `0.2`（低温度，保证输出稳定克制） |
| 响应格式 | `responseMimeType: 'application/json'`（强制 JSON） |
| 密钥 | 环境变量 `GEMINI_API_KEY` |

### 6.2 请求参数

```json
{
  "name": "联系人姓名",          // 必填
  "company": "公司名称",         // 可选
  "inquiryType": "工程物流",     // 业务类型
  "loadingPort": "佛山工厂",     // 起运地
  "dischargePort": "河内",       // 目的地
  "weightEstimate": "18吨",      // 重量/体积
  "details": "项目详情",         // 必填
  "language": "zh"               // 前端附加：输出语言
}
```

校验规则：`name` 和 `details` 缺失 → `400 {"error":"Please submit name and project details"}`

### 6.3 响应结构

```json
{
  "routeRecommendation": "线路与运输方案方向…",
  "documentChecklist": ["Form E 原产地证", "大件超限许可", "…"],
  "hsCodeAdvice": "HS 编码归类方向及关税筹划提醒…",
  "riskMitigation": ["桥梁限高限重", "雨季路况", "…"],
  "consultantStatement": "初步评估寄语，150字以内…"
}
```

前端把这 5 个字段拼接成文本块展示（`main.tsx` 的 `handleSubmit`）。

### 6.4 系统提示词（合规约束）

`server.ts` 中的 `systemPrompt` 内置了硬性合规约束，**修改时必须保留**：

- 这是初步评估，**不是正式报价，也不是时效承诺**
- **不得编造或承诺**具体清关时效、报价金额、运费价格、货损率或任何 SLA 数字
- 越南侧能力统一表述为「通过越南本地合作代理提供服务支持」，**不得宣称**越南自营报关公司、自营仓储或越南全境直营网点
- **不得宣称**全程 GPS 追踪或 7×24 小时客服
- 缺少关键信息时，明确列出需要客户补充的内容，而不是臆测
- 语气专业、克制，引导客户走平台正式询价流程
- 输出语言跟随客户提交内容所用语言

> 这些约束与 `design-system/jiuneng-logistics/MASTER.md` 的 "Avoid" 条款、以及 `AGENTS.md` 记录的踩坑一致。**改动提示词前先确认不违反上述口径。**

### 6.5 错误处理

| 场景 | 响应 |
|---|---|
| `name` 或 `details` 缺失 | `400` + 提示补全 |
| `GEMINI_API_KEY` 未配置 | `500` + `details: "GEMINI_API_KEY variable is missing…"` |
| Gemini 调用失败/超时 | `500` + 通用错误提示（前端回退到本地 `ai.fallback` 文案） |

前端在接口失败时**不显示错误**，而是展示 `translations[lang].ai.fallback` 里的兜底建议文案 —— 保证用户体验不中断。

### 6.6 模型选型历史（避免重复踩坑）

| 模型 | 结果 |
|---|---|
| `gemini-2.5-flash` | 对新手 key 已下线 |
| `gemini-flash-latest` | 高负载时返回 503 |
| **`gemini-3.1-flash-lite`** | **当前使用**，已验证可用且轻量 |

### 6.7 本地测试

```bash
# 启动生产模式（需先在 .env 配置 GEMINI_API_KEY）
NODE_ENV=production PORT=3199 node dist/server.cjs

# 校验逻辑（无需密钥，应返回 400）
curl -s -X POST http://localhost:3199/api/logistics-consult \
  -H "Content-Type: application/json" -d '{}'

# 完整调用（需密钥，应返回含 routeRecommendation 的 JSON）
curl -s -X POST http://localhost:3199/api/logistics-consult \
  -H "Content-Type: application/json" \
  -d '{"name":"测试","details":"从友谊关运一批变压器到河内"}'
```

---

## 7. 设计系统 v0.5

### 7.1 升级内容（v0.4 → v0.5）

v0.5 引入 **Stripe 式排版哲学**：以「轻量即自信」替代传统的粗重标题。

| 维度 | v0.4 | v0.5 |
|---|---|---|
| 标题字重 | 600–700（粗重） | **300**（轻量自信） |
| 字距 | -0.02 ~ -0.03em | **-0.03 ~ -0.04em**（更紧） |
| 圆角 | 6 / 10 / 16px | **4 / 6 / 8 / 12px**（更精致） |
| 阴影 | 单层灰 | **双层蓝调**（`rgba(0,16,48,…)` 双层） |
| 正文字重 | 400 | **300**（大段文字） |
| 组件字重 | 600 | **500**（标签/按钮/小标题） |

**保持不变**：品牌色（navy `#001030` / blue `#0040C0` / cyan `#2080F8`）、IBM Plex Sans 字体、三语支持、所有业务内容。

### 7.2 设计令牌

```css
/* 品牌色（锁定，来自 Logo 标准包） */
--navy: #001030;   --blue: #0040C0;   --cyan: #2080f8;
--cyan-on-dark: #4da3ff;  /* 深色底上的文字/小标签专用：--cyan 只有 4.44:1，达不到 AA 4.5:1 */
--ink: #0a1628;    --ink-soft: #243044;  --muted: #4a5b73;
/* v0.6 明亮版：页面底色与色带整体提亮（原 #f4f7fb / #e8eef6 / #d5deea） */
--bg: #f8fbff;     --bg-paper: #eef4fd;  --surface: #ffffff;
--line: #dbe4f0;   --line-strong: #b7c4d6;

/* v0.6 新增：浅色 chrome（导航/悬浮卡在亮底或照片上的半透明白） */
--chrome: rgba(255,255,255,.88);  --chrome-strong: rgba(255,255,255,.96);
--chrome-soft: rgba(255,255,255,.72);

/* 圆角 */
--radius-xs: 4px;  --radius-sm: 6px;  --radius-md: 8px;  --radius-lg: 12px;

/* 双层蓝调阴影 */
--shadow-xs: 0 1px 2px rgba(0,16,48,.04);
--shadow-sm: 0 2px 6px rgba(0,16,48,.06), 0 1px 2px rgba(0,16,48,.04);
--shadow-md: 0 8px 24px rgba(0,16,48,.08), 0 2px 6px rgba(0,16,48,.04);
--shadow-lg: 0 16px 40px rgba(0,16,48,.12), 0 4px 12px rgba(0,16,48,.06);

/* 动效 */
--ease-enter: cubic-bezier(0.22, 1, 0.36, 1);
--dur-fast: 150ms;  --dur-ui: 220ms;  --dur-slow: 380ms;
```

### 7.3 字体

- **UI / 标题 / 正文**：IBM Plex Sans（Google Fonts，`wght@0,300;0,400;0,500;0,600`）
- **CJK 回退**：PingFang SC → Microsoft YaHei → Noto Sans SC
- 基础 16px，正文行高 1.6–1.8
- 标题：字重 300，字距 -0.03 ~ -0.04em

### 7.4 视觉规范事实来源

**`design-system/jiuneng-logistics/MASTER.md` 是品牌视觉的唯一事实来源**，颜色来自 JIUNENG Logo 标准包。

> ⚠️ **不要用通用 `--design-system` 工具重新生成该文件。**
> ⚠️ **禁用**：Braun 橙色 `#E96A26`、暖纸色 `#E4E1DC`、黑金奢华配色、玻璃拟态作为页面语言、旧版 Braun 文字标 SVG（`logo-horizontal.svg`）。

### 7.5 Logo 使用

| 场景 | 文件 |
|---|---|
| 全站（v0.6 起：导航、Hero、页脚都是浅色） | `/assets/logo-horizontal.png` |
| 深色底区块（当前没有；白色版保留备用） | `/assets/logo-horizontal-white.png` |
| Favicon | `/favicon.png`（官方符号） |

Logo 禁止加投影、描边或改色。

### 7.6 v0.6 明亮版（深色骨架 → 浅色骨架）

**改的是什么**：v0.5 的骨架是「深蓝 Hero + 深蓝询价区 + 深蓝页脚」，观感头尾压重。
v0.6 把这三块全部改成浅色，**品牌色相（navy/blue/cyan）一个没动**，只把深色从
「大面积色块」退回到「文字与点缀」。

| 位置 | v0.5 | v0.6 |
|---|---|---|
| Hero 遮罩 | 深蓝，最浓处 `rgba(0,16,48,.94)` | 白色雾化：左侧 `.96` 保证深色标题对比，右侧降到 `.04` 让照片真正可见；底部淡入页面底色 |
| Hero 文字 | 白字 on 深蓝 | `--navy` 标题 + `--ink-soft` 正文 |
| 导航 | 深色 chrome（压深蓝底） | 浅色 chrome `--chrome`，顶部白雾向下淡出 |
| 询价区 `.consult-band` | `linear-gradient(navy-mid, navy)` | 白 → `--bg-paper` 渐变 + 淡青径向 |
| 页脚 | `background: var(--navy)` | `--bg-paper` + 1px 上边框 |
| 平台系统截图 | 裸图直贴页面（深色仪表盘 → 一块暗区） | 套浅色浏览器框 `.shot-frame`（窗口圆点 + 三语标签 `shotLabels`） |
| 页面底色 | `#f4f7fb` / `#e8eef6` | `#f8fbff` / `#eef4fd` |
| `theme-color` | `#001030` | `#f8fbff` |
| og 社交分享图 | 深蓝卡（亮度 37/255） | 浅色卡（亮度 236/255，61 KB） |

**已废弃**：`--navy-mid`、`--navy-soft`、`--on-dark`、`--on-dark-muted`、
`--on-dark-line`、`--cyan-on-dark` 这 6 个令牌当前页面已不再引用（保留定义，供将来
再出现深色区块时直接取用；`--cyan-on-dark` 的对比度规则依然有效）。

**验证数据（生产构建 + 无头 Chrome 整页截图，1440 宽）**：整页按 200px 带扫描，
平均亮度区间 **158–255**，无任何 <120 的暗块；首屏平均亮度 230（改前为深蓝大面积）。
布局无回归：375 / 680 / 1440 三档 `scrollWidth == clientWidth`，导航与内容网格对齐差 0px。

> 换配图时先读 [`IMAGE-SPEC.md`](IMAGE-SPEC.md)：比例不符会被 `object-fit: cover` 裁掉主体。

---

## 8. SEO 配置

### 8.1 已实现（v0.5 新增）

| 项 | 文件 / 位置 | 说明 |
|---|---|---|
| `robots.txt` | `public/robots.txt` | 允许全站抓取 + 指向 sitemap |
| `sitemap.xml` | `public/sitemap.xml` | 7 个 URL（首页 + 6 个锚点区块） |
| Open Graph | `index.html` | `og:type/title/description/image/url/site_name/locale` |
| Twitter Card | `index.html` | `summary_large_image` |
| Canonical | `index.html` | `https://jiuneng.space` |
| JSON-LD | `index.html` | `Organization` 结构化数据（含地址、联系方式、3 项 service） |
| 社交分享图 | `public/assets/og-image.png` | 1200×630，浅色品牌卡（61 KB）；改文案后跑 `python scripts/make-og-image.py` 重新生成 |
| 多尺寸图标 | `favicon-64.png`、`apple-touch-icon.png` | 64×64 / 180×180 |

### 8.2 动态 meta 更新

切换语言时，`main.tsx` 的 `useEffect` 会同步更新：
- `document.documentElement.lang`（`zh-CN` / `vi-VN` / `en`）
- `document.title`（取 `translations[lang].meta.title`）
- `meta[name="description"]` 的 content

> 注意：这是**客户端**更新，搜索引擎抓取时看到的是 `index.html` 里的静态中文版本。如需多语言 SEO，需要服务端渲染（SSR）或为每种语言生成独立静态页 —— 当前架构未做，属已知限制。

### 8.3 更新 sitemap

站点结构变化时手动更新 `public/sitemap.xml` 的 `<lastmod>` 和 URL 列表。

---

## 9. 性能优化

### 9.1 图片管线（v0.5 主要成果）

**优化前**：`public/assets/` 40 MB，单张 PNG 2.0–2.7 MB，共 17 张 PNG。

**优化后**：`public/` 总计 **6.0 MB**，全部转为 JPEG（quality 80, optimize）。

| 文件 | 前 | 后 | 节省 |
|---|---|---|---|
| `01-封面-中越陆运工程重卡…` | 2561 KB | 259 KB | 2302 KB |
| `case-04-cross-border-heavy-truck…` | 2589 KB | 295 KB | 2294 KB |
| `sol-wind` | 2684 KB | 299 KB | 2384 KB |
| `vehicle-blade` | 2684 KB | 299 KB | 2384 KB |
| `hero-wind-tower` | 2145 KB | 208 KB | 1937 KB |
| …（共 17 个文件） | | | |
| **合计** | **~40 MB** | **~4 MB** | **33 MB** |

**转换脚本**（复用方式）：

```python
from PIL import Image
import os

assets_dir = 'public/assets'
for f in os.listdir(assets_dir):
    if f.endswith('.png') and not f.startswith('logo'):   # Logo 保持 PNG（需透明通道）
        path = os.path.join(assets_dir, f)
        img = Image.open(path)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')                       # 去透明通道
        img.save(path.replace('.png', '.jpg'), 'JPEG', quality=80, optimize=True)
        os.remove(path)
```

> ⚠️ **Logo 文件（`logo-*.png`、`favicon.png`、`logo-symbol.png`）必须保持 PNG** —— 需要透明通道，转 JPEG 会出现白底方块。
> ⚠️ 新增图片请沿用此管线，转换后同步更新 `src/main.tsx` 中 `translations` 的 `image` 字段扩展名。

### 9.2 图片懒加载

`main.tsx` 中所有 `<img>` 已按优先级标注：

| 图片 | 策略 |
|---|---|
| Hero 背景图 | `loading="eager" decoding="async" fetchPriority="high"` |
| 导航 Logo | `loading="eager" decoding="async"` |
| 其余全部（about / platform / solutions / vehicles / cases / footer） | `loading="lazy" decoding="async"` |

> ⚠️ **改图片扩展名时，除了 `translations` 里的 `image` 字段，还必须改 `main.tsx` 里硬编码的路径。**
> 硬编码的 4 处：`heroImage`、`team-collab`（均在 `.about-media`）、
> 以及 `.platform-shots` 里 `system-overview` / `system-tracking` 的数组（v0.6 起这两张
> 包在 `.shot-frame` 浅色窗口框里，标签取自 `t.platform.shotLabels`，改图时别把 `<figure>` 结构删掉）。
> Logo（`logo-horizontal.png` / `logo-horizontal-white.png`）保持 `.png`，不要改。
> 漏改的后果是图片静默 404 —— 页面不报错，只是那一块背景/配图不见了（Hero 会变成纯色块）。

### 9.3 动画与内容可见性（重要）

站点的入场动画由 motion 驱动，**初始态是 `opacity: 0`**。这带来一个风险：装饰性动画一旦失效，内容会永久不可见。

已验证的失效场景：**IntersectionObserver 回调不触发**（爬虫/截图工具渲染、rAF 被节流、IO 异常）。此时页面首屏以下全部空白。

已实施的三层防护：

| 层 | 位置 | 作用 |
|---|---|---|
| 1. 去掉无谓的 IO 门控 | `AnimatedCounter` | Hero 统计数字原本各自 `useInView` 门控，但并没有计数动画需要它门控 —— 已改为纯展示 `<div>`，由父级 `.hero-stats` 统一淡入 |
| 2. Hero CSS 兜底动画 | `styles.css` `@keyframes jn-reveal-fallback` | 1.5s 后强制落到最终态。CSS 动画在层叠中优先级高于内联样式，delay 期间不影响 motion 动画 |
| 3. Section 双路径显形 | `Section` 组件 | IO 之外另加 `getBoundingClientRect` + scroll/resize 监听的独立显形路径 |

> ⚠️ **兜底动画只能加在 Hero 这类「挂载即播放」的元素上。**
> 不要加到 section 上：section 是滚动到视口才播放的，固定延迟的兜底会在元素还没滚到时把它强制显形，滚动入场效果会整个失效。

> ⚠️ `usePrefersReducedMotion` 必须**首帧同步读取**媒体查询（`useState` 惰性初始化），
> 不能放在 `useEffect` 里 —— 否则首帧 `reduced` 恒为 `false`，「减少动效」用户也会先被套上 `opacity: 0`。

### 9.4 字体加载

`index.html` 采用非阻塞字体加载：

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="preload" as="style" href="…IBM+Plex+Sans…" />
<link rel="stylesheet" href="…IBM+Plex+Sans…" media="print" onload="this.media='all'" />
<noscript><link rel="stylesheet" href="…" /></noscript>
```

### 9.5 构建产物

JS 381 KB（gzip 120 KB）、CSS 22 KB（gzip 5 KB）。若需进一步压缩，可考虑：

- 代码分割（当前单文件 SPA，无路由级分割需求）
- 移除 `lucide-react` 依赖（`package.json` 有但 `main.tsx` 实际用自写 SVG，未导入）
- 图片转 WebP/AVIF（兼容性 vs 体积权衡）
- 清理 `public/assets/` 里 11 个未被引用的文件（约 2.4 MB）：`01-封面-…`、`case-01~04`、`case-rail`、`customs`、`trade`、`sol-wind`、`logo-symbol.png`、`logo-horizontal.svg`（旧版文字标，禁用）。`logo-horizontal-white.png` 虽当前无引用但**保留备用**

### 9.6 无浏览器环境下的视觉验证

#### ⚠️ 先记住：`--window-size` 在窄视口下不可靠

`chrome --headless --screenshot --window-size=375,812` **算出的布局宽度会大于截图宽度**
（实测约 394px vs 375px），于是右侧被真实裁掉：语言切换器、汉堡按钮看起来"被切"。

这会骗过你，也会骗过视觉分析模型 —— 实测中它据此连续三轮断言
「页面横向溢出、语言切换器被裁切、汉堡菜单不可见」，而 CDP 实测三项全是错的
（`scrollWidth 375 = clientWidth 375`；语言切换器 `231→318`；汉堡按钮 `328→363`，均完整可见）。

**结论：窄视口（<700px）的判断和截图一律走 CDP**，别用 `--window-size`。

#### 宽视口可以用 `--window-size`

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=30000 \
  --window-size=1440,900 --screenshot="out.png" "http://localhost:3300/"
```

两个坑：

1. **`--window-size` 的高度会改变 `100vh`。** Hero 是 `min-height: 100vh`，
   把窗口高度设成 9500px（想一次截全页），Hero 就撑满 9500px，
   你截到的「全页」整个都是 Hero —— 看不到任何 section。想截全页需先临时中和：

   ```bash
   # 临时改构建产物（dist/ 是产物，重建即还原；改完记得重新 build）
   python -c "p='dist/index.html';h=open(p,encoding='utf-8').read();open(p,'w',encoding='utf-8').write(h.replace('</head>','<style>.hero{min-height:auto !important}</style></head>'))"
   ```

2. **无头模式下 motion 的动画循环不执行**，`--dump-dom` 里所有动画元素都停在 `opacity: 0`，
   因此 dump-dom **不能**用来判断「内容是否可见」。要判断可见性用 `--force-prefers-reduced-motion`
   （reduced-motion 分支不套 `opacity: 0`，元素直接以最终态渲染）：

   ```bash
   "$CHROME" --headless=new --disable-gpu --force-prefers-reduced-motion \
     --dump-dom "http://localhost:3300/" | grep -o 'class="section"[^>]*'
   # 期望：style="opacity: 1; transform: none;"，且 opacity: 0 计数为 0
   ```

3. **SPA 的 `#anchor` 在首次加载时不存在**，`http://host/#services` 不会滚动到该 section。

#### 布局问题的权威判定：用 CDP 量

```bash
# 先起生产服务器
NODE_ENV=production PORT=3300 node dist/server.cjs

# 跑验证脚本（本项目自带）
python scripts/verify-layout.py --widths 375 680 768 1440
```

脚本会输出每个视口的 `scrollWidth` vs `clientWidth`（判溢出）、越界元素清单、
以及导航与内容网格的对齐差值。关键判据：

```js
document.documentElement.scrollWidth === document.documentElement.clientWidth   // 无横向溢出
[...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > innerWidth + 1)
// 注意 .hero-media img 因 transform:scale(1.04) 越界属正常，被父级 overflow:hidden 裁切
```

**需要截图时也必须用 CDP**（`Emulation.setDeviceMetricsOverride` 设视口 →
`Page.navigate` → `Page.captureScreenshot`），这样测量与截图才在同一视口下，不会自相矛盾。

#### 读像素的正确姿势

想自己看结构时，**打印 ASCII 亮度图**比让视觉模型描述可靠得多：

```python
# 每个字符代表 2x2 像素块，直接读行列位置
# . <60   : 60-110   o 110-170   O 170-215   # >215
```

⚠️ 但**别用「最右亮像素」找内容边界** —— Hero 背景照片全幅铺满，
最右亮像素来自照片高光（天空）而非内容，实测据此得出的「导航内容到 x=374」是错的。

> ⚠️ 视觉分析模型还会**编造具体文本**：实测中它把源码里三处一致的地址
> 「纸桥坊 5 楼 R03」读成「还剑郡 6 楼 603 室」，把当时的联系邮箱（旧地址 `quoctejiuneng@`，
> 现已统一换成 **`jiuneng.vn@gmail.com`**）读成 `quotejiuneng@`。
> **涉及事实性内容（地址、编号、邮箱）和布局尺寸，必须回源码 / 用 CDP 核对，不要采信视觉分析的字面读数。**

---

## 10. 服务器配置

### 10.1 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Gemini AI 询价顾问密钥。**部署平台 Secrets / 环境变量里设置，勿提交仓库** |
| `PORT` | 否 | 服务端口，部署平台自动注入（默认 3000） |
| `APP_URL` | 否 | 站点公网地址（自引用链接用） |
| `NODE_ENV` | 生产必填 | 必须为 `production`，否则走 Vite 中间件 dev 模式 |
| `HMR_PORT` | 否 | 开发模式 HMR 端口（默认 24679） |

> **没有 `GEMINI_API_KEY` 时页面能正常打开，但 `/api/logistics-consult` 返回 500** —— 部署后必须验证 AI 接口。

### 10.2 Express 服务要点

- 监听 `0.0.0.0:${PORT}`（Render 等平台需要绑定 0.0.0.0）
- `express.json()` 解析 JSON body
- Gemini 客户端**懒初始化**（首次调用才创建，避免启动时因缺密钥崩溃）
- 生产模式：`express.static(dist)` + `app.get('*')` 回退 `index.html`（SPA 路由）

### 10.3 健康检查

```
GET /api/health  →  {"status":"ok","time":"...","engine":{"configured":true,"base":"127.0.0.1:18001","lastProbe":{"ok":true,"at":"...","ms":5}}}
```

轻量档**永远 HTTP 200**（保活 ping / 监控 / Render 健康检查都靠它），引擎状态只是随附的「上一次探针结果」。
两种模式与全部字段见 §10.4。

### 10.4 引擎可信度运维（A 切片，2026-09）

> A 切片 = 「引擎可信度」：引擎不可达时如实降级、本机三服务崩溃自恢复、引擎参数体检成表。
> 设计与计划见 [`docs/superpowers/specs/2026-09-25-engine-trustworthiness-design.md`](docs/superpowers/specs/2026-09-25-engine-trustworthiness-design.md)、[`docs/plans/2026-09-25-engine-trustworthiness.md`](docs/plans/2026-09-25-engine-trustworthiness.md)。

**`npm run engine:audit` —— 引擎参数只读体检**

```bash
OSRM_API_BASE=http://127.0.0.1:18000 npm run engine:audit
```

- 产出人读表 `docs/engine-audit/<日期>-engine-audit.md` + 机读 `engine-params.json`（费率 / 汇率 / 油价 / 口岸费用 / 税率口径对照 五区块，每个数字带 `source`＝端点＋字段路径）。
- **引擎不可达 → 非 0 退出**，绝不产出半空的表当成功；失败路径**零副作用**（不覆盖上次产物）。
- ⚠️ **产物含内部成本参数**（售价因子 / 油价 / 汇率 / 口岸费用 / 税率）。仓库是 **public**，故 `docs/engine-audit/` 已在 `.gitignore` 里排除，**产物只落本地、绝不入库**；对客只能露售价。
- 未校准 / 未启用 / 默认值会**显式标注**（如费率样本 0 条、`price_factor.active=false`、油价 `manual_default`），不静默留空。

**`npm run stack` —— 本机三服务守护**

```bash
ENGINE_API_KEY=<key> npm run stack     # 引擎 18000 + 网关 18001 + 官网 3300
```

- 退避重启 `1/2/4/8/16s`，每服务独立计数、上限 5 次（`STACK_MAX_RESTARTS` 可覆盖）；**超限 → 停掉全部子进程 + 打印「哪个服务 / 几次 / 日志路径」+ 退出码 1**。
- 启动前做**端口占用前置检查**：数 `LISTENING` **行数**（不是「端口在不在」——Windows 允许同端口多 listener），被占则报出占用 PID 并退出 3。
- 退出码：`0` 正常 / `1` 重启超限 / `2` 参数非法 / `3` 端口被占。缺 `ENGINE_API_KEY` **拒绝启动**（否则网关起不来或密钥不一致 → `/health` 绿而客户测算全 401）。
- **只管本机**；云上由 Render 平台负责重启。

**`/api/health` 两种模式**

| 模式 | 行为 | 用途 |
|---|---|---|
| `GET /api/health`（轻量） | **永远 200** + 上次探针结果 `engine{configured,base,lastProbe{ok,at,ms}}`；首探之前 `ok:null` | 保活 / 监控 / **Render 健康检查的安全前提**（依赖挂了也不让平台把站点判死） |
| `GET /api/health?deep=1` | 实时探一次引擎，3s 超时，**单飞且无 TTL 缓存** | 排查「到底通不通」 |

- 未配置引擎（无 `OSRM_API_BASE`/`OSRM_ENGINE_KEY`）→ `configured:false` / `reason:'not_configured'`，**不算 degraded**，HTTP 仍 200；依赖不可达 → `lastProbe.ok=false` + `reason='unreachable'|'timeout'`。
- 站点侧 env：`OSRM_API_BASE`、`OSRM_ENGINE_KEY`（**必须与网关的 `ENGINE_API_KEY` 一致**，不一致时客户测算 401 而 `/health` 仍是绿的）、`HEALTH_PROBE_MS`（默认 60000，本机调试常设 5000）、`HEALTH_PROBE_TIMEOUT_MS`、`HEALTH_DEEP_TIMEOUT_MS`。
- env 数值一律做有限性/正性校验 + 上界夹到 `2147483647`（Node `setTimeout` 超过 2³¹−1 会**静默**回绕成 1ms）、下限各自不同（`HEALTH_PROBE_MS` 为 1000ms）；非法值 warn（附被拒原值）并回落默认，**不静默**。

**验收脚本跑法（全部在 `scripts/`）**

```bash
ENGINE_API_KEY=<key> python scripts/verify-health.py     # 健康检查全链路（会杀/重启依赖；必须从仓库根跑）
python scripts/verify-stack.py                           # 三服务守护（会杀三服务 → 自恢复）
python scripts/verify-engine-audit.py                    # 体检导出（死端口必须非 0 退出）
python scripts/probe-quote-api.py                        # 测算区间 + 内部字段零泄漏
npx tsx scripts/verify-engine-probe.ts                   # probeEngine 四分支（含上界直调用例）
uv run --with websockets python scripts/verify-agent-page.py --url http://127.0.0.1:3300/ai   # /ai 页六档视口+交互（本机 python 无 websockets）
```

- 项目 python 调用一律加 `env -u PYTHONPATH`（Hermes 的 `PYTHONPATH` 会污染解释器）。
- 杀任何进程前先核 `CommandLine` 身份，并数端口 `LISTENING` 行数（须为 1）；PowerShell 读 `CommandLine` 前要 `[Console]::OutputEncoding=UTF8`，否则中文路径被写坏、含中文的强身份标识永不命中。

---

## 11. 部署与域名自动配置

### 11.1 部署链路总览

```
本地 git push
    ↓  （GitHub 仓库 miiinniam/jiuneng-website）
GitHub main 分支
    ↓  （Render Blueprint 监听仓库，检测到 push 自动触发）
Render 构建：npm ci --include=dev && npm run build
    ↓
Render 启动：npm start（node dist/server.cjs）
    ↓
公网访问：https://jiuneng-website.onrender.com
```

**这就是「自动配置」的核心**：`render.yaml` 已把仓库与 Render 服务绑定，**此后每次 `git push` 到 `main` 分支，Render 自动重新构建并部署**，无需任何手动操作。

### 11.2 render.yaml 声明式配置

```yaml
services:
  - type: web
    name: jiuneng-website
    runtime: node
    repo: https://github.com/miiinniam/jiuneng-website
    plan: free
    buildCommand: npm ci --include=dev && npm run build
    startCommand: npm start
    envVars:
      - key: NODE_ENV
        value: production
      - key: GEMINI_API_KEY
        sync: false        # 密钥不同步，必须在 Render 面板手动填
      - key: APP_URL
        sync: false        # 可选，上线后填
```

> `sync: false` 表示该变量**不会**从仓库同步，必须在 Render 面板 Settings → Environment 手动填写。这是密钥不落仓库的安全设计。

### 11.3 首次部署（一次性）

完整步骤见 [`DEPLOY.md`](DEPLOY.md)。摘要：

1. 代码推送到 `github.com/miiinniam/jiuneng-website`（main 分支）
2. Render Dashboard → **New → Blueprint** → 选择该仓库 → Render 自动读取 `render.yaml`
3. **Settings → Environment** 填入 `GEMINI_API_KEY`（必须手动填）
4. Manual Deploy 触发一次，让环境变量生效
5. 验证：`curl https://jiuneng-website.onrender.com/api/health`

### 11.4 绑定官网域名

#### 情况 A：绑定子域（推荐，如 `www.jiuneng.space`）

> ⚠️ **根域 `jiuneng.space` 当前指向 Vercel（OSRM++ 官网项目），不要动根域解析。**

1. Render 服务 → **Settings → Custom Domains** → **Add Domain** → 填子域名（如 `www.jiuneng.space`）
2. Render 会显示需要配置的 DNS 记录
3. 到域名 DNS 服务商添加 CNAME 记录：

   | 类型 | 主机记录 | 记录值 | TTL |
   |---|---|---|---|
   | CNAME | `www` | `jiuneng-website.onrender.com` | 自动 / 600 |

4. 等待 DNS 生效（通常几分钟到几小时）
5. Render 自动签发 HTTPS 证书（Let's Encrypt，几分钟）
6. 更新 `APP_URL` 环境变量为 `https://www.jiuneng.space` → 重部署

#### 情况 B：把根域指向本站

需要先确认 `jiuneng.space` 上的 OSRM++ 项目是否可以迁移/合并。**未确认前不要改根域解析**，否则 OSRM++ 官网会下线。

#### 域名生效验证

```bash
# DNS 解析是否指向 Render
nslookup www.jiuneng.space

# HTTPS 与证书
curl -sI https://www.jiuneng.space/ | head -5

# 健康检查
curl -s https://www.jiuneng.space/api/health
```

### 11.5 免费层休眠与保活（必读）

Render 免费实例 **15 分钟无请求即休眠**。休眠后第一个请求会 404 / 超时（唤醒需 5–15 秒）。

> ⚠️ **这是免费层特性，不是代码 bug。**

**保活方案（推荐 UptimeRobot，云端生产级）**：

1. 注册 https://uptimerobot.com（免费版够用）
2. **Add New Monitor** → HTTP(S) → URL = `https://<你的域名>/api/health` → Interval = **5 分钟**
3. 云端运行，不依赖本机开机

**备选：本机 Hermes cron**（开发期可用，电脑关机即失效）
- 脚本：`~/AppData/Local/hermes/scripts/render_keepalive.py`，每 10 分钟 GET `/api/health`
- ⚠️ 必须用 `.py` 文件（Windows 上 `.sh` 的反斜杠路径会被吞）

### 11.6 日常更新流程

```bash
cd "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4"

npm run lint        # 类型检查（必须通过）
npm run build       # 本地构建验证（必须通过）

git add -A
git commit -m "描述本次改动"
git push            # ← 推送即触发 Render 自动部署

# 等 2–3 分钟构建完成，然后验证
curl https://<你的域名>/api/health
```

### 11.7 回滚

Render 服务页 → **Events** → 找到上次正常部署 → **Deploy** 即可回滚。

---

## 12. 故障排查速查

| 症状 | 原因 | 处理 |
|---|---|---|
| `/api/health` 404/超时，等一会又 200 | 免费层休眠 | 配保活（§11.5），**非代码 bug** |
| 页面 200 但 AI 询价 500 | `GEMINI_API_KEY` 缺失/错误 | 检查 Render 环境变量 → Manual Deploy |
| 页面白屏 / 样式全乱 | `NODE_ENV` 不是 `production` | 确认 `render.yaml` 的 `NODE_ENV=production` 生效 |
| 构建失败，dist 不存在 | 依赖未装全 / 构建命令错 | 确认 Build Command = `npm ci --include=dev && npm run build` |
| 图片 404 | 改了扩展名但没更新 `main.tsx` 的 `image` 字段 | 同步更新引用 |
| 图片显示白底方块 | Logo 被误转 JPEG（丢失透明通道） | Logo 必须保持 PNG |
| `git push` 未触发部署 | GitHub 连接异常 | Render → Settings 检查连接，或 Manual Deploy |
| 中文路径报错（本地） | Windows 路径含中文 | Render 上无此问题；本地先 `cd` 到目录再操作 |
| 语言切换后 SEO 不更新 | 客户端渲染，爬虫看到静态中文版 | 已知限制，需 SSR 才能解决（§8.2） |

---

## 13. 已知限制与待办

| 项 | 说明 |
|---|---|
| 多语言 SEO | meta 由客户端更新，爬虫只看到中文静态版。需 SSR 或生成多语言静态页 |
| 单文件 SPA | `src/main.tsx` 1633 行，含全部组件 + 三语数据。后续可拆分为 `components/` + `i18n/` |
| 手写 SVG 图标 | `package.json` 依赖了 `lucide-react` 但未使用（`main.tsx` 用自写 SVG）。可移除依赖或迁移到 lucide |
| `README.md` | 仍是 AI Studio 原始模板，未更新为项目说明 |
| 微信 / WhatsApp | 联系方式在文案中标注「待补充」 |
| 备案信息 | 页脚标注「备案信息待补充」 |
| 图片格式 | 当前 JPEG。可进一步转 WebP/AVIF 减小体积 |
| 项目目录名 | 仍为 `开发版v0.4`，实际已是 v0.5 内容 |
| `package.json` name | 仍为 `react-example` |

---

## 14. /ai 物流 AI 智能体页（新增，2026-09）

参照 oneaix.com/cuber 的版式语言新增的独立页面，与旧首页并存（**未改动旧首页任何代码**）。

### 14.1 架构

| 项 | 值 |
|---|---|
| 入口 | `ai.html` → `src/agent/main.tsx` → `src/agent/App.tsx`（页面组件）+ `src/agent/styles.css`（页面级 CSS，`.jx-*` 前缀，与 `styles.css` 完全隔离） |
| 三语内容 | `src/agent/content.ts`（`agentI18n` / `zh`+`vi`+`en`，与旧站同一套合规口径） |
| 素材清单 | `src/agent/media.ts` 读 `assets.manifest.json`（构建时打进包，不是运行时 fetch） |
| 路由 | `server.ts` 里 `/ai` 与 `/ai/` → dev 走 `vite.transformIndexHtml`，prod 走 `dist/ai.html`；Vite 多入口见 `vite.config.ts` 的 `build.rollupOptions.input` |
| 对话模型 | 右下角气泡 `POST /api/agent-chat`（SSE）**DeepSeek 优先**（`DEEPSEEK_API_KEY`；`DEEPSEEK_BASE_URL` 必须含 `/v1`；`DEEPSEEK_MODEL` 默认 `deepseek-flash`）→ 未配/调用失败**回退 Gemini** → 都没有则如实回 `error` 事件（绝不让模型绕开工具自己编里程价格）。`CHAT_PROVIDER=deepseek\|gemini` 可强制指定（强制时不回退）。OpenAI 兼容形状转换（messages / tools / 分片参数拼接 / `tool_call_id` 配对）**只在** `server/agentChat.ts` 的 `deepseekModel()` 内，编排循环 `runAgentChat()` 与 Gemini 路径不动 |
| 对话验收 | `scripts/verify-chat-deepseek.py`（假 DeepSeek + 假引擎 + 临时站点：请求形状 / 分片拼接 / id 配对 / 真工具链 / 回退与如实报错 / 白名单零泄漏 / `AGENT_CHAT_SELFTEST` 回归）；真密钥活链路用 `scripts/probe-chat-live.py` |
| 多页构建 | `vite build` 产出 `dist/index.html` + `dist/ai.html`，两者都必须在 `dist/` 里 |
| SEO | `ai.html` 内 canonical/og:url 指向 `https://site.jiuneng.space/ai`；`?lang=zh|vi|en` 可直达指定语言 |

### 14.2 页面区块（14 段，2026-09 起为「旧首页内容全量移植版」）

数字员工线：Hero（提问式小标题 + 渐变主标题 + 5 个角色胶囊 + 渐变描边输入框）→ AI 数字员工岗位矩阵（5 卡，首卡跨两列）
→ 智能体服务轮播（4 条，圆点/箭头/自动播放/触屏滑动）→ 应用场景标签页（5 个）→ AI 底座（3 卡 + 4 项数据）
→ 代表项目 + 领域跑马灯 → 在线询价（复用 `/api/logistics-consult`）→ CTA 渐变带 → 联系 → 页脚。

公司/业务线（移植自旧首页，`#system` `#solutions` `#fleet` `#network` `#qual` 五个锚点）：

| 区块 | 内容 | 图片来源 |
|---|---|---|
| `#system` 平台系统 | 12 步全流程 + 5 个系统模块 + 第二张系统截图 | `photos.sys2` = `system-tracking.jpg` |
| `#solutions` 解决方案 | 4 卡（轨交/基建/电力/新能源，sector + 图） | `photos.sol1..sol4` |
| `#fleet` 设备资源 | 3 卡（风机特种车/叶片举升车/配套资源 + spec 行） | `photos.fleet1..fleet3` |
| `#network` 中越协同网络 | 中国侧/越南侧两栏 + 合规说明 | 无 |
| `#qual` 企业信息与资质 | 2 张企业登记卡（代码/税号/地址） | 无 |

排序（用户 2026-09 确认）：岗位矩阵 → 智能体服务 → 应用场景 → AI 底座 → **平台系统** → **解决方案** → **设备资源** → 代表项目 → **中越协同网络** → **企业信息与资质** → 在线询价 → CTA → 联系 → 页脚。
导航 7 项（`数字员工/智能体服务/应用场景/平台系统/解决方案/项目案例/在线询价`），页脚「解决方案」「企业信息」已改指新锚点。

> **`#about`「关于玖能」已按用户评论整块删除**（2026-09，评论原文「这一些不要」）：数字带 + 2 段正文 + 使命/愿景 + 4 条价值观全部移除，
> 组件 / `content.ts` 的 `about` 类型与三语文案 / 导航项 / 样式一起删干净（`grep -rn "t.about\|jx-about\|#about" src/agent/` 应为空）。
> 该块文案仍可从旧站 `src/main.tsx` 的 `about` 段落复原，本次删除未提交、无历史损失。

> 移植的取舍：① 旧站 `about` 与 `qual` 都放了企业登记信息，新页只在 `#qual` 保留一处（`about` 现已整块删除）；
> ② 旧站 hero 的 4 条数字**不做数字滚动动效** —— 4 项里 3 项不是数字，计数器没有意义；数字带随 `#about` 一并删除；
> ③ 旧站 `#platform` 第二张截图原样复用，但 `#brain` 已用 `system-overview.jpg`，所以新板块只放 `system-tracking.jpg`，全页不重复同一张图；
> ④ 三语文案**直接从旧站 `src/main.tsx` 搬**（vi/en 未重译）；⑤ 新增 `#system` 的合规兜底句：
> 「平台系统为项目内部管理工具……不构成对外实时追踪服务」，避免与「不宣称全程 GPS 追踪」的口径冲突。

> **新增样式不要复用既有类名**：新板块最初用了 `.jx-stats` 做数字带，而 **AI 底座区块原本就用 `.jx-stats`**，
> 后写的规则把它压掉，底座高度从 868px 变成 890px（样式漂移）。删掉 `#about` 时一并移除了这组规则，底座恢复原样。
> 改 /ai 样式前先 `grep` 类名是否已被占用。

**能力状态必须如实标注**：`已上线 / 内测中 / 建设中` 三档（`content.ts` 的 `status` 字段），
目前只有「询价顾问」是 `live`。/ai 的合规口径与旧站一致：越南侧一律「本地合作代理网络」，
不宣称自营报关/仓储/GPS 全程追踪/7×24，AI 输出统一表述为「初步评估，不构成报价或时效承诺」。

### 14.3 素材管线（图片与动效）

- 目录 `public/assets/agent/`，命名与规格见 [`AI-ASSET-PROMPTS.md`](AI-ASSET-PROMPTS.md)。
- `npm run assets:scan` 扫描目录 → 生成 `src/agent/assets.manifest.json`（缺失即不渲染，不 404、不留空框）。
- 动效形态照参照站：**透明底循环 MP4 + 同名 PNG 首帧**（`<video autoplay muted loop playsinline poster>`）。
- `prefers-reduced-motion: reduce` 时 **video 元素数 = 0**，自动只显示 PNG 首帧（已实测）。
- 素材超体积时扫描脚本直接报警并给出 ffmpeg 压缩命令。

### 14.4 验证配方（实测通过）

```bash
npm run lint && npm run build
NODE_ENV=production PORT=3300 node dist/server.cjs
npm run verify:agent        # scripts/verify-agent-page.py，六档视口 + 交互 + 全页亮度
```

覆盖内容：360/390/768/1024/1440/1920 无横向溢出、内容隐身计数为 0、汉堡菜单可展开、
场景标签切换、轮播翻页、hero 输入 → 询价表单预填、表单 → API 的**成功与失败两条分支**
（成功分支用 CDP `Fetch.fulfillRequest` 拦截塞回契约 JSON，不依赖真实密钥）、全页 200px 带亮度扫描。

> 旧脚本 `verify-layout.py` 的探针选择器是旧首页类名，对 /ai 恒返回 `None`，判定 /ai 必须用 `verify-agent-page.py`。

### 14.5 AI 数字员工对话（2026-09 新增）

右下角悬浮按钮「问数字员工」→ 面板 → `POST /api/agent-chat`（**SSE 流式 + 函数调用**）。

| 文件 | 作用 |
|---|---|
| `server/agentChat.ts` | 编排器：SSE 事件、工具声明/执行、Gemini 适配器、自测假模型、历史清洗 |
| `server.ts` | 挂 `POST /api/agent-chat`；自测路由 `POST /api/agent-chat/selftest` **仅在 `AGENT_CHAT_SELFTEST=1` 时挂载** |
| `src/agent/ChatPanel.tsx` | 面板 UI：SSE 消费、极简 markdown、工具状态条、三语建议条、免责声明 |
| `src/agent/content.ts` | `chat` 文案块（中/越/英三份，含 `toolLabels`/`error`/`emptyReply`） |

**SSE 事件契约**（前端按 `event:`+`data:` 帧解析）：

```
event: text        {"content":"…"}                       # 正文增量
event: tool_start  {"name":"query_route_cost","label":"正在查询线路…"}
event: tool_done   {"name":"…","ok":true,"summary":"已取到线路：约 172 km"}
event: error       {"message":"站内兜底文案（按语言）"}
event: done        {"tools":1,"rounds":2}
```

**两个工具（都是"查不到就说查不到"，不许编）**

| 工具 | 数据来源 | 关键约束 |
|---|---|---|
| `query_route_cost` | `OSRM_API_BASE` 的 OSRM++ `POST /route/alternatives` | **只回里程/时长/车型/备选数，价格字段在服务端白名单式重建 payload 时被丢掉**（`pricing: 'withheld'`）。未配 `OSRM_API_BASE` → `ok:false`「报价引擎未接入」；网络/非 2xx → `ok:false`「报价引擎暂时不可用」 |
| `lookup_service_info` | 直接 import `src/agent/content.ts`（站内内容单一事实来源） | 按 `service/documents/process/contact/status` 取切片；答案来自站内而不是模型记忆 |

> **为什么把价格剥掉**：站内口径写死「不得承诺运费价格」，官网不对外报运费。OSRM++ 返回里带 `cost_total` 等字段，若原样进模型上下文，AI 迟早会报出来。剥离动作在**服务端代码**里（不是靠提示词），并且有断言覆盖（见下）。

**环境变量**：`OSRM_API_BASE`（可选，如 `https://jiuneng.space/api/v1`；不配则该能力如实标为未接入）、`AGENT_CHAT_SELFTEST=1`（仅调试用，生产**不要**开）。

**验证配方（本地实测通过）**

```bash
# 1) 工具层：价格剥离断言（需要引擎在跑）
#    注意：脚本先断言「工具真的算出了里程/车数」再做泄漏检查——不然参数契约一变就会空转假通过
OSRM_API_BASE=http://127.0.0.1:18000 npx tsx scripts/probe-tools.ts
#    期望：distance_km / vehicle_count 有值；breakdown / profit_vnd / margin_rate / border_fees / cost_* / geometry 全部「未出现」

# 2) 编排层：三场景自测（不需要 GEMINI_API_KEY）
curl -s -X POST localhost:3300/api/agent-chat/selftest -H 'Content-Type: application/json' -d '{"scenario":"route"}'   # 已配 base → ok:true
curl -s -X POST localhost:3301/api/agent-chat/selftest -H 'Content-Type: application/json' -d '{"scenario":"route"}'   # 未配 base → ok:false「报价引擎未接入」
curl -s -X POST localhost:3300/api/agent-chat/selftest -H 'Content-Type: application/json' -d '{"scenario":"info"}'    # 站内资料工具

# 3) UI 层（scripts/verify-agent-page.py 不覆盖对话面板）
#    ⚠️ 用真链路探针（零拦截，真打服务端 SSE），工具条里的数字必须来自真实引擎：
python scripts/probe-chat-live.py
#    已弃用 probe-chat-ui.py：它用 CDP 拦截伪造 SSE、从没跑过服务端那条路由，
#    /api/agent-chat 因 req.on('close') 返回 200 空流的生产 bug 就是这么被藏住的。
```

**坑**

- 本机没有 `GEMINI_API_KEY` → 真实对话只走得到 `error` 帧，**这正是"不许假装成功"那条路径**，要按语言显示站内兜底文案，不要显示空白气泡。
- 自测假模型必须**一次性消费脚本**（游标），不能每次 `stream()` 都从头重放——编排循环会多轮调用它，重放会让同一轮工具调用跑满 `MAX_ROUNDS`（这个 bug 就是自测抓出来的）。
- 悬浮按钮展开面板后**必须隐藏**，否则和面板头部关闭按钮重复。
- 工具状态条收敛时用服务端 `summary` 替换文案，不要拼「正在查询… 完成」（语义自相矛盾）。

### 14.6 待决策（未执行）

| 项 | 说明 |
|---|---|
| `/ai` 是否升为首页 | 现在是独立页，旧首页未动；升首页需改 `index.html`/`server.ts` 路由或做跳转 |
| 旧首页是否加入口 | 目前在旧站导航/页脚没有任何指向 `/ai` 的链接 |
| sitemap | `public/sitemap.xml` 尚未收录 `/ai` |
| CTA 深蓝色块 | 全页亮度扫描有 2 个 200px 带 <120（那条 CTA 渐变带，约占页面积 5%），保留与否待定 |
| 旧首页 CTA 与 /ai 的衔接 | `/ai` 的询价表单与旧站 `#consult` 是两套 UI、同一个 API |

> **已决（2026-09，见 §14.7）**：① OSRM++ 接口地址 —— 引擎就是本机 `D:\01_业务\立三方\AIOSRM++`（不是 `…\玖能\OSRM\OSRM++`，那里只有车型库），已按 Render 独立服务方案接入；
> ② 要不要报参考价 —— 业务确认对客给「参考价区间」= 引擎售价 ±10%，内部成本/利润/口岸费用明细一律不出官网。

---

### 14.7 快速测算 + OSRM++ 引擎接入（2026-09 完成）

#### 对客口径（业务已拍板）

| 项 | 口径 |
|---|---|
| 价格 | **只给参考价区间** = 引擎 `price_vnd`（售价）× 0.9 ~ × 1.1，取整到 10 万 VND；文案统一「初步测算，非正式报价」 |
| 可给 | 里程、预计行驶时长、车数、车型 |
| **绝不给** | `breakdown`（内部成本）、`profit_vnd`（利润）、`margin_rate`（毛利率）、`border_fees`（两端口岸费用明细）、`cost_*`、`geometry`；引擎的 `profile_note` 原文含 `OSRM_AVAILABLE_PROFILES` 等内部措辞，也不对客展示（只写服务端日志，页面用本地化标准说明代替） |

#### 唯一出口

```
浏览器 ──POST /api/osrm-quote──┐
AI 对话工具 query_route_cost ──┤→ server/osrmQuote.ts runQuote() ──POST {base}/route/cost──→ 引擎（带 X-API-Key）
                               └→ 白名单重建出参（内部字段在此丢弃）
```

- `server/osrmQuote.ts`：**所有剥价/校验/契约拼装只在这里**。别在别处再写一套（曾经因为「假后端照单全收松散参数」而掩盖了真契约不符的问题）。
- `server.ts` 挂 `POST /api/osrm-quote`（表单用）与 `GET /api/osrm-quote/places`（下拉清单，城市/车型白名单的服务端唯一来源，前端不重复维护）。
- 真契约：`{route:{origin:{lat,lng}, destination, border?}, cargo:{weight_kg, volume_m3?, type}, vehicle:{loading_mode, vehicle_model_id?}}` → `{ok, distance_km, driving_h, vehicle_count, vehicle_id, vehicle_label, price_min_vnd, price_max_vnd, profile_honored, ...}`。
- **引擎校验踩坑**：拼车（`consolidated`）**必须给 `cargo.volume_m3`**，否则 422（`Value error, 拼货模式（consolidated）必须填写 cargo.volume_m3`）。官网侧已提前拦（`reason: need_volume`），UI 上体积在拼车时是必填、整车时可空。
- 起终点走**白名单城市/口岸**（17 个，服务端坐标），不用地理编码：既避免依赖 Nominatim（本机实测 DNS 不通），也避免客户随便填地址。车型只放常用 6 种，**不下发引擎的 34 个内部车型库**。
- `OSRM_API_BASE` 填根地址（`https://host`）或 `https://host/api/v1` 都行（自动补 `/api/v1`）；超时 40s（Render 免费层冷启动 15–30s）。

#### 引擎部署（Render 第二个服务）

`deploy/osrm-engine/` 是 AIOSRM++ 引擎的**窄暴露网关**（不改引擎源码）：

```bash
npm run sync:engine        # 从 D:/01_业务/立三方/AIOSRM++ 同步引擎代码 + 最小运行数据
```

- `server.py`：只放行 `GET /health`（免密钥，给 Render 探活）与 `POST /api/v1/route/cost`，其余端点一律 404 —— 挡住 `/api/v1/vehicles`（车型库后台，`role: internal`）、`/rates/*`、`/border/*`、`/quote/export`、`/ai/*`、`/docs`、`/openapi.json`；业务端点必须带 `X-API-Key`（= `ENGINE_API_KEY`，未配置则拒绝启动）；每 IP 每分钟 60 次限流。
- **同步排除表是安全硬约束（只增不减）**：`company_seal.png`、`company_sign.png`（印章/签名图）、`data/ai_config.json`（真实 API Key）、`data/company_info.json`（银行账号 + SWIFT）、审计与计数状态文件。脚本每次同步后自动复核，发现即报错退出。
- `render.yaml` 里的两个服务：`jiuneng-website`（Node）+ `jiuneng-osrm-engine`（Python，`rootDir: deploy/osrm-engine`）。
- 上线只需在 Render 面板填三样：引擎服务 `ENGINE_API_KEY`（随机串）、官网服务 `OSRM_API_BASE`（引擎公网地址）、`OSRM_ENGINE_KEY`（与前者同值）。
- 已知限制：免费层休眠（配 UptimeRobot ping `/health` 保活）、运行时可写但重启即丢（改费率/汇率要改源文件并重新 `sync:engine`）。

#### 验证配方（实测通过）

```bash
# 1) 起引擎（本机）：把 AIOSRM++ 的 FastAPI 跑在 18000
# 2) 起网关：PORT=18001 ENGINE_API_KEY=xxx python deploy/osrm-engine/server.py
# 3) 起站点：OSRM_API_BASE=http://127.0.0.1:18001 OSRM_ENGINE_KEY=xxx node dist/server.cjs
# 4) 接口层与网关（脚本均已入库，参数可用 argv 覆盖）
python scripts/probe-quote-api.py            # 区间算法 = 售价±10% + 内部字段零泄漏 + 三条错误分支
python scripts/probe-engine-gateway.py       # 端点白名单全 404 + 无密钥/错密钥 401 + 最小数据目录仍可算
python scripts/probe-calc-ui.py              # 三语：填表→结果四格+区间+一键带到询价表单
#    ⚠️ 探针脚本必须入库（scripts/），别放临时目录——临时目录会被清理，文档里的命令就失效了
```

**踩过的坑（探针报「表单提交 HTTP None / 拦截 0 个响应」时先查这个）**：测算表单最初复用了
`.jx-form-grid` / `.jx-submit` 两个既有类名，而 `verify-agent-page.py` 是按这两个类名取元素的
——它先命中测算表单，于是询价表单的必填项没被填上，浏览器原生校验拦住提交，请求根本没发出去。
看着像接口故障，实为类名撞车。规矩：**新表单/按钮用独立类名**（`.jx-calc-form` / `.jx-calc-grid` /
`.jx-calc-submit`），验收脚本里的选择器一律用 `#consult .jx-consult` 作用域化。

---

## 15. 相关文档

| 文档 | 用途 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 给 AI 编码 agent 的项目上下文与踩坑记录 |
| [`DEPLOY.md`](DEPLOY.md) | Render 部署操作手册（逐步命令） |
| [`AI-ASSET-PROMPTS.md`](AI-ASSET-PROMPTS.md) | /ai 页配图/动效的规格与生成提示词表 |
| [`design-system/jiuneng-logistics/MASTER.md`](design-system/jiuneng-logistics/MASTER.md) | 品牌视觉规范（唯一事实来源） |
| `metadata.json` | AI Studio 元数据 |

---

*最后更新：v0.5 升级（设计系统重构 + SEO + 性能优化）；2026-09 新增 /ai 物流 AI 智能体页*
