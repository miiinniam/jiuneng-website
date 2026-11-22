/**
 * v7 营销页文案。
 * 已审文案逐字取自旧站 src/main.tsx 的 translations.zh（不重写、不润色）；
 * 新增内容只用可核对的业务事实（口岸数、车型、费用口径），不写形容词。
 */

export const hero = {
  eyebrow: '工程物流 · 进出口报关 · 国际贸易',
  titleLines: ['面向中国企业的', '工程物流平台'],
  lead: '玖能国际聚焦工程物流、进出口报关与国际贸易，以数字化系统管理客户询价、方案设计、报价、业务实施和项目交付，连接中越两地资源，为复杂工程项目提供可靠支持。',
  primary: '在线询价',
  secondary: '看项目',
  stats: [
    { value: 'CN-VN', label: '中越资源协同' },
    { value: '3', label: '工程物流 · 报关 · 贸易' },
    { value: '轨交·风电·电力', label: '工程解决方案' },
    { value: '2024', label: '越南公司登记' },
  ],
  photo: {
    src: '/assets/v8/hero-blade-convoy.jpg',
    alt: '风电叶片在山路运输，现场护送与道路保障',
    caption: '风电叶片山路运输 · 现场护送',
  },
};

/** 项目照片库：34 张素材按画面类型分 7 类（v9）。
 *  规则：一张素材只归一类；带 CC 授权的必须在 credit 里署名；
 *  地点不得张冠李戴（欧洲地铁施工照必须写明非越南项目）。 */
export type PhotoItem = {
  src: string;
  alt: string;
  caption: string;
  credit?: string;
  /** 暗图：只进缩略图格，不做满幅/主图 */
  dark?: boolean;
};

export type PhotoCat = {
  id: string;
  n: string;
  sector: string;
  name: string;
  lead: string;
  body: string;
  lines: string[];
  note: string;
  main: PhotoItem;
  thumbs: PhotoItem[];
};

