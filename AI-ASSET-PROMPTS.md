# 玖能 AI 智能体页（/ai）—— 配图与动效提示词表

> 给「生成素材 → 发给我添加」用的规格书。生成前先看这一页；按编号命名、按规格出图，
> 发来我就能直接接上，不用返工。
>
> 参照对象：oneaix.com/cuber。**他们的素材只作内部风格参照，不上线**（见第 0 节）。

---

## 0. 先说清楚：哪些能借鉴、哪些不能扒

已下载到本机**仅作内部风格参照**（不放进站点、不对外发布）：
`C:\Users\fayypp\AppData\Local\hermes\cache\scratch\oneaix\ref\`
（他们的 5 个角色头像、服务区动效首帧 s2.png、优势区插图、合作 logo 拼图等）

| 素材类型 | 能不能直接扒下来用 | 原因 |
|---|---|---|
| 合作企业 logo（中远海运/中国外运/青岛港/DSV…） | ❌ **绝对不能** | 第三方商标 + 暗示合作关系，属于商标侵权与虚假宣传。我们案例页自己写的口径是「具体客户名称、照片与数据将在取得授权与核验后公开」 |
| 他们的 AI 角色立绘、s2.png 插画、advantages 插图 | ❌ 不能 | 对方的著作权作品，直接照搬可被投诉下架 |
| 版式机制：1212 容器、30px 圆角、渐变高亮标题、胶囊 tab、跑马灯、透明底循环 MP4 | ✅ 可以 | 设计手法不受保护，已经用在我们的 /ai 页上了 |
| 我们自己拍的现场照片、自己生成的插画/动效 | ✅ 可以 | 下面这套提示词就是干这个的 |

所以：**logo 类等授权，插画/动效类我们自己做一套。** 自己做还有个好处——比对方的通用素材更贴中越工程物流。

---

## 1. 素材清单表（生成什么、放哪里、什么规格）

落库目录：`public/assets/agent/`（新建）。**文件名必须与下表完全一致**，我按名字接线。

### P0 必做（没有它页面就还是纯文字）

| 编号 | 素材 | 用在哪里 | 尺寸 | 格式 | 体积上限 | 文件名 |
|---|---|---|---|---|---|---|
| R1 | 询价顾问「小玖」头像 | Hero 角色胶囊 + 数字员工首卡（显示 60–88px） | 512×512 | PNG 透明底 | 120 KB | `role-inquiry.png` |
| R2 | 关务专员头像 | 同上 | 512×512 | PNG 透明底 | 120 KB | `role-customs.png` |
| R3 | 单证专员头像 | 同上 | 512×512 | PNG 透明底 | 120 KB | `role-docs.png` |
| R4 | 调度专员头像 | 同上 | 512×512 | PNG 透明底 | 120 KB | `role-dispatch.png` |
| R5 | 翻译专员头像 | 同上 | 512×512 | PNG 透明底 | 120 KB | `role-translate.png` |
| V1 | 询价受理动效 | 「询价受理与初步评估」服务卡左侧动效区 | 1040×780 | MP4 透明底（+PNG 首帧） | 2.5 MB | `svc-inquiry.mp4` / `svc-inquiry.png` |
| V2 | 单证预审动效 | 「报关单证预审」服务卡 | 1040×780 | MP4 透明底（+PNG） | 2.5 MB | `svc-customs.mp4` / `.png` |
| V3 | 方案要点动效 | 「运输方案要点生成」服务卡 | 1040×780 | MP4 透明底（+PNG） | 2.5 MB | `svc-plan.mp4` / `.png` |
| V4 | 双语沟通动效 | 「中越双语业务沟通」服务卡 | 1040×780 | MP4 透明底（+PNG） | 2.5 MB | `svc-bilingual.mp4` / `.png` |

### P1 建议做（场景区从「流程列表」升级成动效 + 列表）

| 编号 | 素材 | 用在哪里 | 尺寸 | 格式 | 体积上限 | 文件名 |
|---|---|---|---|---|---|---|
| A1 | 智能询价 | 应用场景①左侧 | 1200×750（16:10） | MP4 浅底（+PNG） | 3 MB | `app-inquiry.mp4` / `.png` |
| A2 | 报关单证 | 应用场景② | 1200×750 | MP4 浅底（+PNG） | 3 MB | `app-customs.mp4` / `.png` |
| A3 | 装载与车型 | 应用场景③ | 1200×750 | MP4 浅底（+PNG） | 3 MB | `app-loading.mp4` / `.png` |
| A4 | 在途与节点 | 应用场景④ | 1200×750 | MP4 浅底（+PNG） | 3 MB | `app-milestone.mp4` / `.png` |
| A5 | 流程自动化 | 应用场景⑤ | 1200×750 | MP4 浅底（+PNG） | 3 MB | `app-automation.mp4` / `.png` |
| B1 | AI 底座插图 | 「玖能物流大脑」区块配图 | 800×800 | PNG 透明底 | 200 KB | `brain.png` |

### P2 加分项（全页动效氛围）

| 编号 | 素材 | 用在哪里 | 尺寸 | 格式 | 体积上限 | 文件名 |
|---|---|---|---|---|---|---|
| C1 | Hero 背景微动效 | 首屏光晕缓慢流动（**文字对比度不能掉**） | 1920×1080 | MP4 / WebM，10–14s 无缝循环，无音轨 | 4 MB | `hero-loop.mp4` |
| C2 | CTA 背景微动效 | 「让 AI 数字员工先干起来」深蓝渐变带 | 1920×600 | MP4 / WebM，8–12s 循环，深底浅光 | 3 MB | `cta-loop.mp4` |

### P3 只在拿到授权后才做

| 编号 | 素材 | 规格 | 备注 |
|---|---|---|---|
| L1 | 合作方 / 客户 logo 跑马灯 | 每个 logo 高 80px，PNG 透明底，深蓝单色版优先；一个 logo 一个文件 `logo-01.png`… | **必须先拿到对方书面同意**，否则继续用现在的「业务领域」文字胶囊（轨道交通/风电/电力…） |

### 通用硬要求（视频类）

- **竖屏/横屏**：一律横屏（16:10 或更宽），不要竖版。
- **无音轨**：`-an`，页面是 `autoplay muted loop playsinline`，带音轨会被浏览器拦。
- **无缝循环**：首帧 = 末帧，否则每轮会"跳一下"。
- **时长**：6–12s，不做长片；体积优先。
- **不要预置文字**：画面里别带中/越文字（三语切换会露怯），要说明的部分我们用 HTML 写。
- **脱敏**：不出现真实客户名、车牌、金额、证件号。

---

## 2. 提示词表（直接复制去生成）

统一风格锚（每段提示词都已含它，中文工具用中文、Sora/Veo/Runway 用英文版）：

> 浅色明亮、蓝白科技感、3D 微立体、大面积留白、干净利落、无文字、单主体居中

### R1–R5 数字员工头像（512×512 透明底，3D 卡通半身）

| 编号 | 中文提示词（即梦 / 可灵 / 海螺 / Vidu） | 英文提示词（Midjourney / Sora / GPT-Image） |
|---|---|---|
| R1 询价顾问 | 3D 卡通半身头像，年轻专业的物流询价顾问，深蓝色合身工装马甲配青色高光边，胸前一个小徽章，手持平板电脑，微笑自信看向镜头；浅蓝白色科技感背景，柔和顶部光，大面积留白，3D 渲染质感，超干净；**纯色背景便于抠图**，无文字，无 logo，正方形构图，512×512 | 3D cartoon half-body portrait of a young professional logistics quoting advisor, navy fitted work vest with cyan trim, small badge, holding a tablet, confident smile at camera; light blue-white tech backdrop, soft top light, lots of negative space, clean 3D render, flat background for easy cutout, no text, no logo, square |
| R2 关务专员 | 同上风格：严谨的关务专员，深蓝制服衬衫配青色领边，一手拿文件夹一手做"确认"手势，表情沉稳；背景同上 | same style: meticulous customs specialist, navy uniform shirt with cyan collar trim, one hand holding a document folder, other hand making a confirm gesture, calm expression; same background |
| R3 单证专员 | 同上风格：专注的单证专员，深蓝工装配青色袖口，面前悬浮两张半透明单据并做出比对动作，戴着细框眼镜 | same style: focused documents specialist, navy uniform with cyan cuffs, two translucent documents floating in front while comparing them, thin-frame glasses |
| R4 调度专员 | 同上风格：干练的调度专员，深蓝工装配青色肩线，手边一个悬浮的卡车/设备三维小图标，戴耳机，自信站姿 | same style: sharp dispatch specialist, navy uniform with cyan shoulder lines, floating minimal 3D truck/equipment icon beside them, wearing a headset, confident posture |
| R5 翻译专员 | 同上风格：亲和的翻译专员，深蓝工装配青色丝巾/领结，双手之间一个中越双向箭头图标，微笑 | same style: approachable translation specialist, navy uniform with cyan scarf/collar accent, a CN-VI two-way arrow icon between both hands, warm smile |

**共用负面提示词**：写实真人照片、真实面孔、文字/字母/数字、logo、水印、复杂背景、多个主体、暗色、浓艳原色、低分辨率、塑料感过强、肢体畸形、多余手指。
**共通英文负面词**：photorealistic real person, real face, text, letters, numbers, logo, watermark, cluttered background, multiple subjects, dark mood, oversaturated, low-res, deformed hands.

> 抠图提示：先用纯色背景（亮天蓝或纯白）生成，再抠成 PNG 透明底；能直接出透明底的模型（可灵/即梦的透明背景选项）优先。

### V1–V4 服务卡动效（1040×780，透明底循环 MP4）

| 编号 | 中文提示词 | 英文提示词 |
|---|---|---|
| V1 询价受理 | 透明背景上的 3D 微立体动效：一张半透明询价单据从左侧滑入，自动被拆解成几行数据条并整齐排队，一条数据条高亮后化作箭头指向右侧一张"已整理"卡片；蓝白配色、青色高光、节奏轻盈匀速、无缝循环，无文字 | 3D micro-animation on transparent background: a translucent inquiry document slides in from the left, is automatically broken into data rows that line up neatly, one row highlights and turns into an arrow pointing to a tidy "organized" card on the right; blue-white palette, cyan highlights, light even pacing, seamless loop, no text |
| V2 单证预审 | 两张叠放单据缓慢对齐，一处字段闪红色提示后自动修正为青色对勾，最后叠成一摞；蓝白配色、克制专业、无缝循环 | two stacked documents slowly align, one field flashes red then self-corrects into a cyan check mark, finally stacking into a neat pile; blue-white palette, restrained and professional, seamless loop |
| V3 方案要点 | 一个 3D 卡车小模型沿路线从 A 点滑到 B 点，途中浮出三枚要点卡片（车型/限高/吊装）依次点亮；蓝白配色、匀速、无缝循环 | a small 3D truck model glides along a route from A to B, three key-point cards (vehicle type / height limit / lifting) light up in sequence along the way; blue-white palette, even pacing, seamless loop |
| V4 双语沟通 | 一张中文单据与一张越南文单据左右浮现，中间一条青色光带把两者对齐，末尾各自出现对勾；蓝白配色、安静、无缝循环 | a Chinese document and a Vietnamese document appear left and right, a cyan light band aligns the pair, both end with check marks; blue-white palette, calm, seamless loop |

### A1–A5 应用场景动效（1200×750，浅底不透明）

| 编号 | 中文提示词 | 英文提示词 |
|---|---|---|
| A1 智能询价 | 浅蓝白渐变的干净产品动效场景：几条杂乱的信息（消息气泡、表格、图片缩略）从四周飘入，被中间一道柔和的蓝色光柱收拢，输出成一张整齐排布的信息卡片；无文字，仅示意图形，匀速无缝循环 | clean product animation on a light blue-white gradient: scattered inputs (chat bubbles, a table, an image thumbnail) drift in and are gathered by a soft blue light column in the middle, output as one neatly arranged card; no text, abstract shapes only, even pacing, seamless loop |
| A2 报关单证 | 两份单证并排悬浮，一条青色扫描线自上而下扫过，被扫到的字段依次亮起，末尾一列小对勾全部点亮；浅底，克制专业 | two documents float side by side, a cyan scan line sweeps top to bottom, fields light up as they are scanned, ending with a column of small check marks all lit; light background, restrained and professional |
| A3 装载与车型 | 俯视视角：一件超大型设备（变压器）被缓慢放进平板车轮廓中，四周的尺寸标注线依次出现，装好后车体轻微下沉示意承载；浅底蓝白 | top-down view: an oversized transformer is slowly loaded onto a flatbed trailer outline, dimension lines appear one by one, the trailer settles slightly to suggest load; light blue-white background |
| A4 在途与节点 | 一条中越跨境路线从中国侧缓慢延伸到越南侧，沿途依次亮起节点圆点，其中一个节点亮成橙色提示，随后被修正为青色对勾（注意：**不做 GPS 实时定位效果**，只用抽象节点） | a cross-border route slowly extends from China to Vietnam, milestone dots light up along the way, one turns orange as a flag then corrects to a cyan check (abstract milestones only, no live GPS/map tracking look) |
| A5 流程自动化 | 一排重复的小方块动作自动循环（复制→粘贴→归档），中间一只半透明机械手把它接过来，人工图标转为"审核"图标；浅底蓝白，机械感但不冷 | a row of repetitive small-square actions loops automatically (copy → paste → archive), a translucent robotic hand takes over, the human icon shifts to a "review" icon; light blue-white background, mechanical yet warm |

### B1 AI 底座插图（800×800 透明底）

> 中文：3D 微立体的"物流大脑"图形：一个由蓝色至青色渐变的半透明球状核心，表面浮现细密的路线网络与集装箱、卡车、口岸线条符号，向下延伸出三条接入线连接三个小立方体；浅色明亮、干净、留白多、无文字、透明背景、单主体居中。
> English: 3D semi-transparent sphere core in blue-to-cyan gradient, its surface showing a fine route network with container, truck and border-gate symbols, three connector lines branching down to three small cubes; bright, clean, lots of negative space, no text, transparent background, single centered subject.

### C1 Hero 背景微动效（1920×1080）

> 中文：极简抽象背景动效：深蓝到白的柔和光晕在画面上部缓慢呼吸位移，细密的网格线与数据点极轻地流动，整体明亮通透、低对比度；**画面中下部的亮度不要压暗**（那里要放深色文字），10–14 秒无缝循环，无文字。
> English: minimal abstract background loop: a soft deep-blue-to-white glow slowly breathes and drifts across the upper area, a fine grid and data dots move very subtly, overall bright and airy, low contrast, keep the lower-middle area bright (dark text sits there), 10–14s seamless loop, no text.

### C2 CTA 背景微动效（1920×600）

> 中文：深蓝底（#001030 → #0040C0）上极缓慢流动的青蓝色光带与微粒，像夜间跨境干线的流光；低亮度、慢速、不干扰白色文字，8–12 秒无缝循环。
> English: on a deep navy (#001030 → #0040C0) ground, very slow cyan-blue light bands and particles drift like traffic light trails on a night cross-border corridor; low brightness, slow motion, must not fight white text, 8–12s seamless loop.

### L1 合作方 logo（授权后才用）

> 不需要提示词——找我方合作方要**官方 VI 源文件**（AI/EPS 优先），我转成 80px 高透明 PNG。**没有书面授权就不上**。

---

## 3. 我这边接上后的处理（你不用管，列出来是让你知道为什么要这些规格）

1. 头像走 `<img>` + `loading="lazy" decoding="async"`；Hero 胶囊内的用 `loading="eager"`。
2. 动效用 `<video autoplay muted loop playsinline preload="metadata">`，**PNG 首帧做 poster**；`prefers-reduced-motion: reduce` 时直接停播只显示首帧 PNG（本项目已有该偏好的硬要求，不能让动效藏内容）。
3. 体积超限先用 `ffmpeg` 压一遍：`-vcodec libx264 -crf 28 -preset slow -an -movflags +faststart`；透明底用 `libvpx-vp9 -pix_fmt yuva420p` 出 WebM 更小。
4. 接完跑 `npm run lint && npm run build` + `python scripts/verify-agent-page.py`（六档视口无横向溢出、内容不隐身、交互链路通过）+ 全页亮度扫描。

## 4. 生成工具建议

| 要什么 | 推荐 | 备注 |
|---|---|---|
| R1–R5 头像 | 即梦 / Midjourney / GPT-Image，再抠透明底 | 5 张要同风格：固定同一段风格锚，只换岗位描述 |
| V1–V4 透明底动效 | 可灵（支持透明背景）/ 即梦视频 | 出不了透明底就出亮底，我做抠像 |
| A1–A5 场景动效 | 可灵 / Vidu / 海螺 | 浅底不透明即可，别做暗色 |
| C1/C2 背景动效 | 可灵 / Runway / Sora，或直接用 After Effects 模板 | 强调"低对比度、慢速、无缝循环" |
| L1 logo | 我方合作方的官方 VI 源文件 | 需书面授权 |

**优先级**：先把 R1–R5 + V1–V4 做出来发我（P0，直接决定页面从"文字版"变成"有画面的产品页"）；P1/P2 可以下一批。

---

## 5. 素材到位后怎么用（已接好线，2026-09）

页面已经写好素材槽，**素材一到就自动切换版式**，不需要改代码：

```bash
# 1) 把文件按上面命名丢进 public/assets/agent/（P0 就是 9 个文件 + 4 张同名 PNG 首帧）
# 2) 扫清单
npm run assets:scan        # 扫描目录 → 生成 src/agent/assets.manifest.json
# 3) 构建
npm run build
# 4) 复验（六档视口 + 交互 + 全页亮度）
npm run verify:agent
```

机制说明（为什么这么设计）：

- 页面**不写死图片路径**，而是读 `src/agent/assets.manifest.json`（构建时打进包）。
  素材没到位时**不会 404、不会出现破图、不会留空框**，版式自动维持现在的纯文字形态。
- 动效一律 `<video autoplay muted loop playsinline poster="同名PNG">`；
  用户开启「减少动效」时**直接不渲染 video，只用 PNG 首帧**（已实测：reduce 模式下 video 元素数 = 0，图片版兜底 4/4）。
- 角色头像：素材到位后 Hero 胶囊、输入框头像、数字员工卡片（放大到 88px）全部自动换成图片；
  Hero 输入框里的头像跟随当前选中的角色切换。
- 服务卡：有动效 → 变成「左动效 + 右文案」；没动效 → 维持现在的「文案 + 要点」两栏。
- 场景区：动效出现在流程列表上方；AI 底座：插图出现在小标题下方。
- 体积超限时 `assets:scan` 会直接报警并给出压缩命令，不会静默放行。

扫描脚本还会做一致性检查：有 `.mp4` 但没有同名 `.png` 首帧时会提醒补图（弱网/减少动效下没有首帧会闪黑框）。

