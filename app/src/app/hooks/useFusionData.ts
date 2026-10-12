import { useState, useEffect } from 'react';
import { ageSeconds } from './useSensorData';

export interface SensorClass {
  value:    number | null;
  status:   'LIVE' | 'NORMAL' | 'CAUTION' | 'ELEVATED' | 'WARNING' | 'CRITICAL' | 'OFFLINE' | 'CALIBRATING';
  label:    string;
  rank:     number;
  display?: string;
}

export interface Threat {
  id:           string;
  label:        string;
  severity:     'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  confidence:   number;
  contributing: string[];
  description:  string;
}

export interface SourceState {
  live:         boolean;
  age_s?:       number | null;
  origin?:      string | null;
  calibrating?: boolean;
  missing?:     string[];
  source?:      string | null;
}

/** One hazard model's current state. */
export interface HazardState {
  state:      'clear' | 'detected' | 'unavailable' | 'untrained';
  name?:      string;
  p?:         number;      // model probability right now
  threshold?: number;      // fitted detection threshold
  reason?:    string;      // why it cannot be evaluated / was not trained
  method?:    'rule';      // set when a fallback rule (not a trained model) decides it
  rule?:      string;      // the rule's conditions, e.g. "mq2_rise >= 0.5 or mq4_rise >= 0.5"
}

/** Held-out results of the trained model, from train_fusion.py. */
export interface ModelInfo {
  trained_at: string;
  trials:     Record<string, number>;
  evaluation: string;
  hazards:    Record<string, { name: string; threshold: number; trials: number;
                               precision: number; recall: number; f1: number }>;
}

export interface FusionDecision {
  timestamp:          string;
  zone:               string;
  data_mode?:         'LIVE' | 'SIMULATED';
  sources?:           { sensors: SourceState; camera: SourceState; audio: SourceState };
  model?:             ModelInfo | null;
  hazard_states?:     Record<string, HazardState>;
  sensor_classes:     Record<string, SensorClass>;
  threats:            Threat[];
  zone_status:        'CLEAR' | 'ELEVATED' | 'WARNING' | 'CRITICAL' | 'CATASTROPHIC' | 'NO_DATA' | 'UNTRAINED';
  threat_level:       number;
  recommended_action: string;
  action_label:       string;
  action_detail:      string;
  confidence:         number;
  decision_log:       string[];
  processing_time_ms: number;
}

/** Latest fusion decision, or null when the coordinator is not running. */
export function useFusionData(pollInterval = 3000) {
  const [fusion, setFusion] = useState<FusionDecision | null>(null);

  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      let next: FusionDecision | null = null;
      try {
        const res = await fetch('/fusion_log.json', { cache: 'no-store' });
        if (res.ok) {
          const data: FusionDecision = await res.json();
          // A decision older than 15 s means the coordinator has stopped
          if (data?.zone_status && ageSeconds(data.timestamp) <= 15) next = data;
        }
      } catch {
        // coordinator not running
      }
      if (mounted) setFusion(next);
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => { mounted = false; clearInterval(id); };
  }, [pollInterval]);

  return fusion;
}
