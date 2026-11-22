import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import CustomsForm from './CustomsForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

function Customs() {
  const { lang } = useLang();
  const t = getTools(lang);
  return (
    <>
      <ToolHeader
        index={t.customs.index}
        title={t.customs.title}
        lead={t.customs.lead}
        aside={
          <p className="t-hero-note">
            {t.customs.aside}
          </p>
        }
      />

      <div className="t-section">
        <CustomsForm />
      </div>

      <nav className="t-cross" aria-label={t.nav.crossAria}>
        <p className="micro">{t.nav.continue}</p>
        <ul>
          <li>
            <a href="/platform/routing">{t.nav.toRouting}</a>
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

mountPage(<Customs />);
