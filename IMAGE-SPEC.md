# 图片替换规格（IMAGE-SPEC）

给「往站点里放新照片」定的规格。**放图前先看这一页**，尺寸/比例不对会被 CSS
`object-fit: cover` 居中裁切 —— 主体贴边的内容（标题栏、设备铭牌、人员）会被切掉。

配套脚本：`python scripts/optimize-images.py 新图.png --as <用途>`
（自动按规格缩放+裁切+压 JPEG，超体积自动降质量；`--dry-run` 只预览）

---

## 1. 本次要换的两张：平台系统截图

页面位置：`#platform` 区块右侧，`main.tsx` 里 `.platform-shots` 的两张图。

| 项 | 要求 |
|---|---|
| 命名 | **必须叫 `system-overview.jpg` 和 `system-tracking.jpg`**，直接放进 `public/assets/` 覆盖旧的 |
| 尺寸 | **1750 × 1000 px（1.75:1）**；最低 1400×800 |
| 显式比例 | CSS 写死 `aspect-ratio: 1.75` + `object-fit: cover`，比例不符会被上下或左右裁掉 |
| 实际显示宽度 | 1440 视口下约 **616 CSS px 宽**（两列网格），2× 屏占 1232 物理像素 → 1750 宽有富余 |
| 体积 | 单张 **≤ 320 KB**（JPEG q80 optimize；旧图 132 KB / 163 KB） |
| 格式 | JPEG（PNG 截图先用脚本转，别直接丢进来） |

### 内容要求

- **优先浅色/明亮界面**：在系统里切浅色模式再截图。深色仪表盘不是不能用
  （已套浅色窗口外框 `.shot-frame`），但浅色截图和 v0.6 明亮风格更统一。
- **字号**：缩到 616px 宽后，卡片标题这一层文字仍要看得清；不要把整个桌面截进来。
- **脱敏**：不要出现真实客户名、真实车牌、合同金额、身份证件号 —— 换成演示数据或打码。
- **框内标签**由代码里的 `t.platform.shotLabels` 提供（中/越/英三语），不需要截进图里；
  标签文字是「物流系统 · 项目总览」「物流系统 · 节点追踪」，若与截图内容不符请一起改
  `src/main.tsx` 的 `translations`。

---

## 2. 其他位置的规格（以后要换时照此办理）

| 用途 | 出现位置 | 目标尺寸 | 显示比例 | 体积上限 |
|---|---|---|---|---|
| `hero` | 首屏背景（`heroImage`，硬编码路径） | 2000×1200 | 5:3（全屏裁切，主体居中偏右更安全） | 350 KB |
| `solution` | 解决方案 4 张卡片 | 1680×1292 | 1.3:1 | 300 KB |
| `card` | 车辆 3 张 / 案例 3 张卡片 | 1680×1120 | 1.5:1 | 300 KB |

> ⚠️ **当前图片复用严重**：`sol-rail` / `sol-infra` / `sol-tower` 各被引用 6 次
> （解决方案、车辆、案例三处共用同一张），`sol-power`（= `case-02` 同一文件）3 次，
> `case-portrail` 3 次。补图时优先把这三处拆开，各给一张独立照片。

> ⚠️ **未被引用的图**（可直接删或改用途）：`01-封面-中越陆运工程重卡-定制生成`、
> `case-01-night-heavy-haul`、`case-02-transformer-inspection`、
> `case-03-intermodal-logistics`、`case-04-cross-border-heavy-truck`、`case-rail`、
> `customs`、`trade`、`sol-wind`、`logo-symbol.png`、`logo-horizontal.svg`（旧版文字标，禁用）。

---

## 3. Logo / 图标（**不要动**）

`logo-horizontal.png`、`logo-horizontal-white.png`、`logo-symbol.png`、`favicon*.png`、
`apple-touch-icon.png` **必须保持 PNG**（需要透明通道，转 JPEG 会出白底方块），
也不要加投影、描边或改色 —— 官方 Logo 标准包不改。

v0.6 全站浅色后，导航和页脚统一用彩色版 `logo-horizontal.png`；
白色版 `logo-horizontal-white.png` 保留备用（将来若再加深色区块才会用到）。

---

## 4. 落库流程

```bash
# 1) 按规格处理（自动裁切+压缩，超体积自动降质量）
python scripts/optimize-images.py "D:/照片/新系统截图.png" --as system-overview

# 2) 预览不写盘
python scripts/optimize-images.py "D:/照片/新系统截图.png" --as system-overview --dry-run

# 3) 换其他位置：--as solution / --as card / --as hero
```

处理完**必须**：

1. 确认文件名与代码里的引用一致（改扩展名要同时改 `src/main.tsx`：`translations` 里的
   `image` 字段 + 4 处硬编码路径 —— `heroImage`、`team-collab`、`system-overview`、
   `system-tracking`；漏改会静默 404，页面不报错但图变空白）。
2. `npm run lint && npm run build`
3. 起生产服务 `NODE_ENV=production PORT=3300 node dist/server.cjs`，用
   `python scripts/verify-layout.py --widths 375 680 1440` 确认没把布局撑破。

---

## 5. 交图前自查

- [ ] 文件名与代码引用完全一致（含扩展名 `.jpg`）
- [ ] 尺寸/比例符合上表，主体没有贴边（会被裁）
- [ ] 单张体积在限值内
- [ ] 没有敏感信息（客户名、车牌、金额、证件号）
- [ ] 横图；不要在图片里预置文字标签或白边
- [ ] 若替换 `system-*`：截图是浅色界面，或至少主体清晰、缩到 616px 仍可辨
