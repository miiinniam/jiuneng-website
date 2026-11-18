/**
 * 满幅实拍：直接作为 section 的块级子元素，width:100% 贴到视口左右边缘。
 * 不用 100vw（滚动条宽度会导致横向溢出），不套框、不加圆角、不叠渐变。
 */
export default function PhotoFull({
  src,
  alt,
  caption,
  ratio = '16/9',
  priority = false,
}: {
  src: string;
  alt: string;
  caption?: string;
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
      {caption ? <figcaption className="figcap wrap">{caption}</figcaption> : null}
    </figure>
  );
}
