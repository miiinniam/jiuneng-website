# ⚠️ 本项目已归档 —— 请勿在此继续开发

**状态：已停止维护（2026-09）。功能已并入 OSRM++ 统一站点。**

## 现在改哪里

**活跃项目：`D:\01_业务\立三方\货运一站式\OSRM++\`**

```
D:\01_业务\立三方\货运一站式\OSRM++\
├── frontend/     ← Next.js 16 官网 + 报价工具（改官网来这里）
├── backend/      ← FastAPI 报价引擎 + AI 对话
└── ...
```

- GitHub：`github.com/miiinniam/jiuneng-osrm`
- 线上：`https://jiuneng.space`（Vercel，前端 + `/api/v1` 同域反代后端）
- 开发技能：`osrmpp-dev`（含全部踩坑记录）

> 注意本机有**三份 OSRM++ 副本**，只有上面这份是活跃的。
> `D:\01_业务\立三方\OSRM\OSRM++\` 是旧副本；`D:\01_业务\玖能\OSRM\OSRM++\` 是空目录。

## 为什么合并

| | 本项目（独立站） | OSRM++ 统一站 |
|---|---|---|
| 技术栈 | React 19 + Vite + Express | **Next.js 16 + FastAPI** |
| 渲染 | CSR 单页 | **SSR/SSG**（SEO 友好） |
| 报价能力 | 无 | **真实报价引擎**（四约束车数公式、31 车型） |
| AI | Gemini 询价（无工具） | **DeepSeek + 6 个真实计算工具** |
| 工具页 | 无 | `/quote` `/batch` `/planner` `/tools/loader` |
| 案例详情 | 仅卡片 | `/cases/[id]` 含图片画廊 |

两边品牌色（`#001030` / `#0040c0` / `#2080f8`）与字体（IBM Plex Sans）本就逐值相同，合并成本低。

## 本项目已完成、已并入 OSRM++ 的工作

- **设计系统 v0.5**：标题字重 300 + 负字距、双层蓝调阴影、圆角收窄、`text-wrap: balance` 中文标题配平、`--cyan-on-dark` 深色底对比度修复（4.44:1 → 6.4:1）
- **SEO**：robots、sitemap、OG/Twitter、JSON-LD Organization、1200×630 分享图
- **图片管线**：40MB PNG → 6MB JPEG（quality 80），Logo 保持 PNG
- **动画健壮性**：Hero CSS 兜底动画 + `Section` 双路径显形 + `usePrefersReducedMotion` 首帧同步读取

## 本项目仍可作为参考的部分

- `DEVELOPMENT.md` —— 完整技术参考，含**无浏览器环境下的验证方法论**（CDP 判溢出、ASCII 亮度图、`--window-size` 在窄视口不可靠等）
- `scripts/verify-layout.py` —— CDP 布局验证脚本，可复用
- `src/styles.css` —— v0.5 设计令牌的完整实现（比 OSRM++ 的 globals.css 详细）

## 本地启动（仅供查看历史版本）

```bash
cd "D:\01_业务\玖能\JIUNENG 企业背景建设\JIUNENG 官网\开发版v0.4"
npm install
npm run dev          # http://localhost:3000（缺 GEMINI_API_KEY 时 AI 询价会 500）
```

---

*归档说明由 2026-09 官网整合工作生成。*
