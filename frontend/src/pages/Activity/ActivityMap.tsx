import { useMemo, useEffect } from 'react';
import { MapContainer, TileLayer, Polyline, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression, LatLngTuple } from 'leaflet';
import 'leaflet/dist/leaflet.css';

function decodePolyline(encoded: string): LatLngTuple[] {
  const points: LatLngTuple[] = [];
  let index = 0;
  let lat = 0;
  let lng = 0;
  while (index < encoded.length) {
    let shift = 0;
    let result = 0;
    let byte: number;
    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    lat += result & 1 ? ~(result >> 1) : result >> 1;
    shift = 0;
    result = 0;
    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    lng += result & 1 ? ~(result >> 1) : result >> 1;
    points.push([lat / 1e5, lng / 1e5]);
  }
  return points;
}

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [30, 30] });
  }, [map, bounds]);
  return null;
}

interface ActivityMapProps {
  polyline: string;
}

// OSM tiles in both themes. The previous dark provider (CARTO dark_all) needs an API key and
// answered HTTP 400 from the production domain, leaving the route on a watermark. Dark mode is
// obtained with a CSS filter on .leaflet-tile-pane (styles/tokens.css), which leaves the route
// (overlay pane) untouched.
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
// Transparent 1x1 GIF: a failed tile shows the themed map background instead of a broken image.
const ERROR_TILE_URL = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export function ActivityMap({ polyline }: ActivityMapProps) {
  const positions = useMemo(() => {
    try {
      return decodePolyline(polyline);
    } catch {
      return [];
    }
  }, [polyline]);

  if (positions.length === 0) return null;

  const bounds = positions as LatLngBoundsExpression;

  return (
    <div className="activity-map h-[300px] w-full overflow-hidden rounded-xl">
      <MapContainer
        key={polyline}
        bounds={bounds}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer url={TILE_URL} attribution={ATTRIBUTION} errorTileUrl={ERROR_TILE_URL} />
        {/* stroke comes from .activity-route (var(--primary)); SVG attributes cannot resolve var(). */}
        <Polyline
          positions={positions}
          pathOptions={{ color: '#fc4c02', weight: 3, className: 'activity-route' }}
        />
        <FitBounds bounds={bounds} />
      </MapContainer>
    </div>
  );
}
