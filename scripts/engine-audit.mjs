#!/usr/bin/env node
/**
 * 引擎参数体检：**只读**拉取 → 出两张产物
 *   1) docs/engine-audit/<YYYY-MM-DD>-engine-audit.md   给业务方核对的体检表（每项带 source/原值）
 *   2) docs/engine-audit/engine-params.json             机器可读快照，便于下次 diff 发现参数漂移
 *
 * ⚠️ 产物**绝不入库**：本仓库是 public，这些是内部成本参数（售价公式因子/油价/汇率/口岸费用/税率）。
 *    `.gitignore` 里已忽略 `docs/engine-audit/`；对客只能露售价。
 *
 * 只读纪律（绝不违反）：
 *   · 只发 GET（可复用的只读参数端点）。唯一例外是 `POST /api/v1/border/import-tax`——
 *     该端点**只有 POST**（用 GET 直接 405），而它是纯计算（`calc_import_duty_and_vat` 无任何写入、
 *     无审计写、无外部额度），是「税率口径对照」必需的一半。除此之外不碰任何写操作。
 *   · 绝不调用 `/route/cost`（配额 + 限流）、`/batch/*`、以及任何 `apply / fit / import / save /`
 *     `refresh / rollback` 写端点，也不碰 `quote/export`、`vehicles|templates` 的写方法、`/ai/*`（外部额度）。
 *   · 引擎自带 IP 限流（滑动窗口 60 req/min，实测触发过 429）→ 顺序调用 + 固定间隔 + 429 退避重试。
 *   · 先探 `/health`：引擎不可达 = **失败**（非 0 退出、**一个字节都不写**），绝不产出半空的表当成功。
 *
 * 退出码：0 = 体检完成且无拉取问题；1 = 有拉取问题（表已写出并在「拉取问题」区列出）；
 *         2 = 缺 OSRM_API_BASE；3 = 引擎不可达（体检无法进行，未落盘）。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');           // 绝不硬编码（仓库路径含中文与空格）
const OUT_DIR = path.join(ROOT, 'docs', 'engine-audit');
const SPACING_MS = 1600;                                        // 顺序 + 间隔：不撞 60 req/min 限流
const HEALTH_TIMEOUT_MS = 5000;
const FETCH_TIMEOUT_MS = 30000;
const HS_SAMPLE = '730890';                                     // 税率口径对照用的同一 HS
const CARGO_VALUE_RMB = 500000;

const rawBase = (process.env.OSRM_API_BASE || '').trim().replace(/\/+$/, '');
if (!rawBase) {
  console.error('[audit] 缺 OSRM_API_BASE，无法体检（拒绝猜一个地址：体检结果会不可信）');
  console.error('        用法：OSRM_API_BASE=http://127.0.0.1:18000 npm run engine:audit');
  process.exit(2);
}
const BASE = /\/api\/v1$/.test(rawBase) ? rawBase : `${rawBase}/api/v1`;
let ORIGIN;
try {
  ORIGIN = new URL(BASE).origin;
} catch {
  console.error(`[audit] OSRM_API_BASE 不是合法 URL：${rawBase}`);
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const HEADERS = { 'User-Agent': 'jiuneng-engine-audit' };

/** 带超时 + 429 退避的只读请求 → {ok, status, data|error} */
async function get(url, { retries = 3, method = 'GET' } = {}) {
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(url, {
        method,
        signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
        headers: HEADERS,
      });
      if (res.status === 429 && attempt < retries) {
        const wait = 2000 * (attempt + 1);
        console.warn(`[audit] 429 限流，${wait}ms 后重试 ${url}`);
        await sleep(wait);
        continue;
      }
      if (!res.ok) return { ok: false, status: res.status, raw: (await res.text()).slice(0, 300) };
      return { ok: true, status: res.status, data: await res.json() };
    } catch (error) {
      if (attempt === retries) return { ok: false, status: 0, error: String(error?.message || error) };
      await sleep(800);
    }
  }
  return { ok: false, status: 0, error: 'unreachable' };
}

