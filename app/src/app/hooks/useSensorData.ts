import { useState, useEffect } from 'react';

/**
 * Latest reading from the rover's sensor board, as published by coordinator.py.
 *
 * Gas values (mq2 / mq4 / mq135) are a calibrated index, not a percentage:
 * 0 = the sensor's clean-air baseline, 40 = 2.5× baseline. The board's raw
 * analog values are in mq2_raw / mq4_raw / mq135_raw.
 *
 * A sensor the board does not report arrives as null. To keep older panels
 * working those fields are set to 0 here and listed in `missing`; panels should
 * check `missing` and show "—" rather than the 0.
 */
export interface SensorReading {
  timestamp: string;
  temperature: number;
  humidity: number;
  pressure: number;
  lat: number | null;
  lon: number | null;
  gps_valid: boolean;
  gps_satellites: number;
  roll: number;
  pitch: number;
  yaw: number;
  water_detected: boolean;
  mq2: number;
  mq4: number;
  mq135: number;
  air_toxicity: number;   // same as mq135 (kept for older panels)
  mq2_raw?: number | null;
  mq4_raw?: number | null;
  mq135_raw?: number | null;
  gas_calibrating?: boolean;
  people_detected: number;
  event_rate: number;
  missing: string[];      // fields with no real value behind them
}

export interface EHSData {
  timestamp: string;
  zone: string;
  score: number | null;
  grade: string;
  status: string;
  trend: 'IMPROVING' | 'STABLE' | 'DEGRADING';
  coverage?: number;
  weights: Record<string, number>;
  sub_scores: Record<string, { score: number | null; weight: number; live?: boolean }>;
  penalties: Record<string, number>;
  score_history: number[];
}

const NUMERIC = ['temperature', 'humidity', 'pressure', 'roll', 'pitch', 'yaw',
                 'mq2', 'mq4', 'mq135', 'air_toxicity', 'gps_satellites'] as const;

/** Shown when there is no live reading. Every field is listed as missing. */
const NO_DATA: SensorReading = {
  timestamp: '---',
  temperature: 0, humidity: 0, pressure: 0,
  lat: null, lon: null, gps_valid: false, gps_satellites: 0,
  roll: 0, pitch: 0, yaw: 0,
  water_detected: false,
  mq2: 0, mq4: 0, mq135: 0, air_toxicity: 0,
  people_detected: 0, event_rate: 0,
  missing: [...NUMERIC, 'water_detected'],
};

const STALE_AFTER_S = 15;

/** Seconds since a "YYYY-MM-DD HH:MM:SS" local timestamp, or Infinity. */
export function ageSeconds(ts: string | undefined | null): number {
  if (!ts) return Infinity;
  const t = new Date(ts.replace(' ', 'T')).getTime();
  return Number.isNaN(t) ? Infinity : (Date.now() - t) / 1000;
}

function normalise(raw: Record<string, unknown>): SensorReading {
  const missing: string[] = [];
  const out: Record<string, unknown> = { ...raw };
  for (const k of NUMERIC) {
    if (typeof raw[k] !== 'number') { out[k] = 0; missing.push(k); }
  }
  if (typeof raw.water_detected !== 'boolean') { out.water_detected = false; missing.push('water_detected'); }
  out.people_detected = typeof raw.people_detected === 'number' ? raw.people_detected : 0;
  out.event_rate = typeof raw.event_rate === 'number' ? raw.event_rate : 0;
  out.missing = missing;
  return out as unknown as SensorReading;
}

export function useSensorData(pollInterval = 3000) {
  const [sensor, setSensor] = useState<SensorReading>(NO_DATA);
  const [ehs,    setEhs]    = useState<EHSData | null>(null);
  const [live,   setLive]   = useState(false);

  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      let latest: Record<string, unknown> | null = null;
      let ehsData: EHSData | null = null;
      try {
        const [sRes, eRes] = await Promise.all([
          fetch('/sensor_log.json', { cache: 'no-store' }),
          fetch('/ehs_log.json', { cache: 'no-store' }),
        ]);
        if (sRes.ok) {
          const arr = await sRes.json();
          if (Array.isArray(arr) && arr.length > 0) latest = arr[arr.length - 1];
        }
        if (eRes.ok) {
          const data: EHSData = await eRes.json();
          if (data && 'score' in data && ageSeconds(data.timestamp) <= STALE_AFTER_S) ehsData = data;
        }
      } catch {
        // coordinator not running — fall through to "no data"
      }
      if (!mounted) return;

      const fresh = latest !== null && ageSeconds(latest.timestamp as string) <= STALE_AFTER_S;
      setSensor(fresh ? normalise(latest!) : NO_DATA);
      setLive(fresh);
      setEhs(ehsData);
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => { mounted = false; clearInterval(id); };
  }, [pollInterval]);

  return { sensor, ehs, live };
}
