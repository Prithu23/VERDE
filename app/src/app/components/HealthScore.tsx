import { motion } from 'motion/react';
import { TrendingUp, TrendingDown, Minus, ShieldCheck } from 'lucide-react';
import type { EHSData, SensorReading } from '../hooks/useSensorData';

interface Props {
  ehs: EHSData | null;
  sensor: SensorReading;
  live: boolean;
}

const SUB_META: Record<string, { label: string; desc: string; color: string }> = {
  climate: { label: 'Climate',  desc: 'Gas · Fire / heat · Water · Tilt models', color: '#06b6d4' },
  visual:  { label: 'Visual',   desc: 'Structural · Spill models',               color: '#a78bfa' },
  audio:   { label: 'Audio',    desc: 'Human distress model',                    color: '#f59e0b' },
  anomaly: { label: 'Anomaly',  desc: 'shown below, not part of this score',     color: '#ec4899' },
};

function scoreColor(s: number): string {
  if (s >= 75) return '#22c55e';
  if (s >= 60) return '#eab308';
  if (s >= 40) return '#f97316';
  return '#ef4444';
}

function scoreGlow(s: number): string {
  if (s >= 75) return 'rgba(34,197,94,0.35)';
  if (s >= 60) return 'rgba(234,179,8,0.35)';
  if (s >= 40) return 'rgba(249,115,22,0.35)';
  return 'rgba(239,68,68,0.35)';
}

