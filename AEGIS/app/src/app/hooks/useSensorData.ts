import { useState, useEffect } from 'react';

export interface SensorReading {
  timestamp: string;
  temperature: number;
  humidity: number;
  pressure: number;
  // GPS from rover sensor board
  lat: number | null;
  lon: number | null;
  gps_valid: boolean;
  gps_satellites: number;
  // MPU-6050 gyro/accelerometer
  roll: number;
  pitch: number;
  yaw: number;
  // Water sensor
  water_detected: boolean;
  // Gas sensors
  mq2: number;          // flammable gas / LPG
  mq4: number;          // methane
  mq135: number;        // SO2 / air quality
  air_toxicity: number; // alias for mq135 (backward compat)
  // Detection stats
  people_detected: number;
  event_rate: number;
}

export interface EHSData {
  timestamp: string;
  zone: string;
  score: number;
  grade: string;
  status: string;
  trend: 'IMPROVING' | 'STABLE' | 'DEGRADING';
  weights: Record<string, number>;
  sub_scores: Record<string, { score: number; weight: number }>;
  penalties: Record<string, number>;
  score_history: number[];
}

const SENSOR_DEFAULTS: SensorReading = {
  timestamp:       '---',
  temperature:     28.5,
  humidity:        65.0,
  pressure:        1013.0,
  lat:             null,
  lon:             null,
  gps_valid:       false,
  gps_satellites:  0,
  roll:            0.0,
  pitch:           0.0,
  yaw:             0.0,
  water_detected:  false,
  mq2:             12.0,
  mq4:             8.0,
  mq135:           15.0,
  air_toxicity:    15.0,
  people_detected: 0,
  event_rate:      0.5,
};

export function useSensorData(pollInterval = 3000) {
  const [sensor, setSensor] = useState<SensorReading>(SENSOR_DEFAULTS);
  const [ehs,    setEhs]    = useState<EHSData | null>(null);
  const [live,   setLive]   = useState(false);

  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      try {
        const [sRes, eRes] = await Promise.all([
          fetch('/sensor_log.json'),
          fetch('/ehs_log.json'),
        ]);

        if (sRes.ok) {
          const arr: SensorReading[] = await sRes.json();
          if (mounted && Array.isArray(arr) && arr.length > 0) {
            const latest = arr[arr.length - 1];
            // Ensure mq135 and air_toxicity are in sync
            if (latest.mq135 === undefined) latest.mq135 = latest.air_toxicity ?? 15;
            if (latest.air_toxicity === undefined) latest.air_toxicity = latest.mq135;
            setSensor(latest);
            setLive(true);
          }
        }

        if (eRes.ok) {
          const data: EHSData = await eRes.json();
          if (mounted && data?.score !== undefined) setEhs(data);
        }
      } catch {
        // files not yet created — use defaults
      }
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => { mounted = false; clearInterval(id); };
  }, [pollInterval]);

  return { sensor, ehs, live };
}
