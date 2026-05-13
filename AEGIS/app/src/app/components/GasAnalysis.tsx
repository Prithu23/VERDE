import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { Activity } from 'lucide-react';
import type { SensorReading } from '../hooks/useSensorData';

interface Props {
  sensor: SensorReading;
}

export default function GasAnalysis({ sensor }: Props) {
  const data = [
    { name: 'MQ2 - Flammable', value: Math.max(0.1, sensor.mq2),  color: '#ef4444' },
    { name: 'MQ4 - Methane',   value: Math.max(0.1, sensor.mq4),  color: '#06b6d4' },
  ];

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-black/90 backdrop-blur-xl border border-cyan-400/50 rounded-lg p-3">
          <p className="text-white font-medium">{payload[0].name}</p>
          <p className="text-cyan-400">{payload[0].value.toFixed(1)}%</p>
        </div>
      );
    }
    return null;
  };

  const mq2Warn = sensor.mq2 > 20;
  const mq4Warn = sensor.mq4 > 15;

  return (
    <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300"
      style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
    >
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">Gas Analysis</h2>
        {(mq2Warn || mq4Warn) && (
          <span className="ml-auto text-xs text-orange-400 font-bold animate-pulse">⚠ ELEVATED</span>
        )}
      </div>

      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%" cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${name.split(' - ')[0]}: ${(percent * 100).toFixed(1)}%`}
              outerRadius={100} innerRadius={50}
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
      </div>

      <div className="grid grid-cols-2 gap-3 mt-4">
        {data.map((sensor_item) => {
          const isWarn = (sensor_item.name.includes('MQ2') && mq2Warn) ||
                         (sensor_item.name.includes('MQ4') && mq4Warn);
          return (
            <div key={sensor_item.name}
              className={`text-center p-3 rounded-lg border ${
                isWarn ? 'bg-orange-500/10 border-orange-500/30' : 'bg-white/5 border-white/10'
              }`}
            >
              <div className="text-2xl font-bold" style={{ color: sensor_item.color }}>
                {sensor_item.value.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {sensor_item.name.split(' - ')[1]}
              </div>
              {isWarn && <div className="text-[10px] text-orange-400 mt-0.5">ELEVATED</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
