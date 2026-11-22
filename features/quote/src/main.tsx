import { mountPage } from '../../../src/shell/mount';
import { detectLang } from '../../../src/shell/i18n';
import type { QuoteScope } from './api';
import QuoteApp from './pages/QuoteApp';
import './quote.css';
import './panels.css';

/**
 * 报价功能入口。
 *
 * 一条 HTML 入口服务两个口径：`/quote`（客户）与 `/quote/internal`（内部，口令）。
 * 判断只看 pathname —— 不做 query 参数，避免客户改个参数就看到成本。
 */
function resolveScope(): QuoteScope {
  return /\/internal\/?$/.test(window.location.pathname) ? 'internal' : 'public';
}

const scope = resolveScope();

// 内部版不进搜索引擎：同一个 HTML 服务两个口径，meta 只能在运行时改。
if (scope === 'internal') {
  const meta = document.createElement('meta');
  meta.name = 'robots';
  meta.content = 'noindex,nofollow';
  document.head.appendChild(meta);
  const title: Record<string, string> = {
    zh: '内部报价 | JIUNENG logistics',
    vi: 'Báo giá nội bộ | JIUNENG logistics',
    en: 'Internal quote | JIUNENG logistics',
  };
  document.title = title[detectLang()];
}

mountPage(<QuoteApp scope={scope} />);
