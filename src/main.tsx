import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { motion, useInView, useScroll, useTransform, AnimatePresence } from 'motion/react';
import './styles.css';

type Lang = 'zh' | 'vi' | 'en';
type IconProps = { size?: number; className?: string };

function Icon({ size = 24, className, children }: React.PropsWithChildren<IconProps>) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
      width={size}
    >
      {children}
    </svg>
  );
}

const ArrowRight = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5 12h14" />
    <path d="m12 5 7 7-7 7" />
  </Icon>
);
const CheckCircle2 = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="m9 12 2 2 4-5" />
  </Icon>
);
const ChevronRight = (props: IconProps) => (
  <Icon {...props}>
    <path d="m9 18 6-6-6-6" />
  </Icon>
);
const ClipboardCheck = (props: IconProps) => (
  <Icon {...props}>
    <path d="M9 5h6" />
    <path d="M9 3h6v4H9z" />
    <path d="M5 5h2" />
    <path d="M17 5h2v17H5V5" />
    <path d="m8 14 2 2 5-5" />
  </Icon>
);
const Globe2 = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20" />
    <path d="M12 2a15 15 0 0 1 0 20" />
    <path d="M12 2a15 15 0 0 0 0 20" />
  </Icon>
);
const Mail = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 4h16v16H4z" />
    <path d="m4 7 8 6 8-6" />
  </Icon>
);
const MapPin = (props: IconProps) => (
  <Icon {...props}>
    <path d="M18 8c0 5-6 10-6 10S6 13 6 8a6 6 0 1 1 12 0" />
    <circle cx="12" cy="8" r="2" />
  </Icon>
);
const Menu = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 6h16" />
    <path d="M4 12h16" />
    <path d="M4 18h16" />
  </Icon>
);
const Phone = (props: IconProps) => (
  <Icon {...props}>
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.4 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2" />
  </Icon>
);
const Route = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="6" cy="19" r="3" />
    <circle cx="18" cy="5" r="3" />
    <path d="M12 19h1a5 5 0 0 0 0-10H9a5 5 0 0 1 0-10h3" />
  </Icon>
);
const Workflow = (props: IconProps) => (
  <Icon {...props}>
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
    <path d="M6.5 10v4a2 2 0 0 0 2 2H14" />
  </Icon>
);
const FileCheck = (props: IconProps) => (
  <Icon {...props}>
    <path d="M14 3H6v18h12V7z" />
    <path d="M14 3v4h4" />
    <path d="m9 14 2 2 4-4" />
  </Icon>
);
const Building = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 21V4h11v17" />
    <path d="M15 9h5v12" />
    <path d="M8 8h3M8 12h3M8 16h3" />
  </Icon>
);
const Network = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="5" r="2.5" />
    <circle cx="5" cy="19" r="2.5" />
    <circle cx="19" cy="19" r="2.5" />
    <path d="M12 7.5V12M12 12 6.5 17M12 12l5.5 5" />
  </Icon>
);
const Layers = (props: IconProps) => (
  <Icon {...props}>
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </Icon>
);
const Wind = (props: IconProps) => (
  <Icon {...props}>
    <path d="M3 8h11a3 3 0 1 0-3-3" />
    <path d="M3 16h15a3 3 0 1 1-3 3" />
    <path d="M3 12h7" />
  </Icon>
);
const Activity = (props: IconProps) => (
  <Icon {...props}>
    <path d="M3 12h4l3 8 4-16 3 8h4" />
  </Icon>
);
const Truck = (props: IconProps) => (
  <Icon {...props}>
    <path d="M3 7h11v10H3z" />
    <path d="M14 10h4l3 3v4h-7z" />
    <circle cx="7" cy="17" r="2" />
    <circle cx="18" cy="17" r="2" />
  </Icon>
);
const Search = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </Icon>
);
const X = (props: IconProps) => (
  <Icon {...props}>
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </Icon>
);

const moduleIcons = [Search, Layers, Truck, Activity, FileCheck];
const serviceIcons = [Truck, FileCheck, Globe2];
const solutionIcons = [Route, Building, Activity, Wind];

type Entity = { tag: string; name: string; rows: { label: string; value: string }[] };

type Translation = {
  meta: { title: string; description: string };
  nav: { label: string; href: string }[];
  langName: string;
  common: {
    company: string;
    tag: string;
    submit: string;
    submitting: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    lead: string;
    primary: string;
    secondary: string;
    stats: { value: string; label: string }[];
    panelTitle: string;
    panelItems: string[];
  };
  about: {
    eyebrow: string;
    title: string;
    body: string[];
    mvv: { mission: { label: string; text: string }; vision: { label: string; text: string } };
    valuesTitle: string;
    values: { name: string; body: string }[];
    entities: Entity[];
  };
  platform: {
    eyebrow: string;
    title: string;
    intro: string;
    steps: string[];
    modulesTitle: string;
    modules: { title: string; body: string }[];
  };
  services: {
    eyebrow: string;
    title: string;
    intro: string;
    items: { title: string; body: string; points: string[] }[];
  };
  solutions: {
    eyebrow: string;
    title: string;
    intro: string;
    items: { sector: string; title: string; body: string; image: string }[];
  };
  vehicles: {
    eyebrow: string;
    title: string;
    intro: string;
    items: { title: string; body: string; spec: string; image: string }[];
  };
  cases: {
    eyebrow: string;
    title: string;
    intro: string;
    items: { title: string; type: string; body: string; tags: string[]; image: string }[];
    note: string;
  };
  network: {
    eyebrow: string;
    title: string;
    intro: string;
    china: { flag: string; name: string; body: string; points: string[] };
    vietnam: { flag: string; name: string; body: string; points: string[] };
    note: string;
  };
  qual: {
    eyebrow: string;
    title: string;
    intro: string;
    entities: Entity[];
  };
  ai: {
    eyebrow: string;
    title: string;
    intro: string;
    steps: string[];
    fields: Record<string, string>;
    placeholders: Record<string, string>;
    types: string[];
    resultTitle: string;
    fallback: string;
    disclaimer: string;
  };
  contact: {
    eyebrow: string;
    title: string;
    intro: string;
    cta: string;
    details: { label: string; value: string; pending?: boolean }[];
  };
  footer: { intro: string; site: string; legal: string };
};

const imageBase = '/assets/';

