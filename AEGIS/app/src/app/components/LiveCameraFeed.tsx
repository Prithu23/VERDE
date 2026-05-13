import { useState, useEffect } from 'react'
import { Camera, Boxes, Droplet, Users, WifiOff, Play, Square, RefreshCw } from 'lucide-react'
import { motion } from 'motion/react'
import { useMissionLog } from '../hooks/useMissionLog'
import { useDetectionState } from '../hooks/useDetectionState'

// detect.py annotated MJPEG (laptop or ESP32 depending on --source)
const VERDE_CAM_STREAM = 'http://localhost:8765'
// ESP32-CAM raw stream — try port-81 MJPEG then port-80 snapshot
const ESP32_STREAM     = 'http://10.97.202.27:81/stream'
const ESP32_CAPTURE    = 'http://10.97.202.27/capture'

type Source      = 'laptop' | 'esp32'
type EspMode     = 'stream' | 'snapshot' | 'offline'
type LaptopStatus = 'connecting' | 'live' | 'offline'

export default function LiveCameraFeed() {
  const { totalEvents, lastEntry } = useMissionLog()
  const detection = useDetectionState()          // per-frame live counts from detect.py
  const people = detection.people
  const damage = detection.rubble
  const spills = detection.spills

  const [running, setRunning]       = useState(true)
  const [source, setSource]         = useState<Source>('laptop')

  // LAPTOP CAM (detect.py MJPEG stream)
  const [laptopStatus, setLaptopStatus] = useState<LaptopStatus>('connecting')

  // ESP32 fallback state
  const [espMode, setEspMode]   = useState<EspMode>('stream')
  const [snapSrc, setSnapSrc]   = useState('')

  // Reset laptop status when toggling source/running
  useEffect(() => {
    if (source === 'laptop' && running) setLaptopStatus('connecting')
  }, [source, running])

  // ESP32 snapshot polling
  useEffect(() => {
    if (!running || source !== 'esp32' || espMode !== 'snapshot') return
    const refresh = () => setSnapSrc(`${ESP32_CAPTURE}?t=${Date.now()}`)
    refresh()
    const id = setInterval(refresh, 800)
    return () => clearInterval(id)
  }, [running, source, espMode])

  // ESP32 offline auto-retry
  useEffect(() => {
    if (espMode !== 'offline') return
    const id = setTimeout(() => setEspMode('stream'), 10_000)
    return () => clearTimeout(id)
  }, [espMode])

  // Laptop CAM offline auto-retry
  useEffect(() => {
    if (laptopStatus !== 'offline') return
    const id = setTimeout(() => setLaptopStatus('connecting'), 8_000)
    return () => clearTimeout(id)
  }, [laptopStatus])

  // ── Status label ────────────────────────────────────────────────────────
  let statusLabel: string
  let statusCls: string
  if (!running) {
    statusLabel = 'STOPPED'; statusCls = 'text-gray-400 border-gray-500/40'
  } else if (source === 'laptop') {
    const map = { connecting:'CONNECTING', live:'LIVE', offline:'OFFLINE' }
    const cls = { connecting:'text-yellow-400 border-yellow-500/40', live:'text-green-400 border-green-500/40', offline:'text-red-400 border-red-500/40' }
    statusLabel = map[laptopStatus]; statusCls = cls[laptopStatus]
  } else {
    const map: Record<EspMode,string> = { stream:'LIVE', snapshot:'SNAPSHOT', offline:'OFFLINE' }
    const cls: Record<EspMode,string> = { stream:'text-green-400 border-green-500/40', snapshot:'text-cyan-400 border-cyan-500/40', offline:'text-red-400 border-red-500/40' }
    statusLabel = map[espMode]; statusCls = cls[espMode]
  }

  const showRec = running && (
    (source === 'laptop' && laptopStatus === 'live') ||
    (source === 'esp32' && espMode !== 'offline')
  )

  const timestamp = lastEntry?.time ?? new Date().toLocaleString()

  const detections = [
    { label: 'People',    value: people, Icon: Users,   color: 'text-green-400'  },
    { label: 'Rubble',    value: damage, Icon: Boxes,   color: 'text-red-400'    },
    { label: 'Oil Spills',value: spills, Icon: Droplet, color: 'text-yellow-400' },
  ]
  const fpsLabel = detection.fps > 0 ? `${detection.fps} fps · ${detection.source}` : null

  return (
    <div
      className="h-full rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300 flex flex-col"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      {/* ── Header ── */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Camera className="w-5 h-5 text-cyan-400 flex-shrink-0" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Camera Feed</h2>
        <span className={`text-xs font-mono px-2 py-0.5 rounded border ${statusCls}`}>
          {statusLabel}
        </span>

        <div className="ml-auto flex items-center gap-2">
          {/* Source toggle */}
          <div className="flex rounded-lg border border-white/10 overflow-hidden text-xs">
            <button
              onClick={() => setSource('laptop')}
              className={`px-3 py-1.5 transition-colors ${source === 'laptop' ? 'bg-cyan-500/20 text-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
            >
              LAPTOP CAM
            </button>
            <button
              onClick={() => setSource('esp32')}
              className={`px-3 py-1.5 transition-colors ${source === 'esp32' ? 'bg-cyan-500/20 text-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
            >
              ESP32
            </button>
          </div>

          {/* Start / Stop */}
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

          {/* ── LAPTOP CAM (detect.py MJPEG @ :8765) ── */}
          {running && source === 'laptop' && laptopStatus !== 'offline' && (
            <img
              key={laptopStatus}
              src={VERDE_CAM_STREAM}
              alt="Laptop annotated feed"
              className="absolute inset-0 w-full h-full object-cover"
              onLoad={() => setLaptopStatus('live')}
              onError={() => setLaptopStatus('offline')}
            />
          )}
          {running && source === 'laptop' && laptopStatus === 'offline' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <WifiOff className="w-12 h-12 text-red-400/50 mx-auto mb-2" />
                <p className="text-red-400/70 text-sm font-medium">detect.py not running</p>
                <p className="text-gray-500 text-xs mt-1">Run: python detect.py</p>
                <button
                  onClick={() => setLaptopStatus('connecting')}
                  className="mt-3 flex items-center gap-1.5 mx-auto px-3 py-1.5 rounded-lg text-xs border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                >
                  <RefreshCw className="w-3 h-3" /> Retry
                </button>
              </div>
            </div>
          )}

          {/* ── ESP32 MJPEG stream ── */}
          {running && source === 'esp32' && espMode === 'stream' && (
            <img
              src={ESP32_STREAM}
              alt="ESP32-CAM"
              className="absolute inset-0 w-full h-full object-cover"
              onError={() => setEspMode('snapshot')}
            />
          )}

          {/* ── ESP32 snapshot fallback ── */}
          {running && source === 'esp32' && espMode === 'snapshot' && snapSrc && (
            <img
              src={snapSrc}
              alt="ESP32-CAM snapshot"
              className="absolute inset-0 w-full h-full object-cover"
              onError={() => setEspMode('offline')}
            />
          )}

          {/* ── ESP32 offline ── */}
          {running && source === 'esp32' && espMode === 'offline' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <WifiOff className="w-12 h-12 text-red-400/50 mx-auto mb-2" />
                <p className="text-red-400/70 text-sm">ESP32-CAM Offline</p>
                <p className="text-gray-500 text-xs mt-0.5">Retrying in 10 s…</p>
              </div>
            </div>
          )}

          {/* ── Overlays ── */}
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
