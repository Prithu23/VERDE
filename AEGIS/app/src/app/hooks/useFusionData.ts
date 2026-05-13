import { useState, useEffect } from 'react';

export interface SensorClass {
  value:  number;
  status: 'NORMAL' | 'CAUTION' | 'ELEVATED' | 'WARNING' | 'CRITICAL';
  label:  string;
  rank:   number;
}

export interface Threat {
  id:           string;
  label:        string;
  severity:     'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  confidence:   number;
  contributing: string[];
  description:  string;
}

export interface FusionDecision {
  timestamp:          string;
  zone:               string;
  sensor_classes:     Record<string, SensorClass>;
  threats:            Threat[];
  zone_status:        'CLEAR' | 'ELEVATED' | 'WARNING' | 'CRITICAL' | 'CATASTROPHIC';
  threat_level:       number;
  recommended_action: string;
  action_label:       string;
  action_detail:      string;
  confidence:         number;
  decision_log:       string[];
  processing_time_ms: number;
}

export function useFusionData(pollInterval = 3000) {
  const [fusion, setFusion] = useState<FusionDecision | null>(null);

  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      try {
        const res = await fetch('/fusion_log.json');
        if (res.ok) {
          const data: FusionDecision = await res.json();
          if (mounted && data?.zone_status) setFusion(data);
        }
      } catch {
        // fusion_engine.py not running yet — stay null
      }
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => { mounted = false; clearInterval(id); };
  }, [pollInterval]);

  return fusion;
}
