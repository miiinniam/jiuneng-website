// 来源：OSRM++ 报价站原始代码 features/quote/legacy/frontend/src/lib/
// 移植：迁入官网 features/quote/src/engine/（2026-11-20），字段名/函数名一律不改。

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  perpendicularDistance,
  simplify,
  principalAngle,
  rotate,
  fitToBox,
  toPath,
  type Pt,
} from "./geometry.ts";

test("perpendicularDistance: 点到水平线段的正交距离", () => {
  assert.equal(perpendicularDistance([1, 3], [0, 0], [5, 0]), 3);
});

test("perpendicularDistance: 退化线段（两端重合）时退化为点距", () => {
  assert.equal(perpendicularDistance([3, 4], [0, 0], [0, 0]), 5);
});

test("simplify: 共线点被压掉，只留两端", () => {
  const line: Pt[] = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
  const out = simplify(line, 0.01);
  assert.deepEqual(out, [[0, 0], [4, 0]]);
});

test("simplify: 明显偏离的点被保留", () => {
  const spike: Pt[] = [[0, 0], [1, 0], [2, 5], [3, 0], [4, 0]];
  const out = simplify(spike, 0.01);
  assert.ok(out.length >= 3, `拐点应被保留，实际 ${out.length} 点`);
  assert.ok(out.some((p) => p[1] === 5), "峰值点必须保留");
});

test("simplify: 容差越大点数越少（单调性）", () => {
  const pts: Pt[] = Array.from({ length: 60 }, (_, i) => [i, Math.sin(i / 3) * 4] as Pt);
  const loose = simplify(pts, 1.0).length;
  const tight = simplify(pts, 0.05).length;
  assert.ok(loose < tight, `容差大应更少：loose=${loose} tight=${tight}`);
});

test("simplify: 空数组与单点不崩", () => {
  assert.deepEqual(simplify([], 0.1), []);
  assert.deepEqual(simplify([[1, 1]], 0.1), [[1, 1]]);
});

test("principalAngle: 沿 x 轴分布的点主轴为 0", () => {
  const pts: Pt[] = [[0, 0], [1, 0], [2, 0], [3, 0]];
  assert.ok(Math.abs(principalAngle(pts)) < 1e-9);
});

test("principalAngle: 沿 45° 对角线分布的点主轴为 45°", () => {
  const pts: Pt[] = [[0, 0], [1, 1], [2, 2], [3, 3]];
  assert.ok(Math.abs(principalAngle(pts) - Math.PI / 4) < 1e-9);
});

test("rotate: 旋转 -90° 把主轴转正", () => {
  const pts: Pt[] = [[0, 0], [1, 1], [2, 2]];
  const th = principalAngle(pts);
  const out = rotate(pts, -th);
  const ys = out.map((p) => p[1]);
  const spread = Math.max(...ys) - Math.min(...ys);
  assert.ok(spread < 1e-9, `转正后 y 应几乎无变化，实际跨度 ${spread}`);
});

test("fitToBox: 等比缩放且不超出画布", () => {
  const pts: Pt[] = [[0, 0], [10, 0], [10, 4], [0, 4]];
  const { points, scale } = fitToBox(pts, 200, 100, 10);
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  assert.ok(Math.min(...xs) >= 0 && Math.max(...xs) <= 200, "x 越界");
  assert.ok(Math.min(...ys) >= 0 && Math.max(...ys) <= 100, "y 越界");
  // 等比：原 10:4，缩放后仍应为 10:4
  const w = Math.max(...xs) - Math.min(...xs);
  const h = Math.max(...ys) - Math.min(...ys);
  assert.ok(Math.abs(w / h - 10 / 4) < 1e-6, `长宽比被破坏：${w / h}`);
  assert.ok(scale > 0);
});

test("fitToBox: 宽扁形状填满宽度方向", () => {
  const pts: Pt[] = [[0, 0], [100, 0], [100, 5], [0, 5]];
  const { points } = fitToBox(pts, 300, 200, 5);
  const xs = points.map((p) => p[0]);
  const w = Math.max(...xs) - Math.min(...xs);
  assert.ok(w > 300 - 2 * 5 - 1e-6, `应撑满宽度，实际 ${w}`);
});

test("toPath: 输出 M 开头且段数 = 点数", () => {
  const pts: Pt[] = [[0, 0], [1.234, 2.345], [3, 4]];
  const d = toPath(pts);
  assert.ok(d.startsWith("M"), "必须以 M 开头");
  assert.equal(d.split("L").length, 3, "3 个点应为 M + 2 个 L");
  assert.ok(!d.includes("NaN"), "不能含 NaN");
  assert.ok(!d.includes("undefined"), "不能含 undefined");
});
