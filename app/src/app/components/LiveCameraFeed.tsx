import { useState, useEffect } from 'react'
import { Camera, Boxes, Droplet, Users, WifiOff, RefreshCw, Monitor, Wifi } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { useMissionLog } from '../hooks/useMissionLog'
import { useDetectionState } from '../hooks/useDetectionState'

// detect.py streams annotated frames here for both laptop and ESP32 sources
const MJPEG_URL = 'http://localhost:8765/video_feed'

type Source     = 'laptop' | 'esp32'
type FeedStatus = 'connecting' | 'live' | 'offline'

const CMD: Record<Source, string> = {
  laptop: 'python detect.py',
  esp32:  'python detect.py --source esp32 --ip <camera-ip>',
}

export default function LiveCameraFeed() {
  const { totalEvents } = useMissionLog()
  const det = useDetectionState()

  const [source, setSource] = useState<Source>('laptop')
  const [status, setStatus] = useState<FeedStatus>('connecting')
  const [imgKey, setImgKey]  = useState(0)

  // Retry connection every 8 s when offline
  useEffect(() => {
    if (status !== 'offline') return
    const id = setTimeout(() => {
      setStatus('connecting')
      setImgKey(k => k + 1)
    }, 8_000)
    return () => clearTimeout(id)
  }, [status])

  // Reconnect when source changes
  function switchSource(s: Source) {
    setSource(s)
    setStatus('connecting')
    setImgKey(k => k + 1)
  }

  const statusConfig = {
    connecting: { label: 'CONNECTING', cls: 'text-yellow-400 border-yellow-500/40' },
    live:       { label: 'LIVE',       cls: 'text-green-400  border-green-500/40'  },
    offline:    { label: 'OFFLINE',    cls: 'text-red-400    border-red-500/40'    },
  }
  const { label: statusLabel, cls: statusCls } = statusConfig[status]

  const counters = [
    { label: 'People',    value: det.people, Icon: Users,   color: 'text-green-400',  ring: 'border-green-500/30',  bg: 'bg-green-500/10'  },
    { label: 'Rubble',    value: det.rubble, Icon: Boxes,   color: 'text-red-400',    ring: 'border-red-500/30',    bg: 'bg-red-500/10'    },
    { label: 'Oil Spills',value: det.spills, Icon: Droplet, color: 'text-yellow-400', ring: 'border-yellow-500/30', bg: 'bg-yellow-500/10' },
  ]

  return (
    <div
      className="h-full rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 flex flex-col gap-4 hover:border-cyan-400/50 transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6,182,212,0.15)' }}
    >
      {/* ── Header ── */}
      <div className="flex items-center gap-3 flex-wrap">
        <Camera className="w-5 h-5 text-cyan-400 flex-shrink-0" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Camera Feed</h2>
        <span className={`text-xs font-mono px-2 py-0.5 rounded border ${statusCls}`}>
          {statusLabel}
        </span>
        {det.fps > 0 && (
          <span className="text-xs text-gray-500 font-mono ml-1">
            {det.fps} fps · {det.source}
          </span>
        )}

        {/* Source toggle */}
        <div className="ml-auto flex rounded-lg border border-white/10 overflow-hidden text-xs font-medium">
          <button
            onClick={() => switchSource('laptop')}
            className={`flex items-center gap-1.5 px-3 py-2 transition-colors ${
              source === 'laptop'
                ? 'bg-cyan-500/20 text-cyan-400 border-r border-cyan-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border-r border-white/10'
            }`}
          >
            <Monitor className="w-3.5 h-3.5" />
            LAPTOP
          </button>
          <button
            onClick={() => switchSource('esp32')}
            className={`flex items-center gap-1.5 px-3 py-2 transition-colors ${
              source === 'esp32'
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <Wifi className="w-3.5 h-3.5" />
            ESP32-CAM
          </button>
        </div>
      </div>

      {/* ── Main content: feed + counters ── */}
      <div className="flex gap-4 flex-1 min-h-0">

        {/* ── Live feed ── */}
        <div className="relative flex-1 bg-gradient-to-br from-gray-900 to-black rounded-xl border border-cyan-500/20 overflow-hidden">

          {/* MJPEG stream from detect.py */}
          {status !== 'offline' && (
            <img
              key={imgKey}
              src={`${MJPEG_URL}?t=${imgKey}`}
              alt="Annotated camera feed"
              className="absolute inset-0 w-full h-full object-cover"
              onLoad={() => setStatus('live')}
              onError={() => setStatus('offline')}
            />
          )}

          {/* Offline state */}
          <AnimatePresence>
            {status === 'offline' && (
              <motion.div
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="absolute inset-0 flex items-center justify-center bg-gray-950/90"
              >
                <div className="text-center px-6">
                  <WifiOff className="w-12 h-12 text-red-400/50 mx-auto mb-3" />
                  <p className="text-red-400/80 text-sm font-semibold mb-1">detect.py not running</p>
                  <p className="text-gray-500 text-xs font-mono bg-black/50 rounded px-3 py-1.5 mt-2">
                    {CMD[source]}
                  </p>
                  <button
                    onClick={() => { setStatus('connecting'); setImgKey(k => k + 1) }}
                    className="mt-4 flex items-center gap-1.5 mx-auto px-3 py-1.5 rounded-lg text-xs border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10 transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" /> Retry
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Overlays when live */}
          {status === 'live' && (
            <>
              <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-sm px-3 py-1 rounded text-xs text-cyan-400 font-mono border border-cyan-500/20">
                {new Date().toLocaleString()}
              </div>
              <div className="absolute top-3 right-3 flex items-center gap-2 bg-black/70 backdrop-blur-sm px-3 py-1 rounded border border-red-500/30">
                <motion.div
                  className="w-2 h-2 bg-red-500 rounded-full"
                  animate={{ opacity: [1, 0.2, 1] }}
                  transition={{ duration: 1.4, repeat: Infinity }}
                />
                <span className="text-xs text-red-400 font-semibold">REC</span>
              </div>
              <div className="absolute bottom-3 left-3 flex gap-2">
                <div className="bg-cyan-500/20 backdrop-blur-sm px-2 py-1 rounded text-xs text-cyan-400 border border-cyan-500/40">
                  AI Detection: Active
                </div>
                {totalEvents > 0 && (
                  <div className="bg-orange-500/20 backdrop-blur-sm px-2 py-1 rounded text-xs text-orange-400 border border-orange-500/40">
                    {totalEvents} events logged
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* ── Detection counters ── */}
        <div className="flex flex-col gap-3 w-52">
          <p className="text-xs text-gray-500 font-mono uppercase tracking-widest px-1">
            Model Detections
          </p>
          {counters.map(({ label, value, Icon, color, ring, bg }) => (
            <motion.div
              key={label}
              animate={value > 0 ? { scale: [1, 1.03, 1] } : {}}
              transition={{ duration: 0.3 }}
              className={`flex items-center gap-4 p-4 rounded-xl border ${ring} ${bg} transition-all duration-300`}
            >
              <div className={`p-2 rounded-lg bg-black/30 border ${ring}`}>
                <Icon className={`w-5 h-5 ${color}`} />
              </div>
              <div>
                <div className={`text-3xl font-bold ${value > 0 ? color : 'text-white'}`}>
                  {value}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">{label}</div>
              </div>
            </motion.div>
          ))}

          {/* Command hint */}
          <div className="mt-auto pt-2 border-t border-white/5">
            <p className="text-xs text-gray-600 mb-1">Run in terminal:</p>
            <code className="text-xs text-cyan-600 font-mono break-all">
              {CMD[source]}
            </code>
          </div>
        </div>
      </div>
    </div>
  )
}