// ── 0. 健康前置：不可达 = 失败，且**一个字节都不写** ─────────────────────
console.log(`[audit] 引擎健康检查 ${ORIGIN}/health …`);
let health;
try {
  const res = await fetch(`${ORIGIN}/health`, { signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS), headers: HEADERS });
  const body = await res.text();
  health = { ok: res.ok && body.includes('"ok"'), status: res.status, body: body.slice(0, 200) };
} catch (error) {
  health = { ok: false, status: 0, error: String(error?.message || error) };
}
if (!health.ok) {
  console.error(`[audit] ✗ 引擎不可达：${ORIGIN}/health 健康检查失败` +
    `（${health.status ? `HTTP ${health.status}` : health.error}）`);
  console.error('[audit] 引擎不在，体检无法进行 → 非 0 退出，未写出任何产物（绝不产出半空的表当成功）。');
  process.exit(3);
}
console.log('[audit] 引擎在线，开始只读拉取（顺序 + 间隔，不并发）。');

// ── 1. 只读区块 ─────────────────────────────────────────────────────────
const SECTIONS = [
  { key: 'rates_current', block: '费率', title: '费率主表与价格系数', path: '/rates/current' },
  { key: 'rates_samples', block: '费率', title: '费率样本（未校准时为 0 条）', path: '/rates/samples' },
  { key: 'rates_versions', block: '费率', title: '费率版本', path: '/rates/versions' },
  { key: 'rates_periods', block: '费率', title: '用车需求期间与拟合设置', path: '/rates/periods' },
  { key: 'reference_exchange_rate', block: '汇率', title: 'VND ↔ RMB 汇率', path: '/reference/exchange-rate' },
  { key: 'reference_fuel_price', block: '油价', title: '柴油油价', path: '/reference/fuel-price' },
  { key: 'border_reference_fees', block: '口岸费用', title: '口岸固定费用参数表', path: '/border/reference-fees' },
  { key: 'border_china_side', block: '口岸费用', title: '中国端费用（1 车）', path: '/border/china-side?vehicle_count=1' },
  { key: 'border_vietnam_side', block: '口岸费用', title: '越南端费用（1 车）', path: '/border/vietnam-side?vehicle_count=1' },
  { key: 'reference_cargo_types', block: '货型系数', title: '货型系数', path: '/reference/cargo-types' },
  { key: 'reference_cargo_estimates', block: '进出口费用估算', title: '进出口费用快速估算', path: '/reference/cargo-estimates' },
  { key: 'vehicles', block: '车型库', title: '车型库（role=internal，不下发客户）', path: '/vehicles' },
];

const sections = {};
const meta = {};                                                // key → {method, path, status}
const problems = [];

for (const section of SECTIONS) {
  const res = await get(`${BASE}${section.path}`);
  const endpoint = `GET /api/v1${section.path}`;
  meta[section.key] = { endpoint, method: 'GET', path: section.path, status: res.status };
  if (!res.ok) {
    problems.push(`${section.title}（${endpoint}）拉取失败：status=${res.status}${res.raw ? ` body=${res.raw}` : ''}`);
    console.error(`[audit] ✗ 拉取失败 ${endpoint} → status=${res.status}`);
  } else {
    console.log(`[audit] ✓ ${endpoint} → 200`);
    sections[section.key] = res.data;
  }
  await sleep(SPACING_MS);
}

// ── 2. 税率口径对照：同一 HS 两个端点，各取一次，**并列**（不自己选一个当正确值）──
// hs-lookup 走 GET；import-tax **只有 POST**（GET → 405）。后者是纯计算、无写入、无外部额度。
const taxPaths = {
  hs_lookup: `/border/hs-lookup?hs_code=${HS_SAMPLE}`,
  import_tax: `/border/import-tax?cargo_value_rmb=${CARGO_VALUE_RMB}&hs_code=${HS_SAMPLE}`,
};
const hsLookupRes = await get(`${BASE}${taxPaths.hs_lookup}`, { method: 'GET' });
await sleep(SPACING_MS);
const importTaxRes = await get(`${BASE}${taxPaths.import_tax}`, { method: 'POST' });
await sleep(SPACING_MS);

if (!hsLookupRes.ok) problems.push(`税率口径对照 hs-lookup 拉取失败：status=${hsLookupRes.status}`);
if (!importTaxRes.ok) problems.push(`税率口径对照 import-tax 拉取失败：status=${importTaxRes.status}`);

