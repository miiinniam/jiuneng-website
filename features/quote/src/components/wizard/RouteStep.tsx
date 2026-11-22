/**
 * 步骤 01 · 路线：起终点地址搜索（防抖 geocode）+ 途经点增删 + 地图选点。
 * 地图组件的签名来自 CONTRACT §9（D 代理实现），这里只做 form ↔ LatLng 转换。
 */
import MapPicker from '../map/MapPicker';
import AddressField from './AddressField';
import { QField, QInput } from './fields';
import type { QuoteFormState, LatLng, RouteGeometry } from '../../engine/types';
import { shell } from '../../i18n/shell';
import { useLang } from '../../../../../src/shell/LangProvider';


type StepProps = {
  form: QuoteFormState;
  patch: (p: Partial<QuoteFormState>) => void;
  problems: Partial<Record<keyof QuoteFormState, string>>;
  geometry?: RouteGeometry | null;
};

/** 字符串坐标 → LatLng；空串/非数字一律 null（不要把 "" 当 0 点） */
function toLatLng(lat: string, lng: string): LatLng | null {
  const a = Number(lat);
  const b = Number(lng);
  if (!lat.trim() || !lng.trim()) return null;
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return { lat: a, lng: b };
}

function seq(v: number): string {
  return Number.isFinite(v) ? v.toFixed(6) : '';
}

export default function RouteStep({ form, patch, problems, geometry }: StepProps) {
  const { lang } = useLang();
  const q = shell(lang);
  const origin = toLatLng(form.originLat, form.originLng);
  const destination = toLatLng(form.destLat, form.destLng);
  const waypoints = form.waypoints.filter(
    (w) => Number.isFinite(w.lat) && Number.isFinite(w.lng) && (w.lat !== 0 || w.lng !== 0),
  );

  const addWaypoint = () => {
    // NaN = “还没填”，toRequest() 会把它过滤掉，不会当成 (0,0) 提交
    patch({ waypoints: [...form.waypoints, { lat: Number.NaN, lng: Number.NaN }] });
  };

  const removeWaypoint = (i: number) => {
    patch({ waypoints: form.waypoints.filter((_, j) => j !== i) });
  };

  const patchWaypoint = (i: number, w: Partial<LatLng>) => {
    patch({
      waypoints: form.waypoints.map((prev, j) => (j === i ? { ...prev, ...w } : prev)),
    });
  };

  return (
    <div className="q-step-body">
      {/* 起点 / 终点 */}
      <div className="q-route-pair">
        <div className="q-route-point">
          <p className="q-field-label micro">
            <span>{q.route.origin}</span>
            <span className="q-field-hint">{q.route.required}</span>
          </p>
          <AddressField
            ariaLabel={q.route.searchOrigin}
            placeholder={q.route.originPh}
            onSelect={(r) => patch({ originLat: seq(r.lat), originLng: seq(r.lng), originLabel: r.label })}
          />
          <div className="q-grid q-grid-2">
            <QField label={q.route.lat}>
              <QInput
                value={form.originLat}
                onChange={(v) => patch({ originLat: v })}
                placeholder={q.route.lat}
                ariaLabel={q.route.lat}
              />
            </QField>
            <QField label={q.route.lon}>
              <QInput
                value={form.originLng}
                onChange={(v) => patch({ originLng: v })}
                placeholder={q.route.lon}
                ariaLabel={q.route.lon}
              />
            </QField>
          </div>
        </div>

        <div className="q-route-point">
          <p className="q-field-label micro">
            <span>{q.route.dest}</span>
            <span className="q-field-hint">{q.route.required}</span>
          </p>
          <AddressField
            ariaLabel={q.route.searchDest}
            placeholder={q.route.destPh}
            onSelect={(r) => patch({ destLat: seq(r.lat), destLng: seq(r.lng), destLabel: r.label })}
          />
          <div className="q-grid q-grid-2">
            <QField label={q.route.lat}>
              <QInput
                value={form.destLat}
                onChange={(v) => patch({ destLat: v })}
                placeholder={q.route.lat}
                ariaLabel={q.route.lat}
              />
            </QField>
            <QField label={q.route.lon}>
              <QInput
                value={form.destLng}
                onChange={(v) => patch({ destLng: v })}
                placeholder={q.route.lon}
                ariaLabel={q.route.lon}
              />
            </QField>
          </div>
        </div>
      </div>

      {/* 途经点 */}
      <div className="q-waypoints">
        <div className="q-sub-head">
          <p className="micro">
            {q.route.waypoints(form.waypoints.length)}
          </p>
          <button type="button" className="q-add" onClick={addWaypoint}>
            {q.route.addWaypoint}
          </button>
        </div>

        {form.waypoints.length === 0 ? (
          <p className="q-note micro">{q.route.waypointNote}</p>
        ) : null}

        {form.waypoints.map((w, i) => (
          <div className="q-waypoint" key={i}>
            <div className="q-waypoint-head">
              <span className="micro">{q.route.waypointNo(String(i + 1).padStart(2, '0'))}</span>
              <button
                type="button"
                className="q-x"
                onClick={() => removeWaypoint(i)}
                aria-label={q.route.removeWaypoint(i + 1)}
              >
                {q.route.remove}
              </button>
            </div>
            <AddressField
              ariaLabel={q.route.searchWaypoint(i + 1)}
              placeholder={q.route.waypointPh}
              onSelect={(r) => patchWaypoint(i, { lat: r.lat, lng: r.lng, address: r.label })}
            />
            <div className="q-grid q-grid-2">
              <QField label={q.route.lat}>
                <QInput
                  value={seq(w.lat)}
                  onChange={(v) => patchWaypoint(i, { lat: v.trim() ? Number(v) : Number.NaN })}
                  ariaLabel={q.route.lat}
                />
              </QField>
              <QField label={q.route.lon}>
                <QInput
                  value={seq(w.lng)}
                  onChange={(v) => patchWaypoint(i, { lng: v.trim() ? Number(v) : Number.NaN })}
                  ariaLabel={q.route.lon}
                />
              </QField>
            </div>
          </div>
        ))}
      </div>

      {/* 地图选点 */}
      <div className="q-map-slot">
        <div className="q-sub-head">
          <p className="micro">{q.route.mapPick}</p>
        </div>
        <MapPicker
          origin={origin}
          destination={destination}
          waypoints={waypoints}
          geometry={geometry ?? null}
          onPick={(p) => {
            const next: Partial<QuoteFormState> = {};
            if (p.origin) {
              next.originLat = seq(p.origin.lat);
              next.originLng = seq(p.origin.lng);
            }
            if (p.destination) {
              next.destLat = seq(p.destination.lat);
              next.destLng = seq(p.destination.lng);
            }
            if (p.waypoints) {
              next.waypoints = p.waypoints.map((w) => ({
                lat: w.lat,
                lng: w.lng,
                ...(w.address ? { address: w.address } : {}),
              }));
            }
            if (Object.keys(next).length > 0) patch(next);
          }}
        />
      </div>
    </div>
  );
}
