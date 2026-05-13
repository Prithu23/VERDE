import { Camera, Users, Boxes, Droplet } from 'lucide-react';
import { motion } from 'motion/react';

export default function LiveCameraFeed() {
  const detections = [
    { label: 'People', value: 3, icon: Users, color: 'text-cyan-400' },
    { label: 'Rubble Objects', value: 12, icon: Boxes, color: 'text-cyan-400' },
    { label: 'Oil Spills', value: 1, icon: Droplet, color: 'text-cyan-400' },
  ];

  return (
    <div className="h-full rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300 flex flex-col"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      <div className="flex items-center gap-2 mb-4">
        <Camera className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Live Camera Feed</h2>
      </div>

      <div className="flex gap-4 flex-1">
        {/* Camera Feed Placeholder */}
        <div className="relative flex-1 bg-gradient-to-br from-gray-900 to-black rounded-xl border border-cyan-500/30 overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <Camera className="w-16 h-16 text-cyan-400/50 mx-auto mb-2" />
            <p className="text-cyan-400/70 text-sm">CCTV Feed Active</p>
          </div>
        </div>

        {/* Timestamp Overlay */}
        <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-sm px-3 py-1 rounded text-xs text-cyan-400 font-mono border border-cyan-500/30">
          13 MAY 2026 | 09:15:32
        </div>

        {/* Recording Indicator */}
        <div className="absolute top-3 right-3 flex items-center gap-2 bg-black/70 backdrop-blur-sm px-3 py-1 rounded border border-red-500/30">
          <motion.div
            className="w-2 h-2 bg-red-500 rounded-full"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="text-xs text-red-400 font-medium">REC</span>
        </div>

        {/* AI Detection Overlays */}
        <div className="absolute bottom-3 left-3 right-3 flex gap-2">
          <div className="bg-cyan-500/20 backdrop-blur-sm px-2 py-1 rounded text-xs text-cyan-400 border border-cyan-500/50">
            AI Detection: Active
          </div>
        </div>
        </div>

        {/* Detection Stats */}
        <div className="flex flex-col gap-3 w-64">
          {detections.map((detection) => {
            const Icon = detection.icon;
            return (
              <div
                key={detection.label}
                className="p-4 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all duration-300 flex items-center gap-4"
              >
                <Icon className={`w-8 h-8 ${detection.color}`} />
                <div>
                  <div className="text-3xl font-bold text-white">{detection.value}</div>
                  <div className="text-xs text-gray-400 mt-1">{detection.label}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
