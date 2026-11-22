/**
 * 助手回复的富文本渲染（瑞士编辑风：发丝线、无气泡、无圆角）。
 *
 * 支持：段落（保留作者换行）、无序/有序列表、标题、引用、表格、代码块、
 * 行内 **加粗** / `代码` / [链接](url) / 裸链接。
 * 一律渲染成 React 元素，不拼 HTML 字符串 —— 模型输出的标签只会当文字。
 */
import { Fragment } from 'react';
import { parseBlocks, parseInline, type Block, type Inline } from './parseRichText';

function safeHref(href: string): string | null {
  const h = href.trim();
  if (/^https?:\/\//i.test(h) || /^mailto:/i.test(h)) return h;
  return null;
}

function InlineRun({ text }: { text: string }) {
  const parts: Inline[] = parseInline(text);
  return (
    <>
      {parts.map((p, i) => {
        if (p.kind === 'strong') return <strong key={i}>{p.text}</strong>;
        if (p.kind === 'code') return <code key={i}>{p.text}</code>;
        if (p.kind === 'link') {
          const href = safeHref(p.href);
          if (!href) return <Fragment key={i}>{p.text}</Fragment>;
          return (
            <a key={i} href={href} target="_blank" rel="noreferrer noopener">
              {p.text}
            </a>
          );
        }
        return <Fragment key={i}>{p.text}</Fragment>;
      })}
    </>
  );
}

function BlockView({ b }: { b: Block }) {
  switch (b.kind) {
    case 'h': {
      const Tag = b.level === 3 ? 'h3' : 'h4';
      return (
        <Tag>
          <InlineRun text={b.text} />
        </Tag>
      );
    }
    case 'ul':
      return (
        <ul>
          {b.items.map((it, i) => (
            <li key={i}>
              <InlineRun text={it} />
            </li>
          ))}
        </ul>
      );
    case 'ol':
      return (
        <ol>
          {b.items.map((it, i) => (
            <li key={i}>
              <InlineRun text={it} />
            </li>
          ))}
        </ol>
      );
    case 'quote':
      return (
        <blockquote>
          <InlineRun text={b.text} />
        </blockquote>
      );
    case 'table':
      return (
        <div className="q-rt-scroll">
          <table>
            <thead>
              <tr>
                {b.head.map((c, i) => (
                  <th key={i} scope="col">
                    <InlineRun text={c} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((c, ci) => (
                    <td key={ci}>
                      <InlineRun text={c} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case 'code':
      return (
        <pre>
          <code>{b.text}</code>
        </pre>
      );
    default:
      return (
        <p>
          <InlineRun text={b.text} />
        </p>
      );
  }
}

export default function RichText({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className="q-rt">
      {blocks.map((b, i) => (
        <Fragment key={i}>
          <BlockView b={b} />
        </Fragment>
      ))}
    </div>
  );
}
