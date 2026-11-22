/**
 * 内部版配车明细（P4）：四约束分解 / 轴荷线 / 共车组合。
 *
 * 只在 `/quote/internal` 且拿到内部数据时由 `VehicleStep` 挂载；公开版 `/quote`
 * 既不请求也不渲染本组件（红线：公开口径不给 breakdown / axle_lines / pairs）。
 *
 * 渲染原则：
 * · 值一律「引擎给什么显示什么」——键名与数值不翻译、不推算、不改写业务含义，
 *   `breakdown` / `axle_lines` / `pairs` 的键在引擎侧是动态字典，前端只做键值两列。
 * · 块缺失（`axle_lines` 为 null、`pairs` 空、`breakdown` 空）整块不渲染。
 * · 样式只用 quote.css 既有 `.q-*` 与 `.micro`：发丝线表格（border-top/bottom 1px），
 *   无卡片投影 / 无圆角 / 无自定义色值。
 */
import type { InternalFitGroup } from '../../api';

/** 四约束分解的展示顺序（引擎 `车辆数分解()` 输出这六个主键，其余键排在后面） */
const BREAKDOWN_ORDER = ['车数', '重量', '体积', '长度', '面积', '主因'];

type Row = { k: string; v: string };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** 值 → 单行文本；结构化的值降级成紧凑 JSON，避免表格被撑开 */
function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? '是' : '否';
  if (typeof v === 'number') return Number.isFinite(v) ? String(Math.round(v * 100) / 100) : '—';
  if (typeof v === 'string') return v.trim() || '—';
  if (Array.isArray(v)) return v.length > 0 ? v.map((x) => fmt(x)).join('、') : '—';
  try {
    return JSON.stringify(v) ?? '—';
  } catch {
    return '—';
  }
}

/** 字典 → 行：先按 order 里的键排列（存在才出），再把其余键按原顺序补在后面 */
function rowsOf(dict: Record<string, unknown>, order: string[] = []): Row[] {
  const out: Row[] = [];
  const seen = new Set<string>();
  for (const k of order) {
    if (!Object.prototype.hasOwnProperty.call(dict, k)) continue;
    seen.add(k);
    out.push({ k, v: fmt(dict[k]) });
  }
  for (const [k, v] of Object.entries(dict)) {
    if (seen.has(k)) continue;
    out.push({ k, v: fmt(v) });
  }
  return out;
}

/** 两列发丝线表格（与 InternalResult 的 .q-table 同构） */
function PairTable({ cap, rows }: { cap: string; rows: Row[] }) {
  if (rows.length === 0) return null;
  return (
    <table className="q-table">
      <caption className="q-table-cap micro">{cap}</caption>
      <thead>
        <tr>
          <th scope="col">项</th>
          <th scope="col">值</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.k}>
            <th scope="row">{r.k}</th>
            <td>{r.v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 共车组合：每条只取 per_truck / trucks / reason，三个都没有就跳过该条 */
function pairsTable(pairs: Array<Record<string, unknown>>) {
  const blocks = pairs
    .map((p, i) => {
      if (!isRecord(p)) return null;
      const rows: Row[] = [];
      for (const k of ['per_truck', 'trucks', 'reason']) {
        if (!Object.prototype.hasOwnProperty.call(p, k)) continue;
        rows.push({ k, v: fmt(p[k]) });
      }
      return rows.length > 0 ? { i, rows } : null;
    })
    .filter((b): b is { i: number; rows: Row[] } => b !== null);

  if (blocks.length === 0) return null;

  return (
    <table className="q-table">
      <caption className="q-table-cap micro">共车组合</caption>
      {blocks.map((b) => (
        <tbody key={b.i}>
          <tr className="q-tr-group">
            <th scope="colgroup" colSpan={2}>
              组合 {b.i + 1}
            </th>
          </tr>
          {b.rows.map((r) => (
            <tr key={r.k}>
              <th scope="row">{r.k}</th>
              <td>{r.v}</td>
            </tr>
          ))}
        </tbody>
      ))}
    </table>
  );
}

export default function FitDetail({ groups }: { groups: InternalFitGroup[] }) {
  const list = Array.isArray(groups) ? groups.filter(isRecord) : [];

  // 三块全空的组直接丢掉（公开口径被误带、或引擎这次没给明细时都走这里）
  const blocks = list.filter((g) => {
    const hasBreakdown = isRecord(g.breakdown) && Object.keys(g.breakdown).length > 0;
    const hasAxle = isRecord(g.axle_lines) && Object.keys(g.axle_lines).length > 0;
    const hasPairs = Array.isArray(g.pairs) && g.pairs.length > 0;
    return hasBreakdown || hasAxle || hasPairs;
  });
  if (blocks.length === 0) return null;

  return (
    <div className="q-consol">
      <p className="micro q-result-kicker">配车明细 · 内部口径</p>
      {blocks.map((g, i) => {
        const breakdown = isRecord(g.breakdown) ? rowsOf(g.breakdown, BREAKDOWN_ORDER) : [];
        const axle = isRecord(g.axle_lines) ? rowsOf(g.axle_lines) : [];
        const pairs = Array.isArray(g.pairs) ? g.pairs : [];
        const dimFlags = Array.isArray(g.dim_flags)
          ? g.dim_flags.filter((f) => typeof f === 'string' && f.trim())
          : [];
        const permitFlags = Array.isArray(g.permit_flags)
          ? g.permit_flags.filter((f) => typeof f === 'string' && f.trim())
          : [];

        return (
          <div className="q-vgroup" key={g.model_id || g.display_name || `g${i}`}>
            <p className="q-vgroup-t micro">{g.display_name || g.model_id}</p>
            <div className="q-fit-chips">
              <span className="q-chip">{fmt(g.vehicle_count)} 辆</span>
              {typeof g.transport_units === 'number' ? (
                <span className="q-chip">运输单元 {fmt(g.transport_units)}</span>
              ) : null}
              {typeof g.max_load_ton === 'number' ? (
                <span className="q-chip">载重 {fmt(g.max_load_ton)} t</span>
              ) : null}
              {g.oversize_released ? <span className="q-chip is-warn">超限已放行</span> : null}
              {dimFlags.map((f) => (
                <span className="q-chip is-warn" key={`dim-${f}`}>
                  {f}
                </span>
              ))}
              {permitFlags.map((f) => (
                <span className="q-chip is-warn" key={`permit-${f}`}>
                  {f}
                </span>
              ))}
            </div>

            <PairTable cap="四约束分解" rows={breakdown} />
            <PairTable cap="轴荷线" rows={axle} />
            {pairsTable(pairs)}
          </div>
        );
      })}
    </div>
  );
}
