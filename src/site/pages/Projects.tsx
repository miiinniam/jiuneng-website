import { PageHead } from '../ui';
import { getChrome, getSite } from '../../content';
import { useLang } from '../../shell/LangProvider';

/**
 * v9 项目页：按画面类型分 7 类，每类「主图 7/5 对开 + 缩略图行」，末尾「作业实录」3 段视频。
 * 分类数据在 content.ts 的 photoCats（一张素材只归一类，34 张全量落位）。
 */
export default function Projects() {
  const { lang } = useLang();
  const ui = getChrome(lang);
  const { categoryPage, labels, photoCats, videoStrip } = getSite(lang);

  return (
    <>
      <PageHead
        no="03"
        kicker={categoryPage.kicker}
        title={categoryPage.title}
        lead={categoryPage.lead}
        note={categoryPage.note}
      />

      <nav className="cat-index-wrap" aria-label={ui.projects.navAria}>
        <div className="wrap">
          <ol className="cat-index">
            {photoCats.map((c) => (
              <li key={c.id}>
                <a href={`#${c.id}`}>
                  <span className="micro cat-n">{c.n}</span>
                  <span className="cat-index-name">{c.name}</span>
                  <span className="micro cat-count">{c.thumbs.length + 1}</span>
                </a>
              </li>
            ))}
          </ol>
        </div>
      </nav>

      {photoCats.map((c, i) => (
        <section className="cat-block" id={c.id} key={c.id} data-testid="photo-cat">
          <div className="wrap">
            <header className="cat-head">
              <div>
                <p className="micro cat-sector">
                  {c.n} · {c.sector}
                </p>
                <h2 className="cat-name">{c.name}</h2>
              </div>
              <p className="cat-meta">
                <span className="cat-total">{ui.count.replace('{n}', String(c.thumbs.length + 1))}</span> · {c.lead}
              </p>
            </header>

            <div className={`cat-split${i % 2 === 1 ? ' cat-split-r' : ''}`}>
              <figure className="cat-fig">
                <img src={c.main.src} alt={c.main.alt} loading="lazy" decoding="async" />
                <figcaption>
                  <span>{c.main.caption}</span>
                  {c.main.credit ? <span className="credit">{c.main.credit}</span> : null}
                </figcaption>
              </figure>

              <div className="cat-body">
                <p className="cat-text">{c.body}</p>
                <p className="micro cat-scope-label">{labels.scope}</p>
                <ul className="lines cat-lines">
                  {c.lines.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
                <p className="micro cat-note">{c.note}</p>
              </div>
            </div>

            <div className="cat-strip">
              {c.thumbs.map((t) => (
                <figure className="cat-thumb" key={t.src}>
                  <img src={t.src} alt={t.alt} loading="lazy" decoding="async" />
                  <figcaption>
                    <span>{t.caption}</span>
                    {t.credit ? <span className="credit">{t.credit}</span> : null}
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>
        </section>
      ))}

      <section className="section vid-section" data-testid="video-strip">
        <div className="wrap">
          <div className="proof-head">
            <p className="micro">{videoStrip.eyebrow}</p>
            <p className="micro proof-note">{videoStrip.note}</p>
          </div>
          <h2 className="cat-name vid-title">{videoStrip.title}</h2>
          <div className="vid-strip">
            {videoStrip.items.map((v) => (
              <figure className="vid" key={v.src}>
                <video
                  className="vid-frame"
                  controls
                  preload="none"
                  playsInline
                  muted
                  poster={v.poster}
                  aria-label={v.caption}
                >
                  <source src={v.src} type="video/mp4" />
                </video>
                <figcaption>
                  <span>{v.caption}</span>
                  <span className="micro vid-dur">{v.duration}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-end">
        <div className="wrap">
          <div className="end-row">
            <h2 className="end-title">{ui.projects.endTitle}</h2>
            <a className="btn btn-outline" href="/platform/routing">
              {ui.projects.routing}
            </a>
            <a className="btn" href="/contact">
              {ui.submitQuote}
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
