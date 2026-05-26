import { useMemo, useEffect } from 'react';
import { MapContainer, TileLayer, Polyline, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression, LatLngTuple } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useTheme } from '../../theme/ThemeProvider';

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

export function ActivityMap({ polyline }: ActivityMapProps) {
  const { theme } = useTheme();
  const positions = useMemo(() => {
    try {
      return decodePolyline(polyline);
    } catch {
      return [];
    }
  }, [polyline]);

  if (positions.length === 0) return null;

  const bounds = positions as LatLngBoundsExpression;
  const tileUrl =
    theme === 'dark'
      ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
      : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  const attribution =
    theme === 'dark'
      ? '&copy; <a href="https://carto.com/">CARTO</a>'
      : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

  return (
    <div className="h-[300px] w-full overflow-hidden rounded-xl">
      <MapContainer
        key={polyline}
        bounds={bounds}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer url={tileUrl} attribution={attribution} />
        <Polyline positions={positions} pathOptions={{ color: '#3b82f6', weight: 3 }} />
        <FitBounds bounds={bounds} />
      </MapContainer>
    </div>
  );
}