export default function HealthScore({ ehs, sensor, live }: Props) {
  // No score without live data: an empty gauge, never a default of 100.
  const hasScore = typeof ehs?.score === 'number';
  const score = hasScore ? (ehs!.score as number) : 0;
  const grade = hasScore ? ehs!.grade : '—';
  const status = hasScore ? ehs!.status : 'NO DATA';
  const anyLive = hasScore;
  const miss = (k: string) => sensor.missing.includes(k);
  const trendVal = ehs?.trend ?? 'STABLE';
  const subScores = ehs?.sub_scores ?? {};

  const R = 52;
  const circumference = 2 * Math.PI * R;
  const fill = (score / 100) * circumference;
  const offset = circumference - fill;
  const col = hasScore ? scoreColor(score) : '#6b7280';
  const glow = hasScore ? scoreGlow(score) : 'rgba(107,114,128,0.15)';

  const TrendIcon = trendVal === 'IMPROVING' ? TrendingUp : trendVal === 'DEGRADING' ? TrendingDown : Minus;
  const trendColor = trendVal === 'IMPROVING' ? 'text-green-400' : trendVal === 'DEGRADING' ? 'text-red-400' : 'text-gray-400';

  return (
    <div
      className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/30 transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6,182,212,0.1)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-5">
        <ShieldCheck className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Environmental Health Score</h2>
        <span className={`flex items-center gap-1 ml-auto text-xs ${anyLive ? 'text-green-400' : 'text-gray-600'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${anyLive ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
          {!anyLive ? 'NO LIVE DATA'
            : (ehs?.coverage ?? 1) < 0.99 ? `LIVE · ${Math.round((ehs?.coverage ?? 1) * 100)}% OF HAZARDS CHECKED`
            : 'LIVE'}
        </span>
      </div>

      <div className="flex gap-6 items-start">
        {/* Gauge */}
        <div className="flex flex-col items-center gap-2 flex-shrink-0">
          <div className="relative w-40 h-40">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 128 128">
              {/* Track */}
              <circle cx="64" cy="64" r={R} fill="none"
                stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
              {/* Score arc */}
              <motion.circle
                cx="64" cy="64" r={R}
                fill="none"
                stroke={col}
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset: offset }}
                transition={{ duration: 1.2, ease: 'easeOut' }}
                style={{ filter: `drop-shadow(0 0 8px ${glow})` }}
              />
            </svg>
            {/* Center */}
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
              <motion.div
                key={Math.round(score)}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className="text-4xl font-black tabular-nums"
                style={{ color: col }}
              >
                {hasScore ? Math.round(score) : '—'}
              </motion.div>
              <div className="text-xs text-gray-400 font-mono">/ 100</div>
            </div>
          </div>

          {/* Grade badge */}
          <div className="flex flex-col items-center gap-1">
            <div
              className="text-2xl font-black px-4 py-1 rounded-lg"
              style={{ color: col, background: `${glow}`, border: `1px solid ${col}40` }}
            >
              {grade}
            </div>
            <div className="text-xs font-bold tracking-widest" style={{ color: col }}>
              {status}
            </div>
          </div>

          {/* Trend */}
          <div className={`flex items-center gap-1.5 text-xs font-semibold ${trendColor}`}>
            <TrendIcon className="w-3.5 h-3.5" />
            {trendVal}
          </div>
        </div>

        {/* Right: sub-scores + live sensor snapshot */}
        <div className="flex-1 min-w-0 space-y-3">
          {/* Sub-score bars */}
          {Object.entries(SUB_META).map(([key, meta]) => {
            const raw = subScores[key]?.score;
            const on = typeof raw === 'number';
            const sub = on ? (raw as number) : 0;
            const c = meta.color;
            return (
              <div key={key}>
                <div className="flex items-center justify-between mb-1">
                  <div>
                    <span className="text-xs font-bold text-white/80">{meta.label}</span>
                    <span className="text-[10px] text-gray-600 ml-2">{meta.desc}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[10px] text-gray-600">
                      {on ? 'P(no hazard)' : key === 'anomaly' ? 'not scored' : 'no model / source offline'}
                    </span>
                    <span className="text-xs font-bold tabular-nums" style={{ color: on ? scoreColor(sub) : '#4b5563' }}>
                      {on ? sub.toFixed(0) : '—'}
                    </span>
                  </div>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${sub}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                    style={{ background: c, boxShadow: `0 0 6px ${c}60` }}
                  />
                </div>
              </div>
            );
          })}

          {/* Live sensor snapshot */}
          <div className="pt-2 mt-1 border-t border-white/5">
            <div className="text-[10px] text-gray-500 mb-2">
              Score = probability, from the trained hazard models, that no hazard is present.
            </div>
            <div className="text-[10px] text-gray-600 mb-2 uppercase tracking-wider">
              Live Sensor Snapshot · gas shown as % rise over clean air
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'Temp',     value: miss('temperature') ? '—' : `${sensor.temperature.toFixed(1)}°C`, warn: false },
                { label: 'Humidity', value: miss('humidity') ? '—' : `${sensor.humidity.toFixed(0)}%`,        warn: false },
                { label: 'MQ2',      value: miss('mq2') ? '—' : `+${sensor.mq2.toFixed(0)}%`,                 warn: false },
                { label: 'MQ4',      value: miss('mq4') ? '—' : `+${sensor.mq4.toFixed(0)}%`,                 warn: false },
                { label: 'MQ135',    value: miss('mq135') ? '—' : `+${sensor.mq135.toFixed(0)}%`,             warn: false },
                { label: 'People',   value: `${sensor.people_detected}`,                                      warn: false },
              ].map(item => (
                <div key={item.label} className="p-1.5 rounded-lg bg-white/3 border border-white/5">
                  <div className="text-[9px] text-gray-600">{item.label}</div>
                  <div className={`text-xs font-bold tabular-nums ${item.warn ? 'text-orange-400' : 'text-gray-300'}`}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Score history sparkline */}
      {(ehs?.score_history?.length ?? 0) > 2 && (
        <div className="mt-4 pt-3 border-t border-white/5">
          <div className="text-[10px] text-gray-600 mb-2">Score History</div>
          <div className="flex items-end gap-0.5 h-6">
            {(ehs!.score_history.slice(-30)).map((s, i) => (
              <div
                key={i}
                className="flex-1 rounded-sm min-w-[3px]"
                style={{
                  height: `${(s / 100) * 100}%`,
                  background: scoreColor(s),
                  opacity: 0.5 + (i / 30) * 0.5,
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

