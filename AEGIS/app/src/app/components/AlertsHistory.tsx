import { Clock, AlertTriangle } from 'lucide-react';
import { motion } from 'motion/react';

export default function AlertsHistory() {
  const alerts = [
    {
      id: 1,
      date: '13 May 2026',
      time: '09:15',
      type: 'Gas Leak',
      severity: 'high',
      color: 'red',
    },
    {
      id: 2,
      date: '13 May 2026',
      time: '08:42',
      type: 'Rubble Detected',
      severity: 'medium',
      color: 'orange',
    },
    {
      id: 3,
      date: '13 May 2026',
      time: '07:30',
      type: 'Human Presence',
      severity: 'low',
      color: 'green',
    },
    {
      id: 4,
      date: '12 May 2026',
      time: '23:18',
      type: 'Oil Spill',
      severity: 'high',
      color: 'red',
    },
    {
      id: 5,
      date: '12 May 2026',
      time: '22:05',
      type: 'Temperature Spike',
      severity: 'medium',
      color: 'orange',
    },
    {
      id: 6,
      date: '12 May 2026',
      time: '21:33',
      type: 'Low Visibility',
      severity: 'low',
      color: 'green',
    },
    {
      id: 7,
      date: '12 May 2026',
      time: '20:12',
      type: 'Structural Damage',
      severity: 'high',
      color: 'red',
    },
    {
      id: 8,
      date: '12 May 2026',
      time: '19:45',
      type: 'Air Quality Alert',
      severity: 'medium',
      color: 'orange',
    },
  ];

  const getSeverityColor = (color: string) => {
    switch (color) {
      case 'red':
        return 'bg-red-500';
      case 'orange':
        return 'bg-orange-500';
      case 'green':
        return 'bg-green-500';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <div className="h-full rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6 flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <Clock className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-bold text-cyan-400 tracking-wide">History of Alerts</h2>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
        {alerts.map((alert, index) => (
          <motion.div
            key={alert.id}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1 }}
            className="p-3 rounded-lg bg-white/5 border border-white/10 hover:border-cyan-400/50 transition-all duration-300 hover:bg-white/10"
          >
            <div className="flex items-start gap-3">
              <div className={`w-2 h-2 rounded-full ${getSeverityColor(alert.color)} mt-2 flex-shrink-0`}
                style={{ boxShadow: `0 0 8px ${alert.color === 'red' ? '#ef4444' : alert.color === 'orange' ? '#f97316' : '#22c55e'}` }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-white font-medium text-sm truncate">{alert.type}</div>
                <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                  <span>{alert.date}</span>
                  <span>•</span>
                  <span>{alert.time}</span>
                </div>
              </div>
              <AlertTriangle className={`w-4 h-4 flex-shrink-0 ${
                alert.color === 'red' ? 'text-red-400' :
                alert.color === 'orange' ? 'text-orange-400' :
                'text-green-400'
              }`} />
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
