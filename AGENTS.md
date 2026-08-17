# 玖能国际官网 v0.4 —— 项目上下文(pi agent 必读)

本文件是给 AI 编码 agent(pi / Claude Code / Codex 等)的项目说明书。**在开发、构建、部署本项目的任何操作之前,先读本文件**。

## 项目是什么

玖能国际(JIUNENG International)官方门户网站,面向中国企业的工程物流平台(中越工程物流、进出口报关、国际贸易)。

- **技术栈**:React 19 + Vite + TailwindCSS 4(motion 动画)+ Express(server.ts)
- **入口文件**:`src/main.tsx`(前端单页)、`server.ts`(Express 服务,含 Gemini 在线询价顾问 API)
- **AI 功能**:`POST /api/logistics-consult` 调用 Gemini 2.5 Flash 生成询价初步评估,需要 `GEMINI_API_KEY`
- **健康检查**:`GET /api/health`(保活/监控用)

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
- **public/ 有 39MB 图片**:GitHub 仓库会偏大(单文件未超 100MB 限制,可正常推送);若嫌慢可后续转 WebP(参考 OSRM++ 项目 osrmpp-dev 技能里的图片管线)
- **不要在服务器上跑 `npm run dev`**:HMR 端口和文件监听在无头环境会出问题,生产必须 build + start
- **域名**:当前建议先用 `https://<service>.onrender.com` 上线;绑 `jiuneng.space` 子域(如 `www.` 或 `site.`)时在 Render Settings → Custom Domain 配置 CNAME,并注意根域 `jiuneng.space` 目前指向 Vercel(OSRM++ 官网),**不要动根域解析**

## 项目历史背景

- 由 Google AI Studio 导出(README 指向 ai.studio app),`metadata.json` 标记了 AI Studio 能力
- 业务背景:玖能国际在越南河内,主打中越工程物流;公司定位"面向中国企业的工程物流平台",中国侧由广西玖一进出口贸易有限公司支持
- 同一品牌下还有 OSRM++ 报价工具(Next.js,部署在 Vercel `jiuneng.space`),与本站是两个独立项目,互不依赖
