import { useEffect, useRef, useState } from 'react';
import { useLang } from './LangProvider';
import { LANG_LABEL, LANGS } from './i18n';
import common from '../content/zh/common';

const PLATFORM_LINKS = [
  { href: '/platform', label: common.platformMenu.overview },
  { href: '/platform/routing', label: common.platformMenu.routing },
  { href: '/platform/customs', label: common.platformMenu.customs },
  { href: '/platform/fleet', label: common.platformMenu.fleet },
  { href: '/platform/assistant', label: common.platformMenu.assistant },
];

const NAV = [
  { href: '/services', label: common.nav.services },
  { href: '/projects', label: common.nav.projects },
  { href: '/about', label: common.nav.about },
  { href: '/contact', label: common.nav.contact },
];

export default function TopBar() {
  const { lang, setLang } = useLang();
  const [dropOpen, setDropOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const dropRef = useRef<HTMLDivElement | null>(null);
  const path = typeof window !== 'undefined' ? window.location.pathname : '';
  const platformActive = path.startsWith('/platform') || path === '/ai';

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setDropOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  return (
    <header className="jn-bar">
      <div className="jn-bar-in">
        <a className="jn-mark" href="/" data-testid="nav-home">
          {common.brand}
          <small>{common.brandSub}</small>
        </a>

        <nav className="jn-nav" aria-label="主导航">
          <div className="jn-drop" ref={dropRef}>
            <button
              type="button"
              data-testid="nav-platform"
              className={platformActive ? 'is-active' : ''}
              aria-expanded={dropOpen}
              onClick={() => setDropOpen((v) => !v)}
            >
              {common.nav.platform}
            </button>
            {dropOpen && (
              <div className="jn-drop-panel" data-testid="nav-platform-panel">
                {PLATFORM_LINKS.map((l) => (
                  <a key={l.href} href={l.href} onClick={() => setDropOpen(false)}>
                    {l.label}
                  </a>
                ))}
              </div>
            )}
          </div>
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className={path === n.href ? 'is-active' : ''}>
              {n.label}
            </a>
          ))}
        </nav>

        <div className="jn-right">
          <div className="jn-lang" data-testid="lang-switch">
            {LANGS.map((l) => (
              <button
                key={l}
                type="button"
                className={lang === l ? 'on' : ''}
                onClick={() => setLang(l)}
                aria-pressed={lang === l}
              >
                {LANG_LABEL[l]}
              </button>
            ))}
          </div>
          <a className="jn-btn" href="/contact" data-testid="nav-cta-quote">
            {common.nav.quote}
          </a>
          <button
            type="button"
            className="jn-burger"
            data-testid="nav-toggle"
            aria-label={common.ui.menu}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((v) => !v)}
          >
            ☰
          </button>
        </div>
      </div>

      <div className={`jn-mobile${mobileOpen ? ' is-open' : ''}`} data-testid="nav-mobile">
        {PLATFORM_LINKS.map((l) => (
          <a key={l.href} href={l.href}>
            {l.label}
          </a>
        ))}
        {NAV.map((n) => (
          <a key={n.href} href={n.href}>
            {n.label}
          </a>
        ))}
      </div>
    </header>
  );
}
