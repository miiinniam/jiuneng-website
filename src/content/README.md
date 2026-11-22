# 语言包（三语文案唯一来源）

站点文案全部在这里，**不要在组件里写中文**。改词只改对应语言的这一个文件，改完跑一次检查脚本。

```
src/content/
  zh|vi|en/
    common.ts     导航 / 页脚 / 按钮 / 助手外壳        43 条
    home.ts       首页 Hero                            19 条
    contact.ts    联系页                               57 条
    assistant.ts  悬浮助手对话层                        21 条
    site.ts       现场 7 类 / 业务 / 平台 / 方案 / 车型 / 案例 / 关于 / 标签   482 条
    chrome.ts     页面级内联小字（段头 / 计数 / 按钮 / 合规说明）              48 条
    tools.ts      线路 · 报关 · 车辆匹配 · 测算助手 + 三张表单 + 错误文案      209 条
  zh/company.facts.ts   公司事实（名称 / 税号 / 地址）
  types.ts              ContactCopy / HomeCopy 等契约
  index.ts              getCommon / getHome / getContact / getAssistant / getSite / getChrome / getTools
```

## 规则

- **中文基线不复制**：`zh/site.ts` 直接 re-export `src/site/content.ts`。改中文只改 `src/site/content.ts`，改越/英只改 `vi|en/site.ts`。
- **类型即校验**：`vi|en` 的对象标注 `SiteCopy` / `ToolsCopy` / `ChromeCopy`，少一个字段 `tsc` 直接报错。
- **占位符**：`{n}` 表示数量，代码里用 `.replace('{n}', String(值))`。
- **错误文案**：`src/tools/api.ts` 走 `getTools(lang).api`，语言由 `LangProvider` 通过 `setApiLang()` 注入；服务端 `note` 只有中文，非中文界面一律忽略。

## 检查

```bash
npx tsx scripts/i18n-report.ts     # 生成 docs/i18n/三语对照表.md + 缺漏检查，末行需为 I18N-PACK: PASS
npm run lint                       # 缺字段会在这里先报
npm run build                      # 产物用于验收
```

改动后用 `?lang=vi` / `?lang=en` 打开页面，正文里不应再有中文（品牌法务行、`/quote` 报价工具、服务端返回的城市与分项名除外，见下）。

## 已知未覆盖

| 位置 | 现状 |
|---|---|
| `/quote` 报价工具 | 全站三语：页面壳 / 向导四步 / 地图与地址 / 校验 / 结果面板（公开 + 内部）/ 模板条 / 批量面板 / 口令门禁 / AI 助手与工作台 / 接口错误 / 页面标题（`features/quote/src/i18n/{shell,map,validation,results,panels,gate,workspace,apiErrors,strings}.ts`）。**按设计保留中文**：批量 Excel 的中文列名表头（模板要求）、`parseHints` 的中文口语输入正则 |
| 报关分项明细 `label_zh` | 已映射：服务端按白名单只下发中文标签，前端用 `tools.ts` 的 `customsLines`（11 条）按中文标签换成当前语言，未收录的回落到原值（不改接口契约） |
| 线路测算结果的 `origin.label` / `border.label` / `vehicle_label` | 已在前端按 place/vehicle 清单的 id 映射成当前语言（`RoutingForm` 的 `placeName()`） |
| `/ai` 页脚公司名 | 品牌法务行，保持原文 |
