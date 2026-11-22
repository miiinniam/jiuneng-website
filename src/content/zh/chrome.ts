/** 页面级内联小字（段头、计数、按钮、合规说明）：中文基线。{n} 为数量占位符。 */
const chrome = {
  count: '{n} 张',
  compliance: '合规说明',
  submitQuote: '提交询价',
  aboutLead: '越南河内登记主体，中国侧由广西玖一进出口贸易有限公司提供进出口与报关支持。',
  home: {
    proofKicker: '作业现场 / 7 类',
    proofNote: '34 张实拍与资料图，按货物类型分类',
    toolsKicker: '平台工具 / 在线测算',
    toolsAria: '平台工具',
    linkQuote: '在线报价',
    linkPlatform: '平台总览',
    bandTitle: '提交项目需求',
  },
  services: {
    kicker: '业务与服务',
    headTitle: '三类业务的边界与交付',
    headLead: '每条业务写明定义、要点、适用货物与交付边界，避免把供应链上说不到的事写进来。',
    stepsSuffix: '12 步',
    modulesSuffix: '5 个',
    modulesHead: ['模块', '记录内容'] as [string, string],
    fitPrefix: '适用：',
    endTitle: '四项在线工具，从测算到车辆匹配',
    endLink: '平台总览',
    ctaTitle: '把货物尺寸与交付时间发来，我们按项目匹配车辆',
  },
  projects: {
    navAria: '项目分类',
    endTitle: '同类项目可直接对接测算',
    routing: '线路测算',
  },
  about: {
    kicker: '关于与网络',
    intro: '公司介绍',
    mvv: '使命、愿景与价值观',
    valuesSuffix: '4 条',
    registryHead: ['项目', '登记信息'] as [string, string],
    endTitle: '需要营业执照或登记文件复印件？',
    contact: '联系我们',
  },
  platform: {
    kicker: '平台',
    productTitle: '四项工具，按项目推进顺序排列',
    productLead: '先算线路，再算税费，再匹配车辆；需求还没成形时，用测算助手把要点整理出来交给项目经理。',
    open: '打开',
    reviewTitle: '工具之外，方案仍由人复核',
    reviewLead: '测算结果用于把沟通条件对齐，不替代现场核查与单证核定。',
    givesTitle: '工具给出什么',
    gives: ['干线里程、行车时长、车辆数量与参考运价区间', '中国端与越南端的报关费用区间', '按单件尺寸匹配的车型与超限标注'],
    whoTitle: '谁来确认',
    who: ['项目经理复核线路、车型与单证路径', '正式报价以复核后的方案为准', '越南侧由本地合作代理网络执行'],
    endTitle: '把项目条件发来，直接进入复核',
  },
};

export default chrome;
export type ChromeCopy = typeof chrome;