const taxComparison = {
  hs_code: HS_SAMPLE,
  cargo_value_rmb: CARGO_VALUE_RMB,
  hs_lookup: {
    endpoint: `GET /api/v1${taxPaths.hs_lookup}`,
    method: 'GET',
    status: hsLookupRes.status,
    duty_rate: hsLookupRes.data?.import_duty_rate,
    duty_source: hsLookupRes.data?.duty_source,
    vat_rate: hsLookupRes.data?.vat_rate,
    desc_en: hsLookupRes.data?.desc_en,
  },
  import_tax: {
    endpoint: `POST /api/v1${taxPaths.import_tax}`,
    method: 'POST',
    status: importTaxRes.status,
    duty_rate: importTaxRes.data?.duty_rate,
    duty_source: importTaxRes.data?.duty_source,
    vat_rate: importTaxRes.data?.vat_rate,
    import_duty_rmb: importTaxRes.data?.import_duty_rmb,
    vat_rmb: importTaxRes.data?.vat_rmb,
    total_tax_rmb: importTaxRes.data?.total_tax_rmb,
  },
};
taxComparison.conflict = hsLookupRes.ok && importTaxRes.ok
  && taxComparison.hs_lookup.duty_rate !== taxComparison.import_tax.duty_rate;
taxComparison.note = taxComparison.conflict
  ? `同一 HS ${HS_SAMPLE} 两个端点给出**不同**进口关税税率：`
    + `hs-lookup（协定/最优惠口径）=${taxComparison.hs_lookup.duty_rate}，`
    + `import-tax（含税测算口径）=${taxComparison.import_tax.duty_rate}。`
    + '两者都标 duty_source 相同，属于**待业务方拍板**事项：对客展示只能选一个口径，不得同时展示。'
  : `同一 HS ${HS_SAMPLE} 两个端点口径一致（duty_rate=${taxComparison.hs_lookup.duty_rate}）。`;

// ── 3. 每项 → 端点 + 字段路径 + 原值（provenance）────────────────────────
/** 点号路径取值 → {found, value}（缺失**显式**记录，不静默留空） */
function pick(obj, dotPath) {
  let cur = obj;
  for (const part of String(dotPath).split('.')) {
    if (cur === null || cur === undefined || typeof cur !== 'object' || !(part in cur)) {
      return { found: false, value: undefined };
    }
    cur = cur[part];
  }
  return { found: true, value: cur };
}

const provenance = [];
const missing = [];
function record(block, label, key, dotPath) {
  const endpoint = meta[key]?.endpoint;
  if (!endpoint) {
    // 区块本身拉取失败 → 显式记录，不是静默跳过
    provenance.push({
      block, label, value: null, status: '缺失',
      source: { endpoint: '(区块未取到)', field: dotPath, raw: null },
    });
    missing.push(`${block} · ${label}：区块 ${key} 未取到（${dotPath}）`);
    return;
  }
  const { found, value } = pick(sections[key], dotPath);
  provenance.push({
    block, label,
    value: found ? value : null,
    status: found ? 'ok' : '缺失',
    source: { endpoint, field: dotPath, raw: found ? value : null },
  });
  if (!found) missing.push(`${block} · ${label}：${endpoint} 里没有字段 ${dotPath}`);
}

