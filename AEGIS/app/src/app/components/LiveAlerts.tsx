import { AlertTriangle, Clock } from 'lucide-react';
import { motion } from 'motion/react';
import { useState, useEffect } from 'react';
import type { SensorReading } from '../hooks/useSensorData';

interface Alert {
  id: number;
  time: string;
  type: string;
  location: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
}

interface MissionEntry {
  time: string;
  people: number;
  damage: { type: string; confidence: number }[];
  spills: { type: string; confidence: number }[];
}

interface AudioEntry {
  time: string;
  category: string;
  specific: string;
  confidence: number;
}

interface Props {
  sensor: SensorReading;
}

export default function LiveAlerts({ sensor }: Props) {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const build = async () => {
      try {
        const [mRes, aRes] = await Promise.all([
          fetch('/mission_log.json').then(r => r.json()).catch(() => []),
          fetch('/audio_log.json').then(r => r.json()).catch(() => []),
        ]);

        const built: Alert[] = [];
        let id = 1;
        const now = new Date().toLocaleTimeString('en-US', { hour12: false });

        // ── Sensor-derived alerts (prepended — most urgent first) ──────────────
        if (sensor.mq2 >= 40) {
          built.unshift({ id: id++, time: now, type: `EXPLOSIVE GAS — MQ2 ${sensor.mq2.toFixed(1)}% — EVACUATE`, location: 'Sensor', severity: 'critical' });
        } else if (sensor.mq2 > 20) {
          built.unshift({ id: id++, time: now, type: `MQ2 Flammable Gas ${sensor.mq2.toFixed(1)}%`, location: 'Sensor', severity: 'high' });
        }

        if (sensor.water_detected) {
          built.unshift({ id: id++, time: now, type: 'Water Intrusion Detected', location: 'Water Sensor', severity: 'high' });
        }

        if (sensor.mq135 > 30) {
          built.unshift({ id: id++, time: now, type: `SO2/Air Toxicity ${sensor.mq135.toFixed(1)}%`, location: 'MQ135 Sensor', severity: 'high' });
        } else if (sensor.air_toxicity > 30 && sensor.mq135 <= 30) {
          built.unshift({ id: id++, time: now, type: `Air Toxicity ${sensor.air_toxicity.toFixed(1)}%`, location: 'Sensor', severity: 'high' });
        }

        if (sensor.temperature > 35) {
          built.unshift({ id: id++, time: now, type: `High Temp ${sensor.temperature.toFixed(1)}°C`, location: 'Sensor', severity: 'medium' });
        }

        const maxTilt = Math.max(Math.abs(sensor.roll), Math.abs(sensor.pitch));
        if (maxTilt > 30) {
          built.unshift({ id: id++, time: now, type: `Severe Tilt ${maxTilt.toFixed(1)}° — Structural Risk`, location: 'MPU Gyro', severity: 'high' });
        } else if (maxTilt > 15) {
          built.unshift({ id: id++, time: now, type: `Tilt Detected ${maxTilt.toFixed(1)}°`, location: 'MPU Gyro', severity: 'medium' });
        }

        // ── Mission log (last 10 entries) ──────────────────────────────────────
        const mission: MissionEntry[] = mRes.slice(-10).reverse();
        for (const entry of mission) {
          const t = entry.time?.split(' ')[1] ?? '--:--:--';
          if (entry.people > 0) {
            built.push({ id: id++, time: t, type: `${entry.people} Person(s) Detected`, location: 'Camera Feed', severity: 'high' });
          }
          for (const d of entry.damage ?? []) {
            built.push({ id: id++, time: t, type: `Structural Damage (${(d.confidence * 100).toFixed(0)}%)`, location: 'Zone A', severity: 'high' });
          }
          for (const s of entry.spills ?? []) {
            built.push({ id: id++, time: t, type: `Spill Detected (${(s.confidence * 100).toFixed(0)}%)`, location: 'Zone A', severity: 'medium' });
          }
        }

        // ── Audio log (last 5 entries) ─────────────────────────────────────────
        const audio: AudioEntry[] = aRes.slice(-5).reverse();
        for (const entry of audio) {
          const t = entry.time?.split(' ')[1] ?? '--:--:--';
          const sev: Alert['severity'] =
            ['Fire', 'Explosion/Collapse', 'Gas Leak'].includes(entry.category) ? 'high' :
            entry.category === 'Human' ? 'medium' : 'low';
          built.push({ id: id++, time: t, type: `Audio: ${entry.specific} (${(entry.confidence * 100).toFixed(0)}%)`, location: 'Mic', severity: sev });
        }

        // Fallback placeholder alerts
        if (built.length === 0) {
          setAlerts([
            { id: 1, time: '09:15:32', type: 'Gas Leak Detected',  location: 'Zone A-12', severity: 'high'   },
            { id: 2, time: '08:42:18', type: 'Rubble Detected',     location: 'Zone B-7',  severity: 'medium' },
            { id: 3, time: '07:30:45', type: 'Human Presence',      location: 'Zone C-3',  severity: 'low'    },
            { id: 4, time: '07:15:22', type: 'Oil Spill Detected',  location: 'Zone A-5',  severity: 'high'   },
            { id: 5, time: '06:58:10', type: 'Temperature Spike',   location: 'Zone D-1',  severity: 'medium' },
          ]);
        } else {
          setAlerts(built.slice(0, 5));
        }
      } catch {
        // keep existing alerts
      }
    };

    build();
    const id = setInterval(build, 4000);
    return () => clearInterval(id);
  }, [sensor]);

  const sevColor = (s: string) =>
    s === 'critical' ? 'text-red-300' :
    s === 'high'     ? 'text-red-400' :
    s === 'medium'   ? 'text-yellow-400' : 'text-cyan-400';

  const sevDot = (s: string) =>
    s === 'critical' ? 'bg-red-400' :
    s === 'high'     ? 'bg-red-500' :
    s === 'medium'   ? 'bg-yellow-500' : 'bg-cyan-500';

  const sevGlow = (s: string) =>
    s === 'critical' ? '#f87171' :
    s === 'high'     ? '#ef4444' :
    s === 'medium'   ? '#eab308' : '#06b6d4';

  const sevBg = (s: string) =>
    s === 'critical' ? 'bg-red-500/15 border-red-500/40' :
    s === 'high'     ? 'bg-white/5 border-white/10' :
    s === 'medium'   ? 'bg-white/5 border-white/10' : 'bg-white/5 border-white/10';

  const { dateStr, timeStr } = (() => {
    const o: Intl.DateTimeFormatOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    return {
      dateStr: currentTime.toLocaleDateString('en-US', o),
      timeStr: currentTime.toLocaleTimeString('en-US', { hour12: false }),
    };
  })();

  return (
    <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_25px_rgba(6,182,212,0.4)] transition-all duration-300">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Alerts Feed</h2>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span className="text-gray-300">{dateStr}</span>
          </div>
          <div className="font-mono text-xl text-cyan-400">{timeStr}</div>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3">
        {alerts.map((alert, index) => (
          <motion.div key={alert.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className={`p-4 rounded-lg border hover:bg-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all duration-300 ${sevBg(alert.severity)}`}
          >
            <div className="flex items-start gap-2 mb-2">
              <div
                className={`w-2 h-2 rounded-full ${sevDot(alert.severity)} mt-1 flex-shrink-0 ${alert.severity === 'critical' ? 'animate-pulse' : ''}`}
                style={{ boxShadow: `0 0 8px ${sevGlow(alert.severity)}` }}
              />
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-medium ${sevColor(alert.severity)} truncate`}>
                  {alert.type}
                </div>
              </div>
            </div>
            <div className="space-y-1 text-xs text-gray-400">
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>{alert.time}</span>
              </div>
              <div className="truncate">{alert.location}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
