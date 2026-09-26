# 官网专用 OSRM++ 测算引擎服务（Render 独立服务）

官网 `/ai` 页的「快速测算」与 AI 对话里的线路工具，都由这里提供算力。
官网服务端（`server/osrmQuote.ts`）是**唯一出口**：浏览器永远拿不到本服务的地址。

## 为什么要有这一层

`engine/` 是 AIOSRM++ 引擎的**只读副本**（桌面版的完整后端）。直接把它挂上公网会暴露：

| 被暴露的东西 | 后果 |
|---|---|
| `GET/POST /api/v1/vehicles` | 完整车型库（引擎里标着 `role: internal`） |
| `GET /api/v1/rates/*`、`/border/*` | 费率表、税则、口岸费用明细 |
| `POST /api/v1/quote/export` | 报价单导出（含公司抬头/账号模板） |
| `POST /api/v1/ai/*` | 引擎自带 AI 代理 |
| `GET /docs`、`/openapi.json` | 全部接口与字段结构 |

所以 `server.py` 做两件事，**只放行一个业务端点**：

1. **端点白名单**：只放行 `GET /health`（Render 探活，免密钥）与 `POST /api/v1/route/cost`，其余一律 `404`；
2. **密钥门禁**：业务端点必须带 `X-API-Key`，值等于环境变量 `ENGINE_API_KEY`；**未配置密钥直接拒绝启动**（避免忘记配置导致引擎裸露）；外加每 IP 每分钟 60 次限流。

本服务不改引擎任何源码，只在其前面包一层 ASGI 中间件。

## 内容来源（不要手改 `engine/` 与 `data/`）

```bash
npm run sync:engine        # 从 D:/01_业务/立三方/AIOSRM++ 同步（可用 AIOSRM_DIR 覆盖路径）
```

`scripts/sync-engine.mjs` 的排除表是硬约束，**只增不减**：

- `company_seal.png`、`company_sign.png` —— 公司印章与签名图（资产）
- `data/ai_config.json` —— 内含真实 API Key
- `data/company_info.json` —— 内含银行账号、SWIFT
- `ai_audit.jsonl`、`quote_counter.json` —— 运行时状态

脚本每次同步后会自动复核，一旦这些文件出现在副本里就直接报错退出。

## 环境变量（Render 面板填写）

| 变量 | 必填 | 说明 |
|---|---|---|
| `ENGINE_API_KEY` | ✅ | 与官网服务的 `OSRM_ENGINE_KEY` 填**同一个值**；未配置则服务拒绝启动 |
| `ENGINE_RATE_LIMIT` | 否 | 每 IP 每分钟请求上限，默认 60 |
| `OSRM_RESOURCE_DIR` | 否 | 数据目录，默认取本目录（内含 `data/` 与 `车辆型号库.csv`） |
| `PORT` | 否 | Render 自动注入 |

## 已知限制

- **免费层休眠**：15 分钟无请求即休眠，第一个测算要等 15–30s（官网侧超时设为 40s 并给出「引擎唤醒中」提示）。
  建议用 UptimeRobot 每 5 分钟 ping 一次 `https://<本服务>/health` 保活（该端点免密钥）。
- **运行时可写但重启即丢**：引擎会写 `data/exchange_rate.json`、`quote_counter.json` 等。
  容器重启后回到仓库里的版本；要长期改动费率/汇率，请改源文件并重跑 `sync:engine` 后重新部署。
- **不提供**：报价单导出、车型库维护、口岸费用明细、AI 代理 —— 官网用不到，也不该对外。
- 引擎的 `truck` profile 依赖自建 OSRM 路网，云端没有 → 引擎会按 `driving` 算路并在 `profile_note` 里说明，
  该备注会原样透给客户（官网侧白名单保留了这一字段）。