// 费率
const modelCount = Array.isArray(sections.rates_current?.models) ? sections.rates_current.models.length : null;
for (const [label, p] of [
  ['价格系数 factor', 'price_factor.factor'],
  ['价格系数 active（是否启用）', 'price_factor.active'],
  ['价格系数 period（生效期间）', 'price_factor.period'],
  ['价格系数 demand_ratio', 'price_factor.demand_ratio'],
  ['价格系数 lambda', 'price_factor.lambda'],
  ['价格系数 min_factor', 'price_factor.min_factor'],
  ['价格系数 max_factor', 'price_factor.max_factor'],
  ['价格系数 clamped（是否被夹紧）', 'price_factor.clamped'],
  ['价格系数 note', 'price_factor.note'],
  ['费率样本条数（rates/current 视角）', 'samples_count'],
  ['费率版本数（rates/current 视角）', 'versions_count'],
]) record('费率', label, 'rates_current', p);
if (modelCount === null) {
  missing.push('费率 · 车型基准价条数：rates/current 的 models 不是数组');
} else {
  provenance.push({
    block: '费率', label: `车型基准价条数`, value: modelCount, status: 'ok',
    source: { endpoint: meta.rates_current.endpoint, field: 'models.length', raw: modelCount },
  });
}
record('费率', '费率样本总条数', 'rates_samples', 'stats.total');
record('费率', '费率样本日期范围', 'rates_samples', 'stats.date_range');
record('费率', '费率版本列表', 'rates_versions', 'versions');
record('费率', '用车需求期间列表', 'rates_periods', 'periods');
record('费率', '拟合设置 lambda', 'rates_periods', 'settings.lambda');
record('费率', '拟合设置 min_factor', 'rates_periods', 'settings.min_factor');
record('费率', '拟合设置 max_factor', 'rates_periods', 'settings.max_factor');
record('费率', '拟合设置 baseline_months', 'rates_periods', 'settings.baseline_months');

// 汇率
record('汇率', 'VND per RMB', 'reference_exchange_rate', 'vnd_per_rmb');
record('汇率', '来源 source', 'reference_exchange_rate', 'source');
record('汇率', '更新时间 updated', 'reference_exchange_rate', 'updated');

// 油价
record('油价', '柴油价（VND/L）', 'reference_fuel_price', 'price_vnd');
record('油价', '来源 source', 'reference_fuel_price', 'source');

// 口岸费用
for (const [label, p] of [
  ['参数表说明 _description', '_description'],
  ['参数表更新日期 _updated', '_updated'],
  ['参数表币种 _currency', '_currency'],
  ['中国端 · 报关费/车', 'china_side.customs_declaration_per_vehicle'],
  ['中国端 · 场站费/车', 'china_side.yard_fee_per_vehicle'],
  ['中国端 · 装卸费/车', 'china_side.unloading_fee_per_vehicle'],
  ['中国端 · 换装费/车', 'china_side.transloading_fee_per_vehicle'],
  ['中国端 · 境内运输费率/车/km', 'china_side.domestic_transport_rate_per_km'],
  ['越南端 · 清关费/车', 'vietnam_side.customs_clearance_per_vehicle'],
  ['越南端 · 场站费/车', 'vietnam_side.yard_fee_per_vehicle'],
  ['越南端 · 检验费/柜', 'vietnam_side.inspection_fee_per_container'],
  ['越南端 · 滞港免费小时', 'vietnam_side.detention.free_hours'],
  ['越南端 · 滞港费 第1-3天/天', 'vietnam_side.detention.rate_day1_3_vnd'],
  ['越南端 · 滞港费 第4天起/天', 'vietnam_side.detention.rate_day4_plus_vnd'],
  ['越南端 · 吊装费 <5t/吨', 'vietnam_side.heavy_lift.tier_under_5t_per_ton'],
  ['越南端 · 吊装费 5-20t/吨', 'vietnam_side.heavy_lift.tier_5t_20t_per_ton'],
  ['越南端 · 吊装费 >20t/吨', 'vietnam_side.heavy_lift.tier_over_20t_per_ton'],
  ['集装箱 20GP · 港口费', 'container.20gp.port_charge'],
  ['集装箱 40GP/HQ · 港口费', 'container.40gp_hq.port_charge'],
  ['集装箱 40OT · 港口费', 'container.40ot.port_charge'],
  ['集装箱 40FR · 港口费', 'container.40fr.port_charge'],
  ['件杂货 · 港口费/吨', 'breakbulk.port_charge_per_ton'],
  ['件杂货 · 清关费/吨', 'breakbulk.customs_clearance_per_ton'],
  ['税 · 越南 VAT 税率', 'tax_defaults.vat_rate_vn'],
  ['税 · 进口关税率兜底值', 'tax_defaults.import_duty_fallback_pct'],
  ['税 · 中国出口退税典型值', 'tax_defaults.export_tax_rebate_cn_typical'],
]) record('口岸费用', label, 'border_reference_fees', p);
record('口岸费用', '中国端小计（1 车）', 'border_china_side', 'subtotal');
record('口岸费用', '中国端 · 报关费（计算值）', 'border_china_side', 'items.customs_declaration');
record('口岸费用', '中国端 · 场站费（计算值）', 'border_china_side', 'items.yard_fee');
record('口岸费用', '中国端 · 装卸费（计算值）', 'border_china_side', 'items.unloading');
record('口岸费用', '中国端 · 换装费（计算值）', 'border_china_side', 'items.transloading');
record('口岸费用', '越南端小计（1 车）', 'border_vietnam_side', 'subtotal');
record('口岸费用', '越南端 · 清关费（计算值）', 'border_vietnam_side', 'items.customs_clearance');
record('口岸费用', '越南端 · 场站费（计算值）', 'border_vietnam_side', 'items.yard_fee');
record('口岸费用', '税 · 进口关税率兜底来源', 'border_reference_fees', 'tax_defaults.import_duty_fallback_pct');

