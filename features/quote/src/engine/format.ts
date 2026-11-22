// 来源：OSRM++ 报价站原始代码 features/quote/legacy/frontend/src/lib/
// 移植：迁入官网 features/quote/src/engine/（2026-11-20），字段名/函数名一律不改。

const vndFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

export function formatVnd(value: number): string {
  return `${vndFormatter.format(value)} VND`;
}

export function formatHours(value: number, unit: string): string {
  return `${value.toFixed(1)} ${unit}`;
}
