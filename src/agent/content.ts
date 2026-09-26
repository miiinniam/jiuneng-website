/**
 * 玖能 · 物流 AI 智能体 页面内容（中 / 越 / 英）
 *
 * 口径约束（与站内既有内容一致，勿改）：
 * - 越南侧能力一律表述为「通过越南本地合作代理网络」，不得宣称自营报关 / 自营仓储 / 全境直营网点。
 * - 不得承诺清关时效、运费价格、货损率、SLA 数字；不得宣称全程 GPS 追踪或 7×24 客服。
 * - AI 输出统一为「初步评估 / 初步整理」，不构成报价或时效承诺。
 * - 能力状态（已上线 / 内测中 / 建设中）必须如实标注，不得把开发中的能力写成已提供服务。
 */

export type Lang = 'zh' | 'vi' | 'en';
export type Status = 'live' | 'beta' | 'soon';

export type Role = {
  id: string;
  name: string;
  title: string;
  status: Status;
  tags: string[];
  desc: string;
  featured?: boolean;
};

export type ServiceItem = {
  title: string;
  status: Status;
  desc: string;
  points: string[];
};

export type AppTab = {
  label: string;
  title: string;
  desc: string;
  bullets: string[];
  flow: string[];
};

export type AgentContent = {
  meta: { title: string; description: string };
  nav: { label: string; href: string }[];
  common: {
    company: string;
    tagline: string;
    cta: string;
    ctaSecondary: string;
    phone: string;
    email: string;
    statusLabels: Record<Status, string>;
  };
  hero: {
    line1: string;
    line2a: string;
    line2b: string;
    line2c: string;
    sub: string;
    promptPlaceholder: string;
    promptHint: string;
    promptButton: string;
    promptNote: string;
    quick: string[];
    tabsLabel: string;
  };
  team: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    titleC: string;
    sub: string;
    roles: Role[];
    demoLink: string;
    note: string;
  };
  services: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    titleC: string;
    sub: string;
    items: ServiceItem[];
    prev: string;
    next: string;
    note: string;
  };
  apps: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    titleC: string;
    sub: string;
    tabs: AppTab[];
    note: string;
    flowLabel: string;
  };
  brain: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    titleC: string;
    sub: string;
    cards: { title: string; status: Status; desc: string }[];
    stats: { value: string; label: string }[];
  };
  cases: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    sub: string;
    items: { title: string; type: string; body: string; tags: string[] }[];
    domainsLabel: string;
    domains: string[];
    note: string;
  };
  system: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    intro: string;
    steps: string[];
    modulesTitle: string;
    modules: { title: string; body: string }[];
    shotLabel: string;
    note: string;
  };
  solutions: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    intro: string;
    items: { sector: string; title: string; body: string; slot: string }[];
  };
  fleet: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    intro: string;
    items: { title: string; body: string; spec: string; slot: string }[];
  };
  network: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    intro: string;
    china: { flag: string; name: string; body: string; points: string[] };
    vietnam: { flag: string; name: string; body: string; points: string[] };
    note: string;
  };
  qual: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    intro: string;
    entities: { tag: string; name: string; rows: { label: string; value: string }[] }[];
  };
  consult: {
    eyebrow: string;
    title: string;
    intro: string;
    steps: string[];
    fields: Record<string, string>;
    placeholders: Record<string, string>;
    types: string[];
    submit: string;
    submitting: string;
    resultTitle: string;
    fallback: string;
    disclaimer: string;
    error: string;
  };
  cta: { title: string; desc: string; primary: string; secondary: string };
  chat: {
    open: string;
    title: string;
    subtitle: string;
    placeholder: string;
    send: string;
    close: string;
    empty: string;
    suggestions: string[];
    thinking: string;
    toolLabels: Record<string, string>;
    disclaimer: string;
    error: string;
    emptyReply: string;
  };
  calc: {
    eyebrow: string;
    title: string;
    intro: string;
    fields: { origin: string; destination: string; border: string; weight: string; volume: string; mode: string; vehicle: string };
    placeholders: { weight: string; volume: string; border: string };
    modes: { consolidated: string; full_truck: string };
    submit: string;
    submitting: string;
    again: string;
    resultTitle: string;
    labels: { distance: string; driving: string; trucks: string; vehicle: string; price: string };
    priceNote: string;
    disclosureShort: string;
    profileNoteLabel: string;
    profileNoteFixed: string;
    source: string;
    offline: string;
    toForm: string;
    inquiryTag: string;
  };
  contact: {
    eyebrow: string;
    title: string;
    intro: string;
    items: { label: string; value: string; href?: string }[];
  };
  footer: {
    intro: string;
    columns: { title: string; links: { label: string; href: string }[] }[];
    legal: string;
    site: string;
  };
};

