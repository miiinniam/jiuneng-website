/**
 * 段头：编号（micro） / h2 / lead / 64px 强调线。
 * 版式依据 docs/redesign/02-视觉规范-瑞士编辑风.md §5 SectionHeader。
 */
export default function SectionHeader({
  no,
  title,
  lead,
  as: Tag = 'h2',
}: {
  no: string;
  title: string;
  lead?: string;
  as?: 'h1' | 'h2';
}) {
  return (
    <header className="sec-head">
      <p className="micro sec-head-n">{no}</p>
      <div>
        <Tag className="sec-head-t">{title}</Tag>
        {lead ? <p className="lead sec-head-lead">{lead}</p> : null}
        <span className="sec-head-rule" aria-hidden="true" />
      </div>
    </header>
  );
}
