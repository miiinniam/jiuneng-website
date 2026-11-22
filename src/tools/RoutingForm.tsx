/**
 * 线路与运价测算表单 + 结果区。
 *
 * 契约：`POST /api/quote-route`，请求同 `CalcRequest`，响应原样透传 `CalcResult`。
 * 拼车（consolidated）必须给 `volume_m3` —— 表单前置校验，不让客户白等一轮。
 * 城市清单来自 `GET /api/osrm-quote/places`（kind: cn|border|vn），本页不做 geocode。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ApiError,
  errorText,
  fetchPlaces,
  fmtDecimal,
  fmtInt,
  postQuoteRoute,
  reasonText,
  chineseOnly,
  type PlaceOption,
  type QuoteMode,
  type QuoteResult,
  type VehicleOption,
} from './api';
import { Disclaim, ErrorLine, Hint } from './parts';
import { getTools } from '../content';
import { useLang } from '../shell/LangProvider';

type Status = 'idle' | 'loading' | 'busy' | 'failed';

const DEFAULT_ORIGIN = 'nanning';
const DEFAULT_DESTINATION = 'hanoi';

function firstId(list: PlaceOption[], fallback: string): string {
  if (list.some((p) => p.id === fallback)) return fallback;
  return list[0]?.id ?? '';
}

export default function RoutingForm() {
  const { lang } = useLang();
  const t = getTools(lang);
  /** 服务端下发的中文城市名 → 用本地清单里的当前语言名（清单里没有就回落到服务端值） */
  const placeName = (o: { id: string; label: string } | null): string => {
    if (!o) return '';
    const hit = places.find((pl) => pl.id === o.id) as unknown as Record<string, string> | undefined;
    return hit?.[lang] ?? o.label;
  };
  const [places, setPlaces] = useState<PlaceOption[]>([]);
  const [vehicles, setVehicles] = useState<VehicleOption[]>([]);
  const [status, setStatus] = useState<Status>('loading');
  const [loadError, setLoadError] = useState('');

  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [weight, setWeight] = useState('20000');
  const [volume, setVolume] = useState('');
  const [mode, setMode] = useState<QuoteMode>('full_truck');
  const [vehicleId, setVehicleId] = useState('');

  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [result, setResult] = useState<QuoteResult | null>(null);

  const loadPlaces = useCallback(async () => {
    setStatus('loading');
    setLoadError('');
    try {
      const data = await fetchPlaces();
      setPlaces(Array.isArray(data.places) ? data.places : []);
      setVehicles(Array.isArray(data.vehicles) ? data.vehicles : []);
      setStatus('idle');
    } catch (err) {
      setStatus('failed');
      setLoadError(errorText(err));
    }
  }, []);

  useEffect(() => {
    void loadPlaces();
  }, [loadPlaces]);

  const origins = useMemo(() => places.filter((p) => p.kind === 'cn'), [places]);
  const destinations = useMemo(() => places.filter((p) => p.kind === 'vn'), [places]);

  // 清单到手后填默认值（南宁 → 河内），客户少点两次
  useEffect(() => {
    if (!origins.length || origin) return;
    setOrigin(firstId(origins, DEFAULT_ORIGIN));
  }, [origins, origin]);

  useEffect(() => {
    if (!destinations.length || destination) return;
    setDestination(firstId(destinations, DEFAULT_DESTINATION));
  }, [destinations, destination]);

  useEffect(() => {
    if (!vehicles.length || vehicleId) return;
    setVehicleId(vehicles[0].id);
  }, [vehicles, vehicleId]);

  const validate = (): string => {
    if (!origin) return t.routing.errOrigin;
    if (!destination) return t.routing.errDest;
    if (origin === destination) return t.routing.errSame;
    const kg = Number(weight);
    if (!Number.isFinite(kg) || kg <= 0) return t.routing.errWeight;
    if (mode === 'consolidated') {
      const m3 = Number(volume);
      if (!Number.isFinite(m3) || m3 <= 0) {
        return t.routing.errVolume;
      }
    }
    if (mode === 'full_truck' && !vehicleId) return t.routing.errVehicle;
    return '';
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const problem = validate();
    if (problem) {
      setFormError(problem);
      setResult(null);
      return;
    }
    setFormError('');
    setBusy(true);
    try {
      const m3 = Number(volume);
      const data = await postQuoteRoute({
        origin,
        destination,
        weight_kg: Number(weight),
        volume_m3: Number.isFinite(m3) && m3 > 0 ? m3 : null,
        mode,
        vehicle_model_id: mode === 'full_truck' ? vehicleId : null,
      });
      setResult(data);
    } catch (err) {
      setResult({
        ok: false,
        reason: err instanceof ApiError ? err.reason : 'network',
        note: errorText(err),
      });
    } finally {
      setBusy(false);
    }
  };

  const ok = result && result.ok ? result : null;
  const fail = result && !result.ok ? result : null;
  const failText = fail ? reasonText(fail.reason) : '';
  const suggestions = ok ? chineseOnly(ok.suggestions) : [];

  return (
    <div className="t-grid">
      <form className="t-form" onSubmit={submit} noValidate>
        <div className="t-form-head">
          <p className="micro">{t.routing.inputKicker}</p>
          <h2 className="t-h2">{t.routing.inputTitle}</h2>
        </div>

        {status === 'loading' ? <p className="t-hint">{t.routing.loading}</p> : null}
        {status === 'failed' ? (
          <div className="t-err-box">
            <p className="t-err" role="alert">{loadError || t.routing.loadFail}</p>
            <button type="button" className="t-btn-ghost" onClick={() => void loadPlaces()}>
              {t.routing.retry}
            </button>
          </div>
        ) : null}

        <div className="t-fields">
          <label className="t-field">
            <span className="t-label">{t.routing.origin}</span>
            <select
              className="t-input"
              data-testid="route-origin"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              disabled={status !== 'idle'}
            >
              {origins.length === 0 ? <option value="">—</option> : null}
              {origins.map((p) => (
                <option key={p.id} value={p.id}>
                  {p[lang]}
                </option>
              ))}
            </select>
          </label>

          <label className="t-field">
            <span className="t-label">{t.routing.dest}</span>
            <select
              className="t-input"
              data-testid="route-destination"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              disabled={status !== 'idle'}
            >
              {destinations.length === 0 ? <option value="">—</option> : null}
              {destinations.map((p) => (
                <option key={p.id} value={p.id}>
                  {p[lang]}
                </option>
              ))}
            </select>
          </label>

          <label className="t-field">
            <span className="t-label">{t.routing.weight}</span>
            <input
              className="t-input"
              data-testid="route-weight"
              type="number"
              inputMode="numeric"
              min={1}
              step={100}
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              {t.routing.volume}<span className="t-opt">{t.routing.volumeOpt}</span>
            </span>
            <input
              className="t-input"
              data-testid="route-volume"
              type="number"
              inputMode="decimal"
              min={0}
              step={0.1}
              placeholder={mode === 'consolidated' ? t.routing.volumePh : t.routing.volumePhEmpty}
              value={volume}
              onChange={(e) => setVolume(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">{t.routing.mode}</span>
            <select
              className="t-input"
              data-testid="route-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as QuoteMode)}
            >
              <option value="consolidated">{t.routing.modeConsolidated}</option>
              <option value="full_truck">{t.routing.modeFull}</option>
            </select>
          </label>

          {mode === 'full_truck' ? (
            <label className="t-field">
              <span className="t-label">{t.routing.vehicle}</span>
              <select
                className="t-input"
                data-testid="route-vehicle"
                value={vehicleId}
                onChange={(e) => setVehicleId(e.target.value)}
              >
                {vehicles.length === 0 ? <option value="">—</option> : null}
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v[lang]}{t.routing.vehicleCap.replace('{n}', String(v.max_load_ton))}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        <Hint>
          {t.routing.citiesNotePre}<a href="/contact">{t.nav.contactLink}</a>{t.routing.citiesNotePost}
        </Hint>

        <ErrorLine text={formError} testId="route-error" />

        <div className="t-actions">
          <button type="submit" className="t-btn" data-testid="route-submit" disabled={busy || status !== 'idle'}>
            {busy ? t.routing.submitBusy : t.routing.submit}
          </button>
          {busy ? <span className="t-busy">{t.routing.busyNote}</span> : null}
        </div>
      </form>

      <section className="t-out" data-testid="route-result" aria-live="polite">
        <div className="t-out-head">
          <p className="micro">{t.routing.resultKicker}</p>
          <h2 className="t-h2">{t.routing.resultTitle}</h2>
        </div>

        {busy ? <p className="t-hint">{t.routing.fetching}</p> : null}

        {!busy && !ok && !fail ? (
          <p className="t-hint">{t.routing.empty}</p>
        ) : null}

        {!busy && fail ? <p className="t-err" role="alert">{failText}</p> : null}

        {!busy && ok ? (
          <>
            <dl className="t-stats">
              <div className="t-stat">
                <dt>{t.routing.rowRoute}</dt>
                <dd className="t-num-line">
                  {placeName(ok.origin)} → {placeName(ok.destination)}
                </dd>
              </div>
              {ok.border ? (
                <div className="t-stat">
                  <dt>{t.routing.rowGate}</dt>
                  <dd>{placeName(ok.border)}</dd>
                </div>
              ) : null}
              <div className="t-stat">
                <dt>{t.routing.rowDistance}</dt>
                <dd>
                  <span className="t-num">{fmtInt(ok.distance_km)}</span> km
                </dd>
              </div>
              <div className="t-stat">
                <dt>{t.routing.rowDriving}</dt>
                <dd>
                  <span className="t-num">{fmtDecimal(ok.driving_h)}</span> {t.routing.unitHours}
                </dd>
              </div>
              <div className="t-stat">
                <dt>{t.routing.rowVehicles}</dt>
                <dd>
                  <span className="t-num">{fmtInt(ok.vehicle_count)}</span> {t.routing.unitVehicles}
                </dd>
              </div>
              <div className="t-stat">
                <dt>{t.routing.rowVehicle}</dt>
                <dd>{(vehicles.find((v) => v.id === ok.vehicle_id) as unknown as Record<string, string> | undefined)?.[lang] ?? ok.vehicle_label ?? (ok.mode === 'consolidated' ? t.routing.byVolume : '—')}</dd>
              </div>
            </dl>

            <div className="t-price">
              <p className="t-price-label">{t.routing.priceLabel}</p>
              <p className="t-price-value">
                {ok.price_min_vnd !== null && ok.price_max_vnd !== null ? (
                  <>
                    <span className="t-num">{fmtInt(ok.price_min_vnd)}</span>
                    <span className="t-dash">–</span>
                    <span className="t-num">{fmtInt(ok.price_max_vnd)}</span>
                    <span className="t-unit"> VND</span>
                  </>
                ) : (
                  <span>{t.routing.noRange}</span>
                )}
              </p>
              <p className="t-price-note">
                {t.routing.rangeNote}
              </p>
            </div>

            {ok.profile_honored === false ? (
              <p className="t-warn">{t.routing.untimed}</p>
            ) : null}

            {suggestions.length > 0 ? (
              <div className="t-notes">
                <p className="t-label">{t.routing.extra}</p>
                <ul className="t-list">
                  {suggestions.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="t-out-foot">
              {t.routing.ctaPre}<a href="/contact">{t.nav.contactLink}</a>{t.routing.ctaPost}
            </p>
          </>
        ) : null}

        <Disclaim />
      </section>
    </div>
  );
}
