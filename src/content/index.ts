import type { Lang } from '../shell/i18n';
import type { ContactCopy, HomeCopy } from './types';
import type { CommonCopy } from './zh/common';

import zhCommon from './zh/common';
import viCommon from './vi/common';
import enCommon from './en/common';

import zhContact from './zh/contact';
import viContact from './vi/contact';
import enContact from './en/contact';

export type { CommonCopy, ContactCopy, HomeCopy };
export type { ContactDetail, ContactFieldKey } from './types';

import zhHome from './zh/home';
import viHome from './vi/home';
import enHome from './en/home';

import zhAssistant from './zh/assistant';
import viAssistant from './vi/assistant';
import enAssistant from './en/assistant';
import type { AssistantCopy } from './zh/assistant';

import zhSite from './zh/site';
import viSite from './vi/site';
import enSite from './en/site';
import type { SiteCopy } from './zh/site';

import zhChrome from './zh/chrome';
import viChrome from './vi/chrome';
import enChrome from './en/chrome';
import type { ChromeCopy } from './zh/chrome';

import zhTools from './zh/tools';
import viTools from './vi/tools';
import enTools from './en/tools';
import type { ToolsCopy } from './zh/tools';

/** 全站共用文案（导航/页脚/按钮）。 */
export function getCommon(lang: Lang): CommonCopy {
  if (lang === 'vi') return viCommon;
  if (lang === 'en') return enCommon;
  return zhCommon;
}

/** 联系页正文。新增页面照此加一份 `contact`/`getXxx`。 */
export function getContact(lang: Lang): ContactCopy {
  if (lang === 'vi') return viContact;
  if (lang === 'en') return enContact;
  return zhContact;
}

/** 首页正文（当前只覆盖 Hero；其余段落随批注逐段迁入）。 */
export function getHome(lang: Lang): HomeCopy {
  if (lang === 'vi') return viHome;
  if (lang === 'en') return enHome;
  return zhHome;
}

/** 全站悬浮助手（咨询助手）对话层文案。 */
export function getAssistant(lang: Lang): AssistantCopy {
  if (lang === 'vi') return viAssistant;
  if (lang === 'en') return enAssistant;
  return zhAssistant;
}

/** 营销页数据层（作业现场 7 类 / 业务 / 平台 / 方案 / 车型 / 案例 / 关于 / 通用标签）。 */
export function getSite(lang: Lang): SiteCopy {
  if (lang === 'vi') return viSite;
  if (lang === 'en') return enSite;
  return zhSite;
}

/** 页面级内联小字（段头 / 计数 / 按钮 / 合规说明）。 */
export function getChrome(lang: Lang): ChromeCopy {
  if (lang === 'vi') return viChrome;
  if (lang === 'en') return enChrome;
  return zhChrome;
}

/** 工具页语言包（线路 / 报关 / 车辆匹配 / 测算助手 + 表单 + 错误文案）。 */
export function getTools(lang: Lang): ToolsCopy {
  if (lang === 'vi') return viTools;
  if (lang === 'en') return enTools;
  return zhTools;
}
