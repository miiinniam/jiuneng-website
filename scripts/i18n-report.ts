/**
 * 语言包对照表生成器 + 缺漏检查。
 *
 * 用法：npx tsx scripts/i18n-report.ts [--out docs/i18n/三语对照表.md]
 * 产出：一张「键路径 / 中文 / Tiếng Việt / English」对照表（Markdown），
 *       并在末尾列出三语键不一致、数组长度不一致、空值的位置；有缺漏时 exit 1。
 */
import fs from 'node:fs';
import path from 'node:path';

import zhCommon from '../src/content/zh/common';
import viCommon from '../src/content/vi/common';
import enCommon from '../src/content/en/common';
import zhHome from '../src/content/zh/home';
import viHome from '../src/content/vi/home';
import enHome from '../src/content/en/home';
import zhContact from '../src/content/zh/contact';
import viContact from '../src/content/vi/contact';
import enContact from '../src/content/en/contact';
import zhAssistant from '../src/content/zh/assistant';
import viAssistant from '../src/content/vi/assistant';
import enAssistant from '../src/content/en/assistant';
import zhTools from '../src/content/zh/tools';
import viTools from '../src/content/vi/tools';
import enTools from '../src/content/en/tools';
import zhChrome from '../src/content/zh/chrome';
import viChrome from '../src/content/vi/chrome';
import enChrome from '../src/content/en/chrome';
import zhSite from '../src/content/zh/site';
import viSite from '../src/content/vi/site';
import enSite from '../src/content/en/site';

type Leaf = { key: string; zh: string; vi: string; en: string };

const DOMAINS: Array<[string, unknown, unknown, unknown]> = [
  ['common（导航/页脚/按钮/助手外壳）', zhCommon, viCommon, enCommon],
  ['home（首页 Hero）', zhHome, viHome, enHome],
  ['contact（联系页）', zhContact, viContact, enContact],
  ['assistant（悬浮助手对话层）', zhAssistant, viAssistant, enAssistant],
  ['site（营销页数据：现场 7 类 / 业务 / 平台 / 方案 / 车型 / 案例 / 关于 / 标签）', zhSite, viSite, enSite],
  ['chrome（页面级内联小字：段头 / 计数 / 按钮 / 合规说明）', zhChrome, viChrome, enChrome],
  ['tools（工具页：线路 / 报关 / 车辆匹配 / 测算助手 + 表单 + 错误文案）', zhTools, viTools, enTools],
];

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

function walk(node: unknown, prefix: string, out: Map<string, string>) {
  if (typeof node === 'string') {
    out.set(prefix, node);
    return;
  }
  if (Array.isArray(node)) {
    node.forEach((item, i) => walk(item, `${prefix}[${i}]`, out));
    return;
  }
  if (isObj(node)) {
    for (const [k, v] of Object.entries(node)) walk(v, prefix ? `${prefix}.${k}` : k, out);
  }
}

const rows: Leaf[] = [];
const problems: string[] = [];

function collect(label: string, zh: unknown, vi: unknown, en: unknown) {
  const z = new Map<string, string>();
  const v = new Map<string, string>();
  const e = new Map<string, string>();
  walk(zh, '', z);
  walk(vi, '', v);
  walk(en, '', e);

  for (const key of z.keys()) {
    if (!v.has(key)) problems.push(`vi 缺键：${label} · ${key}`);
    if (!e.has(key)) problems.push(`en 缺键：${label} · ${key}`);
  }
  for (const key of v.keys()) if (!z.has(key)) problems.push(`vi 多出键（中文无）：${label} · ${key}`);
  for (const key of e.keys()) if (!z.has(key)) problems.push(`en 多出键（中文无）：${label} · ${key}`);

  for (const [key, zhText] of z) {
    const viText = v.get(key) ?? '';
    const enText = e.get(key) ?? '';
    if (!zhText.trim()) problems.push(`中文空值：${label} · ${key}`);
    if (!viText.trim()) problems.push(`越南语空值/缺失：${label} · ${key}`);
    if (!enText.trim()) problems.push(`英语空值/缺失：${label} · ${key}`);
    rows.push({ key, zh: zhText, vi: viText, en: enText });
  }
  return { zh: z.size, vi: v.size, en: e.size };
}

const summary: string[] = [];
for (const [label, zh, vi, en] of DOMAINS) {
  const n = collect(label, zh, vi, en);
  summary.push(`| ${label} | ${n.zh} | ${n.vi} | ${n.en} |`);
}

const esc = (s: string) => s.replace(/\|/g, '\\|').replace(/\r?\n/g, ' ').trim();
const date = new Date().toISOString().slice(0, 10);

const md = [
  `# 玖能官网 · 三语对照表（语言包 ${date}）`,
  '',
  '> 由 `npx tsx scripts/i18n-report.ts` 生成，勿手改。改文案请改 `src/content/<lang>/<domain>.ts`。',
  '',
  '## 覆盖统计',
  '',
  '| 语言包 | 中文条数 | 越南语条数 | 英语条数 |',
  '|---|---|---|---|',
  ...summary,
  '',
  `合计 **${rows.length}** 条文案，三语逐条对照见表。`,
  '',
  '## 对照表',
  '',
  '| 键路径 | 中文 | Tiếng Việt | English |',
  '|---|---|---|---|',
  ...rows.map((r) => `| \`${r.key}\` | ${esc(r.zh)} | ${esc(r.vi)} | ${esc(r.en)} |`),
  '',
  '## 缺漏检查',
  '',
  problems.length ? problems.map((p) => `- ❌ ${p}`).join('\n') : '- ✅ 三语键集合一致，无空值',
  '',
].join('\n');

const outArg = process.argv.indexOf('--out');
const outPath = path.resolve(outArg > -1 ? process.argv[outArg + 1] : 'docs/i18n/三语对照表.md');
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, md, 'utf8');

console.log(`条数：${rows.length}`);
for (const line of summary) console.log(line);
console.log(`问题：${problems.length}`);
problems.slice(0, 20).forEach((p) => console.log('  ' + p));
console.log(`已写入：${outPath}`);
console.log(problems.length ? 'I18N-PACK: FAIL' : 'I18N-PACK: PASS');
process.exit(problems.length ? 1 : 0);
