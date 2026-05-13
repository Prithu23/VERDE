import { MapPin, Navigation, Loader, LocateFixed, Wifi, CrosshairIcon } from 'lucide-react';
import { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Circle, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useMissionLog } from '../hooks/useMissionLog';

// ── Leaflet icons ─────────────────────────────────────────────────────────
const gpsIcon = L.divIcon({
  className: '',
  html: `<div style="position:relative;width:36px;height:36px;display:flex;align-items:center;justify-content:center;">
    <div style="width:14px;height:14px;background:#22c55e;border-radius:50%;border:2.5px solid #fff;
      box-shadow:0 0 12px #22c55e,0 0 28px rgba(34,197,94,0.5);z-index:2;position:relative;"></div>
    <div style="position:absolute;width:30px;height:30px;border:1.5px solid rgba(34,197,94,0.5);border-radius:50%;"></div>
  </div>`,
  iconSize: [36, 36], iconAnchor: [18, 18],
});

const ipIcon = L.divIcon({
  className: '',
  html: `<div style="position:relative;width:32px;height:32px;display:flex;align-items:center;justify-content:center;">
    <div style="width:13px;height:13px;background:#06b6d4;border-radius:50%;border:2px solid #fff;
      box-shadow:0 0 10px #06b6d4,0 0 22px rgba(6,182,212,0.4);z-index:2;position:relative;"></div>
    <div style="position:absolute;width:28px;height:28px;border:1.5px solid rgba(6,182,212,0.4);border-radius:50%;"></div>
  </div>`,
  iconSize: [32, 32], iconAnchor: [16, 16],
});

const eventIcon = L.divIcon({
  className: '',
  html: `<div style="width:10px;height:10px;background:#f97316;border-radius:50%;border:2px solid #fff;box-shadow:0 0 6px #f97316;"></div>`,
  iconSize: [10, 10], iconAnchor: [5, 5],
});

// ── Auto-pan + zoom ───────────────────────────────────────────────────────
function FlyTo({ lat, lon, zoom }: { lat: number; lon: number; zoom: number }) {
  const map   = useMap();
  const prev  = useRef<{ lat: number; lon: number } | null>(null);
  useEffect(() => {
    if (!prev.current) {
      map.setView([lat, lon], zoom, { animate: false });
    } else if (prev.current.lat !== lat || prev.current.lon !== lon) {
      map.flyTo([lat, lon], zoom, { duration: 1.2 });
    }
    prev.current = { lat, lon };
  }, [lat, lon, zoom, map]);
  return null;
}

// ── Types ─────────────────────────────────────────────────────────────────
type Source  = 'gps' | 'ip';
type PermState = 'unknown' | 'granted' | 'prompt' | 'denied';

interface Coords {
  lat:      number;
  lon:      number;
  accuracy: number;
  source:   Source;
}

interface Address {
  road?:        string;
  suburb?:      string;
  neighbourhood?:string;
  city?:        string;
  state?:       string;
  postcode?:    string;
}

// ── Hooks ─────────────────────────────────────────────────────────────────
async function fetchIpCoords(): Promise<Coords> {
  const r    = await fetch('/api/location', { cache: 'no-store' });
  const d    = await r.json();
  return { lat: d.lat, lon: d.lon, accuracy: d.accuracy ?? 1500, source: 'ip' };
}

async function fetchAddress(lat: number, lon: number): Promise<Address> {
  const r = await fetch(`/api/address?lat=${lat}&lon=${lon}`, { cache: 'no-store' });
  const d = await r.json();
  return d.address ?? {};
}