const zh: AgentContent = {
  meta: {
    title: 'JIUNENG logistics | 物流 AI 数字员工',
    description:
      '玖能国际把中越工程物流的业务经验做成 AI 数字员工：承接询价整理、单证核对、方案要点与双语沟通，配合数字化平台完成中越工程物流交付。',
  },
  nav: [
    { label: '数字员工', href: '#team' },
    { label: '智能体服务', href: '#services' },
    { label: '应用场景', href: '#apps' },
    { label: '平台系统', href: '#system' },
    { label: '解决方案', href: '#solutions' },
    { label: '项目案例', href: '#cases' },
    { label: '在线询价', href: '#consult' },
  ],
  common: {
    company: 'JIUNENG logistics',
    tagline: '物流 AI 智能体 · 中越工程物流',
    cta: '在线询价',
    ctaSecondary: '看看数字员工',
    phone: '15687419919',
    email: 'jiuneng.vn@gmail.com',
    statusLabels: { live: '已上线', beta: '内测中', soon: '建设中' },
  },
  hero: {
    line1: '订舱、报关、跟单，还在靠人一条条对？',
    line2a: '您的物流 ',
    line2b: 'AI 数字员工',
    line2c: '，来了',
    sub: '玖能把中越工程物流的业务经验沉淀成 AI 数字员工：先替团队把询价、单证、方案要点和双语沟通整理清楚，让人专注在需要判断的地方。',
    promptPlaceholder: '贴一段项目需求或货物信息，数字员工先做初步整理',
    promptHint: '例：越南河内项目，3 台变压器，单件 62 吨，凭祥口岸进，10 月装运',
    promptButton: '开始整理',
    promptNote: '初步整理用于沟通准备，不构成报价或时效承诺，正式方案由项目经理复核。',
    quick: ['我要询价', '报关单证怎么准备', '超限设备怎么运', '中越双语单证翻译'],
    tabsLabel: '选择数字员工',
  },
  team: {
    eyebrow: 'AI 数字员工',
    titleA: '玖能 ',
    titleB: 'AI 数字员工',
    titleC: ' · 一位员工，一类岗位工作',
    sub: '每位数字员工对应一类真实的岗位职责。能力按阶段开放，标注「已上线」的可立即使用。',
    roles: [
      {
        id: 'inquiry',
        name: '小玖',
        title: '询价顾问',
        status: 'live',
        tags: ['询价受理', '线路初判', '单证提示'],
        desc: '接收项目需求，整理货物参数、口岸与线路要点，输出包含单证清单、HS 归类方向与待补资料的风险提示，并同步给项目经理跟进正式方案。',
        featured: true,
      },
      {
        id: 'customs',
        name: '关务专员',
        title: '报关单证核对',
        status: 'beta',
        tags: ['资料核对', '归类方向', '合规提示'],
        desc: '按品类与口岸的常见规则核对报关资料完整性，提示归类方向与容易退单的项，输出需客户确认的差异清单。',
      },
      {
        id: 'docs',
        name: '单证专员',
        title: '单据字段校验',
        status: 'beta',
        tags: ['字段抽取', '版本比对', '差异清单'],
        desc: '从箱单、发票、提单等文件中抽取件重尺与关键字段，交叉校验后标出版本间不一致的字段，供人工复核。',
      },
      {
        id: 'dispatch',
        name: '调度专员',
        title: '车型与通行要点',
        status: 'soon',
        tags: ['车型方向', '超限要点', '节点提醒'],
        desc: '根据尺寸、重量与路线条件给出车型与通行要点建议，协助提前识别限高限重、换装与吊装等前置事项。',
      },
      {
        id: 'translate',
        name: '翻译专员',
        title: '中越双语支持',
        status: 'beta',
        tags: ['中越互译', '术语统一', '函件润色'],
        desc: '面向越南收发货人与合作方，承接单证、邮件与函件的中越互译，并维护项目术语表，保证前后表述一致。',
      },
    ],
    demoLink: '用这位数字员工试试',
    note: '「内测中 / 建设中」为开发中的能力，不构成服务承诺；正式业务口径由项目经理按合同复核后交付。',
  },
  services: {
    eyebrow: 'Agentic Services',
    titleA: '玖能 ',
    titleB: 'AI 智能体服务',
    titleC: ' · 按结果交付',
    sub: '把一段完整的岗位工作交给数字员工：从资料受理到输出可用结果，再由项目经理复核交付。',
    items: [
      {
        title: '询价受理与初步评估',
        status: 'live',
        desc: '提交项目需求，得到结构化的线路方向、单证清单、归类方向与待补资料清单。',
        points: ['线路与口岸要点', '单证清单提示', 'HS 归类方向', '待补资料清单'],
      },
      {
        title: '报关单证预审',
        status: 'beta',
        desc: '把箱单、发票、提单等资料交给数字员工，在提交前先对一遍。',
        points: ['关键字段抽取', '缺失项提示', '版本差异清单', '人工复核留痕'],
      },
      {
        title: '运输方案要点生成',
        status: 'beta',
        desc: '按尺寸、重量与目的地条件，先整理出方案要点与前置条件。',
        points: ['车型与装载方向', '超限通行要点', '换装与吊装提示', '按现场条件复核'],
      },
      {
        title: '中越双语业务沟通',
        status: 'beta',
        desc: '单证、邮件与函件的中越互译，术语统一后再发出。',
        points: ['单证与邮件互译', '术语一致性', '越南本地表达', '人工终审后发出'],
      },
    ],
    prev: '上一条',
    next: '下一条',
    note: '服务内容与交付口径以双方确认的业务范围为准。',
  },
  apps: {
    eyebrow: 'Applications',
    titleA: '覆盖',
    titleB: '工程物流日常场景',
    titleC: '· 开箱即用',
    sub: '不改变岗位职责，先把重复劳动接走，人专注判断与决策。',
    flowLabel: '处理流程',
    tabs: [
      {
        label: '智能询价',
        title: '把每天的询价先整理干净',
        desc: '客户发来的文字、表格、截图，先由数字员工整理成统一的询价信息，再进入方案环节。',
        bullets: ['提取货物、口岸、尺寸重量与时间要求', '按中越线路给出初步线路方向', '同步生成单证清单与待补资料', '输出结果交项目经理做正式方案'],
        flow: ['接收询价信息', '结构化整理', '线路与单证要点', '项目经理复核'],
      },
      {
        label: '报关单证',
        title: '让单证在提交前被对过一遍',
        desc: '按品类与口岸规则核对资料完整性，把差异项与待确认项提前列出来。',
        bullets: ['字段抽取与交叉比对', '缺失项与不一致项提示', '归类方向与合规提醒', '差异清单交人工确认'],
        flow: ['上传或粘贴单证', '字段抽取', '一致性核对', '差异清单'],
      },
      {
        label: '装载与车型',
        title: '装不装得下，先算一遍',
        desc: '按件重尺清单整理装载方向与车型范围，把超限与吊装条件提前标出来。',
        bullets: ['件重尺清单整理', '装载与车型方向', '超限与吊装前置条件', '待现场条件复核确认'],
        flow: ['整理件重尺', '装载与车型方向', '超限条件清单', '现场条件复核'],
      },
      {
        label: '在途与节点',
        title: '节点有变化，第一时间说清楚',
        desc: '按项目经理录入与承运方回传的节点信息，生成节点播报与异常提示，减少来回问。',
        bullets: ['节点信息整理与播报', '异常与偏差提示', '待客户配合事项清单', '重大变化人工确认后发布'],
        flow: ['节点信息汇总', '状态播报', '异常提示', '人工确认'],
      },
      {
        label: '流程自动化',
        title: '把重复劳动从人手里拿走',
        desc: '询价录入、资料归档、双语函件这些重复环节由数字员工承接，人专注在判断上。',
        bullets: ['询价信息录入整理', '项目资料归档命名', '双语函件起草', '权限与留痕可追溯'],
        flow: ['识别重复环节', '数字员工承接', '人工审核', '留痕归档'],
      },
    ],
    note: '场景为能力规划与内测范围说明；开放状态以标注为准。',
  },
  brain: {
    eyebrow: 'AI 底座',
    titleA: '玖能物流大脑：',
    titleB: '让 AI 懂工程物流',
    titleC: '',
    sub: '数字员工不是通用问答，它站在中越工程物流的业务规则与平台数据之上。',
    cards: [
      { title: '玖能物流大脑', status: 'beta', desc: '沉淀中越口岸规则、车型与超限要点、单证与归类经验，作为数字员工的上下文来源。' },
      { title: '数字化物流平台', status: 'live', desc: '从客户询价、方案设计、报价审批到业务实施、节点追踪与项目归档，全过程在系统里留痕。' },
      { title: '中越协同网络', status: 'live', desc: '中国侧业务支持公司 + 越南本地合作代理网络 + 专业车辆资源，数字员工接入的是这张网。' },
    ],
    stats: [
      { value: '2024', label: '越南公司登记' },
      { value: '3', label: '核心业务线' },
      { value: '5', label: 'AI 数字员工岗位' },
      { value: 'CN-VN', label: '两地资源协同' },
    ],
  },
  cases: {
    eyebrow: '代表项目',
    titleA: '用执行能力',
    titleB: '支撑复杂工程',
    sub: '以下为玖能参与的代表性工程物流项目类型，数字员工在其中有资料整理、单证核对与双语沟通的岗位。',
    items: [
      { title: '胡志明二号线', type: '城市轨道交通工程物流', body: '参与城市轨道交通项目工程物流，组织铁路与施工设备运输衔接。', tags: ['轨道交通', '工程物流'] },
      { title: '河内地铁 1 号线', type: '城市轨道交通工程物流', body: '参与城市轨道交通项目工程物流，协调跨境运输与项目节点。', tags: ['轨道交通', '跨境衔接'] },
      { title: '越南风力发电项目', type: '新能源工程物流', body: '参与多个越南风力发电项目，使用专业车辆运输风机叶片、塔筒等大型设备。', tags: ['新能源', '大件运输'] },
    ],
    domainsLabel: '业务覆盖领域',
    domains: ['城市轨道交通', '风力发电', '电力设备', '基建工程', '铁路物资', '工程设备', '新能源设备', '跨境报关'],
    note: '项目以类型与服务范围描述。具体客户名称、照片与数据将在取得授权与核验后公开。',
  },
  system: {
    eyebrow: '工程物流平台系统',
    titleA: '用系统管理工程物流',
    titleB: '全过程',
    intro: '从客户询价到项目归档，每一个关键步骤都清晰可追踪。平台不只协调车辆，而是管理工程物流项目的全过程。',
    steps: [
      '客户询价', '需求收集', '工程条件分析', '物流方案设计', '运输资源匹配', '报价与审批',
      '合同与单证', '业务实施', '节点追踪', '异常处理', '项目交付', '结算与归档',
    ],
    modulesTitle: '系统模块',
    modules: [
      { title: '客户与询价', body: '统一记录客户信息、货物参数和项目需求。' },
      { title: '方案与报价', body: '管理运输方案、报价版本和审批记录。' },
      { title: '项目执行', body: '关联车辆、供应商、报关资料和实施计划。' },
      { title: '节点追踪', body: '跟踪运输状态、关键节点和异常处理。' },
      { title: '项目归档', body: '沉淀合同、单证、结算和案例资料。' },
    ],
    shotLabel: '物流系统 · 节点追踪',
    note: '平台系统为项目内部管理工具，节点信息由项目人员录入与跟进，不构成对外实时追踪服务。',
  },
  solutions: {
    eyebrow: '解决方案',
    titleA: '围绕工程项目，',
    titleB: '提供可落地的运输方案',
    intro: '根据货物尺寸、重量、路线条件、装卸要求和施工节点，组织专业运输方案与现场交付协调。',
    items: [
      { sector: '轨道交通', title: '铁路物资与施工设备', body: '面向城市轨道交通项目，组织铁路物资、施工设备运输与项目节点配送。', slot: 'sol1' },
      { sector: '基建项目', title: '工程设备与材料', body: '面向道路、桥梁等基建项目，衔接工程设备、材料的跨境运输与现场吊装交付。', slot: 'sol2' },
      { sector: '电力项目', title: '电力设备运输', body: '面向火力发电及配套工程，组织变压器等大型电力设备运输与现场协调。', slot: 'sol3' },
      { sector: '新能源', title: '风电叶片与塔筒', body: '面向风力发电项目，使用专业车辆运输风机叶片、塔筒及大型设备。', slot: 'sol4' },
    ],
  },
  fleet: {
    eyebrow: '设备资源',
    titleA: '专业设备资源，',
    titleB: '应对复杂运输场景',
    intro: '针对新能源与大型工程设备运输需求，玖能配备专业车辆，并根据项目路线、设备尺寸和现场条件匹配运输资源。',
    items: [
      { title: '风力风机运输特种车', body: '用于风机设备与大型部件的工程运输。', spec: '适用：风机设备 / 大件部件', slot: 'fleet1' },
      { title: '风机叶片举升车', body: '应对复杂道路条件下的风机叶片运输。', spec: '适用：叶片 / 复杂路况', slot: 'fleet2' },
      { title: '配套运输资源', body: '根据项目路线、设备尺寸和现场条件匹配运输车辆与资源。', spec: '按项目匹配', slot: 'fleet3' },
    ],
  },
  network: {
    eyebrow: '中越协同网络',
    titleA: '连接中国与越南，',
    titleB: '形成工程项目协同网络',
    intro: '玖能以中国侧业务支持公司和越南本地合作代理网络组织资源，为中越工程项目提供协同支持。',
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
  },
  qual: {
    eyebrow: '企业信息与资质',
    titleA: '正式',
    titleB: '企业信息',
    intro: '玖能以越南登记主体和中国侧业务支持公司组成，以下为可公开的企业信息。',
    entities: [
      {
        tag: '越南公司',
        name: '玖能国际有限责任公司',
        rows: [
          { label: '越文名称', value: 'CÔNG TY TNHH QUỐC TẾ JIUNENG' },
          { label: '英文名称', value: 'JIUNENG INTERNATIONAL COMPANY LIMITED' },
          { label: '企业代码', value: '0202235124' },
          { label: '地址', value: '越南河内市纸桥坊 Duy Tân 街 82 号 5 楼 R03 室' },
        ],
      },
      {
        tag: '中国侧公司',
        name: '广西玖一进出口贸易有限公司',
        rows: [
          { label: '纳税人识别号', value: '91451481595108415C' },
          { label: '定位', value: '中国侧业务支持公司' },
          { label: '能力', value: '进出口贸易与报关支持' },
        ],
      },
    ],
  },
  consult: {
    eyebrow: '在线询价',
    title: '先让 AI 数字员工做一份初步评估',
    intro: '填写项目需求，数字员工按中越工程物流的口径整理线路与单证要点，项目经理随后跟进正式方案。',
    steps: ['填写项目需求', '数字员工整理要点', '项目经理跟进方案'],
    fields: {
      name: '联系人',
      company: '公司名称',
      inquiryType: '业务类型',
      loadingPort: '起运地',
      dischargePort: '目的地',
      weightEstimate: '重量/体积',
      details: '项目详情',
    },
    placeholders: {
      name: '请输入姓名',
      company: '公司或项目名称',
      loadingPort: '如：佛山工厂 / 深圳港 / 凭祥口岸',
      dischargePort: '如：河内 / 海防 / 胡志明',
      weightEstimate: '如：62 吨，长 8.5 米，宽 3.4 米',
      details: '请描述货物、件数、尺寸、时限和特殊要求',
    },
    types: ['工程物流', '进出口报关', '国际贸易', '解决方案咨询'],
    submit: '提交询价',
    submitting: '正在生成评估',
    resultTitle: '初步评估',
    fallback: '已收到需求。建议下一步补充货物尺寸、重量、装货时间、HS 编码及目的地现场条件，以便项目经理确认线路、车型和单证路径。',
    disclaimer: '初步评估仅用于整理沟通信息，不构成正式报价或时效承诺。',
    error: '在线评估暂时不可用，请留下联系方式或发送邮件至 jiuneng.vn@gmail.com，我们会尽快回复。',
  },
  cta: {
    title: '让 AI 数字员工先干起来',
    desc: '把项目资料发来，先拿到一份初步评估；剩下的判断，交给我们的人。',
    primary: '在线询价',
    secondary: '电话沟通',
  },
  calc: {
    eyebrow: '快速测算',
    title: '先算一遍，再谈价格',
    intro: '选好起运地、目的地与货量，自有测算引擎给出里程、预计行驶时间、用车数与参考价区间，约 30 秒出结果。',
    fields: {
      origin: '起运地',
      destination: '目的地',
      border: '口岸',
      weight: '货物总重（吨）',
      volume: '总体积（m³，拼车必填）',
      mode: '装货方式',
      vehicle: '车型',
    },
    placeholders: { weight: '例如 20', volume: '例如 60', border: '可不指定' },
    modes: { consolidated: '拼车', full_truck: '整车' },
    submit: '开始测算',
    submitting: '测算中…',
    again: '重新测算',
    resultTitle: '测算结果',
    labels: { distance: '里程', driving: '预计行驶', trucks: '用车数', vehicle: '车型', price: '参考价区间' },
    priceNote: '参考价区间＝引擎测算售价 ±10%，属初步测算，不构成报价或时效承诺；正式价格由项目经理按项目核算。',
    disclosureShort: '初步测算，非正式报价',
    profileNoteLabel: '引擎备注',
    profileNoteFixed: '本次按通用货车规则算路，未按车型限高限重单独选路；超限货物以项目经理确认为准。',
    source: '数据来自玖能自有 OSRM++ 测算引擎（含中越口岸分段与车型库），不引用任何第三方报价。',
    offline: '测算引擎暂时不可用，请在右侧询价表单留下需求，项目经理会尽快回复。',
    toForm: '把这个条件带到询价表单',
    inquiryTag: '快速测算',
  },
  contact: {
    eyebrow: '联系我们',
    title: '把项目资料发来，一起把方案做实',
    intro: '适合发送装箱单、设备图纸、尺寸重量表、目的地地址、交付时间和单证状态。',
    items: [
      { label: '邮箱', value: 'jiuneng.vn@gmail.com', href: 'mailto:jiuneng.vn@gmail.com' },
      { label: '中国咨询电话', value: '15687419919', href: 'tel:+8615687419919' },
      { label: '河内办公地址', value: '越南河内市纸桥坊 Duy Tân 街 82 号 5 楼 R03 室' },
      { label: '越南公司', value: 'CÔNG TY TNHH QUỐC TẾ JIUNENG · 企业代码 0202235124' },
    ],
  },
  chat: {
    open: '问数字员工',
    title: '物流 AI 数字员工',
    subtitle: '先问清楚，再谈方案',
    placeholder: '例如：友谊关到河内，25 吨设备用什么车？',
    send: '发送',
    close: '收起',
    empty: '可以问中越线路与车型、单证准备、超限运输要点，或我们的服务范围。',
    suggestions: [
      '友谊关到河内，25 吨设备用什么车型？',
      '大件设备出口需要准备哪些单证？',
      '你们的服务范围和联系方式？',
      '风机叶片运输要注意什么？',
    ],
    thinking: '正在整理…',
    toolLabels: {
      query_route_cost: '正在查询线路…',
      lookup_service_info: '正在查站内资料…',
    },
    disclaimer: 'AI 输出为初步整理，不构成报价或时效承诺；正式方案由项目经理跟进。',
    error: '对话服务暂时不可用，请稍后重试，或通过页面下方联系方式找到我们。',
    emptyReply: '这次没有生成内容，换个问法或补充线路与货量信息再试。',
  },
  footer: {
    intro: '面向中国企业的工程物流平台，把中越工程物流的业务经验做成 AI 数字员工，让复杂项目更清晰、更可控。',
    columns: [
      {
        title: '数字员工',
        links: [
          { label: '询价顾问', href: '#team' },
          { label: '关务专员', href: '#team' },
          { label: '单证专员', href: '#team' },
          { label: '调度专员', href: '#team' },
          { label: '翻译专员', href: '#team' },
        ],
      },
      {
        title: '核心业务',
        links: [
          { label: '工程物流', href: '#apps' },
          { label: '进出口报关', href: '#apps' },
          { label: '国际贸易', href: '#apps' },
          { label: '解决方案', href: '#solutions' },
        ],
      },
      {
        title: '关于玖能',
        links: [
          { label: 'AI 底座', href: '#brain' },
          { label: '项目案例', href: '#cases' },
          { label: '联系我们', href: '#contact' },
          { label: '企业信息', href: '#qual' },
        ],
      },
    ],
    legal: '玖能国际有限责任公司 · 广西玖一进出口贸易有限公司 · 备案信息待补充',
    site: 'site.jiuneng.space',
  },
};

