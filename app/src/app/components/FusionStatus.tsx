import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Cpu, ChevronDown, ChevronUp, Shield } from 'lucide-react';
import { useFusionData } from '../hooks/useFusionData';
import type { HazardState, ModelInfo, SensorClass, SourceState, Threat } from '../hooks/useFusionData';

// ── Color maps ─────────────────────────────────────────────────────────────────

const ZONE_META: Record<string, { text: string; bg: string; border: string; bar: string; glow: string }> = {
  CLEAR:        { text: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/40',  bar: 'bg-green-500',  glow: 'rgba(34,197,94,0.25)'   },
  ELEVATED:     { text: 'text-cyan-400',   bg: 'bg-cyan-500/10',   border: 'border-cyan-500/40',   bar: 'bg-cyan-500',   glow: 'rgba(6,182,212,0.25)'   },
  WARNING:      { text: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/40', bar: 'bg-orange-500', glow: 'rgba(249,115,22,0.25)'  },
  CRITICAL:     { text: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/40',    bar: 'bg-red-500',    glow: 'rgba(239,68,68,0.30)'   },
  CATASTROPHIC: { text: 'text-red-300',    bg: 'bg-red-500/15',    border: 'border-red-400/60',    bar: 'bg-red-400',    glow: 'rgba(239,68,68,0.50)'   },
  NO_DATA:      { text: 'text-gray-400',   bg: 'bg-white/5',       border: 'border-white/15',      bar: 'bg-gray-500',   glow: 'rgba(0,0,0,0)'          },
  UNTRAINED:    { text: 'text-gray-400',   bg: 'bg-white/5',       border: 'border-white/15',      bar: 'bg-gray-500',   glow: 'rgba(0,0,0,0)'          },
};

const STATUS_META: Record<string, { text: string; dot: string }> = {
  NORMAL:   { text: 'text-gray-400',   dot: 'bg-gray-500'   },
  CAUTION:  { text: 'text-yellow-400', dot: 'bg-yellow-400' },
  ELEVATED: { text: 'text-cyan-400',   dot: 'bg-cyan-400'   },
  WARNING:  { text: 'text-orange-400', dot: 'bg-orange-500' },
  CRITICAL: { text: 'text-red-400',    dot: 'bg-red-500'    },
  LIVE:        { text: 'text-gray-300', dot: 'bg-green-500' },
  OFFLINE:     { text: 'text-gray-600', dot: 'bg-gray-700' },
  CALIBRATING: { text: 'text-blue-300', dot: 'bg-blue-400' },
};

const SEV_META: Record<string, { text: string; border: string; bg: string; bar: string }> = {
  LOW:      { text: 'text-green-400',  border: 'border-green-500/30',  bg: 'bg-green-500/8',   bar: 'bg-green-500'  },
  MEDIUM:   { text: 'text-yellow-400', border: 'border-yellow-500/30', bg: 'bg-yellow-500/8',  bar: 'bg-yellow-400' },
  HIGH:     { text: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/8',  bar: 'bg-orange-500' },
  CRITICAL: { text: 'text-red-400',    border: 'border-red-500/40',    bg: 'bg-red-500/10',    bar: 'bg-red-500'    },
};

const SENSOR_LABEL: Record<string, string> = {
  temperature:    'Temperature',
  humidity:       'Humidity',
  pressure:       'Pressure',
  mq2:            'MQ2 vs clean air',
  mq4:            'MQ4 vs clean air',
  mq135:          'MQ135 vs clean air',
  tilt:           'Rover tilt',
  water_detected: 'Water sensor',
  people_detected:'People (camera)',
  rubble:         'Rubble (camera)',
  spills:         'Spill (camera)',
  audio:          'Top sound score (mic)',
};

/** One trained hazard model: its live probability against its fitted threshold. */
function HazardChip({ id, s, info }: { id: string; s: HazardState; info?: ModelInfo['hazards'][string] }) {
  const tone =
    s.state === 'detected'    ? 'text-red-300 border-red-500/40 bg-red-500/10' :
    s.state === 'clear'       ? 'text-green-300 border-green-500/25 bg-green-500/5' :
    s.state === 'unavailable' ? 'text-yellow-300 border-yellow-500/30 bg-yellow-500/5' :
                                'text-gray-500 border-white/10 bg-white/5';
  const body =
    s.method === 'rule' && (s.state === 'detected' || s.state === 'clear')
      ? `rule: ${s.rule}`
      : s.state === 'detected' || s.state === 'clear'
      ? `p ${(s.p ?? 0).toFixed(2)} / threshold ${s.threshold}`
      : s.state === 'unavailable' ? `cannot evaluate: ${s.reason}` : `not trained: ${s.reason}`;
  return (
    <div className={`px-2.5 py-1.5 rounded-lg border text-[10px] leading-tight ${tone}`}>
      <div className="font-bold">{s.name ?? id}{s.state === 'detected' ? ' — DETECTED' : ''}</div>
      <div className="opacity-80 font-mono">{body}</div>
      {info && (
        <div className="text-gray-500">
          held-out: precision {(info.precision * 100).toFixed(0)}% · recall {(info.recall * 100).toFixed(0)}% · {info.trials} trials
        </div>
      )}
    </div>
  );
}

function SourceChip({ name, state, note }: { name: string; state?: SourceState; note?: string }) {
  const live = !!state?.live;
  return (
    <span
      className={`flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded-full border ${
        live ? 'text-green-300 border-green-500/30 bg-green-500/10'
             : 'text-gray-500 border-white/10 bg-white/5'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${live ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
      {name} {live ? (note ?? 'LIVE') : 'OFFLINE'}
    </span>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ThreatCard({ threat }: { threat: Threat }) {
  const sm = SEV_META[threat.severity] ?? SEV_META['LOW'];
  return (
    <div className={`p-3 rounded-xl border ${sm.bg} ${sm.border}`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-xs font-black truncate ${sm.text}`}>{threat.label}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/5 flex-shrink-0 ${sm.text}`}>
            {threat.severity}
          </span>
        </div>
        <span className={`text-xs font-bold tabular-nums flex-shrink-0 ml-2 ${sm.text}`}>
          {(threat.confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="h-1 bg-white/5 rounded-full overflow-hidden mb-2">
        <motion.div
          className={`h-full rounded-full ${sm.bar}`}
          initial={{ width: 0 }}
          animate={{ width: `${threat.confidence * 100}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>

      <p className="text-[10px] text-gray-400 leading-relaxed line-clamp-2">{threat.description}</p>

      {threat.contributing.length > 0 && (
        <div className="flex gap-1 mt-1.5 flex-wrap">
          {threat.contributing.map(c => (
            <span key={c} className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-gray-500 font-mono">
              {c}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function SensorRow({ name, sc }: { name: string; sc: SensorClass }) {
  const sm   = STATUS_META[sc.status] ?? STATUS_META['NORMAL'];
  const val  = sc.display ?? (sc.value === null ? '—' : String(sc.value));

  return (
    <div className="flex items-center gap-2 py-1.5 border-b border-white/5 last:border-0">
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${sm.dot} ${sc.status === 'CRITICAL' ? 'animate-pulse' : ''}`} />
      <span className="text-[11px] text-gray-500 flex-1 min-w-0 truncate">{SENSOR_LABEL[name] ?? name}</span>
      <span className={`text-[11px] font-bold tabular-nums flex-shrink-0 ${sm.text}`} title={sc.label}>{val}</span>
      <span className={`text-[9px] font-bold flex-shrink-0 w-20 text-right ${sm.text}`}>{sc.status}</span>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function FusionStatus() {
  const fusion   = useFusionData(3000);
  const [showLog, setShowLog] = useState(false);

  if (!fusion) {
    return (
      <div
        className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6"
        style={{ boxShadow: '0 0 20px rgba(6,182,212,0.1)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Cpu className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Sensor Fusion Decision Engine</h2>
        </div>
        <div className="flex flex-col items-center justify-center h-28 gap-3">
          <Cpu className="w-8 h-8 text-cyan-500/25 animate-pulse" />
          <p className="text-sm text-gray-600">Coordinator is not running — no fusion data</p>
          <code className="text-xs text-cyan-600 bg-cyan-500/5 border border-cyan-500/20 px-3 py-1.5 rounded font-mono">
            python coordinator.py
          </code>
        </div>
      </div>
    );
  }

  const zm   = ZONE_META[fusion.zone_status] ?? ZONE_META['CLEAR'];
  const pulse = fusion.zone_status === 'CATASTROPHIC' || fusion.zone_status === 'CRITICAL';
  const simulated = fusion.data_mode === 'SIMULATED';
  const noData = fusion.zone_status === 'NO_DATA' || fusion.zone_status === 'UNTRAINED';
  const untrained = fusion.zone_status === 'UNTRAINED';
  const src = fusion.sources;

  return (
    <div
      className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/30 transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6,182,212,0.1)' }}
    >
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Sensor Fusion Decision Engine</h2>
          {simulated ? (
            <span className="ml-1 text-[10px] font-black px-2 py-0.5 rounded bg-yellow-500/20 border border-yellow-500/40 text-yellow-300">
              SIMULATED SENSORS
            </span>
          ) : (
            <span className="flex items-center gap-1 ml-1">
              <span className={`w-1.5 h-1.5 rounded-full ${noData ? 'bg-gray-600' : 'bg-green-400 animate-pulse'}`} />
              <span className={`text-xs ${noData ? 'text-gray-500' : 'text-green-400'}`}>{untrained ? 'NOT TRAINED' : noData ? 'NO DATA' : 'LIVE'}</span>
            </span>
          )}
        </div>
        <div className="text-right flex-shrink-0 ml-4">
          <div className="text-xs text-gray-600">{fusion.zone} · {fusion.timestamp}</div>
          <div className="text-[10px] text-gray-700">
            {fusion.processing_time_ms}ms · {(fusion.confidence * 100).toFixed(0)}% of trained hazards evaluable
          </div>
        </div>
      </div>

      {/* ── Data sources ────────────────────────────────────────────────────── */}
      {src && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <SourceChip
            name="Sensor board"
            state={src.sensors}
            note={simulated ? 'SIMULATED' : src.sensors.calibrating ? 'CALIBRATING GAS' : 'LIVE'}
          />
          <SourceChip name="Camera" state={src.camera} />
          <SourceChip name="Microphone" state={src.audio} />
          {src.sensors.live && (src.sensors.missing?.length ?? 0) > 0 && (
            <span className="text-[10px] text-gray-500">
              Not reported by board: {src.sensors.missing!.join(', ')}
            </span>
          )}
        </div>
      )}

      {/* ── Trained hazard models ───────────────────────────────────────────── */}
      {fusion.hazard_states && Object.keys(fusion.hazard_states).length > 0 && (
        <div className="mb-4">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
            Hazard models
            {fusion.model?.trained_at && (
              <span className="normal-case tracking-normal text-gray-600">
                {' '}· fitted {fusion.model.trained_at} from {Object.values(fusion.model.trials ?? {}).reduce((a, b) => a + b, 0)} recorded trials · tested {fusion.model.evaluation}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(fusion.hazard_states).map(([id, s]) => (
              <HazardChip key={id} id={id} s={s} info={fusion.model?.hazards?.[id]} />
            ))}
          </div>
        </div>
      )}

      {/* ── Zone Status Banner ──────────────────────────────────────────────── */}
      <div
        className={`rounded-xl border p-4 mb-5 ${zm.bg} ${zm.border}`}
        style={{ boxShadow: `0 0 24px ${zm.glow}` }}
      >
        <div className="flex items-center justify-between mb-3">
          {/* Zone label */}
          <div>
            <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-0.5">Zone Status</div>
            <div className={`text-2xl font-black tracking-widest ${zm.text} ${pulse ? 'animate-pulse' : ''}`}>
              {fusion.zone_status}
            </div>
          </div>

          {/* Threat level bars */}
          <div className="flex flex-col items-end gap-1">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">Threat Level {fusion.threat_level}/4</div>
            <div className="flex items-center gap-1">
              {[0, 1, 2, 3, 4].map(i => (
                <div
                  key={i}
                  className={`h-2 w-7 rounded-sm transition-colors duration-500 ${
                    i <= fusion.threat_level ? zm.bar : 'bg-white/8'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        <div className={`text-xs font-bold mb-1 ${zm.text}`}>{fusion.action_label}</div>
        <p className="text-xs text-gray-400 leading-relaxed">{fusion.action_detail}</p>
      </div>

      {/* ── Body: Threats | Sensor Grid ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-5 mb-4">

        {/* Active Threats */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Active Threats</h3>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
              fusion.threats.length > 0 ? 'bg-red-500/20 text-red-400' : 'bg-white/5 text-gray-600'
            }`}>
              {fusion.threats.length}
            </span>
          </div>

          {fusion.threats.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-28 gap-2">
              <Shield className="w-7 h-7 text-green-500/30" />
              <p className="text-xs text-gray-600">{untrained ? 'Model not trained yet' : noData ? 'No live data to assess' : 'No hazard detected'}</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              <AnimatePresence initial={false}>
                {fusion.threats.map(t => (
                  <motion.div
                    key={t.id}
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <ThreatCard threat={t} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Sensor Classifications */}
        <div>
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">
            Live Inputs
          </h3>
          <div className="bg-white/3 rounded-xl border border-white/5 px-3 py-1">
            {Object.entries(fusion.sensor_classes).map(([name, sc]) => (
              <SensorRow key={name} name={name} sc={sc} />
            ))}
          </div>
        </div>
      </div>

      {/* ── Decision Log ────────────────────────────────────────────────────── */}
      {fusion.decision_log.length > 0 && (
        <div>
          <button
            onClick={() => setShowLog(v => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showLog ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            Decision Log — {fusion.decision_log.length} reasoning steps
          </button>

          <AnimatePresence>
            {showLog && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="mt-2 p-3 rounded-xl bg-black/50 border border-white/5 space-y-1 max-h-48 overflow-y-auto">
                  {fusion.decision_log.map((line, i) => (
                    <div key={i} className="flex gap-2 text-[10px] text-gray-500 font-mono">
                      <span className="text-gray-700 flex-shrink-0 tabular-nums">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="text-gray-500">{line}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
