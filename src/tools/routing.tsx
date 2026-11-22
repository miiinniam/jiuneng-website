import { useEffect } from 'react';
import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import RoutingForm from './RoutingForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

/**
 * 预热测算引擎。
 *
 * 引擎跑在 Render 免费层，15 分钟无请求就休眠，唤醒要 40 秒左右——用户点「测算」
 * 时才去叫它，那 40 秒就白等了。这里在页面挂载时先打一发 `/api/health?deep=1`
 * （免鉴权，`deep=1` 会真实探测引擎），把冷启动藏在用户填表的时间窗口里。
 *
 * 单飞：同一页面只发一次；失败静默——预热是体验优化，不能因为引擎没醒就让页面报错。
 */
function useEngineWarmup() {
  useEffect(() => {
    fetch('/api/health?deep=1', { cache: 'no-store' }).catch(() => { /* 预热失败不影响页面 */ });
  }, []);
}

function Routing() {
  const { lang } = useLang();
  const t = getTools(lang);
  useEngineWarmup();
  return (
    <>
      <ToolHeader
        index={t.routing.index}
        title={t.routing.title}
        lead={t.routing.lead}
        aside={
          <p className="t-hero-note">
            {t.routing.asidePre}<a href="/contact">{t.nav.contactLink}</a>{t.routing.asidePost}
          </p>
        }
      />

      <div className="t-section">
        <RoutingForm />
      </div>

      <nav className="t-cross" aria-label={t.nav.crossAria}>
        <p className="micro">{t.nav.continue}</p>
        <ul>
          <li>
            <a href="/platform/customs">{t.nav.toCustoms}</a>
          </li>
          <li>
            <a href="/platform/fleet">{t.nav.toFleet}</a>
          </li>
          <li>
            <a href="/platform/assistant">{t.nav.toAssistant}</a>
          </li>
        </ul>
      </nav>

      <AssistantLauncher />
    </>
  );
}

mountPage(<Routing />);
