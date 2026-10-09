import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { Activity } from 'lucide-react';
import type { SensorReading } from '../hooks/useSensorData';

interface Props {
  sensor: SensorReading;
}

// Gas values are the percent rise over each sensor's clean-air level
// (0 = clean air, 100 = double). This panel only shows them; whether a rise
// is a hazard is decided by the trained fusion model.
export default function GasAnalysis({ sensor }: Props) {
  const miss = (k: string) => sensor.missing.includes(k);
  const noGas = miss('mq2') && miss('mq4') && miss('mq135');
  const calibrating = !!sensor.gas_calibrating;
  const data = [
    { key: 'mq2',   name: 'MQ2 - Flammable',   value: Math.max(0.1, sensor.mq2),   color: '#ef4444' },
    { key: 'mq4',   name: 'MQ4 - Methane',     value: Math.max(0.1, sensor.mq4),   color: '#06b6d4' },
    { key: 'mq135', name: 'MQ135 - Air quality', value: Math.max(0.1, sensor.mq135), color: '#f59e0b' },
  ];

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-black/90 backdrop-blur-xl border border-cyan-400/50 rounded-lg p-3">
          <p className="text-white font-medium">{payload[0].name}</p>
          <p className="text-cyan-400">+{payload[0].value.toFixed(0)}% over clean air</p>
        </div>
      );
    }
    return null;
  };

  const mq2Warn = false, mq4Warn = false, mq135Warn = false, mq2Crit = false;

  return (
    <div
      className={`rounded-2xl bg-black/40 backdrop-blur-xl border p-6 transition-all duration-300 ${
        mq2Crit
          ? 'border-red-500/60 shadow-[0_0_30px_rgba(239,68,68,0.5)] animate-pulse'
          : 'border-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)]'
      }`}
      style={{ boxShadow: mq2Crit ? '0 0 30px rgba(239,68,68,0.4)' : '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Gas Analysis</h2>
        <span className="text-[10px] text-gray-500">% rise over each sensor's clean-air level</span>
        {mq2Crit && (
          <span className="ml-auto text-xs text-red-400 font-bold animate-pulse">🔴 MQ2 CRITICAL</span>
        )}
        {!mq2Crit && (mq2Warn || mq4Warn || mq135Warn) && (
          <span className="ml-auto text-xs text-orange-400 font-bold animate-pulse">⚠ ELEVATED</span>
        )}
      </div>

      {(noGas || calibrating) && (
        <div className="h-72 flex flex-col items-center justify-center gap-2 text-center">
          <Activity className={`w-8 h-8 ${calibrating ? 'text-blue-400 animate-pulse' : 'text-gray-700'}`} />
          <p className="text-sm text-gray-400">
            {calibrating ? 'Learning each gas sensor\'s clean-air baseline…' : 'No gas sensor data from the board'}
          </p>
          {calibrating && <p className="text-xs text-gray-600">Takes about 30 readings. Keep the rover in clean air.</p>}
        </div>
      )}

      {!(noGas || calibrating) && <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%" cy="50%"
              labelLine={false}
              label={({ name, value }) => (Number(value) > 0.5 ? `${name.split(' - ')[0]}: +${Number(value).toFixed(0)}%` : '')}
              outerRadius={90} innerRadius={45}
              fill="#8884d8" dataKey="value"
              animationBegin={0} animationDuration={800}
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} stroke={entry.color}
                  strokeWidth={2} style={{ filter: `drop-shadow(0 0 8px ${entry.color})` }} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend verticalAlign="bottom" height={36}
              formatter={(value) => <span className="text-gray-300 text-sm">{value}</span>} />
          </PieChart>
        </ResponsiveContainer>
      </div>}

      <div className="grid grid-cols-3 gap-2 mt-2">
        {data.map((item) => {
          const isWarn = (item.name.includes('MQ2')   && mq2Warn)   ||
                         (item.name.includes('MQ4')   && mq4Warn)   ||
                         (item.name.includes('MQ135') && mq135Warn);
          const isCrit = item.name.includes('MQ2') && mq2Crit;
          return (
            <div key={item.name}
              className={`text-center p-3 rounded-lg border ${
                isCrit ? 'bg-red-500/15 border-red-500/50' :
                isWarn ? 'bg-orange-500/10 border-orange-500/30' :
                         'bg-white/5 border-white/10'
              }`}
            >
              <div className="text-xl font-bold" style={{ color: miss(item.key) ? '#4b5563' : item.color }}>
                {miss(item.key) ? '—' : `+${(sensor as any)[item.key].toFixed(0)}%`}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {item.name.split(' - ')[1]}
              </div>
              {isCrit && <div className="text-[10px] text-red-400 mt-0.5 font-bold">CRITICAL</div>}
              {!isCrit && isWarn && <div className="text-[10px] text-orange-400 mt-0.5">ELEVATED</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
