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

type Status = 'idle' | 'loading' | 'busy' | 'failed';

const DEFAULT_ORIGIN = 'nanning';
const DEFAULT_DESTINATION = 'hanoi';

function firstId(list: PlaceOption[], fallback: string): string {
  if (list.some((p) => p.id === fallback)) return fallback;
  return list[0]?.id ?? '';
}

export default function RoutingForm() {
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
    if (!origin) return '请选择起点。';
    if (!destination) return '请选择终点。';
    if (origin === destination) return '起点与终点不能相同。';
    const kg = Number(weight);
    if (!Number.isFinite(kg) || kg <= 0) return '请填写大于 0 的货重（单位 kg）。';
    if (mode === 'consolidated') {
      const m3 = Number(volume);
      if (!Number.isFinite(m3) || m3 <= 0) {
        return '拼车测算需要填写货物总体积（m³）；若无法给出体积，请改选整车或走正式询价。';
      }
    }
    if (mode === 'full_truck' && !vehicleId) return '整车测算请选择一种车型。';
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
          <p className="micro">输入</p>
          <h2 className="t-h2">货物与线路</h2>
        </div>

        {status === 'loading' ? <p className="t-hint">正在载入可测算城市清单…</p> : null}
        {status === 'failed' ? (
          <div className="t-err-box">
            <p className="t-err" role="alert">{loadError || '城市清单加载失败，请重试。'}</p>
            <button type="button" className="t-btn-ghost" onClick={() => void loadPlaces()}>
              重试
            </button>
          </div>
        ) : null}

        <div className="t-fields">
          <label className="t-field">
            <span className="t-label">起点（中国）</span>
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
                  {p.zh}
                </option>
              ))}
            </select>
          </label>

          <label className="t-field">
            <span className="t-label">终点（越南）</span>
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
                  {p.zh}
                </option>
              ))}
            </select>
          </label>

          <label className="t-field">
            <span className="t-label">货重（kg）</span>
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
              体积（m³）<span className="t-opt">拼车必填</span>
            </span>
            <input
              className="t-input"
              data-testid="route-volume"
              type="number"
              inputMode="decimal"
              min={0}
              step={0.1}
              placeholder={mode === 'consolidated' ? '例如 32' : '可留空'}
              value={volume}
              onChange={(e) => setVolume(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">运输方式</span>
            <select
              className="t-input"
              data-testid="route-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as QuoteMode)}
            >
              <option value="consolidated">拼车（零担）</option>
              <option value="full_truck">整车（专车）</option>
            </select>
          </label>

          {mode === 'full_truck' ? (
            <label className="t-field">
              <span className="t-label">车型</span>
              <select
                className="t-input"
                data-testid="route-vehicle"
                value={vehicleId}
                onChange={(e) => setVehicleId(e.target.value)}
              >
                {vehicles.length === 0 ? <option value="">—</option> : null}
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.zh}（限载 {v.max_load_ton} 吨）
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        <Hint>
          起点与终点只能从清单中选择；清单外地址请走<a href="/contact">在线询价</a>，由项目经理核算。
        </Hint>

        <ErrorLine text={formError} testId="route-error" />

        <div className="t-actions">
          <button type="submit" className="t-btn" data-testid="route-submit" disabled={busy || status !== 'idle'}>
            {busy ? '测算中…' : '测算'}
          </button>
          {busy ? <span className="t-busy">首次唤醒测算引擎可能需要 30–60 秒</span> : null}
        </div>
      </form>

      <section className="t-out" data-testid="route-result" aria-live="polite">
        <div className="t-out-head">
          <p className="micro">结果</p>
          <h2 className="t-h2">里程 · 车数 · 参考区间</h2>
        </div>

        {busy ? <p className="t-hint">正在向测算引擎取数…</p> : null}

        {!busy && !ok && !fail ? (
          <p className="t-hint">填写左侧参数后点「测算」，结果会显示在这里。</p>
        ) : null}

        {!busy && fail ? <p className="t-err" role="alert">{failText}</p> : null}

        {!busy && ok ? (
          <>
            <dl className="t-stats">
              <div className="t-stat">
                <dt>线路</dt>
                <dd className="t-num-line">
                  {ok.origin.label} → {ok.destination.label}
                </dd>
              </div>
              {ok.border ? (
                <div className="t-stat">
                  <dt>口岸</dt>
                  <dd>{ok.border.label}</dd>
                </div>
              ) : null}
              <div className="t-stat">
                <dt>里程</dt>
                <dd>
                  <span className="t-num">{fmtInt(ok.distance_km)}</span> km
                </dd>
              </div>
              <div className="t-stat">
                <dt>预计行驶</dt>
                <dd>
                  <span className="t-num">{fmtDecimal(ok.driving_h)}</span> 小时
                </dd>
              </div>
              <div className="t-stat">
                <dt>所需车数</dt>
                <dd>
                  <span className="t-num">{fmtInt(ok.vehicle_count)}</span> 台
                </dd>
              </div>
              <div className="t-stat">
                <dt>车型</dt>
                <dd>{ok.vehicle_label ?? (ok.mode === 'consolidated' ? '拼车（按体积配载）' : '—')}</dd>
              </div>
            </dl>

            <div className="t-price">
              <p className="t-price-label">参考运费区间（VND）</p>
              <p className="t-price-value">
                {ok.price_min_vnd !== null && ok.price_max_vnd !== null ? (
                  <>
                    <span className="t-num">{fmtInt(ok.price_min_vnd)}</span>
                    <span className="t-dash">–</span>
                    <span className="t-num">{fmtInt(ok.price_max_vnd)}</span>
                    <span className="t-unit"> VND</span>
                  </>
                ) : (
                  <span>暂无区间，请走正式询价</span>
                )}
              </p>
              <p className="t-price-note">
                区间为测算售价 ±10% 取整，随燃油、口岸排队与季节浮动。
              </p>
            </div>

            {ok.profile_honored === false ? (
              <p className="t-warn">本次结果未按所选时效参数计算，时长与车数按常规安排估算。</p>
            ) : null}

            {suggestions.length > 0 ? (
              <div className="t-notes">
                <p className="t-label">补充说明</p>
                <ul className="t-list">
                  {suggestions.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="t-out-foot">
              要拿正式价格与船期/车期安排，把这条条件带到<a href="/contact">在线询价</a>，项目经理按实际核算。
            </p>
          </>
        ) : null}

        <Disclaim />
      </section>
    </div>
  );
}
