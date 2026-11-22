import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import FleetForm from './FleetForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

function Fleet() {
  const { lang } = useLang();
  const t = getTools(lang);
  return (
    <>
      <ToolHeader
        index={t.fleet.index}
        title={t.fleet.title}
        lead={t.fleet.lead}
        aside={<p className="t-hero-note">{t.fleet.aside}</p>}
      />

      <div className="t-section">
        <FleetForm />
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
            <a href="/platform/assistant">{t.nav.toAssistant}</a>
          </li>
        </ul>
      </nav>

      <AssistantLauncher />
    </>
  );
}

mountPage(<Fleet />);
