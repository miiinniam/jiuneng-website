import HairlineTable from '../HairlineTable';
import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { PageHead } from '../ui';
import { getChrome, getSite } from '../../content';
import { useLang } from '../../shell/LangProvider';

export default function About() {
  const { lang } = useLang();
  const ui = getChrome(lang);
  const { about } = getSite(lang);

  return (
    <>
      <PageHead
        no="04"
        kicker={ui.about.kicker}
        title={about.title}
        lead={ui.aboutLead}
      />

      {/* 公司介绍 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="01" title={ui.about.intro} />
          <div className="two-col">
            <p className="lead">{about.body[0]}</p>
            <p>{about.body[1]}</p>
          </div>
        </div>
      </section>

      {/* 使命 / 愿景 / 价值观 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="02" title={ui.about.mvv} />
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

          <h3 className="sub-title sub-title-gap">{about.valuesTitle} · {ui.about.valuesSuffix}</h3>
          <ul className="values">
            {about.values.map((v, i) => (
              <li className="value" data-testid="value-item" key={v.name}>
                <span className="micro value-n">0{i + 1}</span>
                <div>
                  <p className="value-name">{v.name}</p>
                  <p className="value-body">{v.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 中越网络 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader
            no="03"
            title={about.network.title}
            lead={about.network.intro}
          />
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

          <div className="net-photos">
            {about.network.photos.map((p) => (
              <figure className="net-photo" key={p.src}>
                <img src={p.src} alt={p.alt} loading="lazy" decoding="async" />
                <figcaption>
                  {p.caption}
                  <span className="credit">{p.credit}</span>
                </figcaption>
              </figure>
            ))}
          </div>
          <p className="callout">
            <span className="micro">{ui.compliance}</span>
            {about.network.note}
          </p>
        </div>
      </section>

      <PhotoFull
        src={about.photo.src}
        alt={about.photo.alt}
        caption={about.photo.caption}
        credit={about.photo.credit}
        ratio="21/9"
      />

      {/* 企业登记 */}
      <section className="section section-end">
        <div className="wrap">
          <SectionHeader
            no="04"
            title={about.registry.title}
            lead={about.registry.intro}
          />
          <HairlineTable
            testId="entity-table"
            groups={about.registry.groups}
            head={ui.about.registryHead}
          />
          <div className="end-row">
            <h2 className="end-title">{ui.about.endTitle}</h2>
            <a className="btn" href="/contact">
              {ui.about.contact}
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
