import type { HomeCopy } from '../types';

/** English: hero copy from translations.en.hero (reviewed on the old site). */
export const home: HomeCopy = {
  meta: { title: 'JIUNENG logistics | Engineering Logistics Platform' },
  hero: {
    eyebrow: 'Engineering logistics · Customs · International trade',
    titleLines: ['An engineering logistics platform', 'for Chinese enterprises'],
    lead: 'JIUNENG focuses on engineering logistics, import-export customs, and international trade. We manage inquiry, planning, quotation, execution, and delivery through a digital system, connecting China and Vietnam resources for complex engineering projects.',
    primary: 'Online inquiry',
    secondary: 'View projects',
    stats: [
      { value: 'CN-VN', label: 'China-Vietnam coordination' },
      { value: '3', label: 'Logistics · Customs · Trade' },
      { value: 'Rail·Wind·Power', label: 'Engineering solutions' },
      { value: '2024', label: 'Registered in Vietnam' },
    ],
    photo: {
      src: '/assets/v8/hero-blade-convoy.jpg',
      alt: 'Wind turbine blade transported on a mountain road with escort and road support',
      caption: 'Wind blade on mountain road · On-site escort',
      index: '01 / Site',
    },
  },
};

export default home;
