import React, { useCallback, useEffect, useRef, useState } from 'react';
import { agentI18n, languages, type AgentContent, type Lang, type Role, type Status } from './content';
import { agentAssets, hasSlot, type MediaSlot } from './media';
import { ChatPanel } from './ChatPanel';

/* ────────────────────────── helpers ────────────────────────── */

function usePrefersReducedMotion() {
  const [reduce, setReduce] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduce(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduce;
}

function getInitialLang(): Lang {
  if (typeof window === 'undefined') return 'zh';
  const url = new URLSearchParams(window.location.search).get('lang');
  if (url === 'zh' || url === 'vi' || url === 'en') return url;
  const stored = window.localStorage.getItem('jiuneng-agent-lang') || window.localStorage.getItem('jiuneng-lang');
  if (stored === 'zh' || stored === 'vi' || stored === 'en') return stored;
  const nav = window.navigator.language.toLowerCase();
  if (nav.startsWith('vi')) return 'vi';
  if (nav.startsWith('en')) return 'en';
  return 'zh';
}

const StatusChip: React.FC<{ status: Status; label: string }> = ({ status, label }) => (
  <span className={`jx-status jx-status-${status}`}>
    <i aria-hidden="true" />
    {label}
  </span>
);

/* Role avatars — inline SVG marks (no stock photos), JIUNENG brand gradient circles. */
const roleGlyph: Record<string, React.ReactNode> = {
  inquiry: (
    <>
      <path d="M11.5 4.5a7 7 0 1 0 4.2 12.6l3.9 3.9" />
      <path d="M8.6 11.5h5.8M11.5 8.6v5.8" />
    </>
  ),
  customs: (
    <>
      <path d="M12 3.5 5 6v5.4c0 4 2.8 7.6 7 9.1 4.2-1.5 7-5.1 7-9.1V6l-7-2.5Z" />
      <path d="M9 12l2.2 2.2L15.5 10" />
    </>
  ),
  docs: (
    <>
      <path d="M14 3.5H7.5A1.5 1.5 0 0 0 6 5v14a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 19V7.5L14 3.5Z" />
      <path d="M13.5 4v4h4.2" />
      <path d="M9 13h6M9 16.5h4" />
    </>
  ),
  dispatch: (
    <>
      <path d="M2.5 7.5h10v9h-10z" />
      <path d="M12.5 10.5h4l3 3v3h-7z" />
      <circle cx="6.5" cy="18.5" r="1.8" />
      <circle cx="16" cy="18.5" r="1.8" />
    </>
  ),
  translate: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c2.4 2.3 3.6 5.3 3.6 8.5S14.4 18.2 12 20.5c-2.4-2.3-3.6-5.3-3.6-8.5S9.6 5.8 12 3.5Z" />
    </>
  ),
};

const RoleAvatar: React.FC<{ role: Role; size?: 'md' | 'lg' | 'xl'; src?: string }> = ({ role, size = 'md', src }) => {
  const [broken, setBroken] = useState(false);
  const showImg = Boolean(src) && !broken;
  return (
    <span className={`jx-avatar jx-avatar-${size} ${showImg ? 'has-img' : ''}`} aria-hidden="true">
      {showImg ? (
        <img src={src} alt="" loading="eager" decoding="async" onError={() => setBroken(true)} />
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          {roleGlyph[role.id] ?? roleGlyph.inquiry}
        </svg>
      )}
    </span>
  );
};

/* 素材槽编号顺序必须与 content.ts 里的数组顺序一致 */
const SERVICE_SLOT_IDS = ['inquiry', 'customs', 'plan', 'bilingual'];
const APP_SLOT_IDS = ['inquiry', 'customs', 'loading', 'milestone', 'automation'];
const CASE_SLOT_IDS = ['case1', 'case2', 'case3'];

/**
 * 素材面板：优先透明底循环 MP4；`prefers-reduced-motion` 或动效缺失时退回 PNG 首帧。
 * 没有素材就整块不渲染 —— 版式自动回落到纯文字形态，不留空框。
 */
const MediaPanel: React.FC<{ slot?: MediaSlot | null; className?: string; alt?: string }> = ({ slot, className = '', alt = '' }) => {
  const reduce = usePrefersReducedMotion();
  const [broken, setBroken] = useState(false);
  if (!slot || broken || (!slot.video && !slot.poster)) return null;
  if (slot.video && !reduce) {
    return (
      <div className={`jx-media ${className}`}>
        <video
          src={slot.video}
          poster={slot.poster ?? undefined}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          aria-hidden="true"
          onError={() => setBroken(true)}
        />
      </div>
    );
  }
  if (slot.poster) {
    return (
      <div className={`jx-media ${className}`}>
        <img src={slot.poster} alt={alt} loading="lazy" decoding="async" onError={() => setBroken(true)} />
      </div>
    );
  }
  return null;
};

/** 背景微动效（Hero / CTA）：装饰层，无声循环、不可交互；减少动效偏好下不渲染 */
const LoopVideo: React.FC<{ src?: string | null; className: string }> = ({ src, className }) => {
  const reduce = usePrefersReducedMotion();
  if (!src || reduce) return null;
  return (
    <video className={className} src={src} autoPlay muted loop playsInline preload="metadata" aria-hidden="true" />
  );
};

function scrollToId(id: string) {
  const el = document.getElementById(id.replace('#', ''));
  if (!el) return;
  const top = el.getBoundingClientRect().top + window.scrollY - 76;
  window.scrollTo({ top, behavior: 'smooth' });
}