const en: AgentContent = {
  meta: {
    title: 'JIUNENG logistics | Logistics AI digital employees',
    description:
      'JIUNENG turns China-Vietnam engineering logistics know-how into AI digital employees that handle inquiry intake, document checking, plan highlights and bilingual communication, working alongside our digital platform.',
  },
  nav: [
    { label: 'Digital employees', href: '#team' },
    { label: 'Agentic services', href: '#services' },
    { label: 'Applications', href: '#apps' },
    { label: 'Platform system', href: '#system' },
    { label: 'Solutions', href: '#solutions' },
    { label: 'Projects', href: '#cases' },
    { label: 'Inquiry', href: '#consult' },
  ],
  common: {
    company: 'JIUNENG logistics',
    tagline: 'Logistics AI agents · China-Vietnam engineering logistics',
    cta: 'Online inquiry',
    ctaSecondary: 'Meet the digital employees',
    phone: '15687419919',
    email: 'jiuneng.vn@gmail.com',
    statusLabels: { live: 'Live', beta: 'Beta', soon: 'In build' },
  },
  hero: {
    line1: 'Booking, customs, follow-up — still checked line by line by hand?',
    line2a: 'Your logistics ',
    line2b: 'AI digital employee',
    line2c: ' is here',
    sub: 'JIUNENG turns China-Vietnam engineering logistics experience into AI digital employees that clear up inquiries, documents, plan highlights and bilingual communication first, so your people can focus on judgement.',
    promptPlaceholder: 'Paste a project brief or cargo details — the digital employee drafts a first pass',
    promptHint: 'e.g. Hanoi project, 3 transformers, 62 t each, entering via Pingxiang, shipping in October',
    promptButton: 'Start',
    promptNote: 'This first pass prepares communication only; it is not a quotation or a lead-time commitment. Formal plans are reviewed by a project manager.',
    quick: ['Request a quote', 'How to prepare customs documents', 'How to move oversized cargo', 'CN-VI document translation'],
    tabsLabel: 'Choose a digital employee',
  },
  team: {
    eyebrow: 'AI digital employees',
    titleA: 'JIUNENG ',
    titleB: 'AI digital employees',
    titleC: ' — one employee, one real role',
    sub: 'Each digital employee maps to a real job function. Capabilities open in stages; anything marked “Live” can be used today.',
    roles: [
      {
        id: 'inquiry',
        name: 'Xiao Jiu',
        title: 'Inquiry advisor',
        status: 'live',
        tags: ['Intake', 'Route first-read', 'Document hints'],
        desc: 'Takes in the project request, structures cargo parameters, border-crossing and route highlights, and returns a first assessment with document checklist, HS classification direction and open questions for the project manager.',
        featured: true,
      },
      {
        id: 'customs',
        name: 'Customs specialist',
        title: 'Declaration document check',
        status: 'beta',
        tags: ['Completeness', 'Classification', 'Compliance'],
        desc: 'Checks declaration documents against common rules for the commodity and border crossing, flags classification direction and frequent rejection points, and lists the items for the client to confirm.',
      },
      {
        id: 'docs',
        name: 'Documents specialist',
        title: 'Field cross-check',
        status: 'beta',
        tags: ['Field extraction', 'Version diff', 'Discrepancies'],
        desc: 'Extracts package, weight and dimension fields from packing lists, invoices and bills of lading, cross-checks them, and marks any field that differs between versions for human review.',
      },
      {
        id: 'dispatch',
        name: 'Dispatch specialist',
        title: 'Equipment & route notes',
        status: 'soon',
        tags: ['Vehicle type', 'Oversize notes', 'Milestones'],
        desc: 'Suggests vehicle type and route considerations from dimensions, weight and route conditions, and helps surface height/weight limits, transloading and lifting requirements in advance.',
      },
      {
        id: 'translate',
        name: 'Translation specialist',
        title: 'Chinese-Vietnamese support',
        status: 'beta',
        tags: ['CN-VI', 'Terminology', 'Letter polish'],
        desc: 'Translates documents, emails and letters between Chinese and Vietnamese for consignees and partners, keeping a project glossary so wording stays consistent.',
      },
    ],
    demoLink: 'Try this employee',
    note: '“Beta” and “In build” mark capabilities under development and are not service commitments. Formal scope is confirmed by a project manager against the contract.',
  },
  services: {
    eyebrow: 'Agentic services',
    titleA: 'JIUNENG ',
    titleB: 'AI agent services',
    titleC: ' — delivered as a result',
    sub: 'Hand over a whole slice of work: the digital employee takes it from intake to a usable output, and a project manager reviews before delivery.',
    items: [
      {
        title: 'Inquiry intake & first assessment',
        status: 'live',
        desc: 'Submit the project request and get structured route direction, document checklist, classification direction and open items.',
        points: ['Route & border points', 'Document checklist', 'HS classification direction', 'Open items list'],
      },
      {
        title: 'Declaration document pre-check',
        status: 'beta',
        desc: 'Give the packing list, invoice and bill of lading to the digital employee before submission.',
        points: ['Key field extraction', 'Missing item flags', 'Version difference list', 'Human review trail'],
      },
      {
        title: 'Transport plan highlights',
        status: 'beta',
        desc: 'From dimensions, weight and destination conditions, get the plan highlights and prerequisites first.',
        points: ['Vehicle & loading direction', 'Oversize route notes', 'Transloading & lifting', 'Reviewed on site conditions'],
      },
      {
        title: 'Bilingual business communication',
        status: 'beta',
        desc: 'Chinese-Vietnamese translation of documents, emails and letters with consistent terminology.',
        points: ['Documents & email', 'Terminology consistency', 'Local Vietnamese wording', 'Sent after human review'],
      },
    ],
    prev: 'Previous',
    next: 'Next',
    note: 'Service scope and delivery terms follow the business scope both parties confirm.',
  },
  apps: {
    eyebrow: 'Applications',
    titleA: 'Built for',
    titleB: 'day-to-day engineering logistics',
    titleC: '',
    sub: 'Job roles stay the same — repetitive work moves to the digital employee, people keep the judgement.',
    flowLabel: 'How it works',
    tabs: [
      {
        label: 'Smart inquiry',
        title: 'Get every inquiry structured first',
        desc: 'Text, spreadsheets and screenshots from clients become one clean inquiry record before planning starts.',
        bullets: ['Extract cargo, border crossing, dimensions and timing', 'Suggest a first route direction for China-Vietnam', 'Generate the document checklist and open items', 'Hand the output to a project manager'],
        flow: ['Inquiry received', 'Structured', 'Route & documents', 'Manager review'],
      },
      {
        label: 'Customs documents',
        title: 'Documents checked before submission',
        desc: 'Completeness is checked against commodity and border rules, with discrepancies listed up front.',
        bullets: ['Field extraction and cross-check', 'Missing and mismatched items', 'Classification and compliance notes', 'Discrepancy list for human confirmation'],
        flow: ['Upload documents', 'Extract fields', 'Cross-check', 'Discrepancy list'],
      },
      {
        label: 'Loading & equipment',
        title: 'Know it fits before it moves',
        desc: 'Packing dimensions and weights are turned into loading direction and vehicle range, with oversize and lifting conditions flagged early.',
        bullets: ['Package, weight & dimension list', 'Loading and vehicle direction', 'Oversize and lifting prerequisites', 'Pending on-site confirmation'],
        flow: ['Dimensions & weight', 'Loading direction', 'Oversize checklist', 'Site confirmation'],
      },
      {
        label: 'Milestones',
        title: 'Milestone changes explained clearly',
        desc: 'Milestones recorded by the project manager and reported by carriers become updates and exception flags, cutting back-and-forth.',
        bullets: ['Milestone consolidation and updates', 'Exception and deviation flags', 'Items the client needs to action', 'Material changes confirmed by a human'],
        flow: ['Consolidate milestones', 'Status update', 'Exception flags', 'Human confirmation'],
      },
      {
        label: 'Process automation',
        title: 'Take the repetitive work off people',
        desc: 'Inquiry entry, document archiving and bilingual letters go to the digital employee; people focus on decisions.',
        bullets: ['Inquiry data entry', 'Project document naming & archiving', 'Bilingual letter drafting', 'Permissions and audit trail'],
        flow: ['Spot repetitive work', 'Digital employee runs it', 'Human review', 'Logged & archived'],
      },
    ],
    note: 'Scenarios describe capability planning and beta scope; availability follows the status labels.',
  },
  brain: {
    eyebrow: 'AI foundation',
    titleA: 'JIUNENG logistics brain:',
    titleB: 'making AI understand engineering logistics',
    titleC: '',
    sub: 'The digital employees are not generic chatbots — they stand on China-Vietnam engineering logistics rules and platform data.',
    cards: [
      { title: 'JIUNENG logistics brain', status: 'beta', desc: 'Accumulates border-crossing rules, vehicle and oversize notes, document and classification experience as context for the digital employees.' },
      { title: 'Digital logistics platform', status: 'live', desc: 'From inquiry, planning and quote approval to execution, milestone tracking and project archiving — every step recorded in the system.' },
      { title: 'China-Vietnam network', status: 'live', desc: 'China-side support company, Vietnam local partner-agent network and specialised vehicle resources — the network the digital employees plug into.' },
    ],
    stats: [
      { value: '2024', label: 'Registered in Vietnam' },
      { value: '3', label: 'Core business lines' },
      { value: '5', label: 'AI digital employee roles' },
      { value: 'CN-VN', label: 'Two-country coordination' },
    ],
  },
  cases: {
    eyebrow: 'Project cases',
    titleA: 'Execution capability for',
    titleB: 'complex engineering',
    sub: 'Representative engineering logistics project types JIUNENG has taken part in, where digital employees handle document intake, checks and bilingual communication.',
    items: [
      { title: 'Ho Chi Minh City Line 2', type: 'Urban rail transit logistics', body: 'Engineering logistics for an urban rail transit project, coordinating railway and construction equipment transport.', tags: ['Rail transit', 'Engineering logistics'] },
      { title: 'Hanoi Metro Line 1', type: 'Urban rail transit logistics', body: 'Engineering logistics for an urban rail transit project, coordinating cross-border transport and milestones.', tags: ['Rail transit', 'Cross-border'] },
      { title: 'Vietnam wind power projects', type: 'New-energy engineering logistics', body: 'Several Vietnam wind power projects, moving blades, towers and large equipment with specialised vehicles.', tags: ['New energy', 'Oversize cargo'] },
    ],
    domainsLabel: 'Fields we cover',
    domains: ['Urban rail transit', 'Wind power', 'Power equipment', 'Infrastructure', 'Railway materials', 'Engineering equipment', 'New-energy equipment', 'Cross-border customs'],
    note: 'Projects are described by type and scope. Client names, photos and figures are published only after authorisation and verification.',
  },
  consult: {
    eyebrow: 'Online inquiry',
    title: 'Let the digital employee draft a first assessment',
    intro: 'Fill in the project request; the digital employee structures route and document points per China-Vietnam engineering logistics practice, then a project manager follows up with a formal plan.',
    steps: ['Submit requirement', 'Employee structures it', 'Manager follows up'],
    fields: {
      name: 'Contact',
      company: 'Company',
      inquiryType: 'Business type',
      loadingPort: 'Origin',
      dischargePort: 'Destination',
      weightEstimate: 'Weight / volume',
      details: 'Project details',
    },
    placeholders: {
      name: 'Your name',
      company: 'Company or project name',
      loadingPort: 'e.g. Foshan plant / Shenzhen port / Pingxiang',
      dischargePort: 'e.g. Hanoi / Hai Phong / Ho Chi Minh City',
      weightEstimate: 'e.g. 62 t, 8.5 m long, 3.4 m wide',
      details: 'Describe cargo, pieces, dimensions, timing and special requirements',
    },
    types: ['Engineering logistics', 'Import-export customs', 'International trade', 'Solution consulting'],
    submit: 'Submit inquiry',
    submitting: 'Generating assessment',
    resultTitle: 'First assessment',
    fallback: 'Request received. Next step: add cargo dimensions, weight, loading date, HS code and destination site conditions so a project manager can confirm route, equipment and document path.',
    disclaimer: 'The first assessment only organises communication; it is not a formal quotation or a lead-time commitment.',
    error: 'The online assessment is temporarily unavailable. Please leave your contact details or email jiuneng.vn@gmail.com and we will get back to you.',
  },
  cta: {
    title: 'Put the AI digital employee to work',
    desc: 'Send the project files, get a first assessment — the judgement stays with our people.',
    primary: 'Online inquiry',
    secondary: 'Call us',
  },
  calc: {
    eyebrow: 'Quick estimate',
    title: 'Get the numbers first, then talk price',
    intro: 'Pick an origin, a destination and your cargo weight — our own estimation engine returns mileage, estimated driving time, truck count and an indicative price range in about 30 seconds.',
    fields: {
      origin: 'Origin',
      destination: 'Destination',
      border: 'Border crossing',
      weight: 'Total weight (t)',
      volume: 'Total volume (m³, required for shared load)',
      mode: 'Loading mode',
      vehicle: 'Truck type',
    },
    placeholders: { weight: 'e.g. 20', volume: 'e.g. 60', border: 'optional' },
    modes: { consolidated: 'Shared load', full_truck: 'Full truck' },
    submit: 'Get estimate',
    submitting: 'Estimating…',
    again: 'Estimate again',
    resultTitle: 'Estimate',
    labels: { distance: 'Distance', driving: 'Est. driving', trucks: 'Trucks', vehicle: 'Truck type', price: 'Indicative price range' },
    priceNote: 'Indicative range = the engine\'s sell price ±10%. It is a preliminary estimate, not a quotation or a transit-time commitment; final pricing is confirmed by our project manager.',
    disclosureShort: 'preliminary estimate, not a quotation',
    profileNoteLabel: 'Engine note',
    profileNoteFixed: 'This run was routed on the general truck profile, without height/weight-specific routing; oversized cargo is subject to our project manager\'s confirmation.',
    source: 'Powered by JIUNENG\'s own OSRM++ estimation engine (border-segmented routing and truck library). No third-party quotes are used.',
    offline: 'The estimation engine is temporarily unavailable. Please leave your requirement in the inquiry form — our project manager will reply shortly.',
    toForm: 'Carry these details into the inquiry form',
    inquiryTag: 'Quick estimate',
  },
  contact: {
    eyebrow: 'Contact',
    title: 'Send the project files and let us build the plan',
    intro: 'Ideal for packing lists, equipment drawings, dimension and weight tables, destination address, delivery dates and document status.',
    items: [
      { label: 'Email', value: 'jiuneng.vn@gmail.com', href: 'mailto:jiuneng.vn@gmail.com' },
      { label: 'China phone', value: '15687419919', href: 'tel:+8615687419919' },
      { label: 'Hanoi office', value: 'R03, 5th Floor, 82 Duy Tan St., Cau Giay Ward, Hanoi, Vietnam' },
      { label: 'Vietnam entity', value: 'CÔNG TY TNHH QUỐC TẾ JIUNENG · Enterprise code 0202235124' },
    ],
  },
  chat: {
    open: 'Ask the digital employee',
    title: 'Logistics AI digital employee',
    subtitle: 'Get clarity first, then the plan',
    placeholder: 'e.g. Youyi Pass to Hanoi, 25 t equipment — which truck?',
    send: 'Send',
    close: 'Collapse',
    empty: 'Ask about China–Vietnam routes and vehicle types, document preparation, oversize transport points, or our service scope.',
    suggestions: [
      'Youyi Pass to Hanoi, 25 t equipment — which truck?',
      'What documents are needed to export oversize equipment?',
      'What is your service scope and how do we contact you?',
      'What should we watch out for with wind turbine blades?',
    ],
    thinking: 'Organising…',
    toolLabels: {
      query_route_cost: 'Checking the route…',
      lookup_service_info: 'Checking our service information…',
    },
    disclaimer: 'AI output is an initial summary, not a quotation or a lead-time commitment; a project manager follows up on the formal plan.',
    error: 'The chat service is temporarily unavailable. Please retry later, or reach us through the contact details at the bottom of this page.',
    emptyReply: 'Nothing was generated this time — try rephrasing, or add route and cargo details.',
  },
  system: {
    eyebrow: 'Engineering logistics platform system',
    titleA: 'Manage the full engineering logistics process ',
    titleB: 'with a system',
    intro: 'From inquiry to project archiving, every key step is clear and traceable. The platform does more than dispatch trucks — it manages the entire project.',
    steps: [
      'Inquiry', 'Requirement intake', 'Condition analysis', 'Plan design', 'Resource matching', 'Quote & approval',
      'Contract & documents', 'Execution', 'Milestone tracking', 'Exception handling', 'Delivery', 'Settlement & archive',
    ],
    modulesTitle: 'System modules',
    modules: [
      { title: 'Clients & inquiries', body: 'Unified records of client info, cargo parameters, and project needs.' },
      { title: 'Plans & quotes', body: 'Manage transport plans, quote versions, and approval records.' },
      { title: 'Project execution', body: 'Link vehicles, suppliers, customs files, and execution plans.' },
      { title: 'Milestone tracking', body: 'Track transport status, key milestones, and exception handling.' },
      { title: 'Project archive', body: 'Accumulate contracts, documents, settlements, and case records.' },
    ],
    shotLabel: 'Logistics system · Milestone tracking',
    note: 'The platform system is an internal project management tool; milestone data is entered and followed up by project staff and is not an external real-time tracking service.',
  },
  solutions: {
    eyebrow: 'Solutions',
    titleA: 'Workable transport plans ',
    titleB: 'around engineering projects',
    intro: 'We organize professional transport plans and on-site delivery based on cargo dimensions, weight, route conditions, handling needs, and construction milestones.',
    items: [
      { sector: 'Rail transit', title: 'Railway materials & equipment', body: 'For urban rail transit: railway materials, construction equipment transport, and milestone distribution.', slot: 'sol1' },
      { sector: 'Infrastructure', title: 'Equipment & materials', body: 'For road and bridge projects: cross-border transport of equipment and materials with on-site lifting.', slot: 'sol2' },
      { sector: 'Power', title: 'Power equipment transport', body: 'For thermal power and supporting works: transformer and large power-equipment transport with on-site coordination.', slot: 'sol3' },
      { sector: 'New energy', title: 'Wind blades & towers', body: 'For wind power projects: specialized vehicles transporting wind blades, towers, and large equipment.', slot: 'sol4' },
    ],
  },
  fleet: {
    eyebrow: 'Equipment resources',
    titleA: 'Specialized equipment ',
    titleB: 'for complex transport scenarios',
    intro: 'For new-energy and large engineering equipment, JIUNENG provides specialized vehicles and matches resources to project route, equipment size, and site conditions.',
    items: [
      { title: 'Wind-turbine transport vehicle', body: 'For turbine equipment and large components.', spec: 'For: turbines / large parts', slot: 'fleet1' },
      { title: 'Wind-blade lifting vehicle', body: 'Handles blade transport on complex road conditions.', spec: 'For: blades / complex roads', slot: 'fleet2' },
      { title: 'Supporting transport resources', body: 'Match vehicles and resources by route, equipment size, and site conditions.', spec: 'Matched per project', slot: 'fleet3' },
    ],
  },
  network: {
    eyebrow: 'China-Vietnam network',
    titleA: 'Connecting China and Vietnam ',
    titleB: 'into a project network',
    intro: 'JIUNENG organizes resources through a China-side support company and a Vietnam local partner-agent network.',
    china: {
      flag: 'China side',
      name: 'Guangxi Jiuyi Import & Export Trading Co., Ltd.',
      body: 'Provides import-export trade and customs support, linking China origin resources.',
      points: ['Import-export trade support', 'Customs coordination', 'China origin resource linkage'],
    },
    vietnam: {
      flag: 'Vietnam side',
      name: 'JIUNENG INTERNATIONAL COMPANY LIMITED',
      body: 'Connects operations, project execution, and resource coordination through a local partner-agent network.',
      points: ['Local partner-agent network', 'Execution & on-site coordination', 'Hanoi office entity'],
    },
    note: 'JIUNENG provides Vietnam-side support through local partner-agents, with no self-operated warehouses or nationwide branches.',
  },
  qual: {
    eyebrow: 'Company info & credentials',
    titleA: 'Official company ',
    titleB: 'information',
    intro: 'JIUNENG comprises a Vietnam registered entity and a China-side support company. Below is publicly available company information.',
    entities: [
      {
        tag: 'Vietnam company',
        name: 'JIUNENG INTERNATIONAL COMPANY LIMITED',
        rows: [
          { label: 'Vietnamese', value: 'CÔNG TY TNHH QUỐC TẾ JIUNENG' },
          { label: 'Chinese', value: '玖能国际有限责任公司' },
          { label: 'Enterprise code', value: '0202235124' },
          { label: 'Address', value: 'R03, 5th Floor, 82 Duy Tan St., Cau Giay Ward, Hanoi' },
        ],
      },
      {
        tag: 'China-side company',
        name: 'Guangxi Jiuyi Import & Export Trading Co., Ltd.',
        rows: [
          { label: 'Tax ID', value: '91451481595108415C' },
          { label: 'Role', value: 'China-side support company' },
          { label: 'Capability', value: 'Import-export trade & customs' },
        ],
      },
    ],
  },
  footer: {
    intro: 'An engineering logistics platform for Chinese enterprises, turning China-Vietnam logistics experience into AI digital employees so complex projects stay clear and controllable.',
    columns: [
      {
        title: 'Digital employees',
        links: [
          { label: 'Inquiry advisor', href: '#team' },
          { label: 'Customs specialist', href: '#team' },
          { label: 'Documents specialist', href: '#team' },
          { label: 'Dispatch specialist', href: '#team' },
          { label: 'Translation specialist', href: '#team' },
        ],
      },
      {
        title: 'Core business',
        links: [
          { label: 'Engineering logistics', href: '#apps' },
          { label: 'Import-export customs', href: '#apps' },
          { label: 'International trade', href: '#apps' },
          { label: 'Solutions', href: '#solutions' },
        ],
      },
      {
        title: 'Company',
        links: [
          { label: 'AI foundation', href: '#brain' },
          { label: 'Project cases', href: '#cases' },
          { label: 'Contact', href: '#contact' },
          { label: 'Company information', href: '#qual' },
        ],
      },
    ],
    legal: 'JIUNENG INTERNATIONAL COMPANY LIMITED · Guangxi Jiuyi Import & Export Trading Co., Ltd. · Registration details pending',
    site: 'site.jiuneng.space',
  },
};

