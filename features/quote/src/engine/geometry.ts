// 来源：OSRM++ 报价站原始代码 features/quote/legacy/frontend/src/lib/
// 移植：迁入官网 features/quote/src/engine/（2026-11-20），字段名/函数名一律不改。

/** 二维点 [x, y] */
export type Pt = [number, number];

/** 点 p 到线段 ab 的垂直距离；ab 退化时返回点距 */
export function perpendicularDistance(p: Pt, a: Pt, b: Pt): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const norm = Math.hypot(dx, dy);
  if (norm === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  return Math.abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / norm;
}

/** Douglas-Peucker 简化。迭代实现，避免深递归爆栈。 */
export function simplify(points: Pt[], tolerance: number): Pt[] {
  if (points.length <= 2) return points.slice();

  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = true;
  keep[points.length - 1] = true;

  const stack: Array<[number, number]> = [[0, points.length - 1]];
  while (stack.length > 0) {
    const [first, last] = stack.pop() as [number, number];
    let maxDist = 0;
    let index = -1;
    for (let i = first + 1; i < last; i++) {
      const d = perpendicularDistance(points[i], points[first], points[last]);
      if (d > maxDist) {
        maxDist = d;
        index = i;
      }
    }
    if (maxDist > tolerance && index !== -1) {
      keep[index] = true;
      stack.push([first, index], [index, last]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

/** 主成分方向（弧度）。数据退化时返回 0。 */
export function principalAngle(points: Pt[]): number {
  const n = points.length;
  if (n < 2) return 0;
  let mx = 0;
  let my = 0;
  for (const [x, y] of points) {
    mx += x;
    my += y;
  }
  mx /= n;
  my /= n;
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  for (const [x, y] of points) {
    const dx = x - mx;
    const dy = y - my;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  }
  return 0.5 * Math.atan2(2 * sxy, sxx - syy);
}

/** 绕原点旋转 theta 弧度 */
export function rotate(points: Pt[], theta: number): Pt[] {
  const c = Math.cos(theta);
  const s = Math.sin(theta);
  return points.map(([x, y]) => [x * c - y * s, x * s + y * c] as Pt);
}

/** 等比缩放并居中到 w×h 画布（保留 pad 边距）。返回缩放后点集与实际比例尺。 */
export function fitToBox(
  points: Pt[],
  w: number,
  h: number,
  pad: number,
): { points: Pt[]; scale: number } {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;

  const scale = Math.min((w - 2 * pad) / spanX, (h - 2 * pad) / spanY);
  const offX = (w - spanX * scale) / 2 - minX * scale;
  const offY = (h - spanY * scale) / 2 - minY * scale;

  return {
    points: points.map(([x, y]) => [x * scale + offX, y * scale + offY] as Pt),
    scale,
  };
}

/** 点集 → SVG path 字符串（1 位小数） */
export function toPath(points: Pt[]): string {
  return "M" + points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L");
}