// 货型系数
const cargoTypes = sections.reference_cargo_types || {};
if (typeof cargoTypes === 'object' && Object.keys(cargoTypes).length) {
  for (const name of Object.keys(cargoTypes)) {
    record('货型系数', `${name} · 费率倍数`, 'reference_cargo_types', `${name}.rate_multiplier`);
    record('货型系数', `${name} · 油耗惩罚`, 'reference_cargo_types', `${name}.fuel_penalty`);
  }
} else {
  missing.push('货型系数：区块未取到或为空');
}
for (const name of ['normal', 'oversized', 'heavy_equipment', 'cold_chain', 'hazardous', 'other']) {
  for (const [label, p] of [
    [`${name} · 出口费/车（RMB）`, `${name}.export_fee_rmb_per_vehicle`],
    [`${name} · 进口费/车（RMB）`, `${name}.import_fee_rmb_per_vehicle`],
    [`${name} · 估算关税率`, `${name}.estimated_duty_rate`],
    [`${name} · 估算 VAT 率`, `${name}.estimated_vat_rate`],
  ]) record('进出口费用估算', label, 'reference_cargo_estimates', p);
}

// 车型库
record('车型库', '车型数 count', 'vehicles', 'count');
const vehicleModels = Array.isArray(sections.vehicles?.models) ? sections.vehicles.models : [];
if (!vehicleModels.length) missing.push('车型库：vehicles.models 空或非数组');
for (const m of vehicleModels) {
  provenance.push({
    block: '车型库', label: `${m.model_id} 基准价/车/km`,
    value: m.base_rate_vnd_per_km, status: 'ok',
    source: { endpoint: `${meta.vehicles.endpoint} · models[model_id=${m.model_id}]`,
              field: 'base_rate_vnd_per_km', raw: m.base_rate_vnd_per_km },
  });
  provenance.push({
    block: '车型库', label: `${m.model_id} 固定调度费`,
    value: m.fixed_surcharge_vnd, status: 'ok',
    source: { endpoint: `${meta.vehicles.endpoint} · models[model_id=${m.model_id}]`,
              field: 'fixed_surcharge_vnd', raw: m.fixed_surcharge_vnd },
  });
}

// ── 4. 显式标注：缺失 / 未校准 / 未启用 / 默认值 ──────────────────────────
const flags = [];
const priceFactor = sections.rates_current?.price_factor;
const samplesTotal = pick(sections.rates_samples, 'stats.total').value;
const versionsArr = sections.rates_versions?.versions;
const fuelSource = sections.reference_fuel_price?.source;
const exchangeSource = sections.reference_exchange_rate?.source;