const vi: AgentContent = {
  meta: {
    title: 'JIUNENG logistics | Nhân viên số AI ngành logistics',
    description:
      'JIUNENG đưa kinh nghiệm logistics công trình Trung - Việt vào nhân viên số AI: tiếp nhận yêu cầu báo giá, kiểm tra chứng từ, điểm chính phương án và trao đổi song ngữ, phối hợp cùng nền tảng số.',
  },
  nav: [
    { label: 'Nhân viên số', href: '#team' },
    { label: 'Dịch vụ AI', href: '#services' },
    { label: 'Ứng dụng', href: '#apps' },
    { label: 'Hệ thống', href: '#system' },
    { label: 'Giải pháp', href: '#solutions' },
    { label: 'Dự án', href: '#cases' },
    { label: 'Báo giá', href: '#consult' },
  ],
  common: {
    company: 'JIUNENG logistics',
    tagline: 'AI agent logistics · Logistics công trình Trung - Việt',
    cta: 'Báo giá trực tuyến',
    ctaSecondary: 'Xem nhân viên số',
    phone: '15687419919',
    email: 'jiuneng.vn@gmail.com',
    statusLabels: { live: 'Đang chạy', beta: 'Thử nghiệm', soon: 'Đang xây dựng' },
  },
  hero: {
    line1: 'Đặt chỗ, khai quan, theo dõi đơn — vẫn phải dò từng dòng?',
    line2a: 'Nhân viên số ',
    line2b: 'AI logistics',
    line2c: ' của bạn đã đến',
    sub: 'JIUNENG chuyển kinh nghiệm logistics công trình Trung - Việt thành nhân viên số AI: làm sạch trước yêu cầu báo giá, chứng từ, điểm chính phương án và trao đổi song ngữ, để đội ngũ tập trung vào việc cần phán đoán.',
    promptPlaceholder: 'Dán nội dung yêu cầu hoặc thông tin hàng hóa, nhân viên số xử lý bước đầu',
    promptHint: 'Ví dụ: dự án Hà Nội, 3 máy biến áp, 62 tấn/kiện, vào qua cửa khẩu Bằng Tường, tháng 10',
    promptButton: 'Bắt đầu',
    promptNote: 'Kết quả xử lý bước đầu chỉ để chuẩn bị trao đổi, không phải báo giá hay cam kết thời gian; phương án chính thức do quản lý dự án thẩm tra.',
    quick: ['Cần báo giá', 'Chuẩn bị chứng từ khai quan', 'Vận chuyển hàng quá khổ', 'Dịch chứng từ Trung - Việt'],
    tabsLabel: 'Chọn nhân viên số',
  },
  team: {
    eyebrow: 'Nhân viên số AI',
    titleA: 'Nhân viên số ',
    titleB: 'AI JIUNENG',
    titleC: ' — mỗi nhân viên, một vị trí thật',
    sub: 'Mỗi nhân viên số gắn với một vị trí công việc thật. Năng lực mở theo giai đoạn; mục ghi “Đang chạy” có thể dùng ngay.',
    roles: [
      {
        id: 'inquiry',
        name: 'Tiểu Cửu',
        title: 'Tư vấn báo giá',
        status: 'live',
        tags: ['Tiếp nhận', 'Đọc tuyến', 'Gợi ý chứng từ'],
        desc: 'Tiếp nhận yêu cầu dự án, sắp xếp thông số hàng hóa, cửa khẩu và tuyến đường; trả về đánh giá bước đầu gồm danh mục chứng từ, hướng phân loại HS và các mục cần bổ sung cho quản lý dự án.',
        featured: true,
      },
      {
        id: 'customs',
        name: 'Chuyên viên hải quan',
        title: 'Kiểm tra chứng từ khai báo',
        status: 'beta',
        tags: ['Đầy đủ', 'Phân loại', 'Tuân thủ'],
        desc: 'Đối chiếu chứng từ khai báo với quy tắc thường gặp theo mặt hàng và cửa khẩu, gợi ý hướng phân loại và các lỗi dễ bị trả hồ sơ, liệt kê mục cần khách hàng xác nhận.',
      },
      {
        id: 'docs',
        name: 'Chuyên viên chứng từ',
        title: 'Đối chiếu trường dữ liệu',
        status: 'beta',
        tags: ['Trích xuất', 'So phiên bản', 'Sai khác'],
        desc: 'Trích xuất số kiện, trọng lượng, kích thước từ packing list, hóa đơn và vận đơn; đối chiếu chéo và đánh dấu các trường lệch giữa các phiên bản để người kiểm tra rà lại.',
      },
      {
        id: 'dispatch',
        name: 'Chuyên viên điều vận',
        title: 'Loại xe và điểm lưu ý',
        status: 'soon',
        tags: ['Loại xe', 'Quá khổ', 'Mốc tiến độ'],
        desc: 'Gợi ý loại xe và điểm cần lưu ý trên tuyến theo kích thước, trọng lượng và điều kiện đường, giúp nhận diện sớm giới hạn chiều cao, tải trọng, sang tải và cẩu hạ.',
      },
      {
        id: 'translate',
        name: 'Chuyên viên dịch thuật',
        title: 'Hỗ trợ Trung - Việt',
        status: 'beta',
        tags: ['Trung - Việt', 'Thuật ngữ', 'Thư từ'],
        desc: 'Dịch chứng từ, email và thư từ giữa tiếng Trung và tiếng Việt cho bên nhận hàng và đối tác, duy trì bảng thuật ngữ của dự án để cách diễn đạt thống nhất.',
      },
    ],
    demoLink: 'Dùng thử nhân viên này',
    note: 'Mục “Thử nghiệm” và “Đang xây dựng” là năng lực đang phát triển, không phải cam kết dịch vụ. Phạm vi chính thức do quản lý dự án xác nhận theo hợp đồng.',
  },
  services: {
    eyebrow: 'Dịch vụ AI agent',
    titleA: 'Dịch vụ ',
    titleB: 'AI agent',
    titleC: ' JIUNENG — giao theo kết quả',
    sub: 'Giao hẳn một phần công việc: nhân viên số nhận từ khâu tiếp nhận đến kết quả dùng được, quản lý dự án thẩm tra trước khi bàn giao.',
    items: [
      {
        title: 'Tiếp nhận báo giá và đánh giá bước đầu',
        status: 'live',
        desc: 'Gửi yêu cầu dự án, nhận hướng tuyến, danh mục chứng từ, hướng phân loại và danh sách mục cần bổ sung.',
        points: ['Tuyến và cửa khẩu', 'Danh mục chứng từ', 'Hướng phân loại HS', 'Danh sách cần bổ sung'],
      },
      {
        title: 'Kiểm tra trước chứng từ khai báo',
        status: 'beta',
        desc: 'Đưa packing list, hóa đơn, vận đơn cho nhân viên số kiểm tra trước khi nộp.',
        points: ['Trích xuất trường chính', 'Cảnh báo thiếu mục', 'Danh sách lệch phiên bản', 'Lưu vết thẩm tra'],
      },
      {
        title: 'Tạo điểm chính phương án vận chuyển',
        status: 'beta',
        desc: 'Từ kích thước, trọng lượng và điều kiện điểm đến, nhận điểm chính và điều kiện tiên quyết trước.',
        points: ['Hướng loại xe, xếp hàng', 'Điểm lưu ý quá khổ', 'Sang tải và cẩu hạ', 'Thẩm tra theo điều kiện thực tế'],
      },
      {
        title: 'Trao đổi song ngữ Trung - Việt',
        status: 'beta',
        desc: 'Dịch chứng từ, email và thư từ Trung - Việt, thống nhất thuật ngữ trước khi gửi.',
        points: ['Chứng từ và email', 'Thống nhất thuật ngữ', 'Cách diễn đạt bản địa', 'Gửi sau khi duyệt'],
      },
    ],
    prev: 'Trước',
    next: 'Sau',
    note: 'Phạm vi dịch vụ và điều kiện bàn giao theo phạm vi hai bên xác nhận.',
  },
  apps: {
    eyebrow: 'Ứng dụng',
    titleA: 'Cho công việc',
    titleB: 'logistics công trình hằng ngày',
    titleC: '',
    sub: 'Không đổi vị trí công việc: việc lặp lại chuyển cho nhân viên số, con người giữ phần phán đoán.',
    flowLabel: 'Quy trình xử lý',
    tabs: [
      {
        label: 'Báo giá thông minh',
        title: 'Làm sạch yêu cầu báo giá mỗi ngày',
        desc: 'Văn bản, bảng biểu, ảnh chụp từ khách hàng được nhân viên số sắp xếp thành một bản yêu cầu thống nhất trước khi vào phương án.',
        bullets: ['Trích xuất hàng hóa, cửa khẩu, kích thước, thời gian', 'Gợi ý hướng tuyến Trung - Việt bước đầu', 'Tạo danh mục chứng từ và mục cần bổ sung', 'Giao kết quả cho quản lý dự án'],
        flow: ['Nhận yêu cầu', 'Sắp xếp dữ liệu', 'Tuyến và chứng từ', 'Quản lý thẩm tra'],
      },
      {
        label: 'Chứng từ khai quan',
        title: 'Chứng từ được kiểm tra trước khi nộp',
        desc: 'Đối chiếu tính đầy đủ theo mặt hàng và cửa khẩu, liệt kê trước các mục lệch và cần xác nhận.',
        bullets: ['Trích xuất và đối chiếu trường', 'Cảnh báo thiếu và lệch', 'Gợi ý phân loại, tuân thủ', 'Danh sách lệch để xác nhận'],
        flow: ['Tải chứng từ', 'Trích xuất trường', 'Đối chiếu', 'Danh sách lệch'],
      },
      {
        label: 'Xếp hàng và loại xe',
        title: 'Tính trước xem có chở được không',
        desc: 'Từ danh sách kiện, trọng lượng và kích thước, sắp xếp hướng xếp hàng và phạm vi loại xe, nêu trước điều kiện quá khổ và cẩu hạ.',
        bullets: ['Danh sách kiện, tải, kích thước', 'Hướng xếp hàng và loại xe', 'Điều kiện quá khổ, cẩu hạ', 'Chờ xác nhận điều kiện thực tế'],
        flow: ['Kích thước, tải', 'Hướng xếp hàng', 'Danh mục quá khổ', 'Xác nhận hiện trường'],
      },
      {
        label: 'Mốc tiến độ',
        title: 'Mốc thay đổi, thông báo rõ ràng',
        desc: 'Thông tin mốc do quản lý dự án nhập và đơn vị vận chuyển phản hồi được tổng hợp thành bản tin và cảnh báo bất thường, giảm hỏi qua lại.',
        bullets: ['Tổng hợp và phát bản tin mốc', 'Cảnh báo bất thường, lệch', 'Mục cần khách hàng phối hợp', 'Thay đổi lớn do người xác nhận'],
        flow: ['Tổng hợp mốc', 'Phát bản tin', 'Cảnh báo bất thường', 'Người xác nhận'],
      },
      {
        label: 'Tự động hóa quy trình',
        title: 'Lấy việc lặp lại khỏi con người',
        desc: 'Nhập yêu cầu, lưu trữ hồ sơ, soạn thư song ngữ do nhân viên số đảm nhận; con người tập trung vào quyết định.',
        bullets: ['Nhập liệu yêu cầu báo giá', 'Đặt tên và lưu trữ hồ sơ', 'Soạn thư song ngữ', 'Phân quyền và lưu vết'],
        flow: ['Nhận diện việc lặp', 'Nhân viên số làm', 'Người kiểm tra', 'Lưu vết hồ sơ'],
      },
    ],
    note: 'Các kịch bản mô tả định hướng năng lực và phạm vi thử nghiệm; trạng thái mở theo nhãn ghi trên từng mục.',
  },
  brain: {
    eyebrow: 'Nền tảng AI',
    titleA: 'Bộ não logistics JIUNENG:',
    titleB: 'để AI hiểu logistics công trình',
    titleC: '',
    sub: 'Nhân viên số không phải chatbot chung: nó đứng trên quy tắc nghiệp vụ và dữ liệu nền tảng của logistics công trình Trung - Việt.',
    cards: [
      { title: 'Bộ não logistics JIUNENG', status: 'beta', desc: 'Tích lũy quy tắc cửa khẩu Trung - Việt, điểm lưu ý về xe và hàng quá khổ, kinh nghiệm chứng từ và phân loại làm ngữ cảnh cho nhân viên số.' },
      { title: 'Nền tảng logistics số', status: 'live', desc: 'Từ báo giá, thiết kế phương án, duyệt giá đến thực hiện, theo dõi mốc và lưu trữ dự án — mọi bước đều có vết trong hệ thống.' },
      { title: 'Mạng lưới Trung - Việt', status: 'live', desc: 'Công ty hỗ trợ phía Trung Quốc, mạng lưới đại lý hợp tác tại Việt Nam và nguồn lực xe chuyên dụng — mạng lưới mà nhân viên số kết nối vào.' },
    ],
    stats: [
      { value: '2024', label: 'Đăng ký tại Việt Nam' },
      { value: '3', label: 'Mảng kinh doanh chính' },
      { value: '5', label: 'Vị trí nhân viên số AI' },
      { value: 'CN-VN', label: 'Phối hợp hai nước' },
    ],
  },
  cases: {
    eyebrow: 'Dự án tiêu biểu',
    titleA: 'Năng lực thực hiện cho',
    titleB: 'công trình phức tạp',
    sub: 'Các dạng dự án logistics công trình tiêu biểu JIUNENG tham gia, nơi nhân viên số đảm nhận khâu sắp xếp hồ sơ, kiểm tra chứng từ và trao đổi song ngữ.',
    items: [
      { title: 'Tuyến số 2 TP.HCM', type: 'Logistics công trình đường sắt đô thị', body: 'Tham gia logistics công trình cho dự án đường sắt đô thị, phối hợp vận chuyển vật tư đường sắt và thiết bị thi công.', tags: ['Đường sắt', 'Logistics công trình'] },
      { title: 'Metro Hà Nội tuyến 1', type: 'Logistics công trình đường sắt đô thị', body: 'Tham gia logistics công trình cho dự án đường sắt đô thị, phối hợp vận chuyển xuyên biên giới và mốc tiến độ.', tags: ['Đường sắt', 'Xuyên biên giới'] },
      { title: 'Dự án điện gió tại Việt Nam', type: 'Logistics công trình năng lượng mới', body: 'Tham gia nhiều dự án điện gió tại Việt Nam, dùng xe chuyên dụng vận chuyển cánh và tháp tuabin cùng thiết bị lớn.', tags: ['Năng lượng mới', 'Hàng quá khổ'] },
    ],
    domainsLabel: 'Lĩnh vực phụ trách',
    domains: ['Đường sắt đô thị', 'Điện gió', 'Thiết bị điện', 'Công trình hạ tầng', 'Vật tư đường sắt', 'Thiết bị công trình', 'Thiết bị năng lượng mới', 'Khai quan xuyên biên giới'],
    note: 'Dự án được mô tả theo loại hình và phạm vi dịch vụ. Tên khách hàng, hình ảnh và số liệu chỉ công bố sau khi được phép và kiểm chứng.',
  },
  consult: {
    eyebrow: 'Báo giá trực tuyến',
    title: 'Để nhân viên số AI làm đánh giá bước đầu',
    intro: 'Điền yêu cầu dự án, nhân viên số sắp xếp tuyến và chứng từ theo nghiệp vụ logistics công trình Trung - Việt, sau đó quản lý dự án theo dõi phương án chính thức.',
    steps: ['Gửi yêu cầu', 'Nhân viên số sắp xếp', 'Quản lý dự án theo dõi'],
    fields: {
      name: 'Người liên hệ',
      company: 'Công ty',
      inquiryType: 'Loại hình',
      loadingPort: 'Điểm đi',
      dischargePort: 'Điểm đến',
      weightEstimate: 'Trọng lượng / thể tích',
      details: 'Chi tiết dự án',
    },
    placeholders: {
      name: 'Nhập họ tên',
      company: 'Tên công ty hoặc dự án',
      loadingPort: 'Ví dụ: nhà máy Phật Sơn / cảng Thâm Quyến / Bằng Tường',
      dischargePort: 'Ví dụ: Hà Nội / Hải Phòng / TP.HCM',
      weightEstimate: 'Ví dụ: 62 tấn, dài 8,5 m, rộng 3,4 m',
      details: 'Mô tả hàng hóa, số kiện, kích thước, thời hạn và yêu cầu đặc biệt',
    },
    types: ['Logistics công trình', 'Khai quan xuất nhập khẩu', 'Thương mại quốc tế', 'Tư vấn giải pháp'],
    submit: 'Gửi yêu cầu',
    submitting: 'Đang tạo đánh giá',
    resultTitle: 'Đánh giá bước đầu',
    fallback: 'Đã nhận yêu cầu. Bước tiếp theo: bổ sung kích thước, trọng lượng hàng, thời gian xếp hàng, mã HS và điều kiện hiện trường điểm đến để quản lý dự án xác nhận tuyến, loại xe và luồng chứng từ.',
    disclaimer: 'Đánh giá bước đầu chỉ để sắp xếp thông tin trao đổi, không phải báo giá chính thức hay cam kết thời gian.',
    error: 'Đánh giá trực tuyến tạm thời không khả dụng. Vui lòng để lại thông tin liên hệ hoặc email jiuneng.vn@gmail.com, chúng tôi sẽ phản hồi sớm.',
  },
  cta: {
    title: 'Để nhân viên số AI bắt đầu làm việc',
    desc: 'Gửi hồ sơ dự án để nhận đánh giá bước đầu; phần phán đoán để đội ngũ của chúng tôi lo.',
    primary: 'Báo giá trực tuyến',
    secondary: 'Gọi điện',
  },
  calc: {
    eyebrow: 'Tính nhanh',
    title: 'Có số trước, rồi mới bàn giá',
    intro: 'Chọn điểm đi, điểm đến và khối lượng hàng — công cụ tính toán riêng của JIUNENG trả về quãng đường, thời gian chạy dự kiến, số xe và khoảng giá tham khảo trong khoảng 30 giây.',
    fields: {
      origin: 'Điểm đi',
      destination: 'Điểm đến',
      border: 'Cửa khẩu',
      weight: 'Tổng khối lượng (tấn)',
      volume: 'Tổng thể tích (m³, bắt buộc khi hàng ghép)',
      mode: 'Cách xếp hàng',
      vehicle: 'Loại xe',
    },
    placeholders: { weight: 'ví dụ 20', volume: 'ví dụ 60', border: 'có thể để trống' },
    modes: { consolidated: 'Hàng ghép', full_truck: 'Nguyên xe' },
    submit: 'Bắt đầu tính',
    submitting: 'Đang tính…',
    again: 'Tính lại',
    resultTitle: 'Kết quả tính',
    labels: { distance: 'Quãng đường', driving: 'Thời gian chạy dự kiến', trucks: 'Số xe', vehicle: 'Loại xe', price: 'Khoảng giá tham khảo' },
    priceNote: 'Khoảng giá tham khảo = giá bán do công cụ tính ±10%. Đây là ước tính ban đầu, không phải báo giá hay cam kết thời gian; giá chính thức do quản lý dự án xác nhận.',
    disclosureShort: 'ước tính ban đầu, không phải báo giá',
    profileNoteLabel: 'Ghi chú từ công cụ',
    profileNoteFixed: 'Lần tính này dùng quy tắc xe tải thông dụng, chưa chọn đường theo giới hạn chiều cao/trọng tải của từng loại xe; hàng quá khổ cần quản lý dự án xác nhận.',
    source: 'Dữ liệu từ công cụ tính OSRM++ của JIUNENG (chia đoạn theo cửa khẩu và thư viện loại xe), không dùng báo giá của bên thứ ba.',
    offline: 'Công cụ tính tạm thời không khả dụng. Vui lòng để lại yêu cầu ở biểu mẫu bên cạnh, quản lý dự án sẽ phản hồi sớm.',
    toForm: 'Đưa thông tin này vào biểu mẫu yêu cầu báo giá',
    inquiryTag: 'Tính nhanh',
  },
  contact: {
    eyebrow: 'Liên hệ',
    title: 'Gửi hồ sơ dự án, cùng làm rõ phương án',
    intro: 'Phù hợp để gửi packing list, bản vẽ thiết bị, bảng kích thước trọng lượng, địa chỉ điểm đến, thời gian bàn giao và tình trạng chứng từ.',
    items: [
      { label: 'Email', value: 'jiuneng.vn@gmail.com', href: 'mailto:jiuneng.vn@gmail.com' },
      { label: 'Điện thoại (Trung Quốc)', value: '15687419919', href: 'tel:+8615687419919' },
      { label: 'Văn phòng Hà Nội', value: 'R03, tầng 5, số 82 phố Duy Tân, phường Cầu Giấy, Hà Nội' },
      { label: 'Pháp nhân Việt Nam', value: 'CÔNG TY TNHH QUỐC TẾ JIUNENG · Mã số doanh nghiệp 0202235124' },
    ],
  },
  chat: {
    open: 'Hỏi nhân viên số',
    title: 'Nhân viên số AI ngành logistics',
    subtitle: 'Hỏi rõ trước, rồi bàn phương án',
    placeholder: 'Ví dụ: Hữu Nghị Quan đi Hà Nội, thiết bị 25 tấn dùng xe gì?',
    send: 'Gửi',
    close: 'Thu gọn',
    empty: 'Bạn có thể hỏi về tuyến Trung – Việt và loại xe, chứng từ cần chuẩn bị, điểm lưu ý khi vận chuyển quá khổ, hoặc phạm vi dịch vụ của chúng tôi.',
    suggestions: [
      'Hữu Nghị Quan đi Hà Nội, thiết bị 25 tấn dùng xe gì?',
      'Xuất khẩu thiết bị quá khổ cần chuẩn bị chứng từ gì?',
      'Phạm vi dịch vụ và thông tin liên hệ của quý công ty?',
      'Vận chuyển cánh turbine gió cần lưu ý gì?',
    ],
    thinking: 'Đang tổng hợp…',
    toolLabels: {
      query_route_cost: 'Đang tra tuyến…',
      lookup_service_info: 'Đang tra thông tin dịch vụ…',
    },
    disclaimer: 'Nội dung do AI tạo là bản tổng hợp bước đầu, không phải báo giá hay cam kết thời gian; quản lý dự án sẽ theo sát phương án chính thức.',
    error: 'Dịch vụ trò chuyện tạm thời không khả dụng. Vui lòng thử lại sau, hoặc liên hệ theo thông tin ở cuối trang.',
    emptyReply: 'Lần này chưa tạo được nội dung — vui lòng hỏi lại hoặc bổ sung thông tin tuyến và khối lượng hàng.',
  },
  system: {
    eyebrow: 'Hệ thống nền tảng logistics công trình',
    titleA: 'Quản lý toàn bộ quá trình logistics công trình ',
    titleB: 'bằng hệ thống',
    intro: 'Từ báo giá đến lưu trữ dự án, mỗi bước then chốt đều rõ ràng và có thể theo dõi. Nền tảng không chỉ điều phối xe mà quản lý toàn bộ dự án.',
    steps: [
      'Báo giá', 'Thu thập nhu cầu', 'Phân tích điều kiện', 'Thiết kế phương án', 'Khớp nguồn lực', 'Báo giá & duyệt',
      'Hợp đồng & chứng từ', 'Thực hiện', 'Theo dõi mốc', 'Xử lý bất thường', 'Bàn giao', 'Quyết toán & lưu trữ',
    ],
    modulesTitle: 'Mô-đun hệ thống',
    modules: [
      { title: 'Khách hàng & báo giá', body: 'Ghi nhận thống nhất thông tin khách hàng, thông số hàng hóa và nhu cầu.' },
      { title: 'Phương án & báo giá', body: 'Quản lý phương án vận chuyển, phiên bản báo giá và hồ sơ duyệt.' },
      { title: 'Thực hiện dự án', body: 'Liên kết xe, nhà cung cấp, hồ sơ khai quan và kế hoạch thực hiện.' },
      { title: 'Theo dõi mốc', body: 'Theo dõi trạng thái vận chuyển, mốc then chốt và xử lý bất thường.' },
      { title: 'Lưu trữ dự án', body: 'Tích lũy hợp đồng, chứng từ, quyết toán và hồ sơ dự án.' },
    ],
    shotLabel: 'Hệ thống logistics · Theo dõi mốc',
    note: 'Hệ thống là công cụ quản lý nội bộ của dự án; thông tin mốc do nhân sự dự án nhập và theo dõi, không phải dịch vụ theo dõi thời gian thực.',
  },
  solutions: {
    eyebrow: 'Giải pháp',
    titleA: 'Phương án vận chuyển khả thi ',
    titleB: 'cho từng dự án',
    intro: 'Tổ chức phương án vận chuyển chuyên nghiệp và phối hợp giao hiện trường theo kích thước, trọng lượng, tuyến đường và mốc thi công.',
    items: [
      { sector: 'Đường sắt đô thị', title: 'Vật tư & thiết bị thi công', body: 'Cho dự án đường sắt đô thị: tổ chức vận chuyển vật tư, thiết bị thi công và phân phối theo mốc.', slot: 'sol1' },
      { sector: 'Hạ tầng', title: 'Thiết bị & vật liệu', body: 'Cho dự án đường, cầu: kết nối vận chuyển thiết bị, vật liệu và cẩu hạ tại hiện trường.', slot: 'sol2' },
      { sector: 'Điện', title: 'Vận chuyển thiết bị điện', body: 'Cho nhà máy nhiệt điện: vận chuyển máy biến áp và thiết bị điện lớn, phối hợp hiện trường.', slot: 'sol3' },
      { sector: 'Năng lượng mới', title: 'Cánh & tháp điện gió', body: 'Cho dự án điện gió: dùng xe chuyên dụng vận chuyển cánh quạt, tháp và thiết bị lớn.', slot: 'sol4' },
    ],
  },
  fleet: {
    eyebrow: 'Nguồn lực thiết bị',
    titleA: 'Thiết bị chuyên dụng ',
    titleB: 'cho các tình huống phức tạp',
    intro: 'Cho nhu cầu vận chuyển thiết bị năng lượng mới và công trình lớn, JIUNENG trang bị xe chuyên dụng và khớp nguồn lực theo tuyến, kích thước và điều kiện hiện trường.',
    items: [
      { title: 'Xe chuyên dụng vận chuyển tua-bin gió', body: 'Dùng cho thiết bị tua-bin và bộ phận lớn.', spec: 'Phù hợp: tua-bin / bộ phận lớn', slot: 'fleet1' },
      { title: 'Xe nâng cánh tua-bin', body: 'Đáp ứng vận chuyển cánh quạt trên đường khó.', spec: 'Phù hợp: cánh quạt / đường khó', slot: 'fleet2' },
      { title: 'Nguồn lực vận chuyển bổ trợ', body: 'Khớp xe và nguồn lực theo tuyến, kích thước và hiện trường.', spec: 'Theo dự án', slot: 'fleet3' },
    ],
  },
  network: {
    eyebrow: 'Mạng lưới Trung - Việt',
    titleA: 'Kết nối Trung Quốc và Việt Nam ',
    titleB: 'thành mạng lưới dự án',
    intro: 'JIUNENG tổ chức nguồn lực qua công ty hỗ trợ phía Trung Quốc và mạng lưới đại lý hợp tác tại Việt Nam.',
    china: {
      flag: 'Phía Trung Quốc',
      name: 'Quảng Tây Cửu Nhất XNK',
      body: 'Hỗ trợ thương mại XNK và khai quan, kết nối nguồn lực điểm đi tại Trung Quốc.',
      points: ['Hỗ trợ thương mại XNK', 'Phối hợp khai quan', 'Kết nối điểm đi Trung Quốc'],
    },
    vietnam: {
      flag: 'Phía Việt Nam',
      name: 'CÔNG TY TNHH QUỐC TẾ JIUNENG',
      body: 'Qua mạng lưới đại lý hợp tác địa phương để kết nối nghiệp vụ, thực hiện dự án và điều phối nguồn lực.',
      points: ['Mạng lưới đại lý hợp tác', 'Thực hiện & phối hợp hiện trường', 'Trụ sở tại Hà Nội'],
    },
    note: 'JIUNENG hỗ trợ dịch vụ phía Việt Nam qua đại lý hợp tác, không có kho tự vận hành hay chi nhánh trực thuộc toàn quốc.',
  },
  qual: {
    eyebrow: 'Thông tin & năng lực',
    titleA: 'Thông tin doanh nghiệp ',
    titleB: 'chính thức',
    intro: 'JIUNENG gồm pháp nhân đăng ký tại Việt Nam và công ty hỗ trợ phía Trung Quốc. Dưới đây là thông tin có thể công khai.',
    entities: [
      {
        tag: 'Công ty Việt Nam',
        name: 'CÔNG TY TNHH QUỐC TẾ JIUNENG',
        rows: [
          { label: 'Tên tiếng Anh', value: 'JIUNENG INTERNATIONAL COMPANY LIMITED' },
          { label: 'Tên tiếng Trung', value: '玖能国际有限责任公司' },
          { label: 'Mã số DN', value: '0202235124' },
          { label: 'Địa chỉ', value: 'R03, Tầng 5, Số 82 phố Duy Tân, Phường Cầu Giấy, Hà Nội' },
        ],
      },
      {
        tag: 'Công ty phía Trung Quốc',
        name: 'Quảng Tây Cửu Nhất XNK',
        rows: [
          { label: 'Mã số thuế', value: '91451481595108415C' },
          { label: 'Vai trò', value: 'Công ty hỗ trợ phía Trung Quốc' },
          { label: 'Năng lực', value: 'Thương mại XNK & khai quan' },
        ],
      },
    ],
  },
  footer: {
    intro: 'Nền tảng logistics công trình cho doanh nghiệp Trung Quốc, đưa kinh nghiệm logistics công trình Trung - Việt thành nhân viên số AI để dự án phức tạp rõ ràng và kiểm soát hơn.',
    columns: [
      {
        title: 'Nhân viên số',
        links: [
          { label: 'Tư vấn báo giá', href: '#team' },
          { label: 'Chuyên viên hải quan', href: '#team' },
          { label: 'Chuyên viên chứng từ', href: '#team' },
          { label: 'Chuyên viên điều vận', href: '#team' },
          { label: 'Chuyên viên dịch thuật', href: '#team' },
        ],
      },
      {
        title: 'Kinh doanh chính',
        links: [
          { label: 'Logistics công trình', href: '#apps' },
          { label: 'Khai quan XNK', href: '#apps' },
          { label: 'Thương mại quốc tế', href: '#apps' },
          { label: 'Giải pháp', href: '#solutions' },
        ],
      },
      {
        title: 'Về JIUNENG',
        links: [
          { label: 'Nền tảng AI', href: '#brain' },
          { label: 'Dự án', href: '#cases' },
          { label: 'Liên hệ', href: '#contact' },
          { label: 'Thông tin doanh nghiệp', href: '#qual' },
        ],
      },
    ],
    legal: 'CÔNG TY TNHH QUỐC TẾ JIUNENG · Công ty TNHH XNK Cửu Nhất Quảng Tây · Thông tin đăng ký đang cập nhật',
    site: 'site.jiuneng.space',
  },
};

export const agentI18n: Record<Lang, AgentContent> = { zh, vi, en };
export const languages: Lang[] = ['zh', 'vi', 'en'];
