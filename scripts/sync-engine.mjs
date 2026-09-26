#!/usr/bin/env node
/**
 * 把 AIOSRM++ 的引擎代码与**最小运行数据**同步到官网仓库的 deploy/osrm-engine/，
 * 供 Render 以独立服务部署（官网服务端带密钥调用）。
 *
 * 为什么是「同步」而不是让引擎仓库自己部署：
 *   AIOSRM++ 是独立的桌面产品（有自己的版本档案与门禁流程），本项目不改它一行源码；
 *   这里生成的是**只读副本**，改了引擎代码要重跑本脚本。
 *
 * ⚠️ 排除表是硬约束（安全红线）：
 *   - 公司印章/签名图（resources/company_seal.png、company_sign.png）—— 资产，绝不进公网包
 *   - resources/data/ai_config.json —— 内含真实 API Key
 *   - resources/data/company_info.json —— 内含银行账号与 SWIFT
 *   - 审计/计数等运行时状态文件
 *   排除表只增不减；新增数据文件前先确认它不含密钥、账号、印章类内容。
 *
 * 用法： npm run sync:engine
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..');
const SRC = process.env.AIOSRM_DIR || 'D:/01_业务/立三方/AIOSRM++';
const DEST = path.join(repo, 'deploy', 'osrm-engine');

/** 绝不外发的文件（文件名或相对路径片段） */
const EXCLUDE_NAMES = new Set([
  'company_seal.png',
  'company_sign.png',
  'ai_config.json',
  'company_info.json',
  'ai_audit.jsonl',
  'quote_counter.json',
  // ── 业务数据：**尚未公开**（公开的引擎仓库 miiinniam/jiuneng-osrm 里没有这三份），
  //    绝不允许进入任何外发副本（含本仓库的 deploy/ 与 Render 服务）。
  //    实测（2026-09-26）：去掉这三份后引擎仍能起且真算 —— 上海→河内 / 20t / flatbed_13m
  //    → 2243.0265 km、调整后 29.89h、售价 77,400,453 VND，与带全部数据的基线逐位一致；
  //    /health 200、白名单 404、无密钥 401 均正常。故三者**不属运行必需**。
  'price_versions.json',      // 历次售价调整记录（9 个版本）
  'calibration_samples.json', // 真实成交样本
  'demand_periods.json',      // 旺季价格系数期间（当前 price_factor.active=false）
]);
const EXCLUDE_DIRS = new Set(['__pycache__', '.pytest_cache', '.venv-build', 'venv']);

/** 引擎运行 /route/cost 需要的数据文件（白名单，逐个人工确认过内容） */
const DATA_FILES = [
  'osrm_plus.db',            // 车型/费率相关的 sqlite
  'fixed_fees.json',         // 固定费用
  'hs_tariff_2026.json',     // 税则（border 计费需要）
  'exchange_rate.json',      // 汇率
];

function copyTree(srcDir, destDir) {
  let files = 0;
  let bytes = 0;
  fs.mkdirSync(destDir, { recursive: true });
  for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
    if (EXCLUDE_DIRS.has(entry.name) || EXCLUDE_NAMES.has(entry.name)) continue;
    const from = path.join(srcDir, entry.name);
    const to = path.join(destDir, entry.name);
    if (entry.isDirectory()) {
      const sub = copyTree(from, to);
      files += sub.files;
      bytes += sub.bytes;
    } else if (entry.isFile()) {
      if (entry.name.endsWith('.bak') || entry.name.endsWith('.pyc')) continue;
      fs.copyFileSync(from, to);
      files += 1;
      bytes += fs.statSync(from).size;
    }
  }
  return { files, bytes };
}

function main() {
  if (!fs.existsSync(path.join(SRC, 'backend', 'app', 'main.py'))) {
    console.error(`✗ 找不到引擎源码：${SRC}/backend/app/main.py`);
    process.exit(1);
  }

  // 清掉上次的副本再同步，避免删掉的文件残留
  for (const dir of ['engine', 'data']) {
    fs.rmSync(path.join(DEST, dir), { recursive: true, force: true });
  }

  const app = copyTree(path.join(SRC, 'backend', 'app'), path.join(DEST, 'engine', 'app'));
  console.log(`✓ 引擎代码  deploy/osrm-engine/engine/app/  ${app.files} 个文件，${(app.bytes / 1024).toFixed(0)} KB`);

  // 引擎数据：resource_dir()/data → 由 OSRM_RESOURCE_DIR 指向 deploy/osrm-engine
  fs.mkdirSync(path.join(DEST, 'data'), { recursive: true });
  let dataBytes = 0;
  const missing = [];
  for (const name of DATA_FILES) {
    const from = path.join(SRC, 'resources', 'data', name);
    if (!fs.existsSync(from)) { missing.push(name); continue; }
    fs.copyFileSync(from, path.join(DEST, 'data', name));
    dataBytes += fs.statSync(from).size;
  }
  console.log(`✓ 运行数据  deploy/osrm-engine/data/  ${DATA_FILES.length - missing.length} 个文件，${(dataBytes / 1024 / 1024).toFixed(1)} MB`);
  if (missing.length) console.log(`  ⚠️ 源目录缺失（引擎缺数据时会报错，请人工确认）：${missing.join(', ')}`);

  const vcsv = path.join(SRC, 'resources', '车辆型号库.csv');
  if (fs.existsSync(vcsv)) {
    fs.copyFileSync(vcsv, path.join(DEST, '车辆型号库.csv'));
    console.log(`✓ 车型库   deploy/osrm-engine/车辆型号库.csv  ${(fs.statSync(vcsv).size / 1024).toFixed(0)} KB`);
  } else {
    console.log('  ⚠️ resources/车辆型号库.csv 不存在');
  }

  // 复核：排除表里的敏感文件绝不能出现在副本里
  const leaked = [];
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (EXCLUDE_NAMES.has(entry.name)) leaked.push(path.relative(DEST, full));
    }
  })(DEST);
  if (leaked.length) {
    console.error(`✗ 敏感文件泄漏到副本：${leaked.join(', ')}`);
    process.exit(1);
  }
  console.log('✓ 安全复核：印章/签名/API Key/银行账号/审计文件均未进入副本');
}

main();
