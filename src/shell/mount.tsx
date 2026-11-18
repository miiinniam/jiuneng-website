import { createRoot } from 'react-dom/client';
import type { ReactNode } from 'react';
import Layout from './Layout';
import { LangProvider } from './LangProvider';
import '../styles/tokens.css';
import '../styles/base.css';
import '../styles/shell.css';

/** 每个页面入口只需调用它：mountPage(<Home />) */
export function mountPage(page: ReactNode) {
  const el = document.getElementById('root');
  if (!el) throw new Error('[v7] 缺少 #root 容器');
  createRoot(el).render(
    <LangProvider>
      <Layout>{page}</Layout>
    </LangProvider>,
  );
}
