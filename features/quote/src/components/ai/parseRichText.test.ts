import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseBlocks, parseInline } from './parseRichText.ts';

test('段落：作者换行保留在一段里，空行切段', () => {
  const b = parseBlocks('第一行\n第二行\n\n第二段');
  assert.equal(b.length, 2);
  assert.equal(b[0].kind, 'p');
  assert.equal(b[0].kind === 'p' && b[0].text, '第一行\n第二行');
});

test('无序列表：- / • / · 都认', () => {
  const b = parseBlocks('- 甲\n• 乙\n· 丙');
  assert.equal(b.length, 1);
  assert.equal(b[0].kind, 'ul');
  assert.deepEqual(b[0].kind === 'ul' && b[0].items, ['甲', '乙', '丙']);
});

test('有序列表：1. 与 1) 都认，且不吞中文序号', () => {
  const b = parseBlocks('1. 起运\n2) 口岸\n3、目的地');
  assert.equal(b[0].kind, 'ol');
  assert.deepEqual(b[0].kind === 'ol' && b[0].items, ['起运', '口岸', '目的地']);
});

test('表格：表头 + 分隔行 + 数据行', () => {
  const b = parseBlocks('| 项目 | 数值 |\n| --- | --- |\n| 里程 | 302.8 km |\n| 车数 | 1 |');
  assert.equal(b.length, 1);
  assert.equal(b[0].kind, 'table');
  if (b[0].kind === 'table') {
    assert.deepEqual(b[0].head, ['项目', '数值']);
    assert.deepEqual(b[0].rows, [['里程', '302.8 km'], ['车数', '1']]);
  }
});

test('没有分隔行的竖线文字不当表格', () => {
  const b = parseBlocks('| 这不是表格');
  assert.equal(b[0].kind, 'p');
});

test('标题与引用', () => {
  const b = parseBlocks('## 结论\n> 报价需项目经理核定');
  assert.deepEqual(b.map((x) => x.kind), ['h', 'quote']);
  assert.equal(b[0].kind === 'h' && b[0].level, 3);
});

test('代码块：未闭合也当代码（流式中途）', () => {
  const b = parseBlocks('```\nfoo()\nbar()');
  assert.equal(b[0].kind, 'code');
  assert.equal(b[0].kind === 'code' && b[0].text, 'foo()\nbar()');
});

test('行内：加粗 / 代码 / 链接 / 裸链', () => {
  const t = parseInline('共 **3 车**，见 `报价单` 与 [说明](https://x.test/a)，或 https://y.test');
  const kinds = t.map((x) => x.kind);
  assert.deepEqual(kinds, ['text', 'strong', 'text', 'code', 'text', 'link', 'text', 'link']);
  const link = t.find((x) => x.kind === 'link');
  assert.equal(link && link.kind === 'link' && link.href, 'https://x.test/a');
});

test('流式半截：未闭合的 ** 不当加粗', () => {
  const t = parseInline('里程 **302');
  assert.equal(t.length, 1);
  assert.equal(t[0].kind, 'text');
});

test('中文标点不被吞进链接', () => {
  const t = parseInline('详见 https://x.test/a，然后');
  const link = t.find((x) => x.kind === 'link');
  assert.equal(link && link.kind === 'link' && link.href, 'https://x.test/a');
});
