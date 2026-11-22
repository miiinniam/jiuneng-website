import type { CommonCopy } from '../zh/common';

/** English: nav / footer / buttons. Reuses the reviewed copy from translations.en. */
const common: CommonCopy = {
  brand: 'JIUNENG',
  brandSub: 'logistics',
  nav: {
    platform: 'Platform',
    services: 'Services',
    projects: 'Projects',
    about: 'About',
    contact: 'Contact',
    quote: 'Inquiry',
  },
  platformMenu: {
    overview: 'Platform overview',
    quote: 'Online quote',
    routing: 'Routes and freight',
    customs: 'Customs and duties',
    fleet: 'Vehicle fit and oversize',
    assistant: 'Quote assistant',
  },
  footer: {
    intro: 'An engineering logistics platform for Chinese enterprises, making complex engineering logistics clearer, more controllable, and more efficient.',
    colServices: 'Services',
    colProjects: 'Projects',
    colContact: 'Contact',
    services: ['Engineering logistics', 'Import-export customs', 'International trade'],
    projects: ['Rail transit', 'Wind power', 'Power'],
    contactLines: ['jiuneng.vn@gmail.com', '15687419919', '82 Duy Tan St., Cau Giay Ward, Hanoi, Vietnam'],
    legal: 'JIUNENG INTERNATIONAL CO., LTD · Guangxi Jiuyi Import & Export Trading Co., Ltd',
  },
  cta: {
    quote: 'Online inquiry',
    seeProjects: 'See projects',
    seeDetail: 'See details',
    openTool: 'Open tool',
  },
  ui: {
    menu: 'Menu',
    close: 'Close',
    loading: 'Calculating…',
    retry: 'Retry',
    required: 'Required',
    skip: 'Skip to main content',
  },
  assistant: {
    fab: 'Assistant',
    title: 'Inquiry assistant · Hall',
    sub: 'Business consulting · Process and documents · No quoting',
    close: 'Collapse assistant',
    grip: 'Resize panel height',
  },
};

export default common;
