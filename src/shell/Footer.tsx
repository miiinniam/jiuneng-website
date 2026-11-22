import { getCommon } from '../content';
import { useLang } from './LangProvider';

export default function Footer() {
  const { lang } = useLang();
  const common = getCommon(lang);
  const f = common.footer;
  return (
    <footer className="jn-foot">
      <div className="jn-foot-grid">
        <div>
          <div className="jn-mark">
            {common.brand}
            <small>{common.brandSub}</small>
          </div>
          <p style={{ fontSize: 14, color: 'var(--ink-3)', marginTop: 12, maxWidth: 320 }}>{f.intro}</p>
        </div>
        <div>
          <h4>{f.colServices}</h4>
          <ul>
            {f.services.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>{f.colProjects}</h4>
          <ul>
            {f.projects.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>{f.colContact}</h4>
          <ul>
            {f.contactLines.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="jn-foot-legal" data-testid="footer-legal">
        {f.legal}
      </div>
    </footer>
  );
}
