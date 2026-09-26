#!/usr/bin/env node
/**
 * 扫描 public/assets/agent/ 里已就位的素材，生成 src/agent/assets.manifest.json。
 *
 * 为什么要走清单：
 *   页面若直接写死 <img src="/assets/agent/role-inquiry.png">，素材没到时会 404
 *   并显示破图。改成「扫描 → 生成清单 → 页面按清单渲染」，素材不在就自动
 *   退回原来的 SVG 图标 / 纯文字版式，不会出现半成品痕迹。
 *
 * 用法（放完素材执行一次即可）：
 *   npm run assets:scan
 *
 * 命名规则见 AI-ASSET-PROMPTS.md（文件名必须完全一致）。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const ASSET_DIR = path.join(ROOT, 'public', 'assets', 'agent');
const OUT = path.join(ROOT, 'src', 'agent', 'assets.manifest.json');

const IMG_EXT = ['.png', '.webp', '.jpg', '.jpeg'];
const VID_EXT = ['.mp4', '.webm'];

const ROLES = ['inquiry', 'customs', 'docs', 'dispatch', 'translate'];
const SERVICES = ['inquiry', 'customs', 'plan', 'bilingual'];
const APPS = ['inquiry', 'customs', 'loading', 'milestone', 'automation'];

// 体积上限（与 AI-ASSET-PROMPTS.md 一致）
const LIMITS = { role: 150 * 1024, service: 2.6 * 1024 * 1024, app: 3.2 * 1024 * 1024, loop: 4.2 * 1024 * 1024 };

/**
 * 现成照片槽位：复用 public/assets/ 里**我们自己的**工程实景图（不需要新生成素材）。
 * 左＝页面槽位名，右＝public/assets/ 下的真实文件名（必须已存在，缺一即告警并跳过）。
 * 刻意避开被旧首页复用 6 次的 sol-rail / sol-infra / sol-tower。
 */
const PHOTOS = {
  case1: 'case-rail.jpg',
  case2: 'case-04-cross-border-heavy-truck-D0zxHgaL.jpg',
  case3: 'hero-wind-tower.jpg',
  platform: 'system-overview.jpg',
  // 旧首页搬过来的板块配图（解决方案 4 张 / 设备资源 3 张 / 平台系统第二张截图）
  sol1: 'sol-rail.jpg',
  sol2: 'sol-infra.jpg',
  sol3: 'sol-power.jpg',
  sol4: 'sol-tower.jpg',
  fleet1: 'vehicle-fleet.jpg',
  fleet2: 'vehicle-blade.jpg',
  fleet3: '01-封面-中越陆运工程重卡-定制生成-bSy7Ns0J.jpg',
  sys2: 'system-tracking.jpg',
};

const PHOTO_DIR = path.join(ROOT, 'public', 'assets');

const warnings = [];

/** 在目录里找 <base><ext>，返回 web 路径或 null */
function pick(base, exts, limitKey, label) {
  for (const ext of exts) {
    const file = path.join(ASSET_DIR, base + ext);
    if (!fs.existsSync(file)) continue;
    const size = fs.statSync(file).size;
    if (size === 0) {
      warnings.push(`${base + ext} 是 0 字节，已跳过`);
      continue;
    }
    const limit = LIMITS[limitKey];
    if (limit && size > limit) {
      warnings.push(`${base + ext} 体积 ${(size / 1024 / 1024).toFixed(2)} MB 超过上限 `
        + `${(limit / 1024 / 1024).toFixed(1)} MB —— 先用 ffmpeg 压一遍（见 AI-ASSET-PROMPTS.md §3）`);
    }
    if (label) console.log(`  ✓ ${label.padEnd(22)} ${base + ext}  ${(size / 1024).toFixed(0)} KB`);
    return `/assets/agent/${base}${ext}`;
  }
  return null;
}

function videoWithPoster(prefix, limitKey, label) {
  const video = pick(`${prefix}`, VID_EXT, limitKey, label ? `${label} 动效` : null);
  const poster = pick(`${prefix}`, IMG_EXT, limitKey, label ? `${label} 首帧` : null);
  if (video && !poster) {
    warnings.push(`${prefix}.mp4 有动效但没有同名 PNG 首帧 —— 建议补一张 `
      + `${prefix}.png（减少动效/弱网时兜底，避免黑框）`);
  }
  if (!video && !poster) return null;
  return { video, poster };
}

const manifest = {
  generatedAt: new Date().toISOString(),
  roles: {},
  services: {},
  apps: {},
  brain: null,
  heroLoop: null,
  ctaLoop: null,
  photos: {},
};

console.log(`扫描 ${path.relative(ROOT, ASSET_DIR)} …`);
if (!fs.existsSync(ASSET_DIR)) {
  fs.mkdirSync(ASSET_DIR, { recursive: true });
  console.log(`  （目录不存在，已新建：${path.relative(ROOT, ASSET_DIR)}）`);
}

for (const id of ROLES) {
  const src = pick(`role-${id}`, IMG_EXT, 'role', `角色头像 ${id}`);
  if (src) manifest.roles[id] = src;
}
for (const id of SERVICES) {
  const item = videoWithPoster(`svc-${id}`, 'service', `服务动效 ${id}`);
  if (item) manifest.services[id] = item;
}
for (const id of APPS) {
  const item = videoWithPoster(`app-${id}`, 'app', `场景动效 ${id}`);
  if (item) manifest.apps[id] = item;
}

const brain = pick('brain', IMG_EXT, 'service', 'AI 底座插图');
if (brain) manifest.brain = brain;
manifest.heroLoop = pick('hero-loop', VID_EXT, 'loop', 'Hero 背景动效');
manifest.ctaLoop = pick('cta-loop', VID_EXT, 'loop', 'CTA 背景动效');

// 现成照片（public/assets/ 根目录，我们自有实景图）
for (const [slot, file] of Object.entries(PHOTOS)) {
  const full = path.join(PHOTO_DIR, file);
  if (!fs.existsSync(full)) {
    warnings.push(`照片槽位 ${slot} 指向的 ${file} 不存在 —— 该位置将只显示文字`);
    continue;
  }
  const size = fs.statSync(full).size;
  manifest.photos[slot] = `/assets/${file}`;
  console.log(`  ✓ ${('照片 ' + slot).padEnd(22)} ${file}  ${(size / 1024).toFixed(0)} KB`);
}

fs.writeFileSync(OUT, JSON.stringify(manifest, null, 2) + '\n', 'utf8');

const counts = {
  角色: Object.keys(manifest.roles).length,
  服务动效: Object.keys(manifest.services).length,
  场景动效: Object.keys(manifest.apps).length,
  '底座/背景': [manifest.brain, manifest.heroLoop, manifest.ctaLoop].filter(Boolean).length,
  照片: Object.keys(manifest.photos).length,
};
console.log(`\n清单已写入 ${path.relative(ROOT, OUT)}`);
console.log('  已就位：' + Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(' · '));
if (warnings.length) {
  console.log('\n提示：');
  for (const w of warnings) console.log('  ! ' + w);
}
if (!Object.keys(manifest.roles).length && !Object.keys(manifest.services).length) {
  console.log('\n（还没有素材 —— 页面保持纯文字版式，属于预期状态。'
    + '素材到位后重跑本命令即可。）');
}
