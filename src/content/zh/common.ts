/** 全站共用文案（导航/页脚/按钮）。页面正文文案暂由各页组件内联（Phase 3 迁移）。 */
const common = {
  brand: 'JIUNENG',
  brandSub: 'logistics',
  nav: {
    platform: '平台',
    services: '服务',
    projects: '项目',
    about: '关于',
    contact: '联系',
    quote: '询价',
  },
  platformMenu: {
    overview: '平台总览',
    quote: '在线报价',
    routing: '线路与运价测算',
    customs: '报关与税费',
    fleet: '车辆匹配与超限',
    assistant: '测算助手',
  },
  footer: {
    intro: '面向中国企业的工程物流平台，让复杂工程物流更清晰、更可控、更高效。',
    colServices: '服务',
    colProjects: '项目',
    colContact: '联系',
    services: ['工程物流', '进出口报关', '国际贸易'],
    projects: ['轨道交通', '风电', '电力'],
    contactLines: ['jiuneng.vn@gmail.com', '15687419919', '越南河内市纸桥坊 Duy Tân 街 82 号'],
    legal: '玖能国际有限责任公司 · 广西玖一进出口贸易有限公司',
  },
  cta: {
    quote: '在线询价',
    seeProjects: '看项目',
    seeDetail: '看详情',
    openTool: '打开工具',
  },
  ui: {
    menu: '菜单',
    close: '关闭',
    loading: '计算中…',
    retry: '重试',
    required: '必填',
    skip: '跳到主要内容',
  },
  assistant: {
    fab: '咨询助手',
    title: '咨询助手 · 大厅',
    sub: '业务咨询 · 流程与单证 · 不做报价',
    close: '收起助手',
    grip: '调整面板高度',
  },
};

export default common;
export type CommonCopy = typeof common;
