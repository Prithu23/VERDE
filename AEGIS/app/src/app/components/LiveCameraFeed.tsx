import { useState, useEffect } from 'react'
import { Camera, Boxes, Droplet, Users, WifiOff, Play, Square, RefreshCw } from 'lucide-react'
import { motion } from 'motion/react'
import { useMissionLog } from '../hooks/useMissionLog'
import { useDetectionState } from '../hooks/useDetectionState'

// detect.py annotated MJPEG — always shows the active camera (ESP32-CAM / phone hotspot)
const VERDE_STREAM = 'http://localhost:8765/video_feed'

type FeedStatus = 'connecting' | 'live' | 'offline'

export default function LiveCameraFeed() {
  const { totalEvents, lastEntry } = useMissionLog()
  const detection = useDetectionState()
  const people = detection.people
  const damage = detection.rubble
  const spills = detection.spills

  const [running, setRunning]     = useState(true)
  const [status, setStatus]       = useState<FeedStatus>('connecting')

  useEffect(() => {
    if (running) setStatus('connecting')
  }, [running])

  // Auto-retry when offline
  useEffect(() => {
    if (status !== 'offline') return
    const id = setTimeout(() => setStatus('connecting'), 8_000)
    return () => clearTimeout(id)
  }, [status])

  const statusCls = {
    connecting: 'text-yellow-400 border-yellow-500/40',
    live:       'text-green-400  border-green-500/40',
    offline:    'text-red-400    border-red-500/40',
  }[status]

  const statusLabel = !running ? 'STOPPED' : status.toUpperCase()
  const showRec     = running && status === 'live'
  const timestamp   = lastEntry?.time ?? new Date().toLocaleString()
  const fpsLabel    = detection.fps > 0 ? `${detection.fps} fps · ${detection.source}` : null

  const detections = [
    { label: 'People',     value: people, Icon: Users,   color: 'text-green-400'  },
    { label: 'Rubble',     value: damage, Icon: Boxes,   color: 'text-red-400'    },
    { label: 'Oil Spills', value: spills, Icon: Droplet, color: 'text-yellow-400' },
  ]

  return (
    <div
      className="h-full rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300 flex flex-col"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      {/* ── Header ── */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Camera className="w-5 h-5 text-cyan-400 flex-shrink-0" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Camera Feed</h2>
        <span className={`text-xs font-mono px-2 py-0.5 rounded border ${!running ? 'text-gray-400 border-gray-500/40' : statusCls}`}>
          {statusLabel}
        </span>

        <div className="ml-auto">
          <button
            onClick={() => setRunning(r => !r)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
              running
                ? 'bg-red-500/10 border-red-500/40 text-red-400 hover:bg-red-500/20'
                : 'bg-green-500/10 border-green-500/40 text-green-400 hover:bg-green-500/20'
            }`}
          >
            {running
              ? <><Square className="w-3 h-3 fill-current" /> Stop</>
              : <><Play   className="w-3 h-3 fill-current" /> Start</>}
          </button>
        </div>
      </div>

      <div className="flex gap-4 flex-1">
        {/* ── Feed area ── */}
        <div className="relative flex-1 bg-gradient-to-br from-gray-900 to-black rounded-xl border border-cyan-500/30 overflow-hidden">

          {/* Stopped */}
          {!running && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <Camera className="w-12 h-12 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">Feed stopped</p>
              </div>
            </div>
          )}

          {/* Live MJPEG from detect.py */}
          {running && status !== 'offline' && (
            <img
              key={status === 'connecting' ? Date.now() : 'live'}
              src={`${VERDE_STREAM}?t=${Date.now()}`}
              alt="Phone camera feed"
              className="absolute inset-0 w-full h-full object-cover"
              onLoad={() => setStatus('live')}
              onError={() => setStatus('offline')}
            />
          )}

          {/* Offline state */}
          {running && status === 'offline' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <WifiOff className="w-12 h-12 text-red-400/50 mx-auto mb-2" />
                <p className="text-red-400/70 text-sm font-medium">Camera not connected</p>
                <p className="text-gray-500 text-xs mt-1">Run: python detect.py --ip &lt;camera-ip&gt;</p>
                <button
                  onClick={() => setStatus('connecting')}
                  className="mt-3 flex items-center gap-1.5 mx-auto px-3 py-1.5 rounded-lg text-xs border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                >
                  <RefreshCw className="w-3 h-3" /> Retry
                </button>
              </div>
            </div>
          )}

          {/* Overlays */}
          {running && (
            <>
              <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-sm px-3 py-1 rounded text-xs text-cyan-400 font-mono border border-cyan-500/30">
                {timestamp}
              </div>
              {showRec && (
                <div className="absolute top-3 right-3 flex items-center gap-2 bg-black/70 backdrop-blur-sm px-3 py-1 rounded border border-red-500/30">
                  <motion.div
                    className="w-2 h-2 bg-red-500 rounded-full"
                    animate={{ opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                  <span className="text-xs text-red-400 font-medium">REC</span>
                </div>
              )}
              <div className="absolute bottom-3 left-3 flex gap-2">
                <div className="bg-cyan-500/20 backdrop-blur-sm px-2 py-1 rounded text-xs text-cyan-400 border border-cyan-500/50">
                  AI Detection: Active
                </div>
                {totalEvents > 0 && (
                  <div className="bg-orange-500/20 backdrop-blur-sm px-2 py-1 rounded text-xs text-orange-400 border border-orange-500/50">
                    {totalEvents} events
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* ── Detection stats ── */}
        <div className="flex flex-col gap-3 w-64">
          {fpsLabel && (
            <div className="text-xs text-gray-500 font-mono text-right px-1">{fpsLabel}</div>
          )}
          {detections.map(({ label, value, Icon, color }) => (
            <div
              key={label}
              className="p-4 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all duration-300 flex items-center gap-4"
            >
              <Icon className={`w-8 h-8 ${color}`} />
              <div>
                <div className="text-3xl font-bold text-white">{value}</div>
                <div className="text-xs text-gray-400 mt-1">{label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