if (samplesTotal === 0) {
  flags.push({
    item: '费率样本条数', value: 0,
    reason: '未校准：引擎里 0 条成交样本 → 费率没有实测数据支撑（校准流程从未跑过）',
    source: `${meta.rates_samples?.endpoint} · stats.total`,
  });
}
if (Array.isArray(versionsArr) && versionsArr.length === 0) {
  flags.push({
    item: '费率版本数', value: 0,
    reason: '未校准：0 个费率版本 → 没有历史版本可回滚或对比',
    source: `${meta.rates_versions?.endpoint} · versions`,
  });
}
if (priceFactor?.active === false) {
  flags.push({
    item: '价格系数 price_factor.active', value: false,
    reason: `未启用：无生效的用车需求期间，系数恒为 ×${priceFactor?.factor ?? 1}（动态定价未生效；`
      + `${priceFactor?.note || ''}）`,
    source: `${meta.rates_current?.endpoint} · price_factor.active`,
  });
}
if (fuelSource === 'manual_default') {
  flags.push({
    item: '油价来源', value: fuelSource,
    reason: '默认值：manual_default = 引擎内置常量，未接 Petrolimex 实时同步（引擎 app/api/reference.py 里还是 TODO）',
    source: `${meta.reference_fuel_price?.endpoint} · source`,
  });
}
if (exchangeSource && exchangeSource !== 'api') {
  flags.push({
    item: '汇率来源', value: exchangeSource,
    reason: `非实时：source=${exchangeSource}（api=实时接口 / file_cache=本机文件缓存 / `
      + `fixed_fees=参数表兜底 / hardcoded=硬编码兜底）`,
    source: `${meta.reference_exchange_rate?.endpoint} · source`,
  });
}
if (Array.isArray(sections.rates_periods?.periods) && sections.rates_periods.periods.length === 0) {
  flags.push({
    item: '用车需求期间', value: 0,
    reason: '未配置：0 个需求期间 → 需求比与节假日系数都不参与定价',
    source: `${meta.rates_periods?.endpoint} · periods`,
  });
}
if (taxComparison.conflict) {
  flags.push({
    item: `税率口径不一致（HS ${HS_SAMPLE}）`,
    value: { hs_lookup: taxComparison.hs_lookup.duty_rate, import_tax: taxComparison.import_tax.duty_rate },
    reason: '不一致：同一 HS 两个端点给出不同进口关税率，且两边都自称 duty_source 相同。'
      + '根因是引擎把「税率为 0」当假值回落成兜底值（`tariff.import_duty_rate or fallback`，'
      + `0.0 为 falsy → 回落 5% 兜底）。**待业务方拍板**：对客只能选一个口径。`,
    source: `${taxComparison.hs_lookup.endpoint} · import_duty_rate ｜ ${taxComparison.import_tax.endpoint} · duty_rate`,
  });
}
for (const m of missing) {
  flags.push({ item: '字段缺失', value: null, reason: `缺失：${m}`, source: '（见 reason）' });
}

// ── 5. 与上次快照 diff（参数漂移）───────────────────────────────────────
const snapshotPath = path.join(OUT_DIR, 'engine-params.json');
let previous = null;
if (fs.existsSync(snapshotPath)) {
  try { previous = JSON.parse(fs.readFileSync(snapshotPath, 'utf8')); } catch { previous = null; }
}
const changes = [];
if (previous?.sections) {
  const flat = (obj, prefix = '') => Object.entries(obj || {}).reduce((acc, [k, v]) => {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) return { ...acc, ...flat(v, key) };
    return { ...acc, [key]: v };
  }, {});
  const a = flat(previous.sections);
  const b = flat(sections);
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    if (JSON.stringify(a[key]) !== JSON.stringify(b[key])) {
      changes.push(`- \`${key}\`：${JSON.stringify(a[key])} → ${JSON.stringify(b[key])}`);
    }
  }
}

// ── 6. 生成体检表 ───────────────────────────────────────────────────────
const today = new Date().toISOString().slice(0, 10);
const nowIso = new Date().toISOString();

/** 原值渲染：**照搬引擎原值**（数字用 JS 默认表示，字符串加反引号），便于业务方逐字核对 */
function fmt(v) {
  if (v === undefined || v === null) return '（无）';
  if (typeof v === 'string') return '`' + v + '`';
  if (typeof v === 'number' || typeof v === 'boolean') return '`' + String(v) + '`';
  return '`' + JSON.stringify(v) + '`';
}
function srcCell(source) {
  return `\`${source.endpoint}\` · \`${source.field}\``;
}
const BLOCK_ORDER = ['费率', '汇率', '油价', '口岸费用', '税率口径对照',
                     '货型系数', '进出口费用估算', '车型库'];
const rows = (block) => provenance.filter((p) => p.block === block);

