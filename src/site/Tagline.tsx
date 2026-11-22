import { useRef } from 'react';
import { getSite } from '../content';
import { useLang } from '../shell/LangProvider';
import { useTaglineScrub } from './motion';

/**
 * 句点段（B11 tagline）：一行大字陈述核心做法。
 *
 * v10 起改由 GSAP ScrollTrigger 按滚动进度逐块着色（`useTaglineScrub`），
 * 取代原来的 IntersectionObserver 一次性切换。两条约束不变：
 *  1) 初态不是 opacity:0，而是 0.28 的中性可读色——内容任何时刻都看得见，
 *     截图/爬虫/rAF 节流下也不会出现空白块（历史事故：opacity:0 初态 + IO 不触发 = 整块消失）；
 *  2) 只动 opacity，不动 transform；reduce 下 GSAP 整段不注册，直接显示终态。
 */
export default function Tagline() {
  const { lang } = useLang();
  const { tagline } = getSite(lang);
  const ref = useRef<HTMLElement | null>(null);
  useTaglineScrub(ref);

  let k = 0;
  return (
    <section className="tagline" ref={ref} data-testid="tagline">
      <div className="wrap">
        <p className="micro tagline-lab">{tagline.label}</p>
        <h2 className="tagline-t">
          {tagline.lines.map((line, li) => (
            <span className="tagline-line" key={li}>
              {line.map((chunk) => {
                k += 1;
                return (
                  <span className="tagline-w" key={`${chunk}-${k}`}>
                    {chunk}
                  </span>
                );
              })}
            </span>
          ))}
        </h2>
        <p className="micro tagline-note">{tagline.note}</p>
      </div>
    </section>
  );
}
