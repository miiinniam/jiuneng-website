import { useEffect, useRef } from 'react';
import SectionHeader from '../SectionHeader';
import Tagline from '../Tagline';
import { ArrowLink, Band } from '../ui';
import { getChrome, getSite } from '../../content';
import { getHome } from '../../content';
import { useLang } from '../../shell/LangProvider';
import { applyLangToDocument } from '../../shell/i18n';
import { refreshScrollTriggersWhenSettled, useEnter, useMomentExpand } from '../motion';

export default function Home() {
  const { lang } = useLang();
  const ui = getChrome(lang);
  const { about, cases, labels, photoCats, services, tools, vehicles } = getSite(lang);
  const copy = getHome(lang);
  const hero = copy.hero;

  useEffect(() => {
    applyLangToDocument(lang, copy.meta.title);
  }, [lang, copy]);

  const heroRef = useRef<HTMLElement | null>(null);
  useEnter(heroRef);
  // 案例段第一张照片：全页唯一的 dealt moment（README 见 motion.ts）
  useMomentExpand();
  refreshScrollTriggersWhenSettled();

  return (
    <>
      {/* ① Hero：左文右图（真实照片进首屏，不压字、不叠渐变） */}
      <section className="hero" data-testid="hero" ref={heroRef}>
        <div className="hero-inner wrap">
          <div className="hero-copy">
            <p className="micro hero-eyebrow" data-enter="eyebrow">{hero.eyebrow}</p>
            <h1 className="hero-title">
              <span className="hero-t-line" data-enter="title-line">{hero.titleLines[0]}</span>
              <span className="hero-t-line" data-enter="title-line">{hero.titleLines[1]}</span>
            </h1>
            <p className="hero-lead" data-enter="lead">{hero.lead}</p>
            <div className="hero-cta" data-enter="cta">
              <a className="btn" href="/contact" data-testid="hero-cta-quote">
                {hero.primary}
              </a>
              <a className="btn btn-outline" href="/projects">
                {hero.secondary}
              </a>
            </div>
          </div>

          <figure className="hero-fig" data-enter="fig">
            <img
              src={hero.photo.src}
              alt={hero.photo.alt}
              loading="eager"
              fetchPriority="high"
              decoding="async"
            />
            <figcaption className="hero-cap" data-enter="figcap">
              <span className="micro">{hero.photo.caption}</span>
              <span className="micro hero-cap-n" aria-hidden="true">
                {hero.photo.index}
              </span>
            </figcaption>
          </figure>
        </div>

        <div className="wrap">
          <dl className="stat-row" data-testid="stat-row" data-enter="stat-row">
            {hero.stats.map((s) => (
              <div className="stat" key={s.label}>
                <dt className="stat-v">{s.value}</dt>
                <dd className="micro stat-l">{s.label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ② 项目分类入口：7 类现场照片，点击进对应分类图集 */}
      <section className="section-tight" data-testid="proof-strip">
        <div className="wrap">
          <div className="proof-head">
            <p className="micro">{ui.home.proofKicker}</p>
            <p className="micro proof-note">{ui.home.proofNote}</p>
          </div>
          <div className="cat-entry-grid">
            {photoCats.map((c) => (
              <a className="cat-entry" href={`/projects#${c.id}`} key={c.id}>
                <img src={c.main.src} alt={c.main.alt} loading="lazy" decoding="async" />
                <span className="cat-entry-meta">
                  <span className="micro cat-entry-n">{c.n}</span>
                  <span className="cat-entry-name">{c.name}</span>
                  <span className="micro cat-entry-count">{ui.count.replace('{n}', String(c.thumbs.length + 1))}</span>
                </span>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ② 句点段：一句大字陈述，放在照片之后、工具之前 */}
      <Tagline />

      {/* ② 工具入口条 */}
      <section className="tool-strip" data-testid="tool-strip" aria-label={ui.home.toolsAria}>
        <div className="wrap">
          <div className="strip-head">
            <p className="micro">{ui.home.toolsKicker}</p>
            <div className="strip-links">
              <ArrowLink href="/quote">{ui.home.linkQuote}</ArrowLink>
              <ArrowLink href="/platform">{ui.home.linkPlatform}</ArrowLink>
            </div>
          </div>
          <div className="tool-grid">
            {tools.map((t) => (
              <a className="tool" href={t.href} key={t.n}>
                <span className="micro tool-n">{t.n}</span>
                <span className="tool-title">{t.title}</span>
                <span className="tool-body">{t.body}</span>
                <span className="tool-open">
                  {labels.open} <span aria-hidden="true">→</span>
                </span>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ③ 三业务 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="01" title={services.title} lead={services.intro} />
          <div className="svc-grid">
            {services.items.map((s) => (
              <article className="svc" data-testid="service-item" key={s.n}>
                <p className="micro svc-n">{s.n}</p>
                <h3>{s.title}</h3>
                <p className="svc-body">{s.body}</p>
                <ul className="svc-points">
                  {s.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
                <ArrowLink href={`/services#svc-${s.n}`}>{labels.detail}</ArrowLink>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ⑤ 设备资源：3 张真实车辆照 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="02" title={vehicles.title} lead={vehicles.intro} />
          <div className="fleet-grid">
            {vehicles.items.map((v) => (
              <article className="fleet-card" data-testid="fleet-item" key={v.title}>
                <img src={v.image} alt={v.alt} loading="lazy" decoding="async" />
                <h3 className="fleet-title">{v.title}</h3>
                <p className="fleet-body">{v.body}</p>
                <p className="micro fleet-spec">{v.spec}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ⑥ 代表项目：图文对开，交替左右 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="03" title={cases.title} lead={cases.intro} />
        </div>
        <div className="wrap proj-rows">
          {cases.items.map((c, i) => (
            <article
              className={`proj-row${i % 2 === 1 ? ' proj-row-r' : ''}`}
              data-testid="case-item"
              key={c.title}
            >
              <figure className="proj-fig" data-moment={i === 0 ? 'expand' : undefined}>
                <img src={c.image} alt={c.alt} loading="lazy" decoding="async" />
                <figcaption>
                  {c.caption}
                  {c.credit ? <span className="credit">{c.credit}</span> : null}
                </figcaption>
              </figure>
              <div className="proj-body">
                <p className="micro proj-type">
                  {c.n} · {c.type}
                </p>
                <h3 className="proj-title">{c.title}</h3>
                <p className="proj-text">{c.body}</p>
                <ul className="tags">
                  {c.tags.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
                <div className="proj-scope">
                  <p className="micro">{labels.scope}</p>
                  <ul className="lines">
                    {c.scope.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
                <ArrowLink href="/projects">{labels.detail}</ArrowLink>
              </div>
            </article>
          ))}
        </div>
        <div className="wrap">
          <p className="note note-after">{cases.note}</p>
        </div>
      </section>

      {/* ⑦ 关于与中越网络 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader
            no="04"
            title={about.title}
            lead={ui.aboutLead}
          />
          <div className="about-split">
            <figure className="about-fig">
              <img src={about.teamPhoto.src} alt={about.teamPhoto.alt} loading="lazy" decoding="async" />
              <figcaption>{about.teamPhoto.caption}</figcaption>
            </figure>

            <div className="about-copy">
              <p className="lead">{about.body[0]}</p>
              <p className="about-body">{about.body[1]}</p>
              <div className="sides">
                {[about.network.china, about.network.vietnam].map((side) => (
                  <div className="side" key={side.flag}>
                    <p className="micro">{side.flag}</p>
                    <h3 className="side-name">{side.name}</h3>
                    <p className="side-body">{side.body}</p>
                    <ul className="side-points">
                      {side.points.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
              <p className="note">{about.network.note}</p>
              <ArrowLink href="/about">{labels.detail}</ArrowLink>
            </div>
          </div>

          <div className="mvv-row">
            <div className="mvv-item">
              <p className="micro">{about.mission.label}</p>
              <p className="mvv-text">{about.mission.text}</p>
            </div>
            <div className="mvv-item">
              <p className="micro">{about.vision.label}</p>
              <p className="mvv-text">{about.vision.text}</p>
            </div>
            <ul className="values values-row">
              {about.values.map((v, i) => (
                <li className="value" key={v.name}>
                  <span className="micro value-n">0{i + 1}</span>
                  <div>
                    <p className="value-name">{v.name}</p>
                    <p className="value-body">{v.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ⑧ 询价 CTA */}
      <Band no="05" title={ui.home.bandTitle} lead={labels.submitBandLead}>
        <a className="btn btn-inverse" href="/contact">
          {ui.submitQuote}
        </a>
        <a className="band-mail" href="mailto:jiuneng.vn@gmail.com">
          jiuneng.vn@gmail.com
        </a>
        <a className="band-mail" href="tel:+8615687419919">
          15687419919
        </a>
      </Band>
    </>
  );
}
