/**
 * 工具舱共用的最小版式件。
 * 三句口径是**硬要求**：三个结果区都必须出现，逐字一致，不许改写。
 */
import type { ReactNode } from 'react';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

export const DISCLAIMER = ['初步测算', '非正式报价', '非时效承诺'] as const;

export function Disclaim({ testId }: { testId?: string }) {
  const { lang } = useLang();
  return (
    <ul className="t-disclaim" data-testid={testId}>
      {getTools(lang).disclaimer.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

export function ToolHeader({
  index,
  title,
  lead,
  aside,
}: {
  index: string;
  title: string;
  lead: string;
  aside?: ReactNode;
}) {
  return (
    <header className="t-hero">
      <p className="micro">{index}</p>
      <h1 className="t-h1">{title}</h1>
      <p className="t-hero-lead">{lead}</p>
      <div className="t-hero-foot">
        <Disclaim testId="tool-disclaim" />
        {aside ? <div className="t-hero-aside">{aside}</div> : null}
      </div>
    </header>
  );
}

export function ErrorLine({ text, testId }: { text: string; testId?: string }) {
  if (!text) return null;
  return (
    <p className="t-err" role="alert" data-testid={testId}>
      {text}
    </p>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="t-hint">{children}</p>;
}