/* ────────────────────────── header ────────────────────────── */

const Header: React.FC<{
  t: AgentContent;
  lang: Lang;
  setLang: (l: Lang) => void;
}> = ({ t, lang, setLang }) => {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const onResize = () => { if (window.innerWidth > 1080) setOpen(false); };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open && window.innerWidth <= 1080 ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  return (
    <header className={`jx-header ${scrolled ? 'is-scrolled' : ''} ${open ? 'is-open' : ''}`}>
      <div className="jx-container jx-header-inner">
        <a className="jx-brand" href="#top" aria-label={t.common.company} onClick={() => setOpen(false)}>
          <img src="/assets/logo-horizontal.png" alt={t.common.company} width="168" height="28" />
        </a>

        <nav className="jx-nav" aria-label="Primary">
          {t.nav.map((item) => (
            <a key={item.href} href={item.href}>{item.label}</a>
          ))}
        </nav>

        <div className="jx-header-actions">
          <div className="jx-lang" role="group" aria-label="Language">
            {languages.map((code) => (
              <button
                key={code}
                type="button"
                className={lang === code ? 'is-active' : ''}
                aria-pressed={lang === code}
                onClick={() => setLang(code)}
              >
                {code.toUpperCase()}
              </button>
            ))}
          </div>
          <a className="jx-btn jx-btn-primary jx-header-cta" href="#consult">{t.common.cta}</a>
          <button
            type="button"
            className="jx-burger"
            aria-label="Menu"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <span /><span /><span />
          </button>
        </div>
      </div>

      <div className={`jx-mobile-panel ${open ? 'is-open' : ''}`}>
        <div className="jx-container">
          {t.nav.map((item) => (
            <a key={item.href} href={item.href} onClick={() => setOpen(false)}>{item.label}</a>
          ))}
          <a className="jx-btn jx-btn-primary" href="#consult" onClick={() => setOpen(false)}>{t.common.cta}</a>
          <div className="jx-mobile-contact">
            <a href={`tel:+86${t.common.phone}`}>{t.common.phone}</a>
            <a href={`mailto:${t.common.email}`}>{t.common.email}</a>
          </div>
        </div>
      </div>
    </header>
  );
};

/* ────────────────────────── hero ────────────────────────── */

const Hero: React.FC<{
  t: AgentContent;
  roles: Role[];
  activeRole: number;
  setActiveRole: (i: number) => void;
  onPrompt: (text: string) => void;
}> = ({ t, roles, activeRole, setActiveRole, onPrompt }) => {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = (text: string) => {
    const payload = text.trim();
    onPrompt(payload);
  };

  return (
    <section className="jx-hero" id="top">
      <div className="jx-hero-glow" aria-hidden="true" />
      <LoopVideo src={agentAssets.heroLoop} className="jx-hero-loop" />
      <div className="jx-container jx-hero-inner">
        <p className="jx-hero-line1">{t.hero.line1}</p>
        <h1 className="jx-hero-title">
          {t.hero.line2a}
          <span className="jx-grad-text">{t.hero.line2b}</span>
          {t.hero.line2c}
        </h1>
        <p className="jx-hero-sub">{t.hero.sub}</p>

        <div className="jx-roletabs" role="tablist" aria-label={t.hero.tabsLabel}>
          {roles.map((role, i) => (
            <button
              key={role.id}
              type="button"
              role="tab"
              aria-selected={activeRole === i}
              className={`jx-roletab ${activeRole === i ? 'is-active' : ''}`}
              onClick={() => {
                setActiveRole(i);
                inputRef.current?.focus();
              }}
            >
              <RoleAvatar role={role} src={agentAssets.roles[role.id]} />
              <span className="jx-roletab-title">{role.title}</span>
              <span className="jx-roletab-short">{role.name}</span>
            </button>
          ))}
        </div>

        <form
          className="jx-prompt"
          onSubmit={(e) => { e.preventDefault(); submit(value || t.hero.promptHint); }}
        >
          <span className="jx-prompt-avatar" aria-hidden="true">
            <RoleAvatar role={roles[activeRole]} size="lg" src={agentAssets.roles[roles[activeRole].id]} />
          </span>
          <textarea
            ref={inputRef}
            className="jx-prompt-input"
            value={value}
            rows={1}
            aria-label={t.hero.promptPlaceholder}
            placeholder={`${roles[activeRole].title}：${t.hero.promptPlaceholder}`}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(value || t.hero.promptHint); }
            }}
          />
          <button className="jx-prompt-send" type="submit" aria-label={t.hero.promptButton}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h13M12.5 6l6 6-6 6" />
            </svg>
          </button>
        </form>

        <div className="jx-quick">
          {t.hero.quick.map((q) => (
            <button key={q} type="button" className="jx-chip" onClick={() => submit(q)}>{q}</button>
          ))}
        </div>
        <p className="jx-hero-note">{t.hero.promptNote}</p>
      </div>
    </section>
  );
};

/* ────────────────────────── team ────────────────────────── */

