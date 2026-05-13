import { useState } from 'react';
import { motion } from 'motion/react';
import { AlertTriangle, AlertCircle, CheckCircle } from 'lucide-react';

export default function CriticalityStatus() {
  const [activeLevel, setActiveLevel] = useState<'high' | 'medium' | 'low'>('medium');

  const levels = [
    {
      id: 'high' as const,
      label: 'HIGH',
      color: 'red',
      icon: AlertTriangle,
      glowColor: 'rgba(239, 68, 68, 0.6)',
      borderColor: 'border-red-500',
      bgGradient: 'from-red-500/20 to-red-600/10',
      textColor: 'text-red-400',
    },
    {
      id: 'medium' as const,
      label: 'MEDIUM',
      color: 'yellow',
      icon: AlertCircle,
      glowColor: 'rgba(234, 179, 8, 0.5)',
      borderColor: 'border-yellow-500',
      bgGradient: 'from-yellow-500/20 to-yellow-600/10',
      textColor: 'text-yellow-400',
    },
    {
      id: 'low' as const,
      label: 'LOW',
      color: 'cyan',
      icon: CheckCircle,
      glowColor: 'rgba(6, 182, 212, 0.5)',
      borderColor: 'border-cyan-500',
      bgGradient: 'from-cyan-500/20 to-cyan-600/10',
      textColor: 'text-cyan-400',
    },
  ];

  return (
    <div>
      <h2 className="text-xl font-bold text-cyan-400 mb-4 tracking-wide">Criticality Status</h2>
      <div className="grid grid-cols-3 gap-4">
        {levels.map((level) => {
          const Icon = level.icon;
          const isActive = activeLevel === level.id;

          return (
            <motion.button
              key={level.id}
              onClick={() => setActiveLevel(level.id)}
              className={`relative p-6 rounded-2xl bg-gradient-to-br ${level.bgGradient} backdrop-blur-xl border ${level.borderColor}/50 transition-all duration-300 ${
                isActive ? 'scale-105' : 'opacity-60 hover:opacity-80 hover:shadow-[0_0_20px_rgba(6,182,212,0.3)]'
              }`}
              style={{
                boxShadow: isActive ? `0 0 30px ${level.glowColor}` : undefined,
              }}
              animate={{
                scale: isActive ? [1, 1.02, 1] : 1,
              }}
              transition={{
                duration: 2,
                repeat: isActive ? Infinity : 0,
                ease: 'easeInOut',
              }}
            >
              <div className="flex flex-col items-center gap-3">
                <motion.div
                  animate={{
                    scale: isActive ? [1, 1.1, 1] : 1,
                  }}
                  transition={{
                    duration: 1.5,
                    repeat: isActive ? Infinity : 0,
                  }}
                >
                  <Icon className={`w-12 h-12 ${level.textColor}`} />
                </motion.div>
                <span className={`text-2xl font-bold ${level.textColor} tracking-wider`}>
                  {level.label}
                </span>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
