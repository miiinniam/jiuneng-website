# 素材目录（/ai 智能体页专用）

把生成好的图片/动效**按下面的文件名**放进本目录，然后跑：

```bash
npm run assets:scan   # 扫描本目录 → 生成 src/agent/assets.manifest.json
npm run build         # 构建（页面按清单渲染）
npm run verify:agent  # 复验：六档视口 + 交互 + 全页亮度
```

不需要改任何代码。**文件名必须完全一致**，否则扫不到。

## 命名与规格（详细提示词见根目录 `AI-ASSET-PROMPTS.md`）

| 文件名 | 内容 | 尺寸 | 格式 | 上限 |
|---|---|---|---|---|
| `role-inquiry.png` | 询价顾问「小玖」头像 | 512×512 | PNG 透明底 | 150 KB |
| `role-customs.png` | 关务专员头像 | 512×512 | PNG 透明底 | 150 KB |
| `role-docs.png` | 单证专员头像 | 512×512 | PNG 透明底 | 150 KB |
| `role-dispatch.png` | 调度专员头像 | 512×512 | PNG 透明底 | 150 KB |
| `role-translate.png` | 翻译专员头像 | 512×512 | PNG 透明底 | 150 KB |
| `svc-inquiry.mp4` + `svc-inquiry.png` | 询价受理动效 + 首帧 | 1040×780 | MP4 透明底 + PNG | 2.5 MB |
| `svc-customs.mp4` + `.png` | 单证预审动效 + 首帧 | 1040×780 | 同上 | 2.5 MB |
| `svc-plan.mp4` + `.png` | 方案要点动效 + 首帧 | 1040×780 | 同上 | 2.5 MB |
| `svc-bilingual.mp4` + `.png` | 双语沟通动效 + 首帧 | 1040×780 | 同上 | 2.5 MB |
| `app-inquiry.mp4` + `.png` | 智能询价场景 | 1200×750 | MP4 浅底 + PNG | 3 MB |
| `app-customs.mp4` + `.png` | 报关单证场景 | 1200×750 | 同上 | 3 MB |
| `app-loading.mp4` + `.png` | 装载与车型场景 | 1200×750 | 同上 | 3 MB |
| `app-milestone.mp4` + `.png` | 在途与节点场景 | 1200×750 | 同上 | 3 MB |
| `app-automation.mp4` + `.png` | 流程自动化场景 | 1200×750 | 同上 | 3 MB |
| `brain.png` | 「物流大脑」插图 | 800×800 | PNG 透明底 | 200 KB |
| `hero-loop.mp4` | 首屏背景微动效 | 1920×1080 | MP4/WebM 无缝循环、无音轨 | 4 MB |
| `cta-loop.mp4` | CTA 背景微动效 | 1920×600 | 同上，深底浅光 | 3 MB |

## 硬要求

- 动效**无音轨**（`ffmpeg -an`）、**横屏**、**6–12s 且首末帧一致**（否则每轮会跳一下）。
- 画面里**不要有文字**（页面是中/越/英三语，图里带字会露馅）。
- **不要**放第三方企业 logo —— 需书面授权（详见 `AI-ASSET-PROMPTS.md` 第 0 节）。
- 脱敏：不出现真实客户名、车牌、金额、证件号。

## 体积超了怎么办

```bash
ffmpeg -y -i 原文件.mp4 -vcodec libx264 -crf 28 -preset slow -an -movflags +faststart 目标.mp4   # 不透明动效
ffmpeg -y -i 原文件.mp4 -vcodec libvpx-vp9 -pix_fmt yuva420p -crf 34 -b:v 0 -an 目标.webm          # 透明底动效（更小）
```

> 本目录空着时页面就是纯文字版式 —— 这是**预期状态**，不是坏了。