// ── Component ─────────────────────────────────────────────────────────────
export default function LiveMap() {
  const [coords,  setCoords]  = useState<Coords | null>(null);
  const [address, setAddress] = useState<Address | null>(null);
  const [perm,    setPerm]    = useState<PermState>('unknown');
  const [loading, setLoading] = useState(true);

  const watchRef = useRef<number | null>(null);
  const { log }  = useMissionLog();
  const eventMarkers = log.filter(e => e.lat !== null && e.lon !== null);

  // ── Reverse geocode whenever GPS coords change ─────────────────────────
  const reverseGeocode = useCallback(async (lat: number, lon: number) => {
    try {
      const addr = await fetchAddress(lat, lon);
      setAddress(addr);
    } catch {}
  }, []);

  // ── Start high-accuracy GPS watch ──────────────────────────────────────
  const startGps = useCallback(() => {
    if (!navigator.geolocation) return;
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);

    watchRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        const c: Coords = {
          lat:      pos.coords.latitude,
          lon:      pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          source:   'gps',
        };
        setCoords(c);
        setLoading(false);
        setPerm('granted');
        reverseGeocode(c.lat, c.lon);
      },
      (err) => {
        if (err.code === 1) setPerm('denied');
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  }, [reverseGeocode]);

  // ── Mount: IP immediately, GPS in parallel ────────────────────────────
  useEffect(() => {
    // IP location — instant, no permission
    fetchIpCoords()
      .then(c => {
        setCoords(prev => prev?.source === 'gps' ? prev : c);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    // Check current permission state
    navigator.permissions?.query({ name: 'geolocation' as PermissionName })
      .then(result => {
        setPerm(result.state as PermState);
        if (result.state === 'granted') startGps();
        result.onchange = () => {
          setPerm(result.state as PermState);
          if (result.state === 'granted') startGps();
        };
      })
      .catch(() => {
        // permissions API unavailable — try GPS directly
        startGps();
      });

    return () => {
      if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
    };
  }, [startGps]);

  // ── "Enable GPS" button handler ────────────────────────────────────────
  const requestGps = useCallback(() => {
    setPerm('prompt');
    startGps();
  }, [startGps]);

  // ── Address string ────────────────────────────────────────────────────
  const addressLine = address
    ? [address.road, address.suburb ?? address.neighbourhood, address.city]
        .filter(Boolean).join(', ')
    : coords?.source === 'ip' ? 'City-level (enable GPS for street precision)' : '';

  const isGps  = coords?.source === 'gps';
  const zoom   = isGps ? 18 : 13;
  const marker = isGps ? gpsIcon : ipIcon;

  // ── Status badge ──────────────────────────────────────────────────────
  type BadgeKey = 'gps' | 'ip' | 'loading';
  const badgeKey: BadgeKey = loading ? 'loading' : isGps ? 'gps' : 'ip';
  const BADGE: Record<BadgeKey, { label: string; cls: string }> = {
    loading: { label: 'LOCATING…',  cls: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400' },
    gps:     { label: 'GPS LIVE',   cls: 'bg-green-500/10  border-green-500/30  text-green-400'  },
    ip:      { label: 'IP APPROX',  cls: 'bg-cyan-500/10   border-cyan-500/30   text-cyan-400'   },
  };
  const badge = BADGE[badgeKey];

  return (
    <div
      className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <MapPin className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Map</h2>
        </div>
        <div className="flex items-center gap-2">
          {/* Enable GPS button — only shown when not yet granted */}
          {perm !== 'granted' && (
            <button
              onClick={requestGps}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-green-500/50 text-green-400 bg-green-500/10 hover:bg-green-500/20 transition-all"
            >
              <CrosshairIcon className="w-3 h-3" />
              {perm === 'denied' ? 'Re-enable GPS' : 'Enable Precise GPS'}
            </button>
          )}
          <div className={`flex items-center gap-1.5 px-3 py-1 rounded border text-xs font-medium ${badge.cls}`}>
            {badgeKey === 'loading' ? <Loader className="w-3 h-3 animate-spin" />
              : badgeKey === 'gps'  ? <Navigation className="w-3 h-3" />
              : <Wifi className="w-3 h-3" />}
            {badge.label}
          </div>
        </div>
      </div>

      {/* Address line */}
      {addressLine && (
        <p className="text-xs text-gray-400 mb-3 truncate">
          {addressLine}
        </p>
      )}

      {/* GPS denied hint */}
      {perm === 'denied' && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-orange-500/10 border border-orange-500/20 text-xs text-orange-300">
          GPS blocked — click the <strong>lock icon</strong> in your browser bar → <strong>Allow Location</strong>, then click Re-enable GPS.
        </div>
      )}

      {/* ── Map ── */}
      <div className="relative h-72 rounded-xl overflow-hidden mb-4 border border-cyan-500/20">
        {/* Loading overlay — only before first fix */}
        {loading && (
          <div className="absolute inset-0 z-[9999] flex items-center justify-center bg-[#060f1e]/95">
            <div className="text-center">
              <Loader className="w-8 h-8 text-cyan-400 animate-spin mx-auto mb-3" />
              <p className="text-cyan-400 text-sm font-medium">Fetching location…</p>
            </div>
          </div>
        )}

        {/* GPS precision prompt — floating button on map */}
        {!loading && !isGps && perm === 'prompt' && (
          <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-[9999]">
            <button
              onClick={requestGps}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold border border-green-500/60 text-green-300 bg-[#060f1e]/90 backdrop-blur-sm hover:bg-green-500/20 shadow-lg transition-all"
            >
              <LocateFixed className="w-4 h-4" />
              Enable Precise Location
            </button>
          </div>
        )}

        <MapContainer
          center={coords ? [coords.lat, coords.lon] : [20, 78]}
          zoom={coords ? zoom : 4}
          style={{ height: '100%', width: '100%' }}
          zoomControl={false}
          attributionControl={false}
          scrollWheelZoom={true}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            subdomains="abcd"
            maxZoom={20}
          />

          {coords && (
            <>
              <Marker position={[coords.lat, coords.lon]} icon={marker} />
              <Circle
                center={[coords.lat, coords.lon]}
                radius={coords.accuracy}
                pathOptions={{
                  color:       isGps ? '#22c55e' : '#06b6d4',
                  fillColor:   isGps ? '#22c55e' : '#06b6d4',
                  fillOpacity: 0.07,
                  weight: 1,
                  opacity: 0.4,
                }}
              />
              <FlyTo lat={coords.lat} lon={coords.lon} zoom={zoom} />
            </>
          )}

          {/* Detection event markers */}
          {eventMarkers.map((e, i) => (
            <Marker key={i} position={[e.lat!, e.lon!]} icon={eventIcon}>
              <Popup>
                <div style={{ fontSize: 11 }}>
                  <b>{e.time}</b><br />
                  People: {e.people} | Damage: {e.damage.length} | Spills: {e.spills.length}
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>

      {/* ── Coords row ── */}
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
            !coords               ? 'text-gray-500'   :
            coords.accuracy < 50  ? 'text-green-400'  :
            coords.accuracy < 300 ? 'text-yellow-400' : 'text-orange-400'
          }`}>
            {coords ? `±${Math.round(coords.accuracy)} m` : '—'}
          </div>
        </div>
      </div>
    </div>
  );
}
