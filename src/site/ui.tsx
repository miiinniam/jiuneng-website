import { useRef } from 'react';
import type { ReactNode } from 'react';
import { useEnter } from './motion';

/** 文字链：4px 下划线偏移，hover 只变色不位移。 */
export function ArrowLink({
  href,
  children,
  className = '',
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a className={`arrow-link ${className}`.trim()} href={href}>
      {children}
      <span aria-hidden="true">→</span>
    </a>
  );
}

/** 页头：编号 + h1 + lead。子页统一用它，不做大图。 */
export function PageHead({
  no,
  kicker,
  title,
  lead,
  note,
}: {
  no: string;
  kicker: string;
  title: string;
  lead?: string;
  note?: string;
}) {
  const ref = useRef<HTMLElement | null>(null);
  useEnter(ref);

  return (
    <header className="page-head" ref={ref}>
      <div className="wrap">
        <p className="micro ph-kicker" data-enter="eyebrow">
          <span className="ph-n">{no}</span>
          <span>{kicker}</span>
        </p>
        <h1 className="page-title" data-enter="title-line">{title}</h1>
        {lead ? <p className="lead page-lead" data-enter="lead">{lead}</p> : null}
        {note ? <p className="page-note">{note}</p> : null}
      </div>
    </header>
  );
}

/** 反色收尾带：全站最多一处（首页 CTA）。 */
export function Band({
  no,
  title,
  lead,
  children,
}: {
  no: string;
  title: string;
  lead?: string;
  children: ReactNode;
}) {
  return (
    <section className="band" data-testid="home-cta">
      <div className="wrap">
        <p className="micro band-n">{no}</p>
        <div className="band-grid">
          <h2 className="band-t">{title}</h2>
          <div className="band-side">
            {lead ? <p className="band-lead">{lead}</p> : null}
            <div className="band-cta">{children}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
