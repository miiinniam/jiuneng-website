import type { ContactCopy } from '../types';

/** 中文基线：逐字沿用 src/site/content.ts 里已审的 contact 块，不重写。 */
export const contact: ContactCopy = {
  meta: { title: '联系与询价 | JIUNENG logistics' },
  eyebrow: '联系与询价',
  title: '把项目资料发来，我们一起把方案做实',
  intro: '适合发送装箱单、设备图纸、尺寸重量表、目的地地址、交付时间和单证状态。',
  detailsTitle: '联系方式',
  detailsLead: '工作日由项目经理直接回复；紧急项目请同时致电。',
  tableHead: ['项目', '信息'],
  details: [
    { label: '邮箱', value: 'jiuneng.vn@gmail.com', href: 'mailto:jiuneng.vn@gmail.com' },
    { label: '中国咨询电话', value: '15687419919', href: 'tel:+8615687419919' },
    { label: '河内办公地址', value: '越南河内市纸桥坊 Duy Tân 街 82 号 5 楼 R03 室' },
    { label: '微信 / WhatsApp', value: '待补充', pending: true },
  ],
  sideKicker: '建议随询价提供',
  sideItems: [
    '装箱单与设备图纸',
    '尺寸重量表（单件最大尺寸）',
    '目的地地址与现场装卸条件',
    '交付时间与单证状态',
  ],
  form: {
    title: '提交项目需求',
    lead: '填写后由系统整理初步评估，项目经理复核后给出正式方案。',
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
    submit: '提交询价',
    submitting: '正在生成评估',
    requiredNote: '联系人与项目详情为必填，其余字段可留空。',
    incompleteTitle: '还需要补充两项',
    incompleteBody: '请填写联系人与项目详情，其余字段可留空，项目经理会电话或邮件补齐。',
    resultTitle: '初步评估',
    docTitle: '可能涉及的单证',
    riskTitle: '需提前确认',
    hsTitle: '归类与关税方向',
    fallback:
      '已收到需求。建议下一步补充货物尺寸、重量、装货时间、HS 编码及目的地现场条件，以便项目经理确认线路、车型和单证路径。',
    errorNote:
      '在线评估暂时不可用，资料已可发送至 jiuneng.vn@gmail.com 或致电 15687419919，由项目经理跟进。',
    disclaimer: '初步评估仅用于整理沟通信息，不构成正式报价或时效承诺。',
  },
  photo: {
    src: '/assets/v8/contact-lowbed.jpg',
    alt: '红色多轴低平板载一台大型变压器停在厂房前场地',
    caption: '多轴低平板载变压器 · 越南场地',
  },
};

export default contact;
