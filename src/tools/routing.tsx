import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import RoutingForm from './RoutingForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

function Routing() {
  const { lang } = useLang();
  const t = getTools(lang);
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
