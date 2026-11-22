import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import AssistantLauncher, { AssistantChat } from './AssistantLauncher';
import { Disclaim, ToolHeader } from './parts';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

function AssistantPage() {
  const { lang } = useLang();
  const a = getTools(lang).assistant;
  const t = getTools(lang);
  return (
    <>
      <ToolHeader
        index={a.index}
        title={a.title}
        lead={a.lead}
        aside={<p className="t-hero-note">{a.aside}</p>}
      />

      <div className="t-section">
        <div className="t-assistant">
          <section className="t-assistant-main">
            <div className="t-out-head">
              <p className="micro">{a.chatKicker}</p>
              <h2 className="t-h2">{a.chatTitle}</h2>
            </div>
            <AssistantChat variant="page" />
          </section>

          <aside className="t-assistant-side">
            <p className="t-label">{a.canLabel}</p>
            <ul className="t-list">
              <li>{a.can[0]}</li>
              <li>{a.can[1]}</li>
              <li>{a.can[2]}</li>
            </ul>

            <p className="t-label">{a.cannotLabel}</p>
            <ul className="t-list">
              <li>{a.cannot[0]}</li>
              <li>{a.cannot[1]}</li>
              <li>{a.cannot[2]}</li>
            </ul>

            <Disclaim />

            <p className="t-hint">
              {a.hintPre}<a href="/contact">{t.nav.contactLink}</a>{a.hintPost}
            </p>
          </aside>
        </div>
      </div>

      <nav className="t-cross" aria-label={t.nav.crossAria}>
        <p className="micro">{t.nav.continue}</p>
        <ul>
          <li>
            <a href="/platform/routing">{t.nav.toRouting}</a>
          </li>
          <li>
            <a href="/platform/customs">{t.nav.toCustoms}</a>
          </li>
          <li>
            <a href="/platform/fleet">{t.nav.toFleet}</a>
          </li>
        </ul>
      </nav>

      <AssistantLauncher />
    </>
  );
}

mountPage(<AssistantPage />);
