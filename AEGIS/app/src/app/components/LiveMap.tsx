import { MapPin, Navigation, Loader } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Circle, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const locationIcon = L.divIcon({
  className: '',
  html: `
    <div style="position:relative;width:32px;height:32px;display:flex;align-items:center;justify-content:center;">
      <div style="
        width:13px;height:13px;
        background:#06b6d4;
        border-radius:50%;
        border:2px solid #fff;
        box-shadow:0 0 10px #06b6d4,0 0 22px rgba(6,182,212,0.6);
        z-index:2;position:relative;
      "></div>
      <div style="
        position:absolute;width:28px;height:28px;
        border:1.5px solid rgba(6,182,212,0.55);
        border-radius:50%;
      "></div>
    </div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

function RecenterMap({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();
  const firstRef = useRef(true);
  useEffect(() => {
    if (firstRef.current) {
      map.setView([lat, lon], 18);
      firstRef.current = false;
    } else {
      map.panTo([lat, lon]);
    }
  }, [lat, lon, map]);
  return null;
}

type GpsStatus = 'loading' | 'found' | 'denied' | 'unavailable';

export default function LiveMap() {
  const [coords, setCoords] = useState<{ lat: number; lon: number; accuracy: number } | null>(null);
  const [status, setStatus] = useState<GpsStatus>('loading');
  const watchIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) {
      setStatus('unavailable');
      setCoords({ lat: 12.9716, lon: 77.5946, accuracy: 0 });
      return;
    }

    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setCoords({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        });
        setStatus('found');
      },
      () => {
        setStatus('denied');
        setCoords({ lat: 12.9716, lon: 77.5946, accuracy: 0 });
      },
      { enableHighAccuracy: true, timeout: 30000, maximumAge: 0 }
    );

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, []);

  const center: [number, number] = coords ? [coords.lat, coords.lon] : [12.9716, 77.5946];

  const statusBadge: Record<GpsStatus, { label: string; cls: string }> = {
    found:       { label: 'GPS LIVE',     cls: 'bg-green-500/10 border-green-500/30 text-green-400' },
    loading:     { label: 'LOCATING...', cls: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400' },
    denied:      { label: 'GPS FALLBACK', cls: 'bg-orange-500/10 border-orange-500/30 text-orange-400' },
    unavailable: { label: 'GPS FALLBACK', cls: 'bg-orange-500/10 border-orange-500/30 text-orange-400' },
  };
  const badge = statusBadge[status];

  return (
    <div
      className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MapPin className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Map</h2>
        </div>
        <div className={`flex items-center gap-1.5 px-3 py-1 rounded border text-xs font-medium ${badge.cls}`}>
          <Navigation className="w-3 h-3" />
          {badge.label}
        </div>
      </div>

      {/* Map */}
      <div className="relative h-72 rounded-xl overflow-hidden mb-4 border border-cyan-500/20">
        {status === 'loading' && (
          <div className="absolute inset-0 z-[9999] flex items-center justify-center bg-[#060f1e]/90">
            <div className="flex flex-col items-center gap-2">
              <Loader className="w-6 h-6 text-cyan-400 animate-spin" />
              <span className="text-xs text-cyan-400 tracking-wide">Acquiring GPS fix...</span>
            </div>
          </div>
        )}
        <MapContainer
          center={center}
          zoom={18}
          style={{ height: '100%', width: '100%' }}
          zoomControl={false}
          attributionControl={false}
          scrollWheelZoom={true}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            subdomains="abcd"
            maxZoom={19}
          />
          {coords && (
            <>
              <Marker position={[coords.lat, coords.lon]} icon={locationIcon} />
              {/* Accuracy radius circle — shrinks as GPS fix improves */}
              {coords.accuracy > 0 && (
                <Circle
                  center={[coords.lat, coords.lon]}
                  radius={coords.accuracy}
                  pathOptions={{
                    color: '#06b6d4',
                    fillColor: '#06b6d4',
                    fillOpacity: 0.08,
                    weight: 1,
                    opacity: 0.5,
                  }}
                />
              )}
              <RecenterMap lat={coords.lat} lon={coords.lon} />
            </>
          )}
        </MapContainer>
      </div>

      {/* Coordinates + accuracy */}
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 rounded-lg bg-white/5 border border-white/10">
          <div className="text-xs text-gray-400 mb-1">Latitude</div>
          <div className="text-sm font-mono text-cyan-400">
            {coords ? `${coords.lat.toFixed(6)}°` : '—'}
          </div>
        </div>
        <div className="p-3 rounded-lg bg-white/5 border border-white/10">
          <div className="text-xs text-gray-400 mb-1">Longitude</div>
          <div className="text-sm font-mono text-cyan-400">
            {coords ? `${coords.lon.toFixed(6)}°` : '—'}
          </div>
        </div>
        <div className="p-3 rounded-lg bg-white/5 border border-white/10">
          <div className="text-xs text-gray-400 mb-1">Accuracy</div>
          <div className={`text-sm font-mono font-bold ${
            coords && coords.accuracy < 20
              ? 'text-green-400'
              : coords && coords.accuracy < 100
              ? 'text-yellow-400'
              : 'text-orange-400'
          }`}>
            {coords && coords.accuracy > 0 ? `±${Math.round(coords.accuracy)} m` : '—'}
          </div>
        </div>
      </div>
    </div>
  );
}
