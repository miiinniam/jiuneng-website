import type { ReactNode } from 'react';
import Footer from './Footer';
import TopBar from './TopBar';
import AssistantLauncher from '../tools/AssistantLauncher';

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <a className="jn-skip" href="#main">
        跳到主要内容
      </a>
      <TopBar />
      <main id="main">{children}</main>
      <Footer />
      {/* 全站悬浮测算助手（默认收起；工具页内的实例由页面自己决定是否再加一个内嵌版） */}
      <AssistantLauncher />
    </>
  );
}