export const photoCats: PhotoCat[] = [
  {
    id: 'cat-blade',
    n: '01',
    sector: '新能源 · 风电',
    name: '风电叶片运输',
    lead: '叶片装车、山路运输与现场护送。',
    body: '风机叶片长度通常在 60–80 米，运输受转弯半径、坡度与净空限制。叶片车组按叶片型号配举升梁与回转鞍座，路线需提前勘察，必要时局部拓宽或移线。',
    lines: ['叶片车组 · 举升梁与回转鞍座', '道路勘察与临时拓宽', '护送与临时交通管制', '堆场装车与绑扎加固'],
    note: '自有项目实拍',
    main: {
      src: '/assets/v9/cat-blade/main.jpg',
      alt: '红色牵引车在山路转弯处拉运风机叶片，边坡与轮胎痕迹可见',
      caption: '叶片山路运输 · 转弯段',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-blade/t-01.jpg',
        alt: '堆场里成组风机叶片已装上红色叶片车',
        caption: '堆场装车 · 成组叶片',
      },
      {
        src: '/assets/v9/cat-blade/t-02.jpg',
        alt: '傍晚时分巨型叶片根部与红色多轴车特写',
        caption: '叶片根部特写 · 傍晚',
        dark: true,
      },
      {
        src: '/assets/v9/cat-blade/t-03.jpg',
        alt: '日间拍摄的风机叶片根部与红色挂车',
        caption: '叶片根部特写 · 日间',
      },
      {
        src: '/assets/v9/cat-blade/t-04.jpg',
        alt: '山谷远景中正在通行的叶片运输车队',
        caption: '车队穿过山谷',
      },
      {
        src: '/assets/v9/cat-blade/t-05.jpg',
        alt: '山路上的叶片运输车队，叶片悬在车尾上方',
        caption: '山路车队 · 叶片后悬',
      },
      {
        src: '/assets/v9/cat-blade/t-06.jpg',
        alt: '山路装载机开道，叶片车在后跟进（竖构图）',
        caption: '山路装载机开道',
      },
      {
        src: '/assets/v9/cat-blade/t-07.jpg',
        alt: '项目团队穿反光背心站在风机叶片与红色运输车前',
        caption: '项目团队与叶片',
      },
    ],
  },
  {
    id: 'cat-lift',
    n: '02',
    sector: '新能源 · 吊装',
    name: '风机部件吊装',
    lead: '叶片根部对接、双吊抬吊与机舱上车。',
    body: '叶片根部、机舱等部件到场后由汽车吊配合装车与就位。吊点、绑扎方式与场地承载力由现场吊装方案确定，双吊抬吊需统一指挥信号。',
    lines: ['叶片根部对接与就位', '机舱吊装上车', '双吊抬吊作业', '现场吊装协调'],
    note: '自有项目实拍',
    main: {
      src: '/assets/v9/cat-lift/main.jpg',
      alt: '作业人员在风机叶片根部与轮毂连接处攀爬作业，汽车吊吊索在上方',
      caption: '叶片与轮毂对接 · 现场吊装',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-lift/t-01.jpg',
        alt: '两台汽车吊抬吊装在运输框架内的风机叶片根部',
        caption: '叶片根部双吊抬吊',
      },
      {
        src: '/assets/v9/cat-lift/t-02.jpg',
        alt: '风力发电机机舱被吊装到红色多轴低平板上',
        caption: '机舱吊装上车',
      },
    ],
  },
  {
    id: 'cat-transformer',
    n: '03',
    sector: '电力工程',
    name: '变压器与港口吊装',
    lead: '船舱绑扎、港口吊装上车与夜间浮吊装船。',
    body: '变压器的自重与外形决定吊装与绑扎方案：船舱内绑扎加固、港口吊装上轴线车、夜间浮吊装船，均由吊装方案与船舶积载图控制，全程按单件最大尺寸核查超限。',
    lines: ['船舱绑扎与加固', '港口吊装上车', '夜间浮吊装船', '超重件车型与轴线匹配'],
    note: '自有项目实拍（含视频抽帧）',
    main: {
      src: '/assets/v9/cat-transformer/main.jpg',
      alt: '船舱内变压器四周绑扎加固，作业人员在舱内操作',
      caption: '船舱内变压器绑扎加固',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-transformer/t-01.jpg',
        alt: '港口汽车吊把变压器吊装到红色轴线车上，工人穿反光背心在旁',
        caption: '港口汽车吊吊装上车',
      },
      {
        src: '/assets/v9/cat-transformer/t-02.jpg',
        alt: '变压器已落在红色多轴低平板上，蓝色牵引车在前',
        caption: '装车完成 · 多轴低平板',
      },
      {
        src: '/assets/v9/cat-transformer/t-03.jpg',
        alt: '夜间浮吊把白色变压器吊装上船',
        caption: '夜间浮吊装船',
        dark: true,
      },
    ],
  },
  {
    id: 'cat-machine',
    n: '04',
    sector: '基建 · 工程机械',
    name: '工程机械与重卡',
    lead: '旋挖钻机、履带设备与挖掘机的整机装载。',
    body: '旋挖钻机、履带设备与挖掘机按整机上车，爬梯角度、整机重心与履带固定决定装载是否安全；越南境内干线转运由本地车队执行，超限设备单独报批。',
    lines: ['整机装载与履带固定', '低平板 / 多轴挂车', '越南境内干线转运', '超限设备单独报批'],
    note: '自有项目实拍',
    main: {
      src: '/assets/v9/cat-machine/main.jpg',
      alt: '越南 QL1 国道上两台低平板载着绿色履带钻机行驶',
      caption: '越南 QL1 国道 · 履带钻机转运',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-machine/t-01.jpg',
        alt: '夜间红色低平板载绿色旋挖钻机行驶',
        caption: '夜间转运 · 旋挖钻机',
        dark: true,
      },
      {
        src: '/assets/v9/cat-machine/t-02.jpg',
        alt: '蓝色多轴低平板载 SG70 旋挖钻机停放',
        caption: '多轴低平板载旋挖钻机',
      },
      {
        src: '/assets/v9/cat-machine/t-03.jpg',
        alt: '绿色低平板载挖掘机在山路行驶',
        caption: '挖掘机整机上车',
      },
      {
        src: '/assets/v9/cat-machine/t-04.jpg',
        alt: '工程堆场里停放的自卸车与机械设备',
        caption: '工程堆场 · 自卸车与设备',
      },
      {
        src: '/assets/v9/cat-machine/t-05.jpg',
        alt: '堆场停放的红色低平板与大件货物',
        caption: '堆场待运大件',
      },
      {
        src: '/assets/v9/cat-machine/t-06.jpg',
        alt: '蓝色牵引车与多轴挂车把大型模块送到河边，驳船靠岸待装',
        caption: '大型模块河运转驳',
      },
    ],
  },
  {
    id: 'cat-lowbed',
    n: '05',
    sector: '车辆资源',
    name: '多轴低平板 / 轴线车',
    lead: '按单件尺寸与重量匹配轴数与纵列。',
    body: '按单件尺寸与重量匹配轴数与纵列：轴线车用于超重超长件，多轴低平板用于常规大件。空载与载货状态都按项目现场条件核查通过性。',
    lines: ['多轴低平板（3–10 轴）', '轴线车纵列组合', '超限件绑扎与支撑', '场地承载力核查'],
    note: '玖一自有车辆',
    main: {
      src: '/assets/v9/cat-lowbed/main.jpg',
      alt: '红色多轴低平板载一台大型变压器停在厂房前场地',
      caption: '多轴低平板载变压器 · 越南场地',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-lowbed/t-01.jpg',
        alt: '红色多轴低平板空载停在厂房前',
        caption: '多轴低平板 · 空载',
      },
      {
        src: '/assets/v9/cat-lowbed/t-02.jpg',
        alt: '红色多轴低平板空载，侧后 3/4 视角',
        caption: '多轴低平板 · 侧后视角',
      },
      {
        src: '/assets/v9/cat-lowbed/t-03.jpg',
        alt: '红色轴线车车轴与轮胎特写',
        caption: '轴线车车轴特写',
      },
      {
        src: '/assets/v9/cat-lowbed/t-04.jpg',
        alt: '红色低平板载蓝色篷布包裹的大件，车辆停在场地内',
        caption: '载篷布大件 · 场地',
      },
    ],
  },
  {
    id: 'cat-rail',
    n: '06',
    sector: '轨道交通',
    name: '轨道交通工程',
    lead: '盾构与车站施工的物资、设备配送。',
    body: '轨道项目的物资与施工设备按节点配送：盾构机及后配套、钢轨与轨枕、车站设备与材料。超大件另走专项运输方案，到场时间与吊装窗口对齐施工节点。',
    lines: ['盾构机与后配套运输', '钢轨 / 轨枕 / 道砟', '车站设备与材料配送', '项目节点配送'],
    note: '越南在建项目与同类场景资料图',
    main: {
      src: '/assets/v9/cat-rail/main.jpg',
      alt: '河内地铁车站工地俯瞰：深基坑开挖、挖掘机作业与预制桥梁构件',
      caption: '河内地铁车站基坑开挖 · 资料图',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-rail/t-01.jpg',
        alt: '河内 Nhổn–河内站线在建高架：沿城市道路的桥墩与箱梁',
        caption: '河内 Nhổn–河内站线在建高架 · 资料图',
        credit: '图：Tycho / Wikimedia Commons, CC BY-SA 3.0',
      },
      {
        src: '/assets/v9/cat-rail/t-02.jpg',
        alt: '胡志明市地铁滨城站施工：车站主体基坑与多台塔吊',
        caption: '胡志明市滨城站施工 · 资料图',
        credit: '图：Ymblanter / Wikimedia Commons, CC BY-SA 4.0',
      },
      {
        src: '/assets/v9/cat-rail/t-03.jpg',
        alt: '隧道内盾构机刀盘与主机内部细节，可见施工人员',
        caption: '盾构机内部 · 马德里地铁（非越南项目，资料图）',
        credit: '图：Monotensión / Wikimedia Commons, CC BY-SA 4.0',
        dark: true,
      },
      {
        src: '/assets/v9/cat-rail/t-04.jpg',
        alt: '地铁竖井内的盾构机始发作业',
        caption: '盾构始发井 · 哥本哈根（非越南项目，资料图）',
        credit: '图：Leif Jørgensen / Wikimedia Commons, CC BY-SA 4.0',
      },
    ],
  },
  {
    id: 'cat-port',
    n: '07',
    sector: '国际贸易',
    name: '港口与船舶',
    lead: '海运段与港口作业的衔接。',
    body: '海运段与港口作业是跨境交付的衔接点：集装箱船靠泊、码头吊机作业与堆场周转，按船期组织集港与提货，陆运与船期在同一张节点表上排。',
    lines: ['集装箱海运', '港口吊装与堆场周转', '船期与集港衔接'],
    note: '玖一素材',
    main: {
      src: '/assets/v9/cat-port/main.jpg',
      alt: '满载集装箱的货轮在海上航行',
      caption: '集装箱船 · 海运段',
    },
    thumbs: [
      {
        src: '/assets/v9/cat-port/t-01.jpg',
        alt: '码头吊机在集装箱船旁作业',
        caption: '码头吊机作业',
      },
    ],
  },
];

