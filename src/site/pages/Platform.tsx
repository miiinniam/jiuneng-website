import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { ArrowLink, PageHead } from '../ui';
import { getChrome, getSite } from '../../content';
import { useLang } from '../../shell/LangProvider';

export default function Platform() {
  const { lang } = useLang();
  const ui = getChrome(lang);
  const { about, platform } = getSite(lang);

  return (
    <>
      <PageHead
        no="01"
        kicker={ui.platform.kicker}
        title={platform.title}
        lead={platform.intro}
        note={platform.note}
      />

      <section className="section-tight">
        <PhotoFull src={about.photo.src} alt={about.photo.alt} caption={about.photo.caption} ratio="21/9" priority />
      </section>

      <section className="section">
        <div className="wrap">
          <SectionHeader
            no="02"
            title={ui.platform.productTitle}
            lead={ui.platform.productLead}
          />

          <div className="prods">
            {platform.products.map((p) => (
              <article className="prod" data-testid="product-item" key={p.n}>
                <p className="micro prod-n">{p.n}</p>
                <div className="prod-main">
                  <h3 className="prod-title">{p.title}</h3>
                  <p className="prod-q">{p.question}</p>
                </div>
                <ul className="prod-caps">
                  {p.caps.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
                <ArrowLink href={p.href} className="prod-link">
                  {ui.platform.open}
                </ArrowLink>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <SectionHeader
            no="03"
            title={ui.platform.reviewTitle}
            lead={ui.platform.reviewLead}
          />
          <div className="two-col">
            <div>
              <h3 className="sub-title">{ui.platform.givesTitle}</h3>
              <ul className="lines">
                {ui.platform.gives.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="sub-title">{ui.platform.whoTitle}</h3>
              <ul className="lines">
                {ui.platform.who.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="end-row">
            <h2 className="end-title">{ui.platform.endTitle}</h2>
            <a className="btn" href="/contact">
              {ui.submitQuote}
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
