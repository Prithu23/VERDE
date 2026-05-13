import { AlertTriangle, Clock } from 'lucide-react';
import { motion } from 'motion/react';
import { useState, useEffect } from 'react';
import type { SensorReading } from '../hooks/useSensorData';

interface Alert {
  id: number;
  time: string;
  type: string;
  location: string;
  severity: 'high' | 'medium' | 'low';
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

  // Build live alerts from mission + audio logs
  useEffect(() => {
    const build = async () => {
      try {
        const [mRes, aRes] = await Promise.all([
          fetch('/mission_log.json').then(r => r.json()).catch(() => []),
          fetch('/audio_log.json').then(r => r.json()).catch(() => []),
        ]);

        const built: Alert[] = [];
        let id = 1;

        // From mission log (last 10 entries)
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

        // From audio log (last 5)
        const audio: AudioEntry[] = aRes.slice(-5).reverse();
        for (const entry of audio) {
          const t = entry.time?.split(' ')[1] ?? '--:--:--';
          const sev: 'high' | 'medium' | 'low' =
            ['Fire', 'Explosion/Collapse', 'Gas Leak'].includes(entry.category) ? 'high' :
            entry.category === 'Human' ? 'medium' : 'low';
          built.push({ id: id++, time: t, type: `Audio: ${entry.specific} (${(entry.confidence * 100).toFixed(0)}%)`, location: 'Mic', severity: sev });
        }

        // Sensor-derived alerts
        const now = new Date().toLocaleTimeString('en-US', { hour12: false });
        if (sensor.air_toxicity > 30) built.unshift({ id: id++, time: now, type: `Air Toxicity ${sensor.air_toxicity.toFixed(1)}%`, location: 'Sensor', severity: 'high' });
        if (sensor.mq2 > 20)         built.unshift({ id: id++, time: now, type: `MQ2 Gas ${sensor.mq2.toFixed(1)}%`, location: 'Sensor', severity: 'high' });
        if (sensor.temperature > 35) built.unshift({ id: id++, time: now, type: `High Temp ${sensor.temperature.toFixed(1)}°C`, location: 'Sensor', severity: 'medium' });

        // Fallback if nothing real yet
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
        // keep existing
      }
    };

    build();
    const id = setInterval(build, 4000);
    return () => clearInterval(id);
  }, [sensor]);

  const sevColor = (s: string) =>
    s === 'high' ? 'text-red-400' : s === 'medium' ? 'text-yellow-400' : 'text-cyan-400';
  const sevDot = (s: string) =>
    s === 'high' ? 'bg-red-500' : s === 'medium' ? 'bg-yellow-500' : 'bg-cyan-500';
  const sevGlow = (s: string) =>
    s === 'high' ? '#ef4444' : s === 'medium' ? '#eab308' : '#06b6d4';

  const { dateStr, timeStr } = (() => {
    const o: Intl.DateTimeFormatOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    return { dateStr: currentTime.toLocaleDateString('en-US', o), timeStr: currentTime.toLocaleTimeString('en-US', { hour12: false }) };
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
            className="p-4 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all duration-300"
          >
            <div className="flex items-start gap-2 mb-2">
              <div className={`w-2 h-2 rounded-full ${sevDot(alert.severity)} mt-1 flex-shrink-0`}
                style={{ boxShadow: `0 0 8px ${sevGlow(alert.severity)}` }} />
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
