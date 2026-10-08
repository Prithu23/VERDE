import { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Activity, TrendingUp, BarChart2, Zap, GitMerge, AlertOctagon } from 'lucide-react';

interface Anomaly {
  id: string;
  timestamp: string;
  sensor: string;
  method: 'CUSUM' | 'Z-SCORE' | 'TREND' | 'BURST' | 'CORRELATION';
  type: string;
  direction: 'rising' | 'falling';
  value: number | null;
  score: number;
  detail: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
}

const METHOD_META: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  'CUSUM':       { icon: TrendingUp,    label: 'CUSUM',       color: 'text-violet-400 bg-violet-500/15 border-violet-500/30' },
  'Z-SCORE':     { icon: BarChart2,     label: 'Z-SCORE',     color: 'text-blue-400   bg-blue-500/15   border-blue-500/30'   },
  'TREND':       { icon: Activity,      label: 'TREND',       color: 'text-cyan-400   bg-cyan-500/15   border-cyan-500/30'   },
  'BURST':       { icon: Zap,           label: 'BURST',       color: 'text-orange-400 bg-orange-500/15 border-orange-500/30' },
  'CORRELATION': { icon: GitMerge,      label: 'MULTI-SENSOR',color: 'text-pink-400   bg-pink-500/15   border-pink-500/30'   },
};

const SEV_META: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  CRITICAL: { bg: 'bg-red-500/15',    text: 'text-red-400',    border: 'border-red-500/40',    dot: 'bg-red-500'    },
  HIGH:     { bg: 'bg-orange-500/15', text: 'text-orange-400', border: 'border-orange-500/40', dot: 'bg-orange-500' },
  MEDIUM:   { bg: 'bg-yellow-500/15', text: 'text-yellow-400', border: 'border-yellow-500/40', dot: 'bg-yellow-400' },
  LOW:      { bg: 'bg-green-500/10',  text: 'text-green-400',  border: 'border-green-500/30',  dot: 'bg-green-400'  },
};

const SENSOR_LABEL: Record<string, string> = {
  temperature: 'Temp',
  humidity:    'Humidity',
  pressure:    'Pressure',
  mq2:         'MQ2 Gas',
  mq4:         'MQ4 Gas',
  air_toxicity:'Air Tox',
  event_rate:  'Events',
  multi:       'Multi',
};

export default function AnomalyFeed() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [filter, setFilter]       = useState<string>('ALL');
  const [isLive, setIsLive]       = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      try {
        const res  = await fetch('/anomaly_log.json');
        const data: Anomaly[] = await res.json();
        if (mounted) {
          setAnomalies(prev => {
            // Only update if new entries arrived
            if (data.length !== prev.length) {
              return [...data].reverse(); // newest first
            }
            return prev;
          });
        }
      } catch {
        // anomaly_log.json not yet present — ignore
      }
    };

    poll();
    const id = setInterval(poll, 3000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  // Auto-scroll to top when new anomaly arrives
  useEffect(() => {
    if (isLive && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [anomalies, isLive]);

  const filters = ['ALL', 'CRITICAL', 'HIGH', 'CUSUM', 'Z-SCORE', 'TREND', 'BURST', 'CORRELATION'];

  const visible = anomalies.filter(a => {
    if (filter === 'ALL')    return true;
    if (['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].includes(filter)) return a.severity === filter;
    return a.method === filter;
  });

  const counts = {
    CRITICAL: anomalies.filter(a => a.severity === 'CRITICAL').length,
    HIGH:     anomalies.filter(a => a.severity === 'HIGH').length,
    total:    anomalies.length,
  };

  return (
    <div
      className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/30 transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.1)' }}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <AlertOctagon className="w-5 h-5 text-cyan-400" />
            <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Anomaly Intelligence</h2>
            {/* live pulse */}
            <span className="flex items-center gap-1 ml-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs text-green-400">LIVE</span>
            </span>
          </div>
          <p className="text-xs text-gray-500">
            Temporal pattern detection · CUSUM · Z-Score · Trend · Burst · Correlation
          </p>
        </div>

        {/* Summary chips */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {counts.CRITICAL > 0 && (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/40">
              {counts.CRITICAL} CRITICAL
            </span>
          )}
          {counts.HIGH > 0 && (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-orange-500/20 text-orange-400 border border-orange-500/40">
              {counts.HIGH} HIGH
            </span>
          )}
          <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-white/5 text-gray-400 border border-white/10">
            {counts.total} total
          </span>
        </div>
      </div>

      {/* ── Filter bar ─────────────────────────────────────────────────── */}
      <div className="flex gap-1.5 flex-wrap mb-4">
        {filters.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-all border ${
              filter === f
                ? 'bg-cyan-500/25 border-cyan-500/50 text-cyan-300'
                : 'bg-white/5 border-white/10 text-gray-500 hover:text-gray-300'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* ── Feed ───────────────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        className="space-y-2 max-h-72 overflow-y-auto pr-1 scrollbar-thin"
      >
        {visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-36 gap-3 text-center">
            <Activity className="w-8 h-8 text-cyan-500/30" />
            <p className="text-sm text-gray-600">
              {anomalies.length === 0
                ? 'No anomalies yet — run anomaly_detector.py to start streaming'
                : 'No anomalies match this filter'}
            </p>
            {anomalies.length === 0 && (
              <code className="text-xs text-cyan-600 bg-cyan-500/5 border border-cyan-500/20 px-3 py-1.5 rounded font-mono">
                python anomaly_detector.py --scenario-interval 30
              </code>
            )}
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {visible.map(a => {
              const m   = METHOD_META[a.method]  ?? METHOD_META['CUSUM'];
              const s   = SEV_META[a.severity]   ?? SEV_META['LOW'];
              const Icon = m.icon;

              return (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className={`flex gap-3 p-3 rounded-xl border ${s.bg} ${s.border}`}
                >
                  {/* Left: severity dot + method icon */}
                  <div className="flex flex-col items-center gap-1.5 flex-shrink-0 pt-0.5">
                    <span className={`w-2 h-2 rounded-full ${s.dot} flex-shrink-0`} />
                    <Icon className={`w-3.5 h-3.5 ${m.color.split(' ')[0]}`} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      {/* Method badge */}
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${m.color}`}>
                        {m.label}
                      </span>
                      {/* Anomaly type */}
                      <span className={`text-xs font-bold ${s.text}`}>{a.type}</span>
                      {/* Sensor */}
                      <span className="text-xs text-gray-500 font-mono">
                        {SENSOR_LABEL[a.sensor] ?? a.sensor}
                        {a.value !== null && <> · {a.value}</>}
                      </span>
                      {/* Score */}
                      <span className="text-[10px] text-gray-600 ml-auto flex-shrink-0">
                        score {a.score}
                      </span>
                    </div>

                    {/* Detail */}
                    <p className="text-xs text-gray-400 leading-relaxed line-clamp-2">
                      {a.detail}
                    </p>

                    {/* Timestamp */}
                    <p className="text-[10px] text-gray-600 mt-1">{a.timestamp}</p>
                  </div>

                  {/* Severity badge */}
                  <div className="flex-shrink-0">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${s.text}`}>
                      {a.severity}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
