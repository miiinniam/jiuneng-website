# 玖能国际官网 v0.5 —— 项目上下文(pi agent 必读)

本文件是给 AI 编码 agent(pi / Claude Code / Codex 等)的项目说明书。**在开发、构建、部署本项目的任何操作之前，先读本文件**。

> **完整技术参考见 [`DEVELOPMENT.md`](DEVELOPMENT.md)** —— 含架构、功能清单、AI 助手细节、设计系统令牌、SEO、性能管线、服务器配置、域名绑定、故障排查。本文件只保留 agent 最需要的上下文。
> **换配图先读 [`IMAGE-SPEC.md`](IMAGE-SPEC.md)** —— 尺寸/比例/命名/压缩规格 + 落库脚本。

## 项目是什么

玖能国际(JIUNENG International)官方门户网站，面向中国企业的工程物流平台(中越工程物流、进出口报关、国际贸易)。

- **技术栈**:React 19 + Vite 6 + TailwindCSS 4(motion 动画)+ Express 4(server.ts)
- **入口文件**:`src/main.tsx`(前端单页，1633 行)、`src/styles.css`(品牌视觉系统，1015 行)、`server.ts`(Express 服务，含 Gemini 在线询价顾问 API)
- **AI 功能**:`POST /api/logistics-consult` 调用 Gemini `gemini-3.1-flash-lite` 生成询价初步评估，需要 `GEMINI_API_KEY`
- **健康检查**:`GET /api/health`(保活/监控用)
- **设计规范**:`design-system/jiuneng-logistics/MASTER.md` 是品牌视觉唯一事实来源，**勿用通用工具重新生成**

## 常用命令

```bash
npm install          # 安装依赖
npm run dev          # 本地开发(tsx server.ts,Vite 中间件模式,HMR 端口 24679)
npm run build        # 生产构建:vite build(前端)→ dist/ + esbuild server.ts → dist/server.cjs
npm start            # 生产运行:node dist/server.cjs(Express 静态服务 dist/)
npm run lint         # tsc --noEmit 类型检查
```

生产模式下 server.ts 用 `express.static(dist)` + `app.get('*')` 回退到 index.html(SPA 路由),监听 `0.0.0.0:${PORT}`(默认 3000)。**构建后必须验证 dist/ 存在且包含 index.html**。

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Gemini AI 询价顾问 API 密钥,部署平台 Secrets/环境变量里设置 |
| `PORT` | 否 | 服务端口,部署平台自动注入(默认 3000) |
| `APP_URL` | 否 | 站点公网地址(自引用链接用) |

**没有 GEMINI_API_KEY 时页面能打开,但 `/api/logistics-consult` 会 500**——部署后必须验证 AI 询价接口。

## 上线部署(目标平台:Render 免费层 Node 服务)

完整步骤见 [`DEPLOY.md`](DEPLOY.md),摘要:

1. **git 初始化 + GitHub 建仓**(仓库 `miiinniam/jiuneng-website`,public),push 代码
2. Render Dashboard → New → **Blueprint**(使用仓库根的 `render.yaml` 声明式配置)→ 创建服务
3. 在 Render 服务 Settings → **Environment** 填入 `GEMINI_API_KEY`(render.yaml 里 `sync: false` 不会自动同步,必须手动填)
4. 免费层实例 15 分钟无请求即**休眠** → 第一个请求会 404/超时(唤醒 5-15s),这是免费层特性,**不是代码 bug**;配 UptimeRobot 每 5 分钟 ping `/api/health` 保活
5. 验证:`curl https://<service>.onrender.com/api/health` 返回 `{"status":"ok",...}`

## 常见坑(已经踩过,别再踩)

