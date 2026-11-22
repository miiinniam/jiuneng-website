import type { ReactNode } from 'react';
import Footer from './Footer';
import TopBar from './TopBar';
import AssistantLauncher from '../tools/AssistantLauncher';
import { useLang } from './LangProvider';
import { getCommon } from '../content';

export default function Layout({ children }: { children: ReactNode }) {
  const { lang } = useLang();
  const common = getCommon(lang);
  // /quote 有自己的一整套 AI 助手（页头按钮 + 右侧滑入面板），
  // 再挂一个全站悬浮球会变成两个 AI 入口，客户分不清点哪个。
  const path = typeof window !== 'undefined' ? window.location.pathname : '';
  const ownAssistant = path.startsWith('/quote');
  return (
    <>
      <a className="jn-skip" href="#main">
        {common.ui.skip}
      </a>
      <TopBar />
      <main id="main">{children}</main>
      <Footer />
      {/* 全站悬浮测算助手（默认收起；工具页内的实例由页面自己决定是否再加一个内嵌版） */}
      {ownAssistant ? null : <AssistantLauncher />}
    </>
  );
}