/** 作业实录：三段现场视频，poster 首帧 + 点击才加载（preload=none），不自动下载。 */
export const videoStrip = {
  eyebrow: '作业实录',
  title: '三段现场视频',
  note: '点击播放，页面不自动加载视频文件。',
  items: [
    {
      src: '/assets/v9/video/loading-drill-rig.mp4',
      poster: '/assets/v9/video/loading-drill-rig.jpg',
      caption: '旋挖钻机上多轴低平板 · 越南场地',
      duration: '0:16',
    },
    {
      src: '/assets/v9/video/port-crane-day.mp4',
      poster: '/assets/v9/video/port-crane-day.jpg',
      caption: '汽车吊把变压器吊装到红色轴线车 · 港口',
      duration: '0:10',
    },
    {
      src: '/assets/v9/video/floating-crane-night.mp4',
      poster: '/assets/v9/video/floating-crane-night.jpg',
      caption: '夜间浮吊把变压器吊装装船',
      duration: '0:09',
    },
  ],
};

/** 句点段：一句话说清"我们怎么做事"。不写形容词，不写无法核对的承诺。 */
export const tagline = {
  label: '我们怎么做事',
  // 每行单独成块（≤18 字，按 19em 上限实测），否则大字会在行内折行、断在意想不到的地方
  lines: [
    ['从中国起运地到越南工地，'],
    ['方案、单证、车辆与节点，'],
    ['写在同一张表上。'],
  ],
  note: '询价、方案、报价、实施、交付在同一套系统里留痕，客户可随时核对到哪一步。',
};

