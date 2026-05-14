import { Thermometer, Droplets, Gauge, Waves, RotateCcw } from 'lucide-react';
import { motion } from 'motion/react';
import type { SensorReading } from '../hooks/useSensorData';

interface Props {
  sensor: SensorReading;
}

export default function MetricsCards({ sensor }: Props) {
  const metrics = [
    {
      id: 'temperature',
      label: 'Temperature',
      value: Number(sensor.temperature ?? 0).toFixed(1),
      unit: '°C',
      icon: Thermometer,
      colorStart: '#06b6d4',
      colorEnd: '#3b82f6',
      glowColor: 'rgba(6, 182, 212, 0.3)',
      percentage: Math.min(100, Math.max(0, ((sensor.temperature - 10) / 50) * 100)),
      warn: sensor.temperature > 35,
    },
    {
      id: 'humidity',
      label: 'Humidity',
      value: Number(sensor.humidity ?? 0).toFixed(0),
      unit: '%',
      icon: Droplets,
      colorStart: '#06b6d4',
      colorEnd: '#0891b2',
      glowColor: 'rgba(6, 182, 212, 0.3)',
      percentage: sensor.humidity,
      warn: sensor.humidity < 35 || sensor.humidity > 80,
    },
    {
      id: 'pressure',
      label: 'Pressure',
      value: Number(sensor.pressure ?? 0).toFixed(1),
      unit: 'hPa',
      icon: Gauge,
      colorStart: '#0891b2',
      colorEnd: '#0e7490',
      glowColor: 'rgba(8, 145, 178, 0.3)',
      percentage: Math.min(100, Math.max(0, ((sensor.pressure - 980) / 60) * 100)),
      warn: false,
    },
  ];

  const maxTilt = Math.max(Math.abs(sensor.roll), Math.abs(sensor.pitch));
  const tiltWarn = maxTilt > 15;

  return (
    <div className="space-y-4">
      {/* ── Row 1: Climate gauges ── */}
      <div className="grid grid-cols-3 gap-4">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          const circumference = 2 * Math.PI * 45;
          const offset = circumference - (metric.percentage / 100) * circumference;

          return (
            <div
              key={metric.id}
              className={`relative p-6 rounded-2xl bg-black/40 backdrop-blur-xl border transition-all duration-300
                ${metric.warn
                  ? 'border-orange-500/50 hover:border-orange-400/70 hover:shadow-[0_0_30px_rgba(249,115,22,0.4)]'
                  : 'border-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)]'
                }`}
              style={{ boxShadow: `0 0 20px ${metric.warn ? 'rgba(249,115,22,0.2)' : metric.glowColor}` }}
            >
              {metric.warn && (
                <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
              )}
              <div className="flex flex-col items-center gap-4">
                <div className="relative w-32 h-32">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle cx="64" cy="64" r="45" fill="none"
                      stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
                    <motion.circle
                      cx="64" cy="64" r="45" fill="none"
                      stroke={metric.warn ? '#f97316' : `url(#gradient-${metric.id})`}
                      strokeWidth="8" strokeLinecap="round"
                      strokeDasharray={circumference}
                      animate={{ strokeDashoffset: offset }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    />
                    <defs>
                      <linearGradient id={`gradient-${metric.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor={metric.colorStart} />
                        <stop offset="100%" stopColor={metric.colorEnd} />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Icon className={`w-10 h-10 ${metric.warn ? 'text-orange-400' : 'text-white/80'}`} />
                  </div>
                </div>
                <div className="text-center">
                  <div className={`text-4xl font-bold bg-gradient-to-r bg-clip-text text-transparent
                    ${metric.warn ? 'from-orange-400 to-red-400' : 'from-white to-gray-300'}`}>
                    {metric.value}
                    <span className="text-2xl ml-1">{metric.unit}</span>
                  </div>
                  <div className="text-gray-400 mt-1 font-medium tracking-wide">{metric.label}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Row 2: Water sensor + MPU Gyro ── */}
      <div className="grid grid-cols-2 gap-4">
        {/* Water sensor */}
        <div
          className={`relative p-5 rounded-2xl backdrop-blur-xl border transition-all duration-300 ${
            sensor.water_detected
              ? 'bg-blue-500/10 border-blue-500/50 shadow-[0_0_25px_rgba(59,130,246,0.4)]'
              : 'bg-black/40 border-white/10 hover:border-cyan-400/30'
          }`}
        >
          {sensor.water_detected && (
            <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
          )}
          <div className="flex items-center gap-4">
            <Waves className={`w-10 h-10 flex-shrink-0 ${sensor.water_detected ? 'text-blue-400' : 'text-gray-600'}`} />
            <div>
              <div className={`text-2xl font-bold ${sensor.water_detected ? 'text-blue-300 animate-pulse' : 'text-gray-500'}`}>
                {sensor.water_detected ? 'DETECTED' : 'CLEAR'}
              </div>
              <div className="text-sm text-gray-400 mt-0.5">Water Sensor</div>
              {sensor.water_detected && (
                <div className="text-xs text-blue-400 mt-1 font-medium">⚠ Flood / Electrical Risk</div>
              )}
            </div>
          </div>
        </div>

        {/* MPU Gyro / Tilt */}
        <div
          className={`p-5 rounded-2xl bg-black/40 backdrop-blur-xl border transition-all duration-300 ${
            tiltWarn
              ? 'border-orange-500/50 hover:border-orange-400/70'
              : 'border-white/10 hover:border-cyan-400/30'
          }`}
        >
          <div className="flex items-center gap-4">
            <RotateCcw className={`w-10 h-10 flex-shrink-0 ${tiltWarn ? 'text-orange-400' : 'text-cyan-400/60'}`} />
            <div className="flex-1">
              <div className="text-sm text-gray-400 mb-2">MPU Gyro · Tilt</div>
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  { label: 'Roll',  val: sensor.roll },
                  { label: 'Pitch', val: sensor.pitch },
                  { label: 'Yaw',   val: sensor.yaw },
                ].map(({ label, val }) => {
                  const abs = Math.abs(val);
                  const color = abs > 30 ? 'text-red-400' : abs > 15 ? 'text-orange-400' : 'text-cyan-400';
                  return (
                    <div key={label}>
                      <div className="text-xs text-gray-500">{label}</div>
                      <div className={`text-base font-mono font-bold ${color}`}>
                        {Number(val ?? 0).toFixed(1)}°
                      </div>
                    </div>
                  );
                })}
              </div>
              {tiltWarn && (
                <div className="text-xs text-orange-400 mt-1 font-medium text-center">
                  ⚠ Significant tilt detected
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
