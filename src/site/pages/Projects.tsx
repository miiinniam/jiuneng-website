import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { PageHead } from '../ui';
import { cases, labels } from '../content';

export default function Projects() {
  return (
    <>
      <PageHead
        no="03"
        kicker="代表项目"
        title={cases.title}
        lead={cases.intro}
        note={cases.note}
      />

      <div className="case-flow">
        {cases.items.map((c) => (
          <article className="case case-detail" data-testid="case-item" key={c.title}>
            <PhotoFull src={c.image} alt={c.alt} ratio="21/9" />
            <div className="wrap">
              <div className="case-body">
                <div className="cb-head">
                  <p className="micro">
                    {c.n} · {c.type}
                  </p>
                  <h2 className="cb-title">{c.title}</h2>
                  <ul className="tags">
                    {c.tags.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
                <p className="cb-body">{c.body}</p>
                <div className="cb-scope">
                  <p className="micro">{labels.scope}</p>
                  <ul className="lines">
                    {c.scope.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>

      <section className="section section-end">
        <div className="wrap">
          <SectionHeader
            no="04"
            title="项目类型索引"
            lead="按货物类型查看对应的运输组织方式；具体客户与数据在取得授权后公开。"
          />
          <ol className="index-list">
            {cases.types.map((t, i) => (
              <li className="index-row" key={t.name}>
                <span className="micro index-n">{String(i + 1).padStart(2, '0')}</span>
                <span className="index-name">{t.name}</span>
                <span className="index-body">{t.body}</span>
              </li>
            ))}
          </ol>

          <div className="end-row">
            <h2 className="end-title">同类项目可直接对接测算</h2>
            <a className="btn btn-outline" href="/platform/routing">
              线路测算
            </a>
            <a className="btn" href="/contact">
              提交询价
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