const L = [];
L.push(`# 引擎参数体检（${today}）`, '');
L.push(`- 引擎地址：\`${ORIGIN}\``);
L.push(`- 生成时间：${nowIso}`);
L.push(`- 引擎端点前缀：\`${BASE}\``);
L.push('- 用途：交给业务方核对**哪些参数是真实数据、哪些需要校准**（A 切片 A4 输入）');
L.push('- 生成方式：`npm run engine:audit`（**只读**：只发 GET；唯一例外是 `POST /api/v1/border/import-tax`，'
  + '该端点只有 POST 且为纯计算；绝不碰 `/route/cost`、批量与任何写端点）');
L.push('- ⚠️ 本文件含**内部成本参数**，仓库为 public → 已 `.gitignore`，**绝不入库**');
L.push('');
L.push('每个数字都带 `source`：**哪个端点 + 哪个字段路径 + 原值**（原值列照搬引擎返回值，可逐字复核）。');
L.push('');
L.push('> **结论速览**：' + (flags.length
  ? `有 ${flags.length} 项需要业务方注意（未校准 / 未启用 / 默认值 / 口径不一致）→ 见「显式标注」区。`
  : '本次未发现未校准/未启用/默认值项。'));
L.push('');

let n = 0;
for (const block of BLOCK_ORDER) {
  n += 1;
  if (block === '税率口径对照') {
    L.push(`## ${n}. ${block}（HS ${HS_SAMPLE}，货值 ${CARGO_VALUE_RMB} RMB）`, '');
    L.push('| 口径 | 结果 | source（端点 · 字段路径） |');
    L.push('|---|---|---|');
    const hl = taxComparison.hs_lookup;
    const it = taxComparison.import_tax;
    L.push(`| hs-lookup（协定/最优惠口径） | 关税率 ${fmt(hl.duty_rate)}，VAT ${fmt(hl.vat_rate)}，`
      + `duty_source ${fmt(hl.duty_source)} | \`${hl.endpoint}\` · \`import_duty_rate\` |`);
    L.push(`| import-tax（含税测算口径） | 关税率 ${fmt(it.duty_rate)}，VAT ${fmt(it.vat_rate)}，`
      + `duty_source ${fmt(it.duty_source)}，关税 ${fmt(it.import_duty_rmb)} RMB，VAT ${fmt(it.vat_rmb)} RMB，`
      + `合计 ${fmt(it.total_tax_rmb)} RMB | \`${it.endpoint}\` · \`duty_rate\` |`);
    L.push('');
    if (taxComparison.conflict) {
      L.push(`> ⚠️ **口径不一致（待业务方拍板）**：同一 HS ${HS_SAMPLE}，`
        + `hs-lookup 给 **${hl.duty_rate}**，import-tax 给 **${it.duty_rate}**，`
        + `而两边 duty_source 都是 ${fmt(it.duty_source)}。` + taxComparison.note);
      L.push('>');
      L.push('> 这两行是**并列对照**，本表**不替业务方选正确值**：对客展示只能选一个口径，不得同时展示。');
    } else {
      L.push(`> 两个端点口径一致（duty_rate=${hl.duty_rate}）。`);
    }
    L.push(`> 注：\`import-tax\` **只有 POST**（GET 会 405）；它是纯计算、无状态、无外部额度。`);
    L.push('');
    continue;
  }
  L.push(`## ${n}. ${block}`, '');
  const rs = rows(block);
  if (!rs.length) {
    L.push(`（本区块未取到数据）`, '');
    continue;
  }
  L.push('| 项 | 原值 | source（端点 · 字段路径） |');
  L.push('|---|---|---|');
  for (const r of rs) {
    L.push(`| ${r.label}${r.status === '缺失' ? ' ⚠️缺失' : ''} | ${fmt(r.value)} | ${srcCell(r.source)} |`);
  }
  L.push('');
  if (block === '费率' && modelCount) {
    L.push(`### 费率基准价明细（${modelCount} 个车型，来源 \`GET /api/v1/rates/current\` · \`models[]\`）`, '');
    L.push('| model_id | 车型 | 基准价 VND/km | 固定调度费 VND |');
    L.push('|---|---|---|---|');
    for (const m of sections.rates_current.models) {
      L.push(`| ${m.model_id} | ${m.display_name} | ${m.base_rate_vnd_per_km} | ${m.fixed_surcharge_vnd} |`);
    }
    L.push('');
  }
  if (block === '车型库' && vehicleModels.length) {
    L.push(`### 车型库明细（${vehicleModels.length} 个，role=internal 不下发客户）`, '');
    L.push('| model_id | 载重 t | 基准价 VND/km | 固定调度费 VND | 油耗 L/100km | OSRM profile |');
    L.push('|---|---|---|---|---|---|');
    for (const m of vehicleModels) {
      L.push(`| ${m.model_id} | ${m.max_load_ton} | ${m.base_rate_vnd_per_km} | ${m.fixed_surcharge_vnd} `
        + `| ${m.fuel_l_per_100km} | ${m.osrm_profile} |`);
    }
    L.push('');
  }
}