/** 项目页页头（v9）：分类浏览代替按客户罗列。 */
export const categoryPage = {
  kicker: '代表项目',
  title: '按货物类型，查看作业现场',
  lead: '7 类工程物流项目的现场记录：叶片运输与吊装、工程机械转运、变压器港口吊装、多轴低平板、轨道施工场景。',
  note: '玖能与玖一自有项目实拍为主；标注「资料图」的为同类场景资料，作者与许可见图注。具体客户名称与数据在取得授权后公开。',
};

export const tools = [
  {
    n: '01',
    title: '线路测算',
    body: '按起运地、口岸与目的地组合，给出干线里程、行车时长、车辆数量与参考运价区间。',
    href: '/platform/routing',
  },
  {
    n: '02',
    title: '报关与税费',
    body: '给出中国端与越南端费用区间，按车辆数、柜量、滞留天数与吊装吨位调整。',
    href: '/platform/customs',
  },
  {
    n: '03',
    title: '车辆匹配',
    body: '按单件尺寸、重量与是否可叠放匹配车型，超长、超宽、超重单独标注。',
    href: '/platform/fleet',
  },
];

export const services = {
  eyebrow: '核心业务',
  title: '三类核心业务，覆盖工程项目跨境需求',
  intro:
    '围绕中国企业在越南开展工程与贸易的真实需求，玖能将工程物流、进出口报关和国际贸易结合起来。',
  items: [
    {
      n: '01',
      title: '工程物流',
      body: '面向轨道交通、基建、电力及新能源项目，提供工程物资与大型设备运输方案、特种车辆支持、项目节点管理和现场交付协调。',
      points: ['大型设备与超限货物运输', '项目节点管理', '现场交付协调'],
      fit: '轨道交通、基建、电力及新能源项目的工程物资与大型设备',
      boundary: '按货物尺寸、重量与现场条件匹配车辆与装卸资源；路线通行条件在报价前核查。',
    },
    {
      n: '02',
      title: '进出口报关',
      body: '依托中国侧公司和越南本地合作代理，为中越贸易业务提供单证、报关和跨境衔接支持。',
      points: ['单证准备与预审', '报关协调', '跨境流程衔接'],
      fit: '中越贸易项下的工程物资、铁路物资与工程设备',
      boundary: '单证与报关由中越两侧协同办理，越南侧由本地合作代理网络执行。',
    },
    {
      n: '03',
      title: '国际贸易',
      body: '围绕中越工程项目，开展工程物资、铁路物资、基建物资、工程设备、新能源设备和电力设备相关业务。',
      points: ['工程与铁路物资', '工程与电力设备', '新能源设备'],
      fit: '工程物资、铁路物资、基建物资、工程设备、新能源设备与电力设备',
      boundary: '按合同与项目节点安排供货与运输衔接，交货条件在合同中约定。',
    },
  ],
  compliance: '越南侧由本地合作代理网络执行，不设自营仓储或越南全境直营网点',
};

