export default function VerdeEmergencyHub() {
  const alerts = [
    {
      agency: 'Fire Department',
      status: 'ACTIVE',
      last: '2 min ago',
      severity: 'RED',
      description: 'High temperature and smoke detected near Sector B-12.',
    },
    {
      agency: 'EMS / Ambulance',
      status: 'EN ROUTE',
      last: '1 min ago',
      severity: 'RED',
      description: 'Critical survivor vitals detected. Immediate assistance required.',
    },
    {
      agency: 'Police Coordination',
      status: 'MONITORING',
      last: '3 min ago',
      severity: 'YELLOW',
      description: 'Crowd movement detected near hazardous perimeter.',
    },
    {
      agency: 'Government Control Room',
      status: 'ESCALATED',
      last: 'JUST NOW',
      severity: 'BLACK',
      description: 'Full disaster escalation report transmitted successfully.',
    },
  ];

  const climateMetrics = [
    {
      id: 'temperature',
      label: 'Temperature',
      value: '28.5',
      unit: '°C',
    },
    {
      id: 'humidity',
      label: 'Humidity',
      value: '65',
      unit: '%',
    },
    {
      id: 'pressure',
      label: 'Pressure',
      value: '1013',
      unit: 'hPa',
    },
  ];

  // Check if there are any RED severity alerts
  const hasHighAlert = alerts.some((alert) => alert.severity === 'RED');
  const highAlertDescription = alerts.find((alert) => alert.severity === 'RED')?.description;

  return (
    <div className="space-y-8">
      {/* High Alert Banner - Only shown if there's a RED severity alert */}
      {hasHighAlert && (
        <section className="rounded-3xl bg-gradient-to-r from-red-500/20 to-red-600/10 border border-red-500/40 p-6 shadow-xl shadow-red-500/20 animate-pulse">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 mt-1">
              <svg className="w-8 h-8 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="flex-1">
              <h3 className="text-xl font-bold text-red-300 mb-2">🚨 HIGH ALERT - CRITICAL SITUATION</h3>
              <p className="text-red-200 text-sm leading-relaxed">{highAlertDescription}</p>
            </div>
          </div>
        </section>
      )}

      {/* Criticality Status - Only shown if there's a high alert */}
      {hasHighAlert && (
        <section className="rounded-3xl bg-[#061223]/90 border border-cyan-500/10 p-8 shadow-xl shadow-cyan-500/10">
          <h2 className="text-xl font-bold text-cyan-400 mb-6 tracking-wide">Criticality Status</h2>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'HIGH', color: 'red', isActive: true },
              { label: 'MEDIUM', color: 'yellow', isActive: false },
              { label: 'LOW', color: 'cyan', isActive: false },
            ].map((level) => (
              <div
                key={level.label}
                className={`relative p-6 rounded-2xl backdrop-blur-xl border transition-all duration-300 ${
                  level.isActive
                    ? `bg-gradient-to-br from-${level.color}-500/20 to-${level.color}-600/10 border-${level.color}-500 scale-105 shadow-[0_0_30px_rgba(${
                        level.color === 'red'
                          ? '239, 68, 68'
                          : level.color === 'yellow'
                          ? '234, 179, 8'
                          : '6, 182, 212'
                      }, 0.6)]`
                    : `bg-gradient-to-br from-${level.color}-500/10 to-${level.color}-600/5 border-${level.color}-500/30 opacity-60`
                }`}
              >
                <div className="flex flex-col items-center gap-3">
                  <div
                    className={`w-12 h-12 ${
                      level.color === 'red'
                        ? 'text-red-400'
                        : level.color === 'yellow'
                        ? 'text-yellow-400'
                        : 'text-cyan-400'
                    }`}
                  >
                    {level.color === 'red' && '⚠️'}
                    {level.color === 'yellow' && '⚡'}
                    {level.color === 'cyan' && '✓'}
                  </div>
                  <span
                    className={`text-2xl font-bold tracking-wider ${
                      level.color === 'red'
                        ? 'text-red-400'
                        : level.color === 'yellow'
                        ? 'text-yellow-400'
                        : 'text-cyan-400'
                    }`}
                  >
                    {level.label}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Climate Parameters - Always visible */}
      <section className="rounded-3xl bg-[#061223]/90 border border-cyan-500/10 p-8 shadow-xl shadow-cyan-500/10">
        <h2 className="text-xl font-bold text-cyan-400 mb-6 tracking-wide">Climate Parameters</h2>
        <div className="grid grid-cols-3 gap-6">
          {climateMetrics.map((metric) => (
            <div
              key={metric.id}
              className="relative p-6 rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.4)] transition-all duration-300 shadow-[0_0_20px_rgba(6,182,212,0.3)]"
            >
              <div className="flex flex-col items-center gap-4">
                <svg className="w-12 h-12 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {metric.id === 'temperature' && (
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                    />
                  )}
                  {metric.id === 'humidity' && (
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  )}
                  {metric.id === 'pressure' && (
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                    />
                  )}
                </svg>
                <div className="text-center">
                  <p className="text-3xl font-bold text-white">
                    {metric.value}
                    <span className="text-lg">{metric.unit}</span>
                  </p>
                  <p className="text-gray-400 text-sm mt-2">{metric.label}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Live Emergency Feed */}
      <section className="rounded-3xl bg-[#061223]/90 border border-cyan-500/10 p-8 shadow-xl shadow-cyan-500/10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h3 className="text-2xl font-semibold text-cyan-300">Live Emergency Feed</h3>
            <p className="text-gray-400 mt-2 max-w-2xl text-sm">
              Real-time alerts from emergency agencies, survivor vitals, and hazard telemetry.
            </p>
          </div>
          <div className="bg-red-500/10 border border-red-500/30 px-5 py-3 rounded-2xl">
            <p className="text-red-300 text-xs uppercase tracking-wider">Current Threat Level</p>
            <h4 className="text-2xl font-bold text-red-400">RED</h4>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
          {alerts.map((alert, index) => (
            <div
              key={index}
              className="bg-[#08132d]/90 border border-cyan-500/20 rounded-3xl p-6 shadow-xl hover:scale-[1.02] transition-all"
            >
              <div className="flex items-center justify-between mb-4">
                <span className="text-cyan-300 font-semibold text-lg">{alert.agency}</span>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-bold ${
                    alert.severity === 'RED'
                      ? 'bg-red-500/20 text-red-300'
                      : alert.severity === 'BLACK'
                      ? 'bg-purple-500/20 text-purple-300'
                      : 'bg-yellow-500/20 text-yellow-300'
                  }`}
                >
                  {alert.severity}
                </span>
              </div>

              <div className="space-y-3">
                <p className="text-white text-xl font-bold">{alert.status}</p>
                <p className="text-gray-400 text-sm leading-relaxed">{alert.description}</p>
                <div className="pt-4 border-t border-cyan-500/10 text-sm text-gray-500">
                  Last Updated: {alert.last}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
