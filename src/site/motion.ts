/**
 * v10 动效层 —— GSAP（官方 gsap-skills：core / timeline / scrolltrigger / react / performance）
 *
 * 本站两条硬约束（都在这里被尊重，改动前先读）：
 *  1) **不用 CSS 写 `opacity:0` 初态**。历史上 `opacity:0` 入场 + IntersectionObserver 不触发
 *     （爬虫 / 截图工具 / rAF 节流）会让整块内容消失。这里全部用 `gsap.from()`：初态由 JS
 *     在动画开始那一刻自己设，JS 没跑（无 JS / 爬虫 / 截图失败）时内容就是常态可见。
 *  2) **入场只加在挂载即播放的元素上**（Hero）。滚动区只用「按滚动进度着色」这种
 *     不改可见性的动效（句点段），不加 fade-in / 不位移 / 不视差。
 *
 * reduce 动效：`gsap.matchMedia()` 里注册，用户开 reduce 时这段代码整段不注册 —— 元素保持终态。
 */
import { useEffect, type RefObject } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/** enter 曲线取自 tokens.css 的 `--ease-enter: cubic-bezier(.22,1,.36,1)` */
const EASE_ENTER = 'power3.out';

const NO_PREF = '(prefers-reduced-motion: no-preference)';

/**
 * 页面入场：一次，挂载即播。首页 Hero 与所有子页 PageHead 共用这一支。
 * 只动 transform / opacity / clip-path —— 不触发布局（gsap-performance）。
 *
 * 选择器「有则动、无则跳过」：子页没有照片/按钮/数据行时对应 tween 自动空转，
 * 不必为每个页面各写一份。
 */
export function useEnter(root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;

    const mm = gsap.matchMedia();
    mm.add(NO_PREF, () => {
      const ctx = gsap.context(() => {
        const tl = gsap.timeline({ defaults: { ease: EASE_ENTER } });

        tl.from('[data-enter="eyebrow"]', { y: 10, opacity: 0, duration: 0.5 }, 0)
          .from(
            '[data-enter="title-line"]',
            { y: 26, opacity: 0, duration: 0.95, stagger: 0.09 },
            0.05,
          )
          .from('[data-enter="lead"]', { y: 14, opacity: 0, duration: 0.7 }, 0.34)
          .from('[data-enter="cta"] > *', { y: 12, opacity: 0, duration: 0.6, stagger: 0.08 }, 0.44)
          // 照片：自右向左「拉开」，同时轻微回缩 —— 只动 clip-path 与 scale
          // 必须 fromTo 写明终值：目标原值是 `clip-path: none`，GSAP 无法从 inset() 插到 none。
          .fromTo(
            '[data-enter="fig"] img',
            { clipPath: 'inset(0% 0% 0% 100%)' },
            { clipPath: 'inset(0% 0% 0% 0%)', duration: 1.1, ease: 'expo.inOut' },
            0.08,
          )
          .fromTo(
            '[data-enter="fig"] img',
            { scale: 1.05 },
            { scale: 1, duration: 1.6, ease: 'expo.out' },
            0.08,
          )
          .from('[data-enter="figcap"]', { opacity: 0, duration: 0.5 }, 0.72)
          .from(
            '[data-enter="stat-row"] > *',
            { y: 8, opacity: 0, duration: 0.5, stagger: 0.06 },
            0.5,
          );
        return tl;
      }, el);

      return () => ctx.revert();
    });

    return () => {
      mm.revert();
    };
  }, [root]);
}

/**
 * 句点段：滚动进度驱动的「逐块着色」（type-led moment）。
 *
 * 与 `opacity:0` 入场的关键区别：初态是 0.28 的中性可读色，**内容任何时刻都看得见**；
 * 动的是颜色浓度，不是有没有。
 */
export function useTaglineScrub(root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;

    const mm = gsap.matchMedia();
    mm.add(NO_PREF, () => {
      const ctx = gsap.context(() => {
        const blocks = gsap.utils.toArray<HTMLElement>('.tagline-w', el);
        if (!blocks.length) return;

        gsap.fromTo(
          blocks,
          { opacity: 0.28 },
          {
            opacity: 1,
            ease: 'none',
            stagger: 0.14,
            scrollTrigger: {
              trigger: el,
              // 起点：块顶进到视口 82%；终点：块底升到视口 55%。
              // 这段距离 ≈ 块高 + 0.27 屏，读得完三段话，不会"刚看见就全亮"。
              start: 'top 82%',
              end: 'bottom 55%',
              scrub: 0.5,
              // 只管浓度，不动布局；刷新时保持当前进度
              invalidateOnRefresh: true,
            },
          },
        );
      }, el);

      return () => ctx.revert();
    });

    return () => {
      mm.revert();
    };
  }, [root]);
}

/**
 * 照片 moment（taste-skill：每页一处"被安排过的瞬间"）。
 *
 * 做法参照 react-bits 的 ScrollExpand 思路，但**按本站规范重写**：
 *  - 没有圆角（品牌 0–2px）、没有 scrim 压暗、没有压在图上的标题；
 *  - 只动 `clip-path` 与 `scale`，照片本身不加遮罩、不加滤镜；
 *  - 初态由 JS 设定：无 JS / reduce 时照片就是满格常态，不存在"空白图位"。
 *
 * 用法：给要展开的那张图的 `<figure>` 加 `data-moment="expand"`，页面里调一次这个 hook。
 * 每页只放一处 —— 多了就成了"每张图都在动"，反而不像设计。
 */
export function useMomentExpand(scope?: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root: ParentNode = scope?.current ?? document;

    const mm = gsap.matchMedia();
    mm.add(NO_PREF, () => {
      const figures = Array.from(root.querySelectorAll<HTMLElement>('[data-moment="expand"]'));
      if (!figures.length) return;

      const ctx = gsap.context(() => {
        for (const fig of figures) {
          const img = fig.querySelector('img');
          if (!img) continue;

          const tl = gsap.timeline({
            scrollTrigger: {
              trigger: fig,
              // 图顶进到视口 92% 开始，升到 45% 时完全展开
              start: 'top 92%',
              end: 'top 45%',
              scrub: 0.6,
            },
          });

          tl.fromTo(
            img,
            { clipPath: 'inset(7% 7% 7% 7%)' },
            { clipPath: 'inset(0% 0% 0% 0%)', ease: 'none' },
            0,
          ).fromTo(img, { scale: 1.07 }, { scale: 1, ease: 'none' }, 0);
        }
      }, root as Element);

      return () => ctx.revert();
    });

    return () => {
      mm.revert();
    };
  }, [scope]);
}

/** 图片加载后再量一次滚动触发点，避免字体/图片回流让 trigger 落在错误位置。 */
export function refreshScrollTriggersWhenSettled() {
  if (typeof window === 'undefined') return;
  const refresh = () => ScrollTrigger.refresh();
  window.addEventListener('load', refresh, { once: true });
  if (document.fonts?.ready) document.fonts.ready.then(refresh).catch(() => {});
}
