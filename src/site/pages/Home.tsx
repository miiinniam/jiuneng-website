import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { ArrowLink, Band } from '../ui';
import { about, cases, hero, labels, services, tools } from '../content';

export default function Home() {
  return (
    <>
      {/* ① Hero */}
      <section className="hero" data-testid="hero">
        <div className="wrap">
          <p className="micro hero-eyebrow">{hero.eyebrow}</p>
          <div className="hero-grid">
            <h1 className="hero-title">
              {hero.titleLines[0]}
              <br />
              {hero.titleLines[1]}
            </h1>
            <div className="hero-side">
              <p className="lead">{hero.lead}</p>
              <div className="hero-cta">
                <a className="btn" href="/contact" data-testid="hero-cta-quote">
                  {hero.primary}
                </a>
                <a className="btn btn-outline" href="/projects">
                  {hero.secondary}
                </a>
              </div>
            </div>
          </div>

          <dl className="stat-row" data-testid="stat-row">
            {hero.stats.map((s) => (
              <div className="stat" key={s.label}>
                <dt className="stat-v">{s.value}</dt>
                <dd className="micro stat-l">{s.label}</dd>
              </div>
            ))}
          </dl>
        </div>

        <PhotoFull
          src={hero.photo.src}
          alt={hero.photo.alt}
          caption={hero.photo.caption}
          ratio="21/9"
          priority
        />
      </section>

      {/* ② 工具入口条 */}
      <section className="tool-strip" data-testid="tool-strip" aria-label="平台工具">
        <div className="wrap">
          <div className="strip-head">
            <p className="micro">平台工具 / 在线测算</p>
            <ArrowLink href="/platform">平台总览</ArrowLink>
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

      {/* ④ 代表项目 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="02" title={cases.title} lead={cases.intro} />
        </div>
        <div className="case-flow">
          {cases.items.map((c) => (
            <article className="case" data-testid="case-item" key={c.title}>
              <PhotoFull src={c.image} alt={c.alt} ratio="21/9" />
              <div className="wrap">
                <div className="case-meta">
                  <p className="micro case-type">
                    {c.n} · {c.type}
                  </p>
                  <div>
                    <h3 className="case-title">{c.title}</h3>
                    <p className="case-line">{c.oneLine}</p>
                  </div>
                  <ArrowLink href="/projects">{labels.detail}</ArrowLink>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ⑤ 关于与网络 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader
            no="03"
            title={about.title}
            lead="越南河内登记主体，中国侧由广西玖一进出口贸易有限公司提供进出口与报关支持。"
          />
          <div className="about-grid">
            <div className="about-l">
              <div className="mvv">
                <div className="mvv-item">
                  <p className="micro">{about.mission.label}</p>
                  <p className="mvv-text">{about.mission.text}</p>
                </div>
                <div className="mvv-item">
                  <p className="micro">{about.vision.label}</p>
                  <p className="mvv-text">{about.vision.text}</p>
                </div>
              </div>

              <h3 className="values-title">{about.valuesTitle}</h3>
              <ul className="values">
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

            <div className="about-r">
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
        </div>
      </section>

      {/* ⑥ 询价 CTA */}
      <Band no="04" title="提交项目需求" lead={labels.submitBandLead}>
        <a className="btn btn-inverse" href="/contact">
          提交询价
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
