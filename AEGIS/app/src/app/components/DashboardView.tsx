import { useSensorData } from '../hooks/useSensorData';
import MetricsCards from './MetricsCards';
import GasAnalysis from './GasAnalysis';
import LiveCameraFeed from './LiveCameraFeed';
import LiveMap from './LiveMap';
import LiveAlerts from './LiveAlerts';
import AnomalyFeed from './AnomalyFeed';
import HealthScore from './HealthScore';
import FusionStatus from './FusionStatus';

export default function DashboardView() {
  const { sensor, ehs, live } = useSensorData(3000);

  const hasHighAlert = sensor.air_toxicity > 30 || sensor.mq2 > 25 || sensor.temperature > 38;

  return (
    <div className="h-full flex flex-col gap-4 pb-4">
      {/* High Alert Banner */}
      {hasHighAlert && (
        <div className="flex-shrink-0 rounded-2xl bg-gradient-to-r from-red-500/20 to-red-600/10 border border-red-500/40 p-4 shadow-lg shadow-red-500/20 animate-pulse">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 mt-1">
              <svg className="w-6 h-6 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd" />
              </svg>
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-bold text-red-300 mb-1">HIGH ALERT — CRITICAL SENSOR READING</h3>
              <p className="text-red-200 text-sm">
                {sensor.air_toxicity > 30 ? `Air toxicity at ${sensor.air_toxicity.toFixed(1)}% — ` : ''}
                {sensor.mq2 > 25 ? `MQ2 gas at ${sensor.mq2.toFixed(1)}% — ` : ''}
                {sensor.temperature > 38 ? `Temperature at ${sensor.temperature.toFixed(1)}°C` : ''}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Climate Parameters */}
      <div className="flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Climate Parameters</h2>
          {live && (
            <span className="flex items-center gap-1.5 text-xs text-green-400">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              Live Sensors · {sensor.timestamp}
            </span>
          )}
        </div>
        <MetricsCards sensor={sensor} />
      </div>

      {/* Gas Analysis + Live Map */}
      <div className="grid grid-cols-2 gap-4 flex-shrink-0">
        <GasAnalysis sensor={sensor} />
        <LiveMap />
      </div>

      {/* Camera Feed + Air Toxicity */}
      <div className="grid grid-cols-3 gap-4 flex-1">
        <div className="col-span-2 flex flex-col">
          <LiveCameraFeed />
        </div>

        {/* Air Toxicity — live */}
        <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300"
          style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
        >
          <div className="flex items-center gap-2 mb-6">
            <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8m0 8l-9-2m9 2l9-2" />
            </svg>
            <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Air Toxicity</h2>
          </div>

          <div className="space-y-4 flex flex-col justify-center">
            <div className="text-center">
              <div className={`text-4xl font-bold mb-2 ${
                sensor.air_toxicity > 40 ? 'text-red-400' :
                sensor.air_toxicity > 25 ? 'text-orange-400' : 'text-cyan-400'
              }`}>
                {sensor.air_toxicity.toFixed(1)}%
              </div>
              <div className="text-sm text-gray-400">Toxicity Level</div>
            </div>

            <div className="relative h-2 bg-white/10 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-cyan-400 to-red-500 rounded-full transition-all duration-700"
                style={{ width: `${Math.min(100, sensor.air_toxicity)}%` }} />
            </div>

            <div className={`mt-4 p-3 rounded-lg text-center text-xs ${
              sensor.air_toxicity > 40
                ? 'bg-red-500/10 border border-red-500/30 text-red-300'
                : sensor.air_toxicity > 25
                ? 'bg-orange-500/10 border border-orange-500/30 text-orange-300'
                : 'bg-cyan-500/10 border border-cyan-500/20 text-cyan-400'
            }`}>
              {sensor.air_toxicity > 40 ? '⚠ Critical — Evacuate area'
               : sensor.air_toxicity > 25 ? '⚠ Elevated — Monitor closely'
               : '✓ Within safe limits'}
            </div>

            {/* Extra sensors */}
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/5">
              <div className="text-center">
                <div className="text-xs text-gray-500">People</div>
                <div className={`text-lg font-bold ${sensor.people_detected > 0 ? 'text-yellow-400' : 'text-gray-500'}`}>
                  {sensor.people_detected}
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500">Event Rate</div>
                <div className={`text-lg font-bold ${sensor.event_rate > 2 ? 'text-orange-400' : 'text-gray-400'}`}>
                  {sensor.event_rate.toFixed(2)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sensor Fusion Decision Engine — full width */}
      <div className="flex-shrink-0">
        <FusionStatus />
      </div>

      {/* EHS Score — full width */}
      <div className="flex-shrink-0">
        <HealthScore ehs={ehs} sensor={sensor} live={live} />
      </div>

      {/* Live Alerts + Anomaly Feed */}
      <div className="grid grid-cols-2 gap-4 flex-shrink-0">
        <LiveAlerts sensor={sensor} />
        <AnomalyFeed />
      </div>
    </div>
  );
}
