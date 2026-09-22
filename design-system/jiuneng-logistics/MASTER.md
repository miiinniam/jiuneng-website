# JIUNENG logistics — Visual Source of Truth

Brand-locked design system for the official website (`JIUNENG 官网/开发版v0.4`).
Do **not** regenerate this file with generic `--design-system` output. Official colors come from the JIUNENG Logo Standard Package.

## Product

- **Name:** JIUNENG logistics
- **Type:** B2B engineering logistics platform (China–Vietnam)
- **Audience:** Chinese enterprises running projects / trade in Vietnam
- **Tone:** Professional, reliable, international, concise, premium
- **Landing pattern:** Trust & Authority + Conversion
  Hero (mission) → Proof stats → About / platform → Services & cases → Inquiry CTA

## Brand colors (locked)

| Token | Hex | Use |
|------|-----|-----|
| `--navy` | `#001030` | Headings, hero title, body-strong text (v0.6: no longer a full-bleed background) |
| `--blue` | `#0040C0` | Primary brand / CTA / key labels |
| `--cyan` | `#2080F8` | Signal / highlight / window-dot accent on light ground |
| `--cyan-on-dark` | `#4DA3FF` | 深色底上文字专用加亮版（v0.6 无深色区块，暂未使用，规则保留） |

> `--cyan` 直接当深色底上的小字用只有 **4.44:1**，低于 WCAG AA 的 4.5:1（eyebrow 仅 11.8px）。
> 因此深色底上的文字/小标签统一用 `--cyan-on-dark`（6.4:1）；图形/图标仍可用 `--cyan`（图形门槛 3:1）。
> 色相与品牌一致，只是提高明度 —— 不是新品牌色。
| `--ink` | `#0A1628` | Body text |
| `--ink-soft` | `#243044` | Secondary text |
| `--muted` | `#4A5B73` | Supporting copy |
| `--bg` | `#F8FBFF` | Page ground（v0.6 由 `#F4F7FB` 提亮） |
| `--bg-paper` | `#EEF4FD` | Alternating bands + footer（v0.6 由 `#E8EEF6` 提亮） |
| `--surface` | `#FFFFFF` | Cards / forms |
| `--line` | `#DBE4F0` | Borders（v0.6 由 `#D5DEEA` 提亮） |
| `--chrome` | `rgba(255,255,255,.88)` | Nav bar over the hero photo |
| `--chrome-strong` | `rgba(255,255,255,.96)` | Scrolled nav |
| `--chrome-soft` | `rgba(255,255,255,.72)` | Ghost buttons, chips, small controls |

Gradient direction for brand marks: `#001030 → #0040C0 → #2080F8`.

**Do not use:** Braun orange `#E96A26`, warm paper `#E4E1DC`, black-gold luxury palettes, glassmorphism as the page language.

## Chrome (v0.6 — light skeleton)

v0.5 的骨架是深蓝满幅（Hero + 询价区 + 页脚），观感头尾压重。v0.6 起**全站浅色骨架**，
品牌色相不变，深色只作为文字与点缀出现：

| 位置 | 做法 |
|---|---|
| Hero | 实拍照片 + **白色雾化遮罩**：文字侧 `rgba(255,255,255,.96)` 保证 `--navy` 标题对比度，照片侧降到 `.04` 让画面可见；底部淡入页面底色 |
| Hero 卡片（`.hero-panel` / `.hero-stats`） | 白底 `.9`/`.94` + `--line` 边框 + `--shadow-md`，边界必须在亮底上分得清 |
| Nav | `--chrome` 白雾，向下淡出；滚动后 `--chrome-strong` + `--line` 下边框 |
| 询价区 | 白 → `--bg-paper` 渐变 + 淡青径向（`rgba(32,128,248,.12)`） |
| 页脚 | `--bg-paper` + 1px `--line` 上边框 |
| 系统截图 | 一律套 `.shot-frame` 浅色窗口框（窗口圆点 + 标签），不裸贴页面 |

**硬约束**：不允许再出现 **>15% 页面面积** 的深色区块；配图优先浅色、日间、明亮的画面。
整页截图按 200px 带扫描，任一区域平均亮度低于 **120/255** 即视为回归。

## Typography

- **UI / headings / body:** IBM Plex Sans (Financial Trust pairing)
- **CJK fallback:** PingFang SC, Microsoft YaHei, Noto Sans SC
- Base 16px, body line-height 1.6–1.75
- Headings: 600, tight tracking `-0.02em` to `-0.03em`

## Shape & elevation

- Radius: 6 / 10 / 16
- Cards: 1px border + soft navy shadow, lift 3px on hover
- No hard offset / brutalist shadows
- Official logos: no extra drop shadow, outline, or recolor

## Logo

| Context | File |
|---------|------|
| All site chrome（v0.6：nav / hero / footer 全为浅色） | `/assets/logo-horizontal.png` |
| Dark-ground blocks（当前没有；白色版留档备用） | `/assets/logo-horizontal-white.png` |
| Favicon | `/favicon.png` (official symbol) |

Never use the old Braun text-mark SVG (`logo-horizontal.svg`).

## Motion

- Purpose: orientation + continuity only
- Enter: `cubic-bezier(0.22, 1, 0.36, 1)`, 200–450ms
- Hover: color / opacity 150–220ms; image scale only
- Press: `scale(0.98)` at 0ms
- Animate `transform` / `opacity` only
- `prefers-reduced-motion: reduce` must skip travel and render final state

## CTA

- Primary: navy-blue fill `#0040C0`, white label, in nav + hero + consult
- Secondary: ghost / outline
- Inquiry form sits on a light band (white → `--bg-paper`) as the closing CTA (v0.6)

## Avoid

- 大面积深色满幅色带（v0.6 起 Hero / 询价区 / 页脚一律浅色骨架）
- Playful / fashion / luxury-gold looks
- Mixing flat cards with skeuomorphic panels
- Emoji as icons
- Unverified claims, fake 7×24, GPS-everywhere, self-operated Vietnam warehouses
