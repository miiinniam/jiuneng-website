export type Lang = 'zh' | 'vi' | 'en';

export const LANGS: Lang[] = ['zh', 'vi', 'en'];

export const LANG_LABEL: Record<Lang, string> = {
  zh: '中文',
  vi: 'VI',
  en: 'EN',
};

/** 语言判定优先级：?lang= → localStorage → navigator.language → zh */
export function detectLang(): Lang {
  try {
    const q = new URLSearchParams(window.location.search).get('lang');
    if (q && (LANGS as string[]).includes(q)) return q as Lang;
  } catch {
    /* 无 window 时忽略 */
  }
  try {
    const saved = window.localStorage.getItem('jiuneng-lang');
    if (saved && (LANGS as string[]).includes(saved)) return saved as Lang;
  } catch {
    /* 隐私模式下 localStorage 会抛 */
  }
  const nav = typeof navigator !== 'undefined' ? navigator.language.toLowerCase() : 'zh';
  if (nav.startsWith('vi')) return 'vi';
  if (nav.startsWith('en')) return 'en';
  return 'zh';
}

export function applyLangToDocument(lang: Lang, title?: string) {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang;
  if (title) document.title = title;
}