const Team: React.FC<{ t: AgentContent; onPick: (i: number) => void }> = ({ t, onPick }) => (
  <section className="jx-section" id="team">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.team.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.team.titleA}<span className="jx-grad-text">{t.team.titleB}</span>{t.team.titleC}
        </h2>
        <p className="jx-sec-sub">{t.team.sub}</p>
      </header>

      <div className="jx-team-grid">
        {t.team.roles.map((role, i) => (
          <article key={role.id} className={`jx-team-card ${role.featured ? 'is-featured' : ''}`}>
            <div className="jx-team-top">
              <RoleAvatar role={role} size={agentAssets.roles[role.id] ? 'xl' : 'lg'} src={agentAssets.roles[role.id]} />
              <StatusChip status={role.status} label={t.common.statusLabels[role.status]} />
            </div>
            <h3 className="jx-team-name">{role.name}</h3>
            <p className="jx-team-role">{role.title}</p>
            <div className="jx-tags">
              {role.tags.map((tag) => <span key={tag} className="jx-tag">{tag}</span>)}
            </div>
            <p className="jx-team-desc">{role.desc}</p>
            <button type="button" className="jx-link" onClick={() => onPick(i)}>
              {t.team.demoLink}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12h13M12.5 6l6 6-6 6" />
              </svg>
            </button>
          </article>
        ))}
      </div>

      <p className="jx-footnote">{t.team.note}</p>
    </div>
  </section>
);

/* ────────────────────────── services carousel ────────────────────────── */