export const platform = {
  eyebrow: '工程物流平台系统',
  title: '用系统管理工程物流全过程',
  intro:
    '从客户询价到项目归档，每一个关键步骤都清晰可追踪。平台不只协调车辆，而是管理工程物流项目的全过程。',
  steps: [
    '客户询价',
    '需求收集',
    '工程条件分析',
    '物流方案设计',
    '运输资源匹配',
    '报价与审批',
    '合同与单证',
    '业务实施',
    '节点追踪',
    '异常处理',
    '项目交付',
    '结算与归档',
  ],
  modules: [
    { title: '客户与询价', body: '统一记录客户信息、货物参数和项目需求。' },
    { title: '方案与报价', body: '管理运输方案、报价版本和审批记录。' },
    { title: '项目执行', body: '关联车辆、供应商、报关资料和实施计划。' },
    { title: '节点追踪', body: '跟踪运输状态、关键节点和异常处理。' },
    { title: '项目归档', body: '沉淀合同、单证、结算和案例资料。' },
  ],
  products: [
    {
      n: '01',
      title: '线路与运价测算',
      question: '从中国起运地到越南目的地，大概多少公里、多久、多少车、什么价？',
      caps: [
        '按城市与口岸组合给出干线里程与行车时长',
        '按货重与车型给出所需车辆数量',
        '给出参考运价区间与测算口径',
        '覆盖中国 9 个起运地、3 个陆路口岸、越南 5 个目的地',
      ],
      href: '/platform/routing',
    },
    {
      n: '02',
      title: '报关与税费',
      question: '中国端与越南端各要花多少，哪些费用会随柜量、滞留与吊装变化？',
      caps: [
        '中国端费用以人民币区间给出',
        '越南端费用以越南盾区间给出',
        '按车辆数、柜量、滞留天数与吊装吨位调整',
        '分项明细需提交项目信息后由项目经理确认',
      ],
      href: '/platform/customs',
    },
    {
      n: '03',
      title: '车辆匹配与超限',
      question: '这批货要用什么车，会不会超限？',
      caps: [
        '按单件尺寸、重量与是否可叠放匹配车型',
        '平板、低平板与厢式车按场景区分',
        '超长、超宽、超重单独标注',
        '超限判定按单件最大尺寸，不看总量',
      ],
      href: '/platform/fleet',
    },
    {
      n: '04',
      title: '测算助手',
      question: '需求还没理清，怎么把要点说清楚？',
      caps: [
        '用对话整理货物、线路、单证与现场条件',
        '把要点整理成可交给项目经理的清单',
        '查不到的条件直接说明，不猜',
        '不替代正式报价与时效确认',
      ],
      href: '/platform/assistant',
    },
  ],
  note: '以上工具给出的是初步测算，不构成正式报价或时效承诺。正式方案由项目经理复核后确认。',
};

