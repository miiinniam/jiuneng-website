// 来源：OSRM++ 报价站原始代码 features/quote/legacy/frontend/src/lib/
// 移植：迁入官网 features/quote/src/engine/（2026-11-20），字段名/函数名一律不改。

import { test } from "node:test";
import assert from "node:assert/strict";
import { TRUNK_ROUTE } from "./trunkRoute.ts";

const { viewBox } = TRUNK_ROUTE;

test("path 以 M 开头且段数等于点数", () => {
  assert.ok(TRUNK_ROUTE.path.startsWith("M"), "必须以 M 开头");
  assert.equal(TRUNK_ROUTE.path.split("L").length, TRUNK_ROUTE.pointCount);
});

test("path 不含 NaN / undefined", () => {
  assert.ok(!TRUNK_ROUTE.path.includes("NaN"));
  assert.ok(!TRUNK_ROUTE.path.includes("undefined"));
});

test("点数达到可辨认下限", () => {
  assert.ok(TRUNK_ROUTE.pointCount >= 40, `点数 ${TRUNK_ROUTE.pointCount} 过少，形状会退化`);
});

test("简化确实压缩了数据", () => {
  assert.ok(
    TRUNK_ROUTE.pointCount < TRUNK_ROUTE.sourcePointCount,
    "简化后应少于原始点数",
  );
});

test("端点落在画布内", () => {
  for (const [name, p] of [["start", TRUNK_ROUTE.start], ["end", TRUNK_ROUTE.end]] as const) {
    assert.ok(p.x >= 0 && p.x <= viewBox.width, `${name}.x=${p.x} 越界`);
    assert.ok(p.y >= 0 && p.y <= viewBox.height, `${name}.y=${p.y} 越界`);
  }
});

test("起点在左、终点在右（母题方向：友谊关 → 河内）", () => {
  assert.ok(
    TRUNK_ROUTE.start.x < TRUNK_ROUTE.end.x,
    `起点 x=${TRUNK_ROUTE.start.x} 应小于终点 x=${TRUNK_ROUTE.end.x}`,
  );
});

test("里程为真实正值", () => {
  assert.ok(TRUNK_ROUTE.distanceKm > 100 && TRUNK_ROUTE.distanceKm < 300, `里程异常：${TRUNK_ROUTE.distanceKm}`);
});

test("转正后横向撑满（≥ 画布 85%）", () => {
  const xs = TRUNK_ROUTE.path
    .replace(/^M/, "")
    .split("L")
    .map((s) => Number(s.split(",")[0]));
  const w = Math.max(...xs) - Math.min(...xs);
  assert.ok(w >= viewBox.width * 0.85, `横向仅占 ${((100 * w) / viewBox.width).toFixed(0)}%`);
});