// 附：货型系数 / 进出口费用估算的原始结构（便于比对，含 source）
L.push(`## ${BLOCK_ORDER.length + 1}. 原始结构附录（便于逐字比对）`, '');
L.push(`货型系数（\`${meta.reference_cargo_types?.endpoint}\` · 整个响应体）：`, '');
L.push('```json');
L.push(JSON.stringify(sections.reference_cargo_types ?? null, null, 2));
L.push('```', '');
L.push(`进出口费用估算（\`${meta.reference_cargo_estimates?.endpoint}\` · 整个响应体）：`, '');
L.push('```json');
L.push(JSON.stringify(sections.reference_cargo_estimates ?? null, null, 2));
L.push('```', '');

L.push(`## ${BLOCK_ORDER.length + 2}. 显式标注：未校准 / 未启用 / 默认值 / 缺失 / 口径不一致`, '');
if (!flags.length) {
  L.push('（本次无此类项）', '');
} else {
  L.push('| 项 | 原值 | 说明 | source |');
  L.push('|---|---|---|---|');
  for (const f of flags) L.push(`| ${f.item} | ${fmt(f.value)} | ${f.reason} | ${f.source} |`);
  L.push('');
}

L.push(`## ${BLOCK_ORDER.length + 3}. 与上次快照的差异（参数漂移）`, '');
L.push(changes.length ? changes.join('\n') : '（无差异或首次体检）', '');

L.push(`## ${BLOCK_ORDER.length + 4}. 拉取问题`, '');
L.push(problems.length ? problems.map((p) => `- ${p}`).join('\n') : '（无：全部只读区块拉取成功）', '');

// ── 7. 落盘（只在全部拉取完成后才建目录 / 写文件）───────────────────────
fs.mkdirSync(OUT_DIR, { recursive: true });
const mdPath = path.join(OUT_DIR, `${today}-engine-audit.md`);
fs.writeFileSync(mdPath, L.join('\n'), 'utf8');
fs.writeFileSync(snapshotPath, JSON.stringify({
  at: nowIso,
  engine: ORIGIN,
  base: BASE,
  hs_sample: HS_SAMPLE,
  cargo_value_rmb: CARGO_VALUE_RMB,
  read_only_sections: SECTIONS.map((s) => ({ key: s.key, endpoint: meta[s.key]?.endpoint, status: meta[s.key]?.status })),
  provenance,
  flags,
  tax_comparison: taxComparison,
  problems,
  missing_fields: missing,
  sections,
}, null, 2), 'utf8');

console.log(`[audit] 已写出 ${path.relative(ROOT, mdPath)} 与 ${path.relative(ROOT, snapshotPath)}`);
console.log(`[audit] provenance ${provenance.length} 条 / flags ${flags.length} 条 / 变更 ${changes.length} 条`);
if (changes.length) console.log(`[audit] 参数变更：\n${changes.join('\n')}`);
if (problems.length || missing.length) {
  console.error(`[audit] ${problems.length} 个拉取问题、${missing.length} 个字段缺失（见表）：`);
  for (const p of problems) console.error(`  - ${p}`);
  for (const m of missing) console.error(`  - ${m}`);
  process.exit(1);
}
console.log('[audit] 全部只读区块拉取成功，关键字段齐备 ✅');