export const solutions = {
  eyebrow: '解决方案',
  title: '围绕工程项目，提供可落地的运输方案',
  intro:
    '根据货物尺寸、重量、路线条件、装卸要求和施工节点，组织专业运输方案与现场交付协调。',
  items: [
    {
      sector: '轨道交通',
      title: '铁路物资与施工设备',
      body: '面向城市轨道交通项目，组织铁路物资、施工设备运输与项目节点配送。',
      fit: '轨道车辆部件 / 施工机械 / 轨道材料',
    },
    {
      sector: '基建项目',
      title: '工程设备与材料',
      body: '面向道路、桥梁等基建项目，衔接工程设备、材料的跨境运输与现场吊装交付。',
      fit: '工程机械 / 钢结构 / 预制构件',
    },
    {
      sector: '电力项目',
      title: '电力设备运输',
      body: '面向火力发电及配套工程，组织变压器等大型电力设备运输与现场协调。',
      fit: '变压器 / 配电设备 / 电缆盘',
    },
    {
      sector: '新能源',
      title: '风电叶片与塔筒',
      body: '面向风力发电项目，使用专业车辆运输风机叶片、塔筒及大型设备。',
      fit: '风机叶片 / 塔筒 / 机舱',
    },
  ],
  photo: {
    src: '/assets/v8/services-transformer.jpg',
    alt: '变压器在港口吊装到红色多轴车上',
    caption: '电力工程 · 大型设备运输',
  },
};

export const vehicles = {
  eyebrow: '设备资源',
  title: '专业设备资源，应对复杂运输场景',
  intro:
    '针对新能源与大型工程设备运输需求，玖能配备专业车辆，并根据项目路线、设备尺寸和现场条件匹配运输资源。',
  items: [
    {
      title: '风机运输特种车',
      body: '用于风机设备与大型部件的工程运输与吊装配合。',
      spec: '适用：机舱 / 塔筒 / 大件部件',
      image: '/assets/v8/fleet-nacelle.jpg',
      alt: '风力发电机机舱被吊装到红色多轴低平板上，红色折臂吊配合',
    },
    {
      title: '叶片运输车组',
      body: '应对复杂道路条件下的风机叶片运输。',
      spec: '适用：叶片 / 复杂路况',
      image: '/assets/v8/fleet-blade.jpg',
      alt: '堆场中装载成组风机叶片的红色叶片车',
    },
    {
      title: '多轴低平板 / 轴线车',
      body: '按设备尺寸与重量匹配多轴低平板与轴线车。',
      spec: '按项目匹配',
      image: '/assets/v8/fleet-lowbed.jpg',
      alt: '红色多轴低平板空载停放',
    },
  ],
};

