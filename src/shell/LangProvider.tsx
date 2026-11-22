import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { applyLangToDocument, detectLang, type Lang } from './i18n';
import { setApiLang } from '../tools/api';

type Ctx = { lang: Lang; setLang: (l: Lang) => void };

const LangContext = createContext<Ctx>({ lang: 'zh', setLang: () => {} });

export function LangProvider({ children }: { children: ReactNode }) {
  // 首帧就按 URL/localStorage 定语言：否则 ?lang=vi 会先闪一下中文再切
  const [lang, setLangState] = useState<Lang>(() => detectLang());

  useEffect(() => {
    const initial = detectLang();
    setLangState(initial);
    applyLangToDocument(initial);
    setApiLang(initial);
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem('jiuneng-lang', l);
    } catch {
      /* 隐私模式忽略 */
    }
    applyLangToDocument(l);
    setApiLang(l);
    // 语言变了就同步 URL（?lang=），便于分享与 SEO
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('lang', l);
      window.history.replaceState(null, '', url.toString());
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): Ctx {
  return useContext(LangContext);
}
