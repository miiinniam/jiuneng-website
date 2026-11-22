import HairlineTable from '../HairlineTable';
import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { PageHead } from '../ui';
import { getChrome, getSite } from '../../content';
import { useLang } from '../../shell/LangProvider';

export default function Services() {
  const { lang } = useLang();
  const ui = getChrome(lang);
  const { labels, platform, services, solutions, vehicles } = getSite(lang);

  return (
    <>
      <PageHead no="02" kicker={ui.services.kicker} title={services.title} lead={services.intro} />

      {/* 三业务详版 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="01" title={ui.services.headTitle} lead={ui.services.headLead} />

          <div className="svc-rows">
            {services.items.map((s) => (
              <article className="svc-row" id={`svc-${s.n}`} data-testid="service-item" key={s.n}>
                <p className="micro svc-row-n">{s.n}</p>
                <div className="svc-row-main">
                  <h3 className="svc-row-title">{s.title}</h3>
                  <p className="svc-row-body">{s.body}</p>
                  <ul className="svc-points">
                    {s.points.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </div>
                <dl className="svc-row-side">
                  <dt className="micro">{labels.fit}</dt>
                  <dd className="side-v">{s.fit}</dd>
                  <dt className="micro">{labels.boundary}</dt>
                  <dd className="side-v">{s.boundary}</dd>
                </dl>
              </article>
            ))}
          </div>

          <p className="callout">
            <span className="micro">{ui.compliance}</span>
            {services.compliance}
          </p>
        </div>
      </section>

      {/* 平台系统 */}
      <section className="section" id="platform">
        <div className="wrap">
          <SectionHeader no="02" title={platform.title} lead={platform.intro} />

          <h3 className="sub-title">{labels.steps} · {ui.services.stepsSuffix}</h3>
          <ol className="steps">
            {platform.steps.map((s, i) => (
              <li className="step" data-testid="step-item" key={s}>
                <span className="micro step-n">{String(i + 1).padStart(2, '0')}</span>
                <span className="step-t">{s}</span>
              </li>
            ))}
          </ol>

          <h3 className="sub-title sub-title-gap">{labels.modules} · {ui.services.modulesSuffix}</h3>
          <HairlineTable
            className="modules"
            head={ui.services.modulesHead}
            groups={[
              {
                rows: platform.modules.map((m) => ({
                  k: m.title,
                  v: m.body,
                })),
              },
            ]}
          />

          <div className="end-row">
            <h2 className="end-title">{ui.services.endTitle}</h2>
            <a className="btn btn-outline" href="/platform">
              {ui.services.endLink}
            </a>
          </div>
        </div>
      </section>

      {/* 解决方案 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="03" title={solutions.title} lead={solutions.intro} />
        </div>
        <PhotoFull
          src={solutions.photo.src}
          alt={solutions.photo.alt}
          caption={solutions.photo.caption}
          ratio="21/9"
        />
        <div className="wrap">
          <div className="ind-grid">
            {solutions.items.map((it) => (
              <article className="ind" key={it.sector}>
                <p className="micro ind-sector">{it.sector}</p>
                <h3 className="ind-title">{it.title}</h3>
                <p className="ind-body">{it.body}</p>
                <p className="ind-fit">{ui.services.fitPrefix}{it.fit}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 设备资源 */}
      <section className="section section-end">
        <div className="wrap">
          <SectionHeader no="04" title={vehicles.title} lead={vehicles.intro} />
          <div className="eq-grid">
            {vehicles.items.map((v) => (
              <article className="eq" key={v.title}>
                <img className="eq-img" src={v.image} alt={v.alt} loading="lazy" decoding="async" />
                <h3 className="eq-title">{v.title}</h3>
                <p className="eq-body">{v.body}</p>
                <p className="micro eq-spec">{v.spec}</p>
              </article>
            ))}
          </div>

          <div className="end-row">
            <h2 className="end-title">{ui.services.ctaTitle}</h2>
            <a className="btn" href="/contact">
              {ui.submitQuote}
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