const translations: Record<Lang, Translation> = {
  zh: {
    meta: {
      title: 'JIUNENG logistics | 工程物流平台',
      description: '玖能国际是面向中国企业的工程物流平台，聚焦工程物流、进出口报关与国际贸易，以数字化系统管理客户询价到项目交付全过程。',
    },
    nav: [
      { label: '关于', href: '#about' },
      { label: '平台系统', href: '#platform' },
      { label: '服务', href: '#services' },
      { label: '解决方案', href: '#solutions' },
      { label: '案例', href: '#cases' },
      { label: '网络', href: '#network' },
      { label: '询价', href: '#consult' },
      { label: '联系', href: '#contact' },
    ],
    langName: '中文',
    common: {
      company: 'JIUNENG logistics',
      tag: 'Engineering Logistics Platform',
      submit: '提交询价',
      submitting: '正在生成评估',
    },
    hero: {
      eyebrow: '工程物流 · 进出口报关 · 国际贸易',
      title: '面向中国企业的工程物流平台',
      lead:
        '玖能国际聚焦工程物流、进出口报关与国际贸易，以数字化系统管理客户询价、方案设计、报价、业务实施和项目交付，连接中越两地资源，为复杂工程项目提供可靠支持。',
      primary: '在线询价',
      secondary: '查看项目案例',
      stats: [
        { value: 'CN-VN', label: '中越资源协同' },
        { value: '3', label: '工程物流 · 报关 · 贸易' },
        { value: '轨交·风电·电力', label: '工程解决方案' },
        { value: '2024', label: '越南公司登记' },
      ],
      panelTitle: '工程物流平台',
      panelItems: ['客户询价与需求收集', '工程条件分析与方案设计', '运输资源匹配与报价审批', '业务实施与关键节点追踪'],
    },
    about: {
      eyebrow: '关于玖能',
      title: '用工程物流平台，连接中越资源',
      body: [
        'JIUNENG logistics（玖能国际）是面向中国企业的工程物流平台，致力于为中国企业在越南开展工程项目和跨境贸易提供专业支持。',
        '平台重点发展工程物流、进出口报关和国际贸易三类业务，以物流系统管理客户询价、需求分析、方案设计、报价审批、业务实施、节点追踪和项目交付。依托广西玖一进出口贸易有限公司、越南本地合作代理网络以及专业车辆资源，帮助客户减少跨境协作中的沟通成本，提高复杂工程项目的执行效率。',
      ],
      mvv: {
        mission: { label: '使命', text: '以数字化工程物流连接中越资源，让复杂项目执行更高效、更可靠。' },
        vision: { label: '愿景', text: '打造专业的工程物流平台，成为中国企业开展中越项目时值得信赖的合作伙伴。' },
      },
      valuesTitle: '核心价值观',
      values: [
        { name: '可靠', body: '对服务边界、项目进度和客户需求保持清晰负责。' },
        { name: '专业', body: '理解工程物流、报关和贸易业务中的关键环节。' },
        { name: '协同', body: '连接中国与越南资源，减少跨境沟通成本。' },
        { name: '务实', body: '以可执行的方案解决真实问题。' },
      ],
      entities: [
        {
          tag: '越南公司',
          name: '玖能国际有限责任公司',
          rows: [
            { label: '英文名称', value: 'JIUNENG INTERNATIONAL COMPANY LIMITED' },
            { label: '企业代码', value: '0202235124' },
            { label: '登记日期', value: '2024 年 3 月 20 日' },
            { label: '地址', value: '越南河内市纸桥坊 Duy Tân 街 82 号 5 楼 R03 室' },
          ],
        },
        {
          tag: '中国侧公司',
          name: '广西玖一进出口贸易有限公司',
          rows: [
            { label: '定位', value: '中国侧业务支持公司' },
            { label: '纳税人识别号', value: '91451481595108415C' },
            { label: '能力', value: '进出口贸易与报关支持' },
          ],
        },
      ],
    },
    platform: {
      eyebrow: '工程物流平台系统',
      title: '用系统管理工程物流全过程',
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
    },
    services: {
      eyebrow: '核心业务',
      title: '三类核心业务，覆盖工程项目跨境需求',
      intro: '围绕中国企业在越南开展工程与贸易的真实需求，玖能将工程物流、进出口报关和国际贸易结合起来。',
      items: [
        {
          title: '工程物流',
          body: '面向轨道交通、基建、电力及新能源项目，提供工程物资与大型设备运输方案、特种车辆支持、项目节点管理和现场交付协调。',
          points: ['大型设备与超限货物运输', '项目节点管理', '现场交付协调'],
        },
        {
          title: '进出口报关',
          body: '依托中国侧公司和越南本地合作代理，为中越贸易业务提供单证、报关和跨境衔接支持。',
          points: ['单证准备与预审', '报关协调', '跨境流程衔接'],
        },
        {
          title: '国际贸易',
          body: '围绕中越工程项目，开展工程物资、铁路物资、基建物资、工程设备、新能源设备和电力设备相关业务。',
          points: ['工程与铁路物资', '工程与电力设备', '新能源设备'],
        },
      ],
    },
    solutions: {
      eyebrow: '解决方案',
      title: '围绕工程项目，提供可落地的运输方案',
      intro: '根据货物尺寸、重量、路线条件、装卸要求和施工节点，组织专业运输方案与现场交付协调。',
      items: [
        { sector: '轨道交通', title: '铁路物资与施工设备', body: '面向城市轨道交通项目，组织铁路物资、施工设备运输与项目节点配送。', image: 'sol-rail.jpg' },
        { sector: '基建项目', title: '工程设备与材料', body: '面向道路、桥梁等基建项目，衔接工程设备、材料的跨境运输与现场吊装交付。', image: 'sol-infra.png' },
        { sector: '电力项目', title: '电力设备运输', body: '面向火力发电及配套工程，组织变压器等大型电力设备运输与现场协调。', image: 'sol-power.png' },
        { sector: '新能源', title: '风电叶片与塔筒', body: '面向风力发电项目，使用专业车辆运输风机叶片、塔筒及大型设备。', image: 'sol-tower.jpg' },
      ],
    },
    vehicles: {
      eyebrow: '设备资源',
      title: '专业设备资源，应对复杂运输场景',
      intro: '针对新能源与大型工程设备运输需求，玖能配备专业车辆，并根据项目路线、设备尺寸和现场条件匹配运输资源。',
      items: [
        { title: '风力风机运输特种车', body: '用于风机设备与大型部件的工程运输。', spec: '适用：风机设备 / 大件部件', image: 'vehicle-fleet.jpg' },
        { title: '风机叶片举升车', body: '应对复杂道路条件下的风机叶片运输。', spec: '适用：叶片 / 复杂路况', image: 'vehicle-blade.png' },
        { title: '配套运输资源', body: '根据项目路线、设备尺寸和现场条件匹配运输车辆与资源。', spec: '按项目匹配', image: 'sol-infra.png' },
      ],
    },
    cases: {
      eyebrow: '代表项目',
      title: '用执行能力支撑复杂工程',
      intro: '以下为玖能参与的代表性工程物流项目类型，展示复杂跨境工程的执行能力。',
      items: [
        { title: '胡志明二号线', type: '城市轨道交通工程物流', body: '参与城市轨道交通项目工程物流，组织铁路与施工设备运输衔接。', tags: ['轨道交通', '工程物流'], image: 'sol-rail.jpg' },
        { title: '河内地铁 1 号线', type: '城市轨道交通工程物流', body: '参与城市轨道交通项目工程物流，协调跨境运输与项目节点。', tags: ['轨道交通', '跨境衔接'], image: 'case-portrail.png' },
        { title: '越南风力发电项目', type: '新能源工程物流', body: '参与多个越南风力发电项目，使用专业车辆运输风机叶片、塔筒等大型设备。', tags: ['新能源', '大件运输'], image: 'sol-tower.jpg' },
      ],
      note: '项目以类型与服务范围描述。具体客户名称、照片与数据将在取得授权与核验后公开。',
    },
    network: {
      eyebrow: '中越协同网络',
      title: '连接中国与越南，形成工程项目协同网络',
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
      title: '正式企业信息',
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
    ai: {
      eyebrow: '在线询价',
      title: '提交项目需求，获得线路与单证初步评估',
      intro: '该入口对接平台「询价 → 方案」流程，用于整理沟通线索。正式报价和操作计划仍需项目经理复核。',
      steps: ['填写项目需求', '系统整理线路与单证要点', '项目经理跟进正式方案'],
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
        weightEstimate: '如：18吨，长12米，宽3.2米',
        details: '请描述货物、件数、尺寸、时限和特殊要求',
      },
      types: ['工程物流', '进出口报关', '国际贸易', '解决方案咨询'],
      resultTitle: '初步评估',
      fallback: '已收到需求。建议下一步补充货物尺寸、重量、装货时间、HS 编码及目的地现场条件，以便项目经理确认线路、车型和单证路径。',
      disclaimer: '初步评估仅用于整理沟通信息，不构成正式报价或时效承诺。',
    },
    contact: {
      eyebrow: '联系我们',
      title: '把项目资料发来，我们一起把方案做实',
      intro: '适合发送装箱单、设备图纸、尺寸重量表、目的地地址、交付时间和单证状态。',
      cta: '立即沟通',
      details: [
        { label: '邮箱', value: 'quoctejiuneng@gmail.com' },
        { label: '中国咨询电话', value: '15687419919' },
        { label: '河内办公地址', value: '越南河内市纸桥坊 Duy Tân 街 82 号 5 楼 R03 室' },
        { label: '微信 / WhatsApp', value: '待补充', pending: true },
      ],
    },
    footer: {
      intro: '面向中国企业的工程物流平台，让复杂工程物流更清晰、更可控、更高效。',
      site: 'jiuneng.space',
      legal: '玖能国际有限责任公司 · 广西玖一进出口贸易有限公司 · 备案信息待补充',
    },
  },
  vi: {
    meta: {
      title: 'JIUNENG logistics | Nền tảng logistics công trình',
      description: 'JIUNENG là nền tảng logistics công trình cho doanh nghiệp Trung Quốc, tập trung logistics công trình, khai quan và thương mại quốc tế, quản lý toàn bộ quá trình từ báo giá đến bàn giao bằng hệ thống số.',
    },
    nav: [
      { label: 'Giới thiệu', href: '#about' },
      { label: 'Hệ thống', href: '#platform' },
      { label: 'Dịch vụ', href: '#services' },
      { label: 'Giải pháp', href: '#solutions' },
      { label: 'Dự án', href: '#cases' },
      { label: 'Mạng lưới', href: '#network' },
      { label: 'Báo giá', href: '#consult' },
      { label: 'Liên hệ', href: '#contact' },
    ],
    langName: 'Tiếng Việt',
    common: {
      company: 'JIUNENG logistics',
      tag: 'Engineering Logistics Platform',
      submit: 'Gửi yêu cầu',
      submitting: 'Đang tạo đánh giá',
    },
    hero: {
      eyebrow: 'Logistics công trình · Khai quan · Thương mại quốc tế',
      title: 'Nền tảng logistics công trình cho doanh nghiệp Trung Quốc',
      lead:
        'JIUNENG tập trung vào logistics công trình, khai quan và thương mại quốc tế, quản lý báo giá, thiết kế phương án, thực hiện và bàn giao dự án bằng hệ thống số, kết nối nguồn lực hai bên Trung - Việt cho các dự án công trình phức tạp.',
      primary: 'Báo giá trực tuyến',
      secondary: 'Xem dự án',
      stats: [
        { value: 'CN-VN', label: 'Phối hợp Trung - Việt' },
        { value: '3', label: 'Logistics · Khai quan · Thương mại' },
        { value: 'Đường sắt·Điện gió·Điện', label: 'Giải pháp công trình' },
        { value: '2024', label: 'Đăng ký tại Việt Nam' },
      ],
      panelTitle: 'Nền tảng logistics công trình',
      panelItems: ['Báo giá và thu thập nhu cầu', 'Phân tích điều kiện và thiết kế phương án', 'Khớp nguồn lực và duyệt báo giá', 'Thực hiện và theo dõi các mốc'],
    },
    about: {
      eyebrow: 'Về JIUNENG',
      title: 'Kết nối nguồn lực Trung - Việt bằng nền tảng logistics công trình',
      body: [
        'JIUNENG logistics là nền tảng logistics công trình dành cho doanh nghiệp Trung Quốc, hỗ trợ triển khai dự án công trình và thương mại xuyên biên giới tại Việt Nam.',
        'Nền tảng phát triển ba mảng: logistics công trình, khai quan và thương mại quốc tế; quản lý báo giá, phân tích nhu cầu, thiết kế phương án, duyệt giá, thực hiện, theo dõi mốc và bàn giao bằng hệ thống logistics. Dựa trên công ty hỗ trợ phía Trung Quốc, mạng lưới đại lý hợp tác tại Việt Nam và nguồn lực xe chuyên dụng, JIUNENG giúp giảm chi phí trao đổi và nâng cao hiệu quả thực hiện dự án.',
      ],
      mvv: {
        mission: { label: 'Sứ mệnh', text: 'Kết nối nguồn lực Trung - Việt bằng logistics công trình số hóa, giúp dự án phức tạp được thực hiện hiệu quả và đáng tin cậy hơn.' },
        vision: { label: 'Tầm nhìn', text: 'Xây dựng nền tảng logistics công trình chuyên nghiệp, trở thành đối tác đáng tin cậy của doanh nghiệp Trung Quốc.' },
      },
      valuesTitle: 'Giá trị cốt lõi',
      values: [
        { name: 'Đáng tin cậy', body: 'Rõ ràng và có trách nhiệm về phạm vi dịch vụ, tiến độ và nhu cầu khách hàng.' },
        { name: 'Chuyên nghiệp', body: 'Hiểu các mắt xích quan trọng của logistics công trình, khai quan và thương mại.' },
        { name: 'Phối hợp', body: 'Kết nối nguồn lực Trung Quốc và Việt Nam, giảm chi phí trao đổi.' },
        { name: 'Thực tế', body: 'Giải quyết vấn đề thực bằng phương án khả thi.' },
      ],
      entities: [
        {
          tag: 'Công ty Việt Nam',
          name: 'CÔNG TY TNHH QUỐC TẾ JIUNENG',
          rows: [
            { label: 'Tên tiếng Anh', value: 'JIUNENG INTERNATIONAL COMPANY LIMITED' },
            { label: 'Mã số DN', value: '0202235124' },
            { label: 'Ngày đăng ký', value: '20/03/2024' },
            { label: 'Địa chỉ', value: 'R03, Tầng 5, Số 82 phố Duy Tân, Phường Cầu Giấy, Hà Nội' },
          ],
        },
        {
          tag: 'Công ty phía Trung Quốc',
          name: 'Quảng Tây Cửu Nhất XNK',
          rows: [
            { label: 'Vai trò', value: 'Công ty hỗ trợ phía Trung Quốc' },
            { label: 'Mã số thuế', value: '91451481595108415C' },
            { label: 'Năng lực', value: 'Thương mại XNK và hỗ trợ khai quan' },
          ],
        },
      ],
    },
    platform: {
      eyebrow: 'Hệ thống nền tảng logistics công trình',
      title: 'Quản lý toàn bộ quá trình logistics công trình bằng hệ thống',
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
    },
    services: {
      eyebrow: 'Mảng kinh doanh cốt lõi',
      title: 'Ba mảng cốt lõi cho nhu cầu xuyên biên giới',
      intro: 'Xoay quanh nhu cầu thực của doanh nghiệp Trung Quốc tại Việt Nam, JIUNENG kết hợp logistics công trình, khai quan và thương mại quốc tế.',
      items: [
        {
          title: 'Logistics công trình',
          body: 'Cho dự án đường sắt đô thị, hạ tầng, điện và năng lượng mới: phương án vận chuyển thiết bị lớn, hỗ trợ xe chuyên dụng, quản lý mốc và phối hợp giao tại hiện trường.',
          points: ['Vận chuyển thiết bị lớn & quá khổ', 'Quản lý mốc dự án', 'Phối hợp giao hiện trường'],
        },
        {
          title: 'Khai quan XNK',
          body: 'Dựa trên công ty phía Trung Quốc và đại lý hợp tác Việt Nam, hỗ trợ chứng từ, khai quan và kết nối xuyên biên giới.',
          points: ['Chuẩn bị & tiền kiểm chứng từ', 'Phối hợp khai quan', 'Kết nối quy trình xuyên biên giới'],
        },
        {
          title: 'Thương mại quốc tế',
          body: 'Quanh các dự án công trình Trung - Việt: vật tư công trình, vật tư đường sắt, hạ tầng, thiết bị công trình, thiết bị năng lượng mới và thiết bị điện.',
          points: ['Vật tư công trình & đường sắt', 'Thiết bị công trình & điện', 'Thiết bị năng lượng mới'],
        },
      ],
    },
    solutions: {
      eyebrow: 'Giải pháp',
      title: 'Phương án vận chuyển khả thi cho từng dự án',
      intro: 'Tổ chức phương án vận chuyển chuyên nghiệp và phối hợp giao hiện trường theo kích thước, trọng lượng, tuyến đường và mốc thi công.',
      items: [
        { sector: 'Đường sắt đô thị', title: 'Vật tư & thiết bị thi công', body: 'Cho dự án đường sắt đô thị: tổ chức vận chuyển vật tư, thiết bị thi công và phân phối theo mốc.', image: 'sol-rail.jpg' },
        { sector: 'Hạ tầng', title: 'Thiết bị & vật liệu', body: 'Cho dự án đường, cầu: kết nối vận chuyển thiết bị, vật liệu và cẩu hạ tại hiện trường.', image: 'sol-infra.png' },
        { sector: 'Điện', title: 'Vận chuyển thiết bị điện', body: 'Cho nhà máy nhiệt điện: vận chuyển máy biến áp và thiết bị điện lớn, phối hợp hiện trường.', image: 'sol-power.png' },
        { sector: 'Năng lượng mới', title: 'Cánh & tháp điện gió', body: 'Cho dự án điện gió: dùng xe chuyên dụng vận chuyển cánh quạt, tháp và thiết bị lớn.', image: 'sol-tower.jpg' },
      ],
    },
    vehicles: {
      eyebrow: 'Nguồn lực thiết bị',
      title: 'Thiết bị chuyên dụng cho các tình huống phức tạp',
      intro: 'Cho nhu cầu vận chuyển thiết bị năng lượng mới và công trình lớn, JIUNENG trang bị xe chuyên dụng và khớp nguồn lực theo tuyến, kích thước và điều kiện hiện trường.',
      items: [
        { title: 'Xe chuyên dụng vận chuyển tua-bin gió', body: 'Dùng cho thiết bị tua-bin và bộ phận lớn.', spec: 'Phù hợp: tua-bin / bộ phận lớn', image: 'vehicle-fleet.jpg' },
        { title: 'Xe nâng cánh tua-bin', body: 'Đáp ứng vận chuyển cánh quạt trên đường khó.', spec: 'Phù hợp: cánh quạt / đường khó', image: 'vehicle-blade.png' },
        { title: 'Nguồn lực vận chuyển bổ trợ', body: 'Khớp xe và nguồn lực theo tuyến, kích thước và hiện trường.', spec: 'Theo dự án', image: 'sol-infra.png' },
      ],
    },
    cases: {
      eyebrow: 'Dự án tiêu biểu',
      title: 'Năng lực thực thi cho công trình phức tạp',
      intro: 'Các loại dự án logistics công trình tiêu biểu mà JIUNENG tham gia, thể hiện năng lực thực thi xuyên biên giới.',
      items: [
        { title: 'Tuyến số 2 TP.HCM', type: 'Logistics đường sắt đô thị', body: 'Tham gia logistics dự án đường sắt đô thị, tổ chức kết nối vận chuyển vật tư và thiết bị thi công.', tags: ['Đường sắt', 'Logistics công trình'], image: 'sol-rail.jpg' },
        { title: 'Metro Hà Nội tuyến 1', type: 'Logistics đường sắt đô thị', body: 'Tham gia logistics dự án đường sắt đô thị, phối hợp vận chuyển xuyên biên giới và mốc dự án.', tags: ['Đường sắt', 'Kết nối xuyên biên'], image: 'case-portrail.png' },
        { title: 'Dự án điện gió Việt Nam', type: 'Logistics năng lượng mới', body: 'Tham gia nhiều dự án điện gió, dùng xe chuyên dụng vận chuyển cánh quạt, tháp và thiết bị lớn.', tags: ['Năng lượng mới', 'Hàng quá khổ'], image: 'sol-tower.jpg' },
      ],
      note: 'Dự án mô tả theo loại hình và phạm vi dịch vụ. Tên khách hàng, hình ảnh và số liệu cụ thể sẽ công khai sau khi được ủy quyền và xác minh.',
    },
    network: {
      eyebrow: 'Mạng lưới Trung - Việt',
      title: 'Kết nối Trung Quốc và Việt Nam thành mạng lưới dự án',
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
      title: 'Thông tin doanh nghiệp chính thức',
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
    ai: {
      eyebrow: 'Báo giá trực tuyến',
      title: 'Gửi nhu cầu để nhận đánh giá tuyến và chứng từ',
      intro: 'Kết nối quy trình "báo giá → phương án" của nền tảng, dùng để sắp xếp thông tin. Báo giá và kế hoạch chính thức cần quản lý dự án kiểm tra.',
      steps: ['Điền nhu cầu dự án', 'Hệ thống sắp xếp tuyến & chứng từ', 'Quản lý dự án theo dõi phương án'],
      fields: {
        name: 'Người liên hệ',
        company: 'Công ty',
        inquiryType: 'Loại nghiệp vụ',
        loadingPort: 'Điểm đi',
        dischargePort: 'Điểm đến',
        weightEstimate: 'Trọng lượng / thể tích',
        details: 'Chi tiết dự án',
      },
      placeholders: {
        name: 'Nhập họ tên',
        company: 'Tên công ty hoặc dự án',
        loadingPort: 'VD: nhà máy Phật Sơn / cảng Thâm Quyến',
        dischargePort: 'VD: Hà Nội / Hải Phòng / TP.HCM',
        weightEstimate: 'VD: 18 tấn, dài 12m, rộng 3.2m',
        details: 'Mô tả hàng hóa, số kiện, kích thước, thời hạn và yêu cầu đặc biệt',
      },
      types: ['Logistics công trình', 'Khai quan XNK', 'Thương mại quốc tế', 'Tư vấn giải pháp'],
      resultTitle: 'Đánh giá ban đầu',
      fallback: 'Đã nhận nhu cầu. Bước tiếp theo nên bổ sung kích thước, trọng lượng, thời gian xếp hàng, mã HS và điều kiện hiện trường để quản lý dự án xác nhận tuyến, loại xe và chứng từ.',
      disclaimer: 'Đánh giá ban đầu chỉ để sắp xếp thông tin, không phải báo giá hay cam kết thời gian.',
    },
    contact: {
      eyebrow: 'Liên hệ',
      title: 'Gửi hồ sơ dự án, chúng ta cùng hoàn thiện phương án',
      intro: 'Phù hợp gửi packing list, bản vẽ thiết bị, bảng kích thước trọng lượng, địa chỉ đích, thời gian giao và trạng thái chứng từ.',
      cta: 'Trao đổi ngay',
      details: [
        { label: 'Email', value: 'quoctejiuneng@gmail.com' },
        { label: 'Hotline Trung Quốc', value: '15687419919' },
        { label: 'Văn phòng Hà Nội', value: 'R03, Tầng 5, Số 82 phố Duy Tân, Phường Cầu Giấy, Hà Nội' },
        { label: 'WeChat / WhatsApp', value: 'Đang cập nhật', pending: true },
      ],
    },
    footer: {
      intro: 'Nền tảng logistics công trình cho doanh nghiệp Trung Quốc, giúp logistics công trình rõ ràng, kiểm soát và hiệu quả hơn.',
      site: 'jiuneng.space',
      legal: 'CÔNG TY TNHH QUỐC TẾ JIUNENG · Quảng Tây Cửu Nhất XNK · Thông tin pháp lý đang cập nhật',
    },
  },
  en: {
    meta: {
      title: 'JIUNENG logistics | Engineering Logistics Platform',
      description: 'JIUNENG is an engineering logistics platform for Chinese enterprises, focused on engineering logistics, import-export customs, and international trade, managing the full process from inquiry to delivery with a digital system.',
    },
    nav: [
      { label: 'About', href: '#about' },
      { label: 'Platform', href: '#platform' },
      { label: 'Services', href: '#services' },
      { label: 'Solutions', href: '#solutions' },
      { label: 'Cases', href: '#cases' },
      { label: 'Network', href: '#network' },
      { label: 'Inquiry', href: '#consult' },
      { label: 'Contact', href: '#contact' },
    ],
    langName: 'English',
    common: {
      company: 'JIUNENG logistics',
      tag: 'Engineering Logistics Platform',
      submit: 'Submit inquiry',
      submitting: 'Generating assessment',
    },
    hero: {
      eyebrow: 'Engineering logistics · Customs · International trade',
      title: 'An engineering logistics platform for Chinese enterprises',
      lead:
        'JIUNENG focuses on engineering logistics, import-export customs, and international trade. We manage inquiry, planning, quotation, execution, and delivery through a digital system, connecting China and Vietnam resources for complex engineering projects.',
      primary: 'Online inquiry',
      secondary: 'View project cases',
      stats: [
        { value: 'CN-VN', label: 'China-Vietnam coordination' },
        { value: '3', label: 'Logistics · Customs · Trade' },
        { value: 'Rail·Wind·Power', label: 'Engineering solutions' },
        { value: '2024', label: 'Registered in Vietnam' },
      ],
      panelTitle: 'Engineering logistics platform',
      panelItems: ['Inquiry and requirement intake', 'Condition analysis and planning', 'Resource matching and quote approval', 'Execution and milestone tracking'],
    },
    about: {
      eyebrow: 'About JIUNENG',
      title: 'Connecting China-Vietnam resources through an engineering logistics platform',
      body: [
        'JIUNENG logistics is an engineering logistics platform for Chinese enterprises, supporting engineering projects and cross-border trade in Vietnam.',
        'The platform develops three business areas — engineering logistics, import-export customs, and international trade — managing inquiry, requirement analysis, planning, quote approval, execution, milestone tracking, and delivery through a logistics system. Backed by a China-side support company, a Vietnam local partner-agent network, and specialized vehicle resources, JIUNENG reduces cross-border communication cost and improves execution efficiency for complex projects.',
      ],
      mvv: {
        mission: { label: 'Mission', text: 'Connect China-Vietnam resources through digital engineering logistics, making complex project execution more efficient and reliable.' },
        vision: { label: 'Vision', text: 'Build a professional engineering logistics platform and become a trusted partner for Chinese enterprises operating China-Vietnam projects.' },
      },
      valuesTitle: 'Core values',
      values: [
        { name: 'Reliable', body: 'Clear and accountable on service scope, project progress, and client needs.' },
        { name: 'Professional', body: 'Understand the key links in engineering logistics, customs, and trade.' },
        { name: 'Collaborative', body: 'Connect China and Vietnam resources to cut cross-border communication cost.' },
        { name: 'Practical', body: 'Solve real problems with executable plans.' },
      ],
      entities: [
        {
          tag: 'Vietnam company',
          name: 'JIUNENG INTERNATIONAL COMPANY LIMITED',
          rows: [
            { label: 'Vietnamese', value: 'CÔNG TY TNHH QUỐC TẾ JIUNENG' },
            { label: 'Enterprise code', value: '0202235124' },
            { label: 'Registered', value: '20 Mar 2024' },
            { label: 'Address', value: 'R03, 5th Floor, 82 Duy Tan St., Cau Giay Ward, Hanoi' },
          ],
        },
        {
          tag: 'China-side company',
          name: 'Guangxi Jiuyi Import & Export Trading Co., Ltd.',
          rows: [
            { label: 'Role', value: 'China-side business support company' },
            { label: 'Tax ID', value: '91451481595108415C' },
            { label: 'Capability', value: 'Import-export trade & customs support' },
          ],
        },
      ],
    },
    platform: {
      eyebrow: 'Engineering logistics platform system',
      title: 'Manage the full engineering logistics process with a system',
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
    },
    services: {
      eyebrow: 'Core businesses',
      title: 'Three core businesses for cross-border engineering needs',
      intro: 'Around the real needs of Chinese enterprises in Vietnam, JIUNENG integrates engineering logistics, customs, and international trade.',
      items: [
        {
          title: 'Engineering logistics',
          body: 'For rail transit, infrastructure, power, and new-energy projects: transport plans for materials and large equipment, specialized vehicle support, milestone management, and on-site delivery coordination.',
          points: ['Large & oversized cargo transport', 'Project milestone management', 'On-site delivery coordination'],
        },
        {
          title: 'Import-export customs',
          body: 'Backed by the China-side company and Vietnam local partner-agents, supporting documentation, customs, and cross-border coordination for China-Vietnam trade.',
          points: ['Document prep & pre-check', 'Customs coordination', 'Cross-border process linkage'],
        },
        {
          title: 'International trade',
          body: 'Around China-Vietnam engineering projects: engineering materials, railway materials, infrastructure materials, equipment, new-energy equipment, and power equipment.',
          points: ['Engineering & railway materials', 'Engineering & power equipment', 'New-energy equipment'],
        },
      ],
    },
    solutions: {
      eyebrow: 'Solutions',
      title: 'Workable transport plans around engineering projects',
      intro: 'We organize professional transport plans and on-site delivery based on cargo dimensions, weight, route conditions, handling needs, and construction milestones.',
      items: [
        { sector: 'Rail transit', title: 'Railway materials & equipment', body: 'For urban rail transit: railway materials, construction equipment transport, and milestone distribution.', image: 'sol-rail.jpg' },
        { sector: 'Infrastructure', title: 'Equipment & materials', body: 'For road and bridge projects: cross-border transport of equipment and materials with on-site lifting.', image: 'sol-infra.png' },
        { sector: 'Power', title: 'Power equipment transport', body: 'For thermal power and supporting works: transformer and large power-equipment transport with on-site coordination.', image: 'sol-power.png' },
        { sector: 'New energy', title: 'Wind blades & towers', body: 'For wind power projects: specialized vehicles transporting wind blades, towers, and large equipment.', image: 'sol-tower.jpg' },
      ],
    },
    vehicles: {
      eyebrow: 'Equipment resources',
      title: 'Specialized equipment for complex transport scenarios',
      intro: 'For new-energy and large engineering equipment, JIUNENG provides specialized vehicles and matches resources to project route, equipment size, and site conditions.',
      items: [
        { title: 'Wind-turbine transport vehicle', body: 'For turbine equipment and large components.', spec: 'For: turbines / large parts', image: 'vehicle-fleet.jpg' },
        { title: 'Wind-blade lifting vehicle', body: 'Handles blade transport on complex road conditions.', spec: 'For: blades / complex roads', image: 'vehicle-blade.png' },
        { title: 'Supporting transport resources', body: 'Match vehicles and resources by route, equipment size, and site conditions.', spec: 'Matched per project', image: 'sol-infra.png' },
      ],
    },
    cases: {
      eyebrow: 'Project cases',
      title: 'Execution capability for complex engineering',
      intro: 'Representative engineering logistics project types JIUNENG has participated in, showing cross-border execution capability.',
      items: [
        { title: 'HCMC Metro Line 2', type: 'Urban rail engineering logistics', body: 'Participated in urban rail project logistics, organizing railway and construction equipment transport linkage.', tags: ['Rail transit', 'Engineering logistics'], image: 'sol-rail.jpg' },
        { title: 'Hanoi Metro Line 1', type: 'Urban rail engineering logistics', body: 'Participated in urban rail project logistics, coordinating cross-border transport and project milestones.', tags: ['Rail transit', 'Cross-border'], image: 'case-portrail.png' },
        { title: 'Vietnam wind power projects', type: 'New-energy engineering logistics', body: 'Participated in multiple Vietnam wind power projects, transporting blades, towers, and large equipment with specialized vehicles.', tags: ['New energy', 'Heavy cargo'], image: 'sol-tower.jpg' },
      ],
      note: 'Projects are described by type and service scope. Specific client names, photos, and data will be published after authorization and verification.',
    },
    network: {
      eyebrow: 'China-Vietnam network',
      title: 'Connecting China and Vietnam into a project network',
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
      title: 'Official company information',
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
    ai: {
      eyebrow: 'Online inquiry',
      title: 'Submit project needs for route and document assessment',
      intro: 'This entry connects to the platform "inquiry → plan" flow to structure early communication. Formal quotes and operating plans still require project-manager review.',
      steps: ['Fill in project needs', 'System structures route & document points', 'Project manager follows up the formal plan'],
      fields: {
        name: 'Contact name',
        company: 'Company',
        inquiryType: 'Business type',
        loadingPort: 'Origin',
        dischargePort: 'Destination',
        weightEstimate: 'Weight / volume',
        details: 'Project details',
      },
      placeholders: {
        name: 'Enter your name',
        company: 'Company or project name',
        loadingPort: 'E.g. Foshan factory / Shenzhen port',
        dischargePort: 'E.g. Hanoi / Haiphong / HCMC',
        weightEstimate: 'E.g. 18 tons, 12m long, 3.2m wide',
        details: 'Describe cargo, pieces, dimensions, timeline, and special requirements',
      },
      types: ['Engineering logistics', 'Import-export customs', 'International trade', 'Solution consulting'],
      resultTitle: 'Initial assessment',
      fallback: 'Request received. Next, please add cargo dimensions, weight, loading time, HS code, and destination site conditions so the project manager can confirm route, vehicle type, and document path.',
      disclaimer: 'The initial assessment only structures communication and is not a formal quote or time commitment.',
    },
    contact: {
      eyebrow: 'Contact',
      title: 'Send the project files and we will firm up the plan together',
      intro: 'Useful files: packing lists, equipment drawings, dimension and weight sheets, destination address, delivery timing, and document status.',
      cta: 'Start a conversation',
      details: [
        { label: 'Email', value: 'quoctejiuneng@gmail.com' },
        { label: 'China hotline', value: '15687419919' },
        { label: 'Hanoi office', value: 'R03, 5th Floor, 82 Duy Tan St., Cau Giay Ward, Hanoi' },
        { label: 'WeChat / WhatsApp', value: 'Coming soon', pending: true },
      ],
    },
    footer: {
      intro: 'An engineering logistics platform for Chinese enterprises, making complex engineering logistics clearer, more controllable, and more efficient.',
      site: 'jiuneng.space',
      legal: 'JIUNENG INTERNATIONAL CO., LTD · Guangxi Jiuyi Import & Export Trading Co., Ltd · Filing info pending',
    },
  },
};

const languages: Lang[] = ['zh', 'vi', 'en'];

function getInitialLang(): Lang {
  const stored = window.localStorage.getItem('jiuneng-lang') as Lang | null;
  if (stored && languages.includes(stored)) return stored;
  const browser = navigator.language.toLowerCase();
  if (browser.startsWith('vi')) return 'vi';
  if (browser.startsWith('en')) return 'en';
  return 'zh';
}

function SectionHeading({ eyebrow, title, intro }: { eyebrow: string; title: string; intro?: string }) {
  return (
    <div className="section-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {intro ? <p>{intro}</p> : null}
    </div>
  );
}

const EntityCard: React.FC<{ entity: Entity }> = ({ entity }) => {
  return (
    <article className="about-card">
      <span className="tag">{entity.tag}</span>
      <h3>{entity.name}</h3>
      <dl>
        {entity.rows.map((row) => (
          <div className="row" key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
};

/* ── Animated section wrapper ── */
const Section: React.FC<{
  id?: string;
  className?: string;
  children: React.ReactNode;
  delay?: number;
  direction?: 'up' | 'left' | 'right' | 'scale';
}> = ({ id, className, children, delay = 0, direction = 'up' }) => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-60px' });
  const variants = {
    up: { opacity: 0, y: 24 },
    left: { opacity: 0, x: -24 },
    right: { opacity: 0, x: 24 },
    scale: { opacity: 0 },
  };
  return (
    <motion.section
      id={id}
      ref={ref}
      className={className}
      initial={variants[direction]}
      animate={isInView ? { opacity: 1, x: 0, y: 0 } : variants[direction]}
      transition={{ duration: 0.4, delay, ease: [0.3, 0, 0, 1] }}
    >
      {children}
    </motion.section>
  );
};

/* ── Animated list item ── */
const StaggerItem: React.FC<{
  index: number;
  children: React.ReactNode;
  className?: string;
}> = ({ index, children, className }) => {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });
  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, y: 16 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.3, delay: index * 0.06, ease: [0.3, 0, 0, 1] }}
    >
      {children}
    </motion.div>
  );
};