export const cases = {
  eyebrow: '代表项目',
  title: '用执行能力支撑复杂工程',
  intro: '以下为玖能参与的代表性工程物流项目类型，展示复杂跨境工程的执行能力。',
  note: '项目以类型与服务范围描述。具体客户名称、照片与数据将在取得授权与核验后公开。',
  items: [
    {
      n: '01',
      title: '河内地铁 1 号线',
      type: '城市轨道交通工程物流',
      body: '参与城市轨道交通项目工程物流，协调跨境运输与项目节点。',
      oneLine: '协调跨境运输与项目节点。',
      tags: ['轨道交通', '跨境衔接'],
      scope: ['铁路物资与施工设备运输', '跨境运输衔接', '项目节点配送'],
      image: '/assets/v8/project-hanoi.jpg',
      alt: '河内城市轨道交通高架桥墩与箱梁在建',
      caption: '河内城市轨道高架在建 · 资料图',
      credit: '图：Tycho / Wikimedia Commons, CC BY-SA 3.0',
    },
    {
      n: '02',
      title: '胡志明二号线',
      type: '城市轨道交通工程物流',
      body: '参与城市轨道交通项目工程物流，组织铁路与施工设备运输衔接。',
      oneLine: '组织铁路与施工设备运输衔接。',
      tags: ['轨道交通', '工程物流'],
      scope: ['铁路物资运输', '施工设备运输', '现场交付协调'],
      image: '/assets/v8/project-hcmc.jpg',
      alt: '胡志明市地铁车站在建基坑与塔吊',
      caption: '胡志明市地铁站施工 · 资料图',
      credit: '图：Ymblanter / Wikimedia Commons, CC BY-SA 4.0',
    },
    {
      n: '03',
      title: '越南风力发电项目',
      type: '新能源工程物流',
      body: '参与多个越南风力发电项目，使用专业车辆运输风机叶片、塔筒等大型设备。',
      oneLine: '使用专业车辆运输风机叶片、塔筒等大型设备。',
      tags: ['新能源', '大件运输'],
      scope: ['风机叶片运输', '塔筒运输', '现场交付协调'],
      image: '/assets/v8/project-wind.jpg',
      alt: '风机叶片在多轴低平板上装车待运',
      caption: '风机叶片运输',
    },
  ],
  types: [
    { name: '轨道交通', body: '城市轨道交通项目的铁路物资、施工设备与节点配送。' },
    { name: '风力发电', body: '风机叶片、塔筒、机舱等大件设备运输。' },
    { name: '电力工程', body: '变压器等大型电力设备运输与现场协调。' },
    { name: '基础设施', body: '道路、桥梁项目的工程设备与材料跨境运输。' },
    { name: '国际贸易', body: '工程物资、铁路物资与设备的中越贸易业务。' },
  ],
};

