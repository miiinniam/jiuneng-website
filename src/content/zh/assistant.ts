/** 全站悬浮测算助手（咨询助手）对话层文案：中文基线。{label} 为占位符。 */
const assistant = {
  suggestions: ['报价需要准备哪些资料？', '报价包含哪些费用？', '客服联系方式是什么？'],
  intro:
    '我是咨询助手，负责业务咨询：服务范围、中越线路流程、单证与时效怎么走。要算里程与运费请用报价页的「报价助手」（/quote），那边按路线与运价引擎出数。',
  actions: {
    docDetail: '看分项明细',
    reMatch: '换车型重算',
    reMatchPrompt: '按整车、低平板 17.5 米重算一次',
    vehicleMatch: '打开车辆匹配',
    submitQuote: '提交正式询价',
  },
  status: {
    idle: '尚未调用测算工具',
    reading: '正在解读问题…',
    calling: '正在调用：{label}',
    callingGeneric: '正在调用测算工具…',
    done: '测算工具已返回结果',
  },
  ui: {
    clear: '清空对话',
    typing: '正在整理…',
    placeholder: '例如：南宁 → 河内，20 吨，整车',
    askAria: '向咨询助手提问',
    sending: '整理中…',
    send: '发送',
    note: '初步测算 · 非正式报价 · 非时效承诺',
  },
};

export default assistant;
export type AssistantCopy = typeof assistant;