const Services: React.FC<{ t: AgentContent }> = ({ t }) => {
  const items = t.services.items;
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduce = usePrefersReducedMotion();
  const touchX = useRef(0);

  const go = useCallback((next: number) => {
    setIndex(((next % items.length) + items.length) % items.length);
  }, [items.length]);

  useEffect(() => {
    if (paused || reduce) return;
    const id = window.setInterval(() => setIndex((i) => (i + 1) % items.length), 7000);
    return () => window.clearInterval(id);
  }, [paused, reduce, items.length]);

  return (
    <section className="jx-section jx-section-alt" id="services">
      <div className="jx-container">
        <header className="jx-sec-head">
          <p className="jx-eyebrow">{t.services.eyebrow}</p>
          <h2 className="jx-sec-title">
            {t.services.titleA}<span className="jx-grad-text">{t.services.titleB}</span>{t.services.titleC}
          </h2>
          <p className="jx-sec-sub">{t.services.sub}</p>
        </header>
      </div>

      <div
        className="jx-carousel"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight') go(index + 1);
          if (e.key === 'ArrowLeft') go(index - 1);
        }}
        onTouchStart={(e) => { touchX.current = e.touches[0].clientX; }}
        onTouchEnd={(e) => {
          const dx = e.changedTouches[0].clientX - touchX.current;
          if (Math.abs(dx) > 48) go(index + (dx < 0 ? 1 : -1));
        }}
      >
        <div className="jx-container jx-carousel-shell">
          <div className="jx-carousel-dots" role="tablist" aria-label={t.services.eyebrow}>
            {items.map((item, i) => (
              <button
                key={item.title}
                type="button"
                aria-label={item.title}
                aria-selected={i === index}
                role="tab"
                className={`jx-dot ${i === index ? 'is-active' : ''}`}
                onClick={() => go(i)}
              />
            ))}
          </div>

          <div className="jx-carousel-view">
            <div className="jx-carousel-track" style={{ transform: `translateX(-${index * 100}%)` }}>
              {items.map((item, i) => {
                const slot = agentAssets.services[SERVICE_SLOT_IDS[i]];
                const withMedia = hasSlot(slot);
                return (
                  <article className={`jx-service ${withMedia ? 'has-media' : ''}`} key={item.title}>
                    <MediaPanel slot={slot} className="jx-media-service" alt={item.title} />
                    <div className="jx-service-body">
                      <div className="jx-service-main">
                        <StatusChip status={item.status} label={t.common.statusLabels[item.status]} />
                        <h3>{item.title}</h3>
                        <p>{item.desc}</p>
                      </div>
                      <ul className="jx-service-points">
                        {item.points.map((p) => (
                          <li key={p}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M5 12.5l4.2 4.2L19 7" />
                            </svg>
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>

          <div className="jx-carousel-nav">
            <button type="button" className="jx-nav-btn" onClick={() => go(index - 1)} aria-label={t.services.prev}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 6l-6 6 6 6" /></svg>
            </button>
            <span className="jx-carousel-count">{index + 1} / {items.length}</span>
            <button type="button" className="jx-nav-btn" onClick={() => go(index + 1)} aria-label={t.services.next}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
            </button>
          </div>
        </div>
      </div>

      <div className="jx-container">
        <p className="jx-footnote">{t.services.note}</p>
      </div>
    </section>
  );
};

/* ────────────────────────── applications ────────────────────────── */

const Apps: React.FC<{ t: AgentContent }> = ({ t }) => {
  const [active, setActive] = useState(0);
  const current = t.apps.tabs[active];

  return (
    <section className="jx-section" id="apps">
      <div className="jx-container">
        <header className="jx-sec-head">
          <p className="jx-eyebrow">{t.apps.eyebrow}</p>
          <h2 className="jx-sec-title">
            {t.apps.titleA}<span className="jx-grad-text">{t.apps.titleB}</span>{t.apps.titleC}
          </h2>
          <p className="jx-sec-sub">{t.apps.sub}</p>
        </header>

        <div className="jx-tabbar" role="tablist" aria-label={t.apps.eyebrow}>
          {t.apps.tabs.map((tab, i) => (
            <button
              key={tab.label}
              type="button"
              role="tab"
              aria-selected={i === active}
              className={`jx-tab ${i === active ? 'is-active' : ''}`}
              onClick={() => setActive(i)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="jx-app-card">
          <div className="jx-app-visual">
            <MediaPanel slot={agentAssets.apps[APP_SLOT_IDS[active]]} className="jx-media-app" alt={current.title} />
            <p className="jx-app-visual-label">{t.apps.flowLabel}</p>
            <ol className="jx-flow">
              {current.flow.map((step, i) => (
                <li key={step}>
                  <span className="jx-flow-index">{String(i + 1).padStart(2, '0')}</span>
                  <span className="jx-flow-text">{step}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="jx-app-content">
            <h3>{current.title}</h3>
            <p>{current.desc}</p>
            <ul className="jx-app-points">
              {current.bullets.map((b) => (
                <li key={b}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12.5l4.2 4.2L19 7" />
                  </svg>
                  {b}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="jx-footnote">{t.apps.note}</p>
      </div>
    </section>
  );
};

/* ────────────────────────── AI foundation ────────────────────────── */

const Brain: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-band" id="brain">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.brain.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.brain.titleA}<span className="jx-grad-text">{t.brain.titleB}</span>{t.brain.titleC}
        </h2>
        <p className="jx-sec-sub">{t.brain.sub}</p>
      </header>

      {agentAssets.brain ? (
        <div className="jx-brain-art">
          <img src={agentAssets.brain} alt="" loading="lazy" decoding="async" />
        </div>
      ) : agentAssets.photos.platform ? (
        /* 我们的数字化平台界面是深色看板，裸贴到浅色页面上会读成一块暗区，
           所以照旧站规矩套一层浅色窗口框（.jx-shot-frame），保留界面感。 */
        <figure className="jx-shot-frame">
          <div className="jx-shot-bar" aria-hidden="true">
            <span /><span /><span />
          </div>
          <img src={agentAssets.photos.platform} alt={t.brain.cards[1]?.title ?? ''} width="1672" height="941" loading="lazy" decoding="async" />
        </figure>
      ) : null}

      <div className="jx-brain-grid">
        {t.brain.cards.map((card) => (
          <article className="jx-brain-card" key={card.title}>
            <StatusChip status={card.status} label={t.common.statusLabels[card.status]} />
            <h3>{card.title}</h3>
            <p>{card.desc}</p>
          </article>
        ))}
      </div>

      <div className="jx-stats">
        {t.brain.stats.map((s) => (
          <div className="jx-stat" key={s.label}>
            <strong>{s.value}</strong>
            <span>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────── system（平台系统全过程）────────────────────── */

const System: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-section jx-section-alt" id="system">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.system.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.system.titleA}<span className="jx-grad-text">{t.system.titleB}</span>
        </h2>
        <p className="jx-sec-sub">{t.system.intro}</p>
      </header>

      <ol className="jx-steps">
        {t.system.steps.map((s, i) => (
          <li key={s}>
            <span className="jx-step-no">{String(i + 1).padStart(2, '0')}</span>
            {s}
          </li>
        ))}
      </ol>

      <h3 className="jx-sub-title">{t.system.modulesTitle}</h3>
      <div className="jx-modules">
        {t.system.modules.map((m) => (
          <article className="jx-module" key={m.title}>
            <h4>{m.title}</h4>
            <p>{m.body}</p>
          </article>
        ))}
      </div>

      {/* 平台界面是深色看板，套浅色窗口框（与 brain 区块同一处理） */}
      {agentAssets.photos.sys2 ? (
        <figure className="jx-shot-frame jx-system-shot">
          <div className="jx-shot-bar" aria-hidden="true"><span /><span /><span /></div>
          <img src={agentAssets.photos.sys2} alt={t.system.shotLabel} width="1600" height="983" loading="lazy" decoding="async" />
          <figcaption>{t.system.shotLabel}</figcaption>
        </figure>
      ) : null}

      <p className="jx-inline-note">{t.system.note}</p>
    </div>
  </section>
);

/* ────────────────────────── solutions（解决方案 4 卡）──────────────────── */

const Solutions: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-section" id="solutions">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.solutions.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.solutions.titleA}<span className="jx-grad-text">{t.solutions.titleB}</span>
        </h2>
        <p className="jx-sec-sub">{t.solutions.intro}</p>
      </header>

      <div className="jx-sol-grid">
        {t.solutions.items.map((it) => (
          <article className="jx-sol-card" key={it.title}>
            {agentAssets.photos[it.slot] ? (
              <figure className="jx-sol-media">
                <img src={agentAssets.photos[it.slot]} alt={it.title} loading="lazy" decoding="async" />
              </figure>
            ) : null}
            <p className="jx-sol-sector">{it.sector}</p>
            <h3>{it.title}</h3>
            <p>{it.body}</p>
          </article>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────── fleet（设备资源 3 卡）─────────────────────── */

const Fleet: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-section jx-section-alt" id="fleet">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.fleet.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.fleet.titleA}<span className="jx-grad-text">{t.fleet.titleB}</span>
        </h2>
        <p className="jx-sec-sub">{t.fleet.intro}</p>
      </header>

      <div className="jx-fleet-grid">
        {t.fleet.items.map((it) => (
          <article className="jx-fleet-card" key={it.title}>
            {agentAssets.photos[it.slot] ? (
              <figure className="jx-fleet-media">
                <img src={agentAssets.photos[it.slot]} alt={it.title} loading="lazy" decoding="async" />
              </figure>
            ) : null}
            <h3>{it.title}</h3>
            <p>{it.body}</p>
            <p className="jx-fleet-spec">{it.spec}</p>
          </article>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────── network（中越协同网络）────────────────────── */

const Network: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-section" id="network">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.network.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.network.titleA}<span className="jx-grad-text">{t.network.titleB}</span>
        </h2>
        <p className="jx-sec-sub">{t.network.intro}</p>
      </header>

      <div className="jx-net-grid">
        {[t.network.china, t.network.vietnam].map((side) => (
          <article className="jx-net-card" key={side.name}>
            <p className="jx-net-flag">{side.flag}</p>
            <h3>{side.name}</h3>
            <p>{side.body}</p>
            <ul>
              {side.points.map((p) => <li key={p}>{p}</li>)}
            </ul>
          </article>
        ))}
      </div>

      <p className="jx-inline-note">{t.network.note}</p>
    </div>
  </section>
);

/* ────────────────────────── qual（企业信息与资质）─────────────────────── */

const Qual: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-section jx-section-alt" id="qual">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.qual.eyebrow}</p>
        <h2 className="jx-sec-title">
          {t.qual.titleA}<span className="jx-grad-text">{t.qual.titleB}</span>
        </h2>
        <p className="jx-sec-sub">{t.qual.intro}</p>
      </header>

      <div className="jx-qual-grid">
        {t.qual.entities.map((e) => (
          <article className="jx-qual-card" key={e.name}>
            <p className="jx-qual-tag">{e.tag}</p>
            <h3>{e.name}</h3>
            <dl className="jx-qual-rows">
              {e.rows.map((r) => (
                <div key={r.label}>
                  <dt>{r.label}</dt>
                  <dd>{r.value}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </div>
  </section>
);

/* ────────────────────────── cases ────────────────────────── */

const Cases: React.FC<{ t: AgentContent }> = ({ t }) => {
  const line = [...t.cases.domains, ...t.cases.domains];
  return (
    <section className="jx-section" id="cases">
      <div className="jx-container">
        <header className="jx-sec-head">
          <p className="jx-eyebrow">{t.cases.eyebrow}</p>
          <h2 className="jx-sec-title">
            {t.cases.titleA}<span className="jx-grad-text">{t.cases.titleB}</span>
          </h2>
          <p className="jx-sec-sub">{t.cases.sub}</p>
        </header>

        <div className="jx-case-grid">
          {t.cases.items.map((c, i) => {
            const photo = agentAssets.photos[CASE_SLOT_IDS[i]];
            return (
              <article className={`jx-case-card ${photo ? 'has-photo' : ''}`} key={c.title}>
                {photo ? (
                  <figure className="jx-case-media">
                    <img src={photo} alt={c.type} loading="lazy" decoding="async" />
                  </figure>
                ) : null}
                <p className="jx-case-type">{c.type}</p>
                <h3>{c.title}</h3>
                <p className="jx-case-body">{c.body}</p>
                <div className="jx-tags">
                  {c.tags.map((tag) => <span key={tag} className="jx-tag">{tag}</span>)}
                </div>
              </article>
            );
          })}
        </div>
      </div>

      <div className="jx-marquee" aria-label={t.cases.domainsLabel}>
        <div className="jx-marquee-track">
          {line.map((d, i) => <span className="jx-marquee-item" key={`${d}-${i}`}>{d}</span>)}
        </div>
      </div>

      <div className="jx-container">
        <p className="jx-footnote">{t.cases.note}</p>
      </div>
    </section>
  );
};

/* ────────────────────────── consult ────────────────────────── */

/* ────────────────────────── 快速测算（与 AI 对话共用同一引擎出口） ────────────────────────── */

type CalcPlace = { id: string; kind: 'cn' | 'vn' | 'border'; zh: string; vi: string; en: string };
type CalcVehicle = { id: string; max_load_ton: number; zh: string; vi: string; en: string };
type CalcOk = {
  ok: true;
  origin: { id: string; label: string };
  destination: { id: string; label: string };
  border: { id: string; label: string } | null;
  mode: 'consolidated' | 'full_truck';
  distance_km: number | null;
  driving_h: number | null;
  vehicle_count: number | null;
  vehicle_id?: string | null;
  vehicle_label: string | null;
  price_min_vnd: number | null;
  price_max_vnd: number | null;
  profile_honored: boolean;
};

const vndFmt = (v: number) => v.toLocaleString('en-US');

const CalcPanel: React.FC<{
  t: AgentContent;
  lang: Lang;
  onUseForInquiry: (text: string) => void;
}> = ({ t, lang, onUseForInquiry }) => {
  const c = t.calc;
  const [places, setPlaces] = useState<CalcPlace[]>([]);
  const [vehicles, setVehicles] = useState<CalcVehicle[]>([]);
  const [form, setForm] = useState({
    origin: 'nanning',
    destination: 'hanoi',
    border: 'youyiguan',
    weight: '',
    volume: '',
    mode: 'consolidated' as 'consolidated' | 'full_truck',
    vehicle: 'flatbed_13m',
  });
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<CalcOk | null>(null);
  const [err, setErr] = useState('');

  // 城市/车型清单来自服务端白名单（同一份来源，前端不重复维护）
  useEffect(() => {
    let alive = true;
    fetch('/api/osrm-quote/places')
      .then((r) => r.json())
      .then((d: { places?: CalcPlace[]; vehicles?: CalcVehicle[] }) => {
        if (!alive) return;
        setPlaces(Array.isArray(d.places) ? d.places : []);
        setVehicles(Array.isArray(d.vehicles) ? d.vehicles : []);
      })
      .catch(() => { /* 清单取不到就保留空下拉，提交时服务端仍会校验 */ });
    return () => { alive = false; };
  }, []);

  const label = (o: { zh: string; vi: string; en: string }) =>
    lang === 'vi' ? o.vi : lang === 'en' ? o.en : o.zh;
  const cn = places.filter((p) => p.kind === 'cn');
  const vn = places.filter((p) => p.kind === 'vn');
  const borders = places.filter((p) => p.kind === 'border');

  // 服务端只回中文 label（便于对话工具/日志统一），页面按当前语言本地化后再展示
  const placeLabel = (id: string, fallback: string) => {
    const p = places.find((x) => x.id === id);
    return p ? label(p) : fallback;
  };
  const vehicleLabel = (id: string, fallback: string) => {
    const v = vehicles.find((x) => x.id === id);
    return v ? label(v) : fallback;
  };

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const canSubmit = cn.length > 0 && vn.length > 0 && form.weight.trim() !== '' && !busy;

  const inquiryText = (r: CalcOk) => {
    const range = r.price_min_vnd !== null && r.price_max_vnd !== null
      ? `${c.labels.price} ${vndFmt(r.price_min_vnd)} – ${vndFmt(r.price_max_vnd)} VND（${c.disclosureShort}）`
      : '';
    const from = placeLabel(r.origin.id, r.origin.label);
    const to = placeLabel(r.destination.id, r.destination.label);
    const border = r.border ? placeLabel(r.border.id, r.border.label) : '';
    const truck = r.vehicle_id ? vehicleLabel(r.vehicle_id, r.vehicle_label ?? '') : (r.vehicle_label ?? '');
    return [
      `${c.inquiryTag}：${from} → ${to}${border ? `（${border}）` : ''}`,
      `${r.distance_km !== null ? `${r.distance_km} km` : ''}${r.driving_h !== null ? ` / ${r.driving_h} h` : ''}`,
      `${r.vehicle_count !== null ? `${c.labels.trucks} ${r.vehicle_count}` : ''}${truck ? ` · ${truck}` : ` · ${c.modes.consolidated}`}`,
      range,
    ].filter(Boolean).join('；');
  };

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const ton = Number(form.weight);
    if (!Number.isFinite(ton) || ton <= 0) return;
    setBusy(true);
    setErr('');
    setRes(null);
    try {
      const volume = Number(form.volume);
      const r = await fetch('/api/osrm-quote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          origin: form.origin,
          destination: form.destination,
          border: form.border || undefined,
          weight_kg: Math.round(ton * 1000),
          volume_m3: Number.isFinite(volume) && volume > 0 ? volume : undefined,
          mode: form.mode,
          vehicle_model_id: form.mode === 'full_truck' ? form.vehicle : undefined,
        }),
      });
      const data = (await r.json()) as CalcOk | { ok: false; note?: string };
      if (data && (data as CalcOk).ok) setRes(data as CalcOk);
      else setErr((data as { note?: string })?.note || c.offline);
    } catch {
      setErr(c.offline);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="jx-calc" id="calc">
      <header className="jx-calc-head">
        <p className="jx-eyebrow">{c.eyebrow}</p>
        <h3 className="jx-calc-title">{c.title}</h3>
        <p className="jx-calc-intro">{c.intro}</p>
      </header>

      <form className="jx-calc-form" onSubmit={submit}>
        <div className="jx-calc-grid">
          <label>
            <span>{c.fields.origin}</span>
            <select required value={form.origin} onChange={set('origin')}>
              {cn.map((p) => <option key={p.id} value={p.id}>{label(p)}</option>)}
            </select>
          </label>
          <label>
            <span>{c.fields.destination}</span>
            <select required value={form.destination} onChange={set('destination')}>
              {vn.map((p) => <option key={p.id} value={p.id}>{label(p)}</option>)}
            </select>
          </label>
          <label>
            <span>{c.fields.border}</span>
            <select value={form.border} onChange={set('border')}>
              <option value="">{c.placeholders.border}</option>
              {borders.map((p) => <option key={p.id} value={p.id}>{label(p)}</option>)}
            </select>
          </label>
          <label>
            <span>{c.fields.weight}</span>
            <input
              required
              type="number"
              min="0.1"
              step="0.1"
              inputMode="decimal"
              value={form.weight}
              onChange={set('weight')}
              placeholder={c.placeholders.weight}
            />
          </label>
          <label>
            <span>{c.fields.volume}</span>
            <input
              required={form.mode === 'consolidated'}
              type="number"
              min={form.mode === 'consolidated' ? '0.1' : '0'}
              step="0.1"
              inputMode="decimal"
              value={form.volume}
              onChange={set('volume')}
              placeholder={c.placeholders.volume}
            />
          </label>
          <label>
            <span>{c.fields.mode}</span>
            <select value={form.mode} onChange={set('mode')}>
              <option value="consolidated">{c.modes.consolidated}</option>
              <option value="full_truck">{c.modes.full_truck}</option>
            </select>
          </label>
          {form.mode === 'full_truck' ? (
            <label>
              <span>{c.fields.vehicle}</span>
              <select value={form.vehicle} onChange={set('vehicle')}>
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>{label(v)} · {v.max_load_ton}t</option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        <button className="jx-btn jx-btn-primary jx-calc-submit" type="submit" disabled={!canSubmit}>
          {busy ? c.submitting : c.submit}
        </button>
      </form>

      <div className="jx-calc-out" aria-live="polite">
        {err ? <p className="jx-calc-error">{err}</p> : null}
        {res ? (
          <>
            <p className="jx-calc-result-title">{c.resultTitle}</p>
            <div className="jx-calc-stats">
              <div>
                <span>{c.labels.distance}</span>
                <strong>{res.distance_km !== null ? `${res.distance_km} km` : '—'}</strong>
              </div>
              <div>
                <span>{c.labels.driving}</span>
                <strong>{res.driving_h !== null ? `${res.driving_h} h` : '—'}</strong>
              </div>
              <div>
                <span>{c.labels.trucks}</span>
                <strong>{res.vehicle_count !== null ? res.vehicle_count : '—'}</strong>
              </div>
              <div>
                <span>{c.labels.vehicle}</span>
                <strong>
                  {res.vehicle_id
                    ? vehicleLabel(res.vehicle_id, res.vehicle_label ?? '—')
                    : (res.mode === 'consolidated' ? c.modes.consolidated : '—')}
                </strong>
              </div>
            </div>
            {res.price_min_vnd !== null && res.price_max_vnd !== null ? (
              <div className="jx-calc-price">
                <span>{c.labels.price}</span>
                <strong>{vndFmt(res.price_min_vnd)} – {vndFmt(res.price_max_vnd)} VND</strong>
              </div>
            ) : null}
            <p className="jx-calc-note">{c.priceNote}</p>
            {res.profile_honored === false ? (
              <p className="jx-calc-profile"><b>{c.profileNoteLabel}</b>{c.profileNoteFixed}</p>
            ) : null}
            <p className="jx-calc-source">{c.source}</p>
            <button type="button" className="jx-btn jx-btn-ghost jx-calc-cta" onClick={() => onUseForInquiry(inquiryText(res))}>
              {c.toForm}
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
};

type ConsultResult = { segments: string[] } | null;

const Consult: React.FC<{
  t: AgentContent;
  lang: Lang;
  prefill: string;
  onPrefillUsed: () => void;
}> = ({ t, lang, prefill, onPrefillUsed }) => {
  const [form, setForm] = useState({
    name: '',
    company: '',
    inquiryType: t.consult.types[0],
    loadingPort: '',
    dischargePort: '',
    weightEstimate: '',
    details: '',
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ConsultResult>(null);
  const [failed, setFailed] = useState(false);
  const detailsRef = useRef<HTMLTextAreaElement>(null);

  // 测算结果一键带到询价表单（同一区块内，客户不必重复填条件）
  const useForInquiry = useCallback((text: string) => {
    setForm((f) => ({ ...f, details: text }));
    setResult(null);
    setFailed(false);
    window.setTimeout(() => detailsRef.current?.focus(), 380);
  }, []);

  useEffect(() => {
    setForm((f) => ({ ...f, inquiryType: t.consult.types[0] }));
  }, [t.consult.types]);

  useEffect(() => {
    if (!prefill) return;
    setForm((f) => ({ ...f, details: f.details ? f.details : prefill }));
    setResult(null);
    setFailed(false);
    onPrefillUsed();
    window.setTimeout(() => detailsRef.current?.focus(), 420);
  }, [prefill, onPrefillUsed]);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setFailed(false);
    try {
      const res = await fetch('/api/logistics-consult', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, language: lang }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'failed');
      const segments = [
        data.routeRecommendation,
        Array.isArray(data.documentChecklist) ? data.documentChecklist.join('\n') : '',
        data.hsCodeAdvice,
        Array.isArray(data.riskMitigation) ? data.riskMitigation.join('\n') : '',
        data.consultantStatement,
      ].filter(Boolean) as string[];
      setResult({ segments: segments.length ? segments : [t.consult.fallback] });
    } catch {
      setFailed(true);
      setResult({ segments: [t.consult.fallback] });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="jx-section jx-section-alt" id="consult">
      <div className="jx-container">
        <CalcPanel t={t} lang={lang} onUseForInquiry={useForInquiry} />
        <div className="jx-consult">
        <div className="jx-consult-copy">
          <p className="jx-eyebrow">{t.consult.eyebrow}</p>
          <h2 className="jx-consult-title">{t.consult.title}</h2>
          <p className="jx-sec-sub">{t.consult.intro}</p>
          <ol className="jx-steps">
            {t.consult.steps.map((s, i) => (
              <li key={s}>
                <span>{i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          <div className="jx-consult-contact">
            <a href={`mailto:${t.common.email}`}>{t.common.email}</a>
            <a href={`tel:+86${t.common.phone}`}>{t.common.phone}</a>
          </div>
        </div>

        <div className="jx-consult-panel">
          <form className="jx-form" onSubmit={submit}>
            <div className="jx-form-grid">
              <label>
                <span>{t.consult.fields.name}</span>
                <input required value={form.name} onChange={set('name')} placeholder={t.consult.placeholders.name} />
              </label>
              <label>
                <span>{t.consult.fields.company}</span>
                <input value={form.company} onChange={set('company')} placeholder={t.consult.placeholders.company} />
              </label>
              <label>
                <span>{t.consult.fields.inquiryType}</span>
                <select value={form.inquiryType} onChange={set('inquiryType')}>
                  {t.consult.types.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>
              </label>
              <label>
                <span>{t.consult.fields.loadingPort}</span>
                <input value={form.loadingPort} onChange={set('loadingPort')} placeholder={t.consult.placeholders.loadingPort} />
              </label>
              <label>
                <span>{t.consult.fields.dischargePort}</span>
                <input value={form.dischargePort} onChange={set('dischargePort')} placeholder={t.consult.placeholders.dischargePort} />
              </label>
              <label>
                <span>{t.consult.fields.weightEstimate}</span>
                <input value={form.weightEstimate} onChange={set('weightEstimate')} placeholder={t.consult.placeholders.weightEstimate} />
              </label>
            </div>
            <label className="jx-full">
              <span>{t.consult.fields.details}</span>
              <textarea
                ref={detailsRef}
                required
                rows={5}
                value={form.details}
                onChange={set('details')}
                placeholder={t.consult.placeholders.details}
              />
            </label>
            <button className="jx-btn jx-btn-primary jx-submit" type="submit" disabled={loading}>
              {loading ? t.consult.submitting : t.consult.submit}
            </button>
          </form>

          <div className="jx-result" aria-live="polite">
            <p className="jx-result-title">{t.consult.resultTitle}</p>
            {loading ? (
              <div className="jx-skeleton" aria-hidden="true"><i /><i /><i /></div>
            ) : result ? (
              <>
                {result.segments.map((seg, i) => (
                  <p className="jx-result-line" key={i}>
                    {seg.split('\n').map((line, j) => <span key={j}>{line}</span>)}
                  </p>
                ))}
              </>
            ) : (
              <p className="jx-result-empty">{t.consult.disclaimer}</p>
            )}
            {failed ? <p className="jx-result-error">{t.consult.error}</p> : null}
            {result && !failed ? <p className="jx-result-note">{t.consult.disclaimer}</p> : null}
          </div>
        </div>
        </div>
      </div>
    </section>
  );
};

/* ────────────────────────── CTA + contact + footer ────────────────────────── */

const Cta: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-cta" id="cta">
    <LoopVideo src={agentAssets.ctaLoop} className="jx-cta-loop" />
    <div className="jx-container jx-cta-inner">
      <h2>{t.cta.title}</h2>
      <p>{t.cta.desc}</p>
      <div className="jx-cta-actions">
        <a className="jx-btn jx-btn-light" href="#consult">{t.cta.primary}</a>
        <a className="jx-btn jx-btn-ghost-light" href={`tel:+86${t.common.phone}`}>{t.cta.secondary} · {t.common.phone}</a>
      </div>
    </div>
  </section>
);

const Contact: React.FC<{ t: AgentContent }> = ({ t }) => (
  <section className="jx-section" id="contact">
    <div className="jx-container">
      <header className="jx-sec-head">
        <p className="jx-eyebrow">{t.contact.eyebrow}</p>
        <h2 className="jx-sec-title">{t.contact.title}</h2>
        <p className="jx-sec-sub">{t.contact.intro}</p>
      </header>
      <div className="jx-contact-grid">
        {t.contact.items.map((item) => (
          <div className="jx-contact-item" key={item.label}>
            <span>{item.label}</span>
            {item.href ? <a href={item.href}>{item.value}</a> : <strong>{item.value}</strong>}
          </div>
        ))}
      </div>
    </div>
  </section>
);

const Footer: React.FC<{ t: AgentContent }> = ({ t }) => (
  <footer className="jx-footer">
    <div className="jx-container jx-footer-inner">
      <div className="jx-footer-brand">
        <img src="/assets/logo-horizontal.png" alt={t.common.company} width="196" height="32" />
        <p>{t.footer.intro}</p>
        <a className="jx-footer-mail" href={`mailto:${t.common.email}`}>{t.common.email}</a>
      </div>
      <div className="jx-footer-cols">
        {t.footer.columns.map((col) => (
          <div className="jx-footer-col" key={col.title}>
            <h4>{col.title}</h4>
            <ul>
              {col.links.map((link) => (
                <li key={link.label}><a href={link.href}>{link.label}</a></li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
    <div className="jx-container jx-footer-bottom">
      <p>{t.footer.legal}</p>
      <p>{t.footer.site}</p>
    </div>
  </footer>
);

/* ────────────────────────── page ────────────────────────── */

export default function AgentApp() {
  const [lang, setLang] = useState<Lang>(getInitialLang);
  const [activeRole, setActiveRole] = useState(0);
  const [prefill, setPrefill] = useState('');
  const t = agentI18n[lang];

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang === 'vi' ? 'vi-VN' : 'en';
    document.title = t.meta.title;
    document.querySelector('meta[name="description"]')?.setAttribute('content', t.meta.description);
    window.localStorage.setItem('jiuneng-agent-lang', lang);
  }, [lang, t.meta.title, t.meta.description]);

  const consumePrefill = useCallback(() => setPrefill(''), []);

  return (
    <div className="jx-page">
      <a className="jx-skip" href="#team">Skip to content</a>
      <Header t={t} lang={lang} setLang={setLang} />
      <main>
        <Hero
          t={t}
          roles={t.team.roles}
          activeRole={activeRole}
          setActiveRole={setActiveRole}
          onPrompt={(text) => {
            setPrefill(text || t.hero.promptHint);
            scrollToId('consult');
          }}
        />
        <Team
          t={t}
          onPick={(i) => {
            setActiveRole(i);
            setPrefill(t.hero.promptHint);
            scrollToId('consult');
          }}
        />
        <Services t={t} />
        <Apps t={t} />
        <Brain t={t} />
        <System t={t} />
        <Solutions t={t} />
        <Fleet t={t} />
        <Cases t={t} />
        <Network t={t} />
        <Qual t={t} />
        <Consult t={t} lang={lang} prefill={prefill} onPrefillUsed={consumePrefill} />
        <Cta t={t} />
        <Contact t={t} />
      </main>
      <Footer t={t} />
      <ChatPanel t={t} lang={lang} />
    </div>
  );
}
