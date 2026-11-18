import HairlineTable from '../HairlineTable';
import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { PageHead } from '../ui';
import { labels, platform, services, solutions, vehicles } from '../content';

export default function Services() {
  return (
    <>
      <PageHead no="02" kicker="业务与服务" title={services.title} lead={services.intro} />

      {/* 三业务详版 */}
      <section className="section">
        <div className="wrap">
          <SectionHeader no="01" title="三类业务的边界与交付" lead="每条业务写明定义、要点、适用货物与交付边界，避免把供应链上说不到的事写进来。" />

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
            <span className="micro">合规说明</span>
            {services.compliance}
          </p>
        </div>
      </section>

      {/* 平台系统 */}
      <section className="section" id="platform">
        <div className="wrap">
          <SectionHeader no="02" title={platform.title} lead={platform.intro} />

          <h3 className="sub-title">{labels.steps} · 12 步</h3>
          <ol className="steps">
            {platform.steps.map((s, i) => (
              <li className="step" data-testid="step-item" key={s}>
                <span className="micro step-n">{String(i + 1).padStart(2, '0')}</span>
                <span className="step-t">{s}</span>
              </li>
            ))}
          </ol>

          <h3 className="sub-title sub-title-gap">{labels.modules} · 5 个</h3>
          <HairlineTable
            className="modules"
            head={['模块', '记录内容']}
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
            <h2 className="end-title">四项在线工具，从测算到车辆匹配</h2>
            <a className="btn btn-outline" href="/platform">
              平台总览
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
                <p className="ind-fit">适用：{it.fit}</p>
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
            <h2 className="end-title">把货物尺寸与交付时间发来，我们按项目匹配车辆</h2>
            <a className="btn" href="/contact">
              提交询价
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