export const about = {
  eyebrow: '关于玖能',
  title: '用工程物流平台，连接中越资源',
  body: [
    'JIUNENG logistics（玖能国际）是面向中国企业的工程物流平台，致力于为中国企业在越南开展工程项目和跨境贸易提供专业支持。',
    '平台重点发展工程物流、进出口报关和国际贸易三类业务，以物流系统管理客户询价、需求分析、方案设计、报价审批、业务实施、节点追踪和项目交付。依托广西玖一进出口贸易有限公司、越南本地合作代理网络以及专业车辆资源，帮助客户减少跨境协作中的沟通成本，提高复杂工程项目的执行效率。',
  ],
  mission: { label: '使命', text: '以数字化工程物流连接中越资源，让复杂项目执行更高效、更可靠。' },
  vision: { label: '愿景', text: '打造专业的工程物流平台，成为中国企业开展中越项目时值得信赖的合作伙伴。' },
  valuesTitle: '核心价值观',
  values: [
    { name: '可靠', body: '对服务边界、项目进度和客户需求保持清晰负责。' },
    { name: '专业', body: '理解工程物流、报关和贸易业务中的关键环节。' },
    { name: '协同', body: '连接中国与越南资源，减少跨境沟通成本。' },
    { name: '务实', body: '以可执行的方案解决真实问题。' },
  ],
  network: {
    eyebrow: '中越协同网络',
    title: '连接中国与越南，形成工程项目协同网络',
    intro:
      '玖能以中国侧业务支持公司和越南本地合作代理网络组织资源，为中越工程项目提供协同支持。',
    china: {
      flag: '中国侧',
      name: '广西玖一进出口贸易有限公司',
      body: '提供进出口贸易与报关支持，衔接中国起运地资源。',
      points: ['进出口贸易支持', '报关协调', '中国起运地资源衔接'],
    },
    vietnam: {
      flag: '越南侧',
      name: '玖能国际有限责任公司',
      body: '通过越南本地合作代理网络完成业务衔接、项目实施与资源协调。',
      points: ['本地合作代理网络', '项目实施与现场协调', '河内办公主体'],
    },
    note: '玖能通过本地合作代理提供越南侧服务支持，不设自营仓储或越南全境直营网点。',
    photos: [
      {
        src: '/assets/v8/trade-port.jpg',
        alt: '满载集装箱的货轮在海上航行',
        caption: '海运段 · 集装箱船',
      },
      {
        src: '/assets/v8/trade-rail.jpg',
        alt: '河内地铁车站工地俯瞰：深基坑开挖与预制桥梁构件',
        caption: '河内地铁车站工程 · 资料图',
      },
    ] as PhotoItem[],
  },
  teamPhoto: {
    src: '/assets/v8/about-team.jpg',
    alt: '项目团队与风机叶片、运输车',
    caption: '项目团队与叶片、运输车',
  },
  registry: {
    eyebrow: '企业登记',
    title: '正式企业信息',
    intro: '玖能以越南登记主体和中国侧业务支持公司组成，以下为可公开的企业信息。',
    groups: [
      {
        label: '越南主体 · 玖能国际有限责任公司',
        rows: [
          { k: '越文名称', v: 'CÔNG TY TNHH QUỐC TẾ JIUNENG' },
          { k: '英文名称', v: 'JIUNENG INTERNATIONAL COMPANY LIMITED' },
          { k: '企业代码', v: '0202235124' },
          { k: '登记日期', v: '2024 年 3 月 20 日' },
          { k: '地址', v: '越南河内市纸桥坊 Duy Tân 街 82 号 5 楼 R03 室' },
        ],
      },
      {
        label: '中国侧 · 广西玖一进出口贸易有限公司',
        rows: [
          { k: '公司名称', v: '广西玖一进出口贸易有限公司' },
          { k: '纳税人识别号', v: '91451481595108415C' },
          { k: '定位', v: '中国侧业务支持公司' },
          { k: '能力', v: '进出口贸易与报关支持' },
        ],
      },
    ],
  },
  photo: {
    src: '/assets/v8/about-wide.jpg',
    alt: '越南 QL1 国道上两台低平板载着履带钻机行驶',
    caption: '越南 QL1 国道 · 干线转运',
  } as PhotoItem,
};

export const labels = {
  open: '打开',
  detail: '看详情',
  allServices: '看业务详版',
  allProjects: '看全部项目',
  scope: '服务范围',
  fit: '适用货物',
  boundary: '交付边界',
  points: '要点',
  modules: '系统模块',
  steps: '流程',
  registry: '企业登记',
  submitBand: '提交项目需求',
  submitBandLead:
    '把货物、线路、单证与时间要求发来，项目经理会给出线路、车型与单证路径的正式方案。',
  contactBand: '联系我们',
  upcoming: '待补充',
};
