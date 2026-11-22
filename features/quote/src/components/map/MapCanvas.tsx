// 地图画布 —— 唯一 import leaflet 的地方。
// 只有 MapPicker 在浏览器里挂载后才会通过 React.lazy 把这一块拉进来，
// 所以没有 DOM 的环境（SSR / 预渲染 / 无浏览器自测）根本不会执行 leaflet 的模块级代码。
//
// 瓦片源沿用 legacy 的做法：ArcGIS World Street Map（无 key、无水印）。
// 原始实现里已经试过 OSM 官方瓦片（当时实测连不上）与 CARTO（免费端点要 key + 水印）。

import { useEffect, useMemo } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapContainer, Marker, Polyline, TileLayer, ZoomControl, useMap, useMapEvents } from 'react-leaflet';
import type { LatLng } from '../../engine/types';
import { validateText } from '../../i18n/validation';
import { useLang } from '../../../../../src/shell/LangProvider';

// 只借类型：签名唯一事实来源留在 MapPicker.tsx（`import type` 编译后整行消失，
// 所以这个循环引用不会产生运行时依赖，也不会把 leaflet 拉回主包）
import type { MapPickerProps } from './MapPicker';

/** 画布内部额外需要的：父层「重设终点」模式的开关 */
type CanvasProps = MapPickerProps & {
  forceDestination: boolean;
  onForceConsumed: () => void;
};

const TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}';
const TILE_ATTR = 'Tiles &copy; Esri';
/** 默认视野落在中越口岸走廊（凭祥 22.1, 河内 21.03）—— 这个工具 95% 的单子在这条线上，
    开在 5 级东南亚全图等于让客户自己找三分钟。 */
const DEFAULT_CENTER: [number, number] = [21.6, 106.6];
const DEFAULT_ZOOM = 7;

type PinKind = 'origin' | 'dest' | 'waypoint';

function makePin(kind: PinKind, tag: string): L.DivIcon {
  return L.divIcon({
    // className 覆盖 leaflet-div-icon 的白底方块，方形点由 panels.css 里的 .q-map-pin 画
    className: 'q-map-pin-wrap',
    html: `<span class="q-map-pin q-map-pin--${kind}"><span class="q-map-pin-dot"></span><span class="q-map-pin-tag">${tag}</span></span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function ClickPicker({
  origin,
  destination,
  forceDestination,
  onPick,
  onForceConsumed,
}: CanvasProps) {
  useMapEvents({
    click(e) {
      const point: LatLng = { lat: e.latlng.lat, lng: e.latlng.lng };
      if (forceDestination) {
        onPick({ destination: point });
        onForceConsumed();
        return;
      }
      // 起终点都在时点击不改任何东西 —— 地图上看路线时太容易误触
      if (!origin) {
        onPick({ origin: point });
        return;
      }
      if (!destination) onPick({ destination: point });
    },
  });
  return null;
}

/** 路线/起终点变化后把视野收进画布。不做飞行动画（reduce 动效下也不该动）。 */
function FitToRoute({ origin, destination, waypoints, geometry }: Pick<MapPickerProps, 'origin' | 'destination' | 'waypoints' | 'geometry'>) {
  const map = useMap();
  const signature = useMemo(() => {
    const first = geometry?.coordinates?.[0];
    const last = geometry?.coordinates?.[geometry.coordinates.length - 1];
    return [
      geometry?.coordinates?.length ?? 0,
      first?.[0] ?? '',
      first?.[1] ?? '',
      last?.[0] ?? '',
      last?.[1] ?? '',
      origin ? `${origin.lat},${origin.lng}` : '',
      destination ? `${destination.lat},${destination.lng}` : '',
      waypoints.map((w) => `${w.lat},${w.lng}`).join('|'),
    ].join('#');
  }, [geometry, origin, destination, waypoints]);

  useEffect(() => {
    const points: [number, number][] = [];
    if (geometry && geometry.coordinates.length > 1) {
      for (const [lng, lat] of geometry.coordinates) points.push([lat, lng]);
    } else {
      if (origin) points.push([origin.lat, origin.lng]);
      for (const w of waypoints) points.push([w.lat, w.lng]);
      if (destination) points.push([destination.lat, destination.lng]);
    }
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 11, { animate: false });
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 12, animate: false });
  }, [signature, geometry, origin, destination, waypoints, map]);

  return null;
}

export default function MapCanvas({
  origin,
  destination,
  waypoints,
  geometry,
  onPick,
  forceDestination,
  onForceConsumed,
}: CanvasProps) {
  const { lang } = useLang();
  const vt = validateText(lang);
  const icons = useMemo(
    () => ({
      origin: makePin('origin', vt.pinOrigin),
      destination: makePin('dest', vt.pinDest),
      waypoints: waypoints.map((_, i) => makePin('waypoint', String(i + 1))),
    }),
    [waypoints, vt],
  );

  const line = useMemo<[number, number][]>(() => {
    if (!geometry || geometry.coordinates.length < 2) return [];
    // GeoJSON 是 [lng, lat]，leaflet 要 [lat, lng]
    return geometry.coordinates.map(([lng, lat]) => [lat, lng] as [number, number]);
  }, [geometry]);

  return (
    <MapContainer
      className="q-map-leaflet"
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      minZoom={3}
      maxZoom={18}
      scrollWheelZoom
      zoomControl={false}
      attributionControl
    >
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={18} />
      <ZoomControl position="bottomright" />

      <ClickPicker
        origin={origin}
        destination={destination}
        waypoints={waypoints}
        onPick={onPick}
        forceDestination={forceDestination}
        onForceConsumed={onForceConsumed}
      />
      <FitToRoute origin={origin} destination={destination} waypoints={waypoints} geometry={geometry} />

      {line.length > 1 && (
        <>
          <Polyline positions={line} className="q-map-route-casing" pathOptions={{ weight: 7, opacity: 1 }} />
          <Polyline positions={line} className="q-map-route" pathOptions={{ weight: 3, opacity: 1 }} />
        </>
      )}

      {origin && <Marker position={[origin.lat, origin.lng]} icon={icons.origin} title={vt.originPin} />}
      {destination && <Marker position={[destination.lat, destination.lng]} icon={icons.destination} title={vt.destPin} />}
      {waypoints.map((w, i) => (
        <Marker key={`${w.lat},${w.lng},${i}`} position={[w.lat, w.lng]} icon={icons.waypoints[i]} title={vt.pinWaypoint(i + 1)} />
      ))}
    </MapContainer>
  );
}
