import type { HomeCopy } from '../types';

/** 首页中文基线：逐字取自 src/site/content.ts 的 hero，不重写。 */
export const home: HomeCopy = {
  meta: { title: 'JIUNENG logistics | 面向中国企业的工程物流平台' },
  hero: {
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
      index: '01 / 现场',
    },
  },
};

export default home;
