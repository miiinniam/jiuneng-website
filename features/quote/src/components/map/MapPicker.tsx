/**
 * 地图选点（leaflet + react-leaflet）。
 * 签名见 features/quote/CONTRACT.md §9，C 代理按此签名调用，**不得改动签名**。
 *
 * 两道懒加载闸门：
 *   1. `mounted` —— 只有浏览器挂载后才渲染画布，服务端/无 DOM 时是占位块；
 *   2. `React.lazy` —— leaflet 本体跟着 MapCanvas 一起拆成独立 chunk，
 *      首屏不为「还没滚到的地图」付解析成本。
 * 风格：容器零圆角、1px 发丝线、高 320px（移动 240px）；缩放控件在右下。
 */

import { lazy, Suspense, useEffect, useState } from 'react';
import type { LatLng, RouteGeometry } from '../../engine/types';
import { mapText } from '../../i18n/map';
import { useLang } from '../../../../../src/shell/LangProvider';


export type MapPickerProps = {
  origin: LatLng | null;
  destination: LatLng | null;
  waypoints: LatLng[];
  geometry?: RouteGeometry | null;
  onPick: (p: { origin?: LatLng; destination?: LatLng; waypoints?: LatLng[] }) => void;
};

const MapCanvas = lazy(() => import('./MapCanvas'));

export default function MapPicker({ origin, destination, waypoints, geometry, onPick }: MapPickerProps) {
  const { lang } = useLang();
  const m = mapText(lang);
  const [mounted, setMounted] = useState(false);
  /** 重设模式：点了哪颗按钮，下一次点地图就改哪个点。null = 正常（防误触）模式。 */
  const [force, setForce] = useState<'origin' | 'dest' | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    setMounted(true);
  }, []);

  const hint =
    force === 'origin'
      ? m.map.pickOriginNew
      : force === 'dest'
        ? m.map.pickDestNew
        : !origin
          ? m.map.pickOrigin
          : !destination
            ? m.map.pickDest
            : m.map.settled;

  return (
    <div className="q-map">
      <div className="q-map-canvas">
        {mounted ? (
          <Suspense fallback={<div className="q-map-loading micro">{m.map.loading}</div>}>
            <MapCanvas
              origin={origin}
              destination={destination}
              waypoints={waypoints}
              geometry={geometry}
              onPick={onPick}
              force={force}
              onForceConsumed={() => setForce(null)}
            />
          </Suspense>
        ) : (
          <div className="q-map-loading micro">{m.map.loading}</div>
        )}
      </div>

      <div className="q-map-bar">
        <p className="q-map-hint micro">{hint}</p>
        {origin && destination && (
          <div className="q-map-actions">
            <button
              type="button"
              className="q-map-reset"
              data-active={force === 'origin' ? 'true' : 'false'}
              onClick={() => setForce((f) => (f === 'origin' ? null : 'origin'))}
            >
              {force === 'origin' ? m.map.cancelReset : m.map.resetOrigin}
            </button>
            <button
              type="button"
              className="q-map-reset"
              data-active={force === 'dest' ? 'true' : 'false'}
              onClick={() => setForce((f) => (f === 'dest' ? null : 'dest'))}
            >
              {force === 'dest' ? m.map.cancelReset : m.map.reset}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