- **NODE_ENV**:Render 需要显式设 `NODE_ENV=production`,否则 server.ts 走 Vite 中间件模式(dev 模式),生产静态文件不生效
- **构建产物**:`npm run build` 同时产出前端静态文件 + `dist/server.cjs`,两者缺一不可;`npm start` 只认 dist/
- **图片已优化**:v0.5 把 public/assets/ 从 40MB PNG 压到约 4MB JPEG(quality 80)。**新增图片走 `python scripts/optimize-images.py 新图.png --as <用途>`**(自动按规格裁切+压缩),规格见 IMAGE-SPEC.md;且 **Logo 文件必须保持 PNG**(需透明通道,转 JPEG 会出白底方块)
- **平台系统截图套在 `.shot-frame` 浅色窗口框里**(标签取 `t.platform.shotLabels`,三语)。这两张图是深色仪表盘,裸贴到亮底页面上会读成一块暗区——换图时保留 `<figure>` 结构,并优先换浅色界面截图
- **同一张图被多处复用**:sol-rail/sol-infra/sol-tower 各被引用 6 次(解决方案+车辆+案例共用)。加图时优先拆开,别再往这三个位置复用同一张
- **改图片扩展名要改两处**:除了 `src/main.tsx` 里 `translations` 的 `image` 字段,还有 **4 处硬编码路径** —— `heroImage`(约 1147 行)、`team-collab`、`system-overview`、`system-tracking`。漏改会静默 404,页面不报错但 Hero 变纯色块
- **装饰性动画不能有能力让内容消失**:入场动画初始态是 `opacity:0`,已验证 IntersectionObserver 不触发时(爬虫/截图工具/rAF 节流)首屏以下全空白。已加三层防护(详见 DEVELOPMENT.md §9.3)。**兜底动画只能加在 Hero 这类挂载即播放的元素上,加到 section 上会让滚动入场效果整个失效**
- **`usePrefersReducedMotion` 必须首帧同步读取**(`useState` 惰性初始化),放 `useEffect` 里首帧恒为 false,减少动效用户也会先被套上 `opacity:0`
- **v0.6 起全站浅色骨架**:Hero(白雾遮罩)/询价区/页脚都是浅色,**不要改回深蓝满幅色块**;整页截图按 200px 带扫描,任何一带平均亮度 <120/255 就算回归(改前有 3 处深蓝大块)
- **深色底上的青色小字用 `--cyan-on-dark`(#4da3ff)**,不要用 `--cyan`(#2080f8)——后者对深蓝只有 4.44:1,低于 WCAG AA 4.5:1。v0.6 已无深色区块,该令牌留作将来加回深色块时使用
- **SEO 文件**:`public/robots.txt`、`public/sitemap.xml`、`public/assets/og-image.png`(1200×630 社交分享图);站点结构变化时手动更新 sitemap 的 lastmod
- **图片懒加载**:Hero 图用 `loading="eager" fetchPriority="high"`,其余全部 `loading="lazy" decoding="async"`,新增图片照此标注
- **无浏览器时怎么验证视觉**:用本机 Chrome 无头截图。⚠️ 两个坑:(1) `--window-size` 的高度会改变 `100vh`,把窗口设很高想截全页时 Hero 会撑满整张图,看不到 section;(2) 无头模式下 motion 动画循环不执行,`--dump-dom` 里所有动画元素恒为 `opacity:0`,**不能**用它判断内容可见性,要用 `--force-prefers-reduced-motion`。详见 DEVELOPMENT.md §9.6
- **视觉分析模型会编造细节**:实测它把源码里三处一致的「纸桥坊 5 楼 R03」读成「还剑郡 6 楼 603 室」、把邮箱 `quoctejiuneng@` 读成 `quotejiuneng@`。涉及地址/编号/邮箱等事实内容**必须回源码核对**
- **不要在服务器上跑 `npm run dev`**:HMR 端口和文件监听在无头环境会出问题,生产必须 build + start
- **域名**:当前建议先用 `https://<service>.onrender.com` 上线;绑 `jiuneng.space` 子域(如 `www.` 或 `site.`)时在 Render Settings → Custom Domain 配置 CNAME,并注意根域 `jiuneng.space` 目前指向 Vercel(OSRM++ 官网),**不要动根域解析**

## 项目历史背景

- 由 Google AI Studio 导出(README 指向 ai.studio app),`metadata.json` 标记了 AI Studio 能力
- 业务背景:玖能国际在越南河内,主打中越工程物流;公司定位"面向中国企业的工程物流平台",中国侧由广西玖一进出口贸易有限公司支持
- 同一品牌下还有 OSRM++ 报价工具(Next.js,部署在 Vercel `jiuneng.space`),与本站是两个独立项目,互不依赖
