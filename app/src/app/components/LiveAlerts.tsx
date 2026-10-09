import { AlertTriangle, Clock } from 'lucide-react';
import { motion } from 'motion/react';
import { useState, useEffect } from 'react';
import { ageSeconds } from '../hooks/useSensorData';
import type { SensorReading } from '../hooks/useSensorData';

// Only events from the last few minutes are shown. Older log entries are history, not alerts.
const RECENT_S = 300;

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
  damage: { type?: string; confidence: number }[];
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

export default function LiveAlerts(_props: Props) {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const build = async () => {
      try {
        const [mRes, aRes, fRes] = await Promise.all([
          fetch('/mission_log.json', { cache: 'no-store' }).then(r => r.json()).catch(() => []),
          fetch('/audio_log.json', { cache: 'no-store' }).then(r => r.json()).catch(() => []),
          fetch('/fusion_log.json', { cache: 'no-store' }).then(r => r.json()).catch(() => null),
        ]);

        const built: Alert[] = [];
        let id = 1;
        const now = new Date().toLocaleTimeString('en-US', { hour12: false });
        const recent = (ts?: string) => ageSeconds(ts) <= RECENT_S;

        // ── Fusion threats (most urgent first) ─────────────────────────────────
        const threats: { label: string; severity: string; confidence: number }[] =
          fRes && ageSeconds(fRes.timestamp) <= 15 ? (fRes.threats ?? []) : [];
        for (const t of threats) {
          const sev: Alert['severity'] =
            t.severity === 'CRITICAL' ? 'critical' : t.severity === 'HIGH' ? 'high' :
            t.severity === 'MEDIUM' ? 'medium' : 'low';
          built.push({ id: id++, time: now, type: `${t.label} (${(t.confidence * 100).toFixed(0)}%)`, location: 'Fusion engine', severity: sev });
        }

        // ── Camera detections from the last few minutes ────────────────────────
        const mission: MissionEntry[] = (Array.isArray(mRes) ? mRes : []).filter((e: MissionEntry) => recent(e.time)).slice(-10).reverse();
        const seen = new Set<string>();
        for (const entry of mission) {
          const t = entry.time?.split(' ')[1] ?? '--:--:--';
          const add = (key: string, type: string, severity: Alert['severity']) => {
            if (seen.has(key)) return;            // newest entry of each kind only
            seen.add(key);
            built.push({ id: id++, time: t, type, location: 'Camera', severity });
          };
          if (entry.people > 0) add('people', `${entry.people} Person(s) in View`, 'medium');
          for (const d of entry.damage ?? []) add('damage', `Structural Damage ${d.type ?? ''} (${(d.confidence * 100).toFixed(0)}%)`, 'high');
          for (const s of entry.spills ?? []) add('spill', `Spill Detected (${(s.confidence * 100).toFixed(0)}%)`, 'medium');
        }

        // ── Sounds from the last few minutes ───────────────────────────────────
        const audio: AudioEntry[] = (Array.isArray(aRes) ? aRes : []).filter((e: AudioEntry) => recent(e.time)).slice(-5).reverse();
        for (const entry of audio) {
          if (seen.has(`a:${entry.specific}`)) continue;
          seen.add(`a:${entry.specific}`);
          const t = entry.time?.split(' ')[1] ?? '--:--:--';
          const sev: Alert['severity'] =
            ['Fire', 'Explosion/Collapse', 'Gas Leak'].includes(entry.category) ? 'high' :
            entry.category === 'Human' ? 'medium' : 'low';
          built.push({ id: id++, time: t, type: `Audio: ${entry.specific} (${(entry.confidence * 100).toFixed(0)}%)`, location: 'Microphone', severity: sev });
        }

        setAlerts(built.slice(0, 5));
      } catch {
        // keep existing alerts
      }
    };

    build();
    const id = setInterval(build, 4000);
    return () => clearInterval(id);
  }, []);

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

      {alerts.length === 0 && (
        <div className="py-6 text-center text-sm text-gray-600">
          No alerts in the last 5 minutes
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
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
                <div className={`text-sm font-medium ${sevColor(alert.severity)}`}>
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
