/**
 * 满幅实拍：直接作为 section 的块级子元素，width:100% 贴到视口左右边缘。
 * 不用 100vw（滚动条宽度会导致横向溢出），不套框、不加圆角、不叠渐变。
 *
 * `credit`：CC BY / CC BY-SA 的图片来源署名（作者 + 许可）。没有署名义务的
 * 自有实拍留空；有义务的必须填，否则等于用图不合规。
 */
export default function PhotoFull({
  src,
  alt,
  caption,
  credit,
  ratio = '16/9',
  priority = false,
}: {
  src: string;
  alt: string;
  caption?: string;
  credit?: string;
  ratio?: '21/9' | '16/9' | '3/2' | '2/1';
  priority?: boolean;
}) {
  return (
    <figure className="fig-full">
      <img
        className={`fig-img fig-img-${ratio.replace('/', '-')}`}
        src={src}
        alt={alt}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        decoding="async"
      />
      {caption || credit ? (
        <figcaption className="figcap wrap">
          {caption ? <span>{caption}</span> : null}
          {credit ? <span className="figcredit">{credit}</span> : null}
        </figcaption>
      ) : null}
    </figure>
  );
}