/* ── Animated counter ── */
const AnimatedCounter: React.FC<{ value: string; label: string }> = ({ value, label }) => {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0 }}
      animate={isInView ? { opacity: 1 } : {}}
      transition={{ duration: 0.3 }}
    >
      <motion.strong
        initial={{ opacity: 0, y: 6 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.25, delay: 0.1 }}
      >
        {value}
      </motion.strong>
      <motion.span
        initial={{ opacity: 0 }}
        animate={isInView ? { opacity: 1 } : {}}
        transition={{ duration: 0.2, delay: 0.2 }}
      >
        {label}
      </motion.span>
    </motion.div>
  );
};

function App() {
  const [lang, setLang] = useState<Lang>(getInitialLang);
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [form, setForm] = useState({
    name: '',
    company: '',
    inquiryType: translations[lang].ai.types[0],
    loadingPort: '',
    dischargePort: '',
    weightEstimate: '',
    details: '',
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string>('');

  const t = translations[lang];

  /* ── Scroll listener for nav ── */
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  /* ── Auto-close mobile menu on resize ── */
  useEffect(() => {
    const onResize = () => { if (window.innerWidth > 980) setMenuOpen(false); };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang === 'vi' ? 'vi-VN' : 'en';
    document.title = t.meta.title;
    const meta = document.querySelector('meta[name="description"]');
    meta?.setAttribute('content', t.meta.description);
    window.localStorage.setItem('jiuneng-lang', lang);
    setForm((current) => ({ ...current, inquiryType: translations[lang].ai.types[0] }));
  }, [lang, t.meta.description, t.meta.title]);

  const heroImage = useMemo(() => `${imageBase}hero-wind-tower.png`, []);
  const logo = `${imageBase}logo-horizontal.svg`;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setResult('');

    try {
      const response = await fetch('/api/logistics-consult', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, language: lang }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Request failed');

      const segments = [
        data.routeRecommendation,
        Array.isArray(data.documentChecklist) ? data.documentChecklist.join('\n') : '',
        data.hsCodeAdvice,
        Array.isArray(data.riskMitigation) ? data.riskMitigation.join('\n') : '',
        data.consultantStatement,
      ].filter(Boolean);

      setResult(segments.length ? segments.join('\n\n') : t.ai.fallback);
    } catch {
      setResult(t.ai.fallback);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="site-shell">
      <header className={`nav ${scrolled ? 'scrolled' : ''}`}>
        <a className="brand" href="#top" aria-label={t.common.company}>
          <img className="brand-logo" src={logo} alt={t.common.company} />
        </a>

        <nav className="desktop-links" aria-label="Primary">
          {t.nav.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
            </a>
          ))}
        </nav>

        <div className="nav-actions">
          <div className="language-switcher" aria-label="Language selector">
            <Globe2 size={16} />
            {languages.map((code) => (
              <button className={lang === code ? 'active' : ''} key={code} onClick={() => setLang(code)} type="button">
                {code.toUpperCase()}
              </button>
            ))}
          </div>
          <button className="menu-button" onClick={() => setMenuOpen((open) => !open)} type="button" aria-label="Menu">
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </header>

      <AnimatePresence>
        {menuOpen ? (
          <motion.div
            className="mobile-menu"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15, ease: [0.3, 0, 0, 1] }}
          >
            {t.nav.map((item) => (
              <a key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>
                {item.label}
              </a>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>

      <main id="top">
        {/* Hero */}
        <section className="hero">
          <motion.div
            className="hero-media"
            aria-hidden="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, ease: [0.3, 0, 0, 1] }}
          >
            <img src={heroImage} alt="" />
          </motion.div>
          <div className="hero-overlay" />
          <div className="hero-content">
            <motion.div
              className="hero-copy"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.3, 0, 0, 1] }}
            >
              <p className="eyebrow">{t.hero.eyebrow}</p>
              <h1>{t.hero.title}</h1>
              <p className="hero-lead">{t.hero.lead}</p>
              <div className="hero-buttons">
                <a className="button primary" href="#consult">
                  {t.hero.primary}
                  <ArrowRight size={18} />
                </a>
                <a className="button secondary" href="#cases">
                  {t.hero.secondary}
                </a>
              </div>
            </motion.div>

            <motion.aside
              className="hero-panel"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.2, ease: [0.3, 0, 0, 1] }}
            >
              <div className="panel-top">
                <span className="status-dot" />
                <span>{t.hero.panelTitle}</span>
              </div>
              <div className="panel-list">
                {t.hero.panelItems.map((item) => (
                  <div key={item}>
                    <CheckCircle2 size={17} />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </motion.aside>

            <motion.div
              className="hero-stats"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.35, ease: [0.3, 0, 0, 1] }}
            >
              {t.hero.stats.map((stat) => (
                <AnimatedCounter key={stat.label} value={stat.value} label={stat.label} />
              ))}
            </motion.div>
          </div>
        </section>

        {/* About */}
        <Section id="about" className="section">
          <SectionHeading eyebrow={t.about.eyebrow} title={t.about.title} />
          <div className="about-grid">
            <div className="about-body">
              {t.about.body.map((p) => (
                <p key={p}>{p}</p>
              ))}
              <div className="mvv-grid">
                <div className="mvv-card">
                  <span>{t.about.mvv.mission.label}</span>
                  <p>{t.about.mvv.mission.text}</p>
                </div>
                <div className="mvv-card">
                  <span>{t.about.mvv.vision.label}</span>
                  <p>{t.about.mvv.vision.text}</p>
                </div>
              </div>
            </div>
            <div className="about-media">
              <img src={`${imageBase}team-collab.png`} alt="" />
            </div>
          </div>

          <div className="values-grid">
            {t.about.values.map((v) => (
              <div className="value-card" key={v.name}>
                <strong>{v.name}</strong>
                <p>{v.body}</p>
              </div>
            ))}
          </div>

          <div className="entity-cards">
            {t.about.entities.map((entity) => (
              <EntityCard entity={entity} key={entity.name} />
            ))}
          </div>
        </Section>

        {/* Platform system */}
        <Section id="platform" className="platform-band">
          <div className="section platform-inner">
            <SectionHeading eyebrow={t.platform.eyebrow} title={t.platform.title} intro={t.platform.intro} />
            <div className="platform-flow">
              {t.platform.steps.map((step, index) => (
                <div className="flow-step" key={step}>
                  <b>{String(index + 1).padStart(2, '0')}</b>
                  <span>{step}</span>
                </div>
              ))}
            </div>

            <div className="platform-systems">
              <div className="modules-grid">
                {t.platform.modules.map((m, index) => {
                  const ModuleIcon = moduleIcons[index];
                  return (
                    <article className="module-card" key={m.title}>
                      <ModuleIcon size={24} />
                      <div>
                        <h3>{m.title}</h3>
                        <p>{m.body}</p>
                      </div>
                    </article>
                  );
                })}
              </div>
              <div className="platform-shots">
                <img src={`${imageBase}system-overview.png`} alt="" />
                <img src={`${imageBase}system-tracking.png`} alt="" />
              </div>
            </div>
          </div>
        </Section>

        {/* Core services */}
        <Section id="services" className="section">
          <SectionHeading eyebrow={t.services.eyebrow} title={t.services.title} intro={t.services.intro} />
          <div className="service-grid">
            {t.services.items.map((item, index) => {
              const ServiceIcon = serviceIcons[index];
              return (
                <article className="service-card" key={item.title}>
                  <span className="num">{String(index + 1).padStart(2, '0')}</span>
                  <ServiceIcon size={28} />
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <ul>
                    {item.points.map((pt) => (
                      <li key={pt}>{pt}</li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        </Section>

        {/* Solutions */}
        <Section id="solutions" className="route-band">
          <div className="section">
            <SectionHeading eyebrow={t.solutions.eyebrow} title={t.solutions.title} intro={t.solutions.intro} />
            <div className="solutions-grid">
              {t.solutions.items.map((item, index) => {
                const SolutionIcon = solutionIcons[index];
                return (
                  <article className="solution-card" key={item.sector}>
                    <img src={`${imageBase}${item.image}`} alt={item.title} />
                    <div className="body">
                      <span>
                        <SolutionIcon size={14} /> {item.sector}
                      </span>
                      <h3>{item.title}</h3>
                      <p>{item.body}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </Section>

        {/* Vehicles */}
        <Section id="vehicles" className="section">
          <SectionHeading eyebrow={t.vehicles.eyebrow} title={t.vehicles.title} intro={t.vehicles.intro} />
          <div className="vehicles-grid">
            {t.vehicles.items.map((item) => (
              <article className="vehicle-card" key={item.title}>
                <img src={`${imageBase}${item.image}`} alt={item.title} />
                <div className="body">
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <span className="spec">{item.spec}</span>
                </div>
              </article>
            ))}
          </div>
        </Section>

        {/* Cases */}
        <Section id="cases" className="section">
          <SectionHeading eyebrow={t.cases.eyebrow} title={t.cases.title} intro={t.cases.intro} />
          <div className="case-grid">
            {t.cases.items.map((item) => (
              <article className="case-card" key={item.title}>
                <img src={`${imageBase}${item.image}`} alt={item.title} />
                <div className="body">
                  <span>{item.type}</span>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <div className="case-tags">
                    {item.tags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
          <p className="network-note">{t.cases.note}</p>
        </Section>

        {/* Network */}
        <Section id="network" className="route-band">
          <div className="section">
            <SectionHeading eyebrow={t.network.eyebrow} title={t.network.title} intro={t.network.intro} />
            <div className="network-grid">
              {[t.network.china, t.network.vietnam].map((col) => (
                <article className="network-col" key={col.name}>
                  <span className="flag">
                    <Network size={16} /> {col.flag}
                  </span>
                  <h3>{col.name}</h3>
                  <p>{col.body}</p>
                  <ul>
                    {col.points.map((pt) => (
                      <li key={pt}>{pt}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
            <p className="network-note">{t.network.note}</p>
          </div>
        </Section>

        {/* Qualifications */}
        <Section id="qual" className="section">
          <SectionHeading eyebrow={t.qual.eyebrow} title={t.qual.title} intro={t.qual.intro} />
          <div className="qual-grid">
            {t.qual.entities.map((entity) => (
              <article className="qual-card" key={entity.name}>
                <h3>
                  {entity.tag} · {entity.name}
                </h3>
                <dl>
                  {entity.rows.map((row) => (
                    <div className="row" key={row.label}>
                      <dt>{row.label}</dt>
                      <dd>{row.value}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
        </Section>

        {/* Online inquiry */}
        <Section id="consult" className="consult-band">
          <div className="section consult-grid">
            <div>
              <SectionHeading eyebrow={t.ai.eyebrow} title={t.ai.title} intro={t.ai.intro} />
              <div className="consult-note">
                <Workflow size={22} />
                <p>{t.contact.intro}</p>
              </div>
              <div className="consult-steps">
                {t.ai.steps.map((step) => (
                  <div key={step}>
                    <ChevronRight size={16} />
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>

            <form className="consult-form" onSubmit={handleSubmit}>
              <label>
                {t.ai.fields.name}
                <input required value={form.name} placeholder={t.ai.placeholders.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
              </label>
              <label>
                {t.ai.fields.company}
                <input value={form.company} placeholder={t.ai.placeholders.company} onChange={(event) => setForm({ ...form, company: event.target.value })} />
              </label>
              <label>
                {t.ai.fields.inquiryType}
                <select value={form.inquiryType} onChange={(event) => setForm({ ...form, inquiryType: event.target.value })}>
                  {t.ai.types.map((type) => (
                    <option key={type}>{type}</option>
                  ))}
                </select>
              </label>
              <label>
                {t.ai.fields.weightEstimate}
                <input value={form.weightEstimate} placeholder={t.ai.placeholders.weightEstimate} onChange={(event) => setForm({ ...form, weightEstimate: event.target.value })} />
              </label>
              <label>
                {t.ai.fields.loadingPort}
                <input value={form.loadingPort} placeholder={t.ai.placeholders.loadingPort} onChange={(event) => setForm({ ...form, loadingPort: event.target.value })} />
              </label>
              <label>
                {t.ai.fields.dischargePort}
                <input value={form.dischargePort} placeholder={t.ai.placeholders.dischargePort} onChange={(event) => setForm({ ...form, dischargePort: event.target.value })} />
              </label>
              <label className="wide">
                {t.ai.fields.details}
                <textarea required value={form.details} placeholder={t.ai.placeholders.details} onChange={(event) => setForm({ ...form, details: event.target.value })} />
              </label>
              <button className="button primary wide" disabled={loading} type="submit">
                {loading ? t.common.submitting : t.common.submit}
                <ArrowRight size={18} />
              </button>
              <p className="consult-disclaimer wide">{t.ai.disclaimer}</p>
              {result ? (
                <div className="result wide">
                  <strong>{t.ai.resultTitle}</strong>
                  <p>{result}</p>
                </div>
              ) : null}
            </form>
          </div>
        </Section>

        {/* Contact */}
        <Section id="contact" className="contact">
          <div className="section contact-inner">
            <div>
              <p className="eyebrow">{t.contact.eyebrow}</p>
              <h2>{t.contact.title}</h2>
              <p>{t.contact.intro}</p>
            </div>
            <div className="contact-details">
              {t.contact.details.map((detail) => (
                <div key={detail.label}>
                  <span>{detail.label}</span>
                  <strong className={detail.pending ? 'ph' : undefined}>{detail.value}</strong>
                </div>
              ))}
              <a className="button primary" href="mailto:quoctejiuneng@gmail.com">
                <Mail size={18} />
                {t.contact.cta}
              </a>
            </div>
          </div>
        </Section>
      </main>

      <footer>
        <div className="footer-brand">
          <img src={logo} alt={t.common.company} />
          <span>{t.footer.intro}</span>
          <small>{t.footer.legal}</small>
        </div>
        <div className="footer-contact">
          <span>
            <Phone size={15} />
            15687419919
          </span>
          <span>
            <Mail size={15} />
            quoctejiuneng@gmail.com
          </span>
          <span>
            <MapPin size={15} />
            Hanoi, Vietnam
          </span>
          <span>
            <Globe2 size={15} />
            {t.footer.site}
          </span>
        </div>
      </footer>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
