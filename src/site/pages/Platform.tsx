import PhotoFull from '../PhotoFull';
import SectionHeader from '../SectionHeader';
import { ArrowLink, PageHead } from '../ui';
import { about, platform } from '../content';

export default function Platform() {
  return (
    <>
      <PageHead
        no="01"
        kicker="平台"
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
            title="四项工具，按项目推进顺序排列"
            lead="先算线路，再算税费，再匹配车辆；需求还没成形时，用测算助手把要点整理出来交给项目经理。"
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
                  打开
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
            title="工具之外，方案仍由人复核"
            lead="测算结果用于把沟通条件对齐，不替代现场核查与单证核定。"
          />
          <div className="two-col">
            <div>
              <h3 className="sub-title">工具给出什么</h3>
              <ul className="lines">
                <li>干线里程、行车时长、车辆数量与参考运价区间</li>
                <li>中国端与越南端的报关费用区间</li>
                <li>按单件尺寸匹配的车型与超限标注</li>
              </ul>
            </div>
            <div>
              <h3 className="sub-title">谁来确认</h3>
              <ul className="lines">
                <li>项目经理复核线路、车型与单证路径</li>
                <li>正式报价以复核后的方案为准</li>
                <li>越南侧由本地合作代理网络执行</li>
              </ul>
            </div>
          </div>

          <div className="end-row">
            <h2 className="end-title">把项目条件发来，直接进入复核</h2>
            <a className="btn" href="/contact">
              提交询价
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
