import type { ReactNode } from 'react';

export type HairlineRow = { k: string; v: ReactNode };
export type HairlineGroup = { label?: string; rows: HairlineRow[] };

/**
 * 发丝线两列表格：表头 micro + 上 1px 粗线，每行下 1px 细线，label 列 168px。
 * 用真实 table 语义（th scope），不套卡片。
 */
export default function HairlineTable({
  groups,
  head,
  testId,
  className = '',
}: {
  groups: HairlineGroup[];
  head?: [string, string];
  testId?: string;
  className?: string;
}) {
  return (
    <table className={`htable ${className}`.trim()} data-testid={testId}>
      <colgroup>
        <col className="ht-k" />
        <col />
      </colgroup>
      {head ? (
        <thead>
          <tr>
            <th scope="col">{head[0]}</th>
            <th scope="col">{head[1]}</th>
          </tr>
        </thead>
      ) : null}
      {groups.map((g, gi) => (
        <tbody key={g.label ?? `g${gi}`}>
          {g.label ? (
            <tr className="ht-group">
              <th scope="colgroup" colSpan={2}>
                {g.label}
              </th>
            </tr>
          ) : null}
          {g.rows.map((r) => (
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
