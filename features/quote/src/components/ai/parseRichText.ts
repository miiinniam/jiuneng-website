/**
 * 助手回复的轻量 Markdown 解析（纯函数，可脱浏览器测）。
 *
 * 为什么自己写：模型回的是 markdown（`**加粗**`、`- 列表`、表格、代码块），
 * 原来直接塞进 `<p>{text}</p>` 会露出星号和竖线，长回答是一坨灰字。
 * 不引第三方库（marked/react-markdown 都要十几到几十 KB），只支持模型真正会用的六种块。
 *
 * 安全：解析结果只产出**结构**，不产出 HTML 字符串，渲染端一律走 React 元素，
 * 所以模型输出里的 `<script>` 永远只是普通文字。
 *
 * 流式：半截的 `**`、不完整的表格行不会被误判成结构，按普通文字渲染，不会闪烁。
 */

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'link'; text: string; href: string };

export type Block =
  | { kind: 'p'; text: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'h'; level: 3 | 4; text: string }
  | { kind: 'quote'; text: string }
  | { kind: 'table'; head: string[]; rows: string[][] }
  | { kind: 'code'; text: string };

const RE_UL = /^[-*•·]\s+/;
const RE_OL = /^\d{1,2}[.)、]\s*/;
const RE_H = /^(#{1,4})\s+(.*)$/;
const RE_QUOTE = /^>\s?/;
const RE_TABLE_ROW = /^\|.*\|?\s*$/;
const RE_TABLE_SEP = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const RE_FENCE = /^```(\w*)\s*$/;

function splitCells(line: string): string[] {
  const body = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return body.split('|').map((c) => c.trim());
}

/** 段内换行保留（作者换行有意义），但把 `\r` 与行尾空格清掉 */
function clean(line: string): string {
  return line.replace(/\r$/, '').replace(/\s+$/, '');
}

export function parseBlocks(src: string): Block[] {
  const lines = String(src ?? '').split('\n').map(clean);
  const blocks: Block[] = [];

  let para: string[] = [];
  const flushPara = () => {
    if (!para.length) return;
    const text = para.join('\n').trim();
    if (text) blocks.push({ kind: 'p', text });
    para = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();

    // 空行：段落结束
    if (!trimmed) {
      flushPara();
      continue;
    }

    // 代码块（未闭合时把剩下的都当代码——流式输出时就是这么来的）
    const fence = RE_FENCE.exec(trimmed);
    if (fence) {
      flushPara();
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) {
        buf.push(lines[i]);
        i += 1;
      }
      blocks.push({ kind: 'code', text: buf.join('\n') });
      continue;
    }

    // 表格：本行以 | 开头，且下一行是分隔行
    if (RE_TABLE_ROW.test(trimmed) && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1].trim())) {
      flushPara();
      const head = splitCells(trimmed);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && RE_TABLE_ROW.test(lines[i].trim())) {
        rows.push(splitCells(lines[i].trim()));
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: 'table', head, rows });
      continue;
    }

    // 标题
    const h = RE_H.exec(trimmed);
    if (h) {
      flushPara();
      const level = h[1].length <= 2 ? 3 : 4;
      blocks.push({ kind: 'h', level, text: h[2].trim() });
      continue;
    }

    // 引用
    if (RE_QUOTE.test(trimmed)) {
      flushPara();
      const buf: string[] = [];
      while (i < lines.length && RE_QUOTE.test(lines[i].trim())) {
        buf.push(lines[i].trim().replace(RE_QUOTE, ''));
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: 'quote', text: buf.join('\n') });
      continue;
    }

    // 无序列表
    if (RE_UL.test(trimmed)) {
      flushPara();
      const items: string[] = [];
      while (i < lines.length && RE_UL.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(RE_UL, ''));
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: 'ul', items });
      continue;
    }

    // 有序列表
    if (RE_OL.test(trimmed)) {
      flushPara();
      const items: string[] = [];
      while (i < lines.length && RE_OL.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(RE_OL, ''));
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: 'ol', items });
      continue;
    }

    para.push(trimmed);
  }

  flushPara();
  return blocks;
}

const RE_INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\)|https?:\/\/[^\s)）,，。]+)/g;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  const src = String(text ?? '');
  RE_INLINE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RE_INLINE.exec(src)) !== null) {
    if (m.index > last) out.push({ kind: 'text', text: src.slice(last, m.index) });
    const tok = m[0];
    if (tok.startsWith('**')) {
      out.push({ kind: 'strong', text: tok.slice(2, -2) });
    } else if (tok.startsWith('`')) {
      out.push({ kind: 'code', text: tok.slice(1, -1) });
    } else if (tok.startsWith('[')) {
      const cut = tok.indexOf('](');
      out.push({ kind: 'link', text: tok.slice(1, cut), href: tok.slice(cut + 2, -1) });
    } else {
      out.push({ kind: 'link', text: tok, href: tok });
    }
    last = m.index + tok.length;
  }
  if (last < src.length) out.push({ kind: 'text', text: src.slice(last) });
  return out;
}
