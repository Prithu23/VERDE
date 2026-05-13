import { useState, useEffect } from 'react';

export interface SensorReading {
  timestamp: string;
  temperature: number;
  humidity: number;
  pressure: number;
  mq2: number;
  mq4: number;
  air_toxicity: number;
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
  mq2:             12.0,
  mq4:             8.0,
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
            setSensor(arr[arr.length - 1]);
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
