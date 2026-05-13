import { useState } from 'react';
import { Toaster, toast } from 'sonner';
import Sidebar from './components/Sidebar';
import DashboardView from './components/DashboardView';
import ReportsView from './components/ReportsView';

const contacts: Record<string, { name: string; phone: string }> = {
  'Fire Department':         { name: 'Prithika', phone: '9108307690' },
  'EMS / Ambulance':         { name: 'Kovidh',   phone: '9284955662' },
  'Police Coordination':     { name: 'Likitha',  phone: '9740019608' },
  'Government Control Room': { name: 'Barath',   phone: '8778036377' },
};

type NotifyState = 'idle' | 'sending' | 'sent' | 'error';

export default function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [notifyState, setNotifyState] = useState<Record<string, NotifyState>>({});

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

  const sendSMS = async (alert: typeof alerts[0]) => {
    const contact = contacts[alert.agency];
    if (!contact) return;

    setNotifyState(prev => ({ ...prev, [alert.agency]: 'sending' }));
    try {
      const res = await fetch('/api/notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone: contact.phone,
          name: contact.name,
          agency: alert.agency,
          severity: alert.severity,
          status: alert.status,
          description: alert.description,
        }),
      });
      const data = await res.json();
      if (data.return) {
        setNotifyState(prev => ({ ...prev, [alert.agency]: 'sent' }));
        toast.success(`SMS sent to ${contact.name} (${contact.phone})`);
      } else {
        throw new Error(Array.isArray(data.message) ? data.message[0] : data.message);
      }
    } catch (e: any) {
      setNotifyState(prev => ({ ...prev, [alert.agency]: 'error' }));
      toast.error(`Failed: ${e.message}`);
    }
  };

  const notifyAll = () => {
    alerts.forEach(alert => {
      if (notifyState[alert.agency] !== 'sending' && notifyState[alert.agency] !== 'sent') {
        sendSMS(alert);
      }
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-950 to-black text-white overflow-hidden">
      <Toaster position="top-right" theme="dark" richColors />

      {/* VERDE Logo */}
      <div className="absolute top-6 left-8 z-50">
        <h1 className="text-3xl font-bold text-blue-400 drop-shadow-[0_0_10px_rgba(52,211,153,0.8)] tracking-wider">
          VERDE
        </h1>
      </div>

      <div className="flex h-screen">
        <Sidebar activeView={activeView} setActiveView={setActiveView} />

        <main className="flex-1 p-6 overflow-y-auto mt-16">
          {activeView === 'dashboard' && <DashboardView />}
          {activeView === 'reports' && <ReportsView />}
          {activeView === 'bbmp' && (
            <div className="space-y-6">
              <div className="rounded-3xl bg-[#061223]/90 border border-cyan-500/10 p-8 shadow-xl shadow-cyan-500/10">
                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                  <div>
                    <h3 className="text-2xl font-semibold text-cyan-300">Live Emergency Feed</h3>
                    <p className="text-gray-400 mt-2 max-w-2xl text-sm">
                      Real-time alerts from emergency agencies, survivor vitals, and hazard telemetry.
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {/* NOTIFY ALL */}
                    <button
                      onClick={notifyAll}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-red-600/40 to-orange-600/30 border border-red-500/50 text-red-300 text-sm font-bold tracking-wide hover:from-red-600/60 hover:to-orange-600/50 transition-all shadow-[0_0_15px_rgba(239,68,68,0.3)] hover:shadow-[0_0_20px_rgba(239,68,68,0.5)]"
                    >
                      ⚡ NOTIFY ALL
                    </button>
                    <div className="bg-red-500/10 border border-red-500/30 px-5 py-3 rounded-2xl">
                      <p className="text-red-300 text-xs uppercase tracking-wider">Current Threat Level</p>
                      <h4 className="text-2xl font-bold text-red-400">RED</h4>
                    </div>
                  </div>
                </div>

                {/* Alert Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                  {alerts.map((alert) => {
                    const contact = contacts[alert.agency];
                    const state = notifyState[alert.agency] ?? 'idle';

                    return (
                      <div
                        key={alert.agency}
                        className="bg-[#08132d]/90 border border-cyan-500/20 rounded-3xl p-6 shadow-xl hover:scale-[1.02] transition-all flex flex-col"
                      >
                        {/* Agency + Severity */}
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-cyan-300 font-semibold text-base leading-tight">{alert.agency}</span>
                          <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                            alert.severity === 'RED'
                              ? 'bg-red-500/20 text-red-300'
                              : alert.severity === 'BLACK'
                              ? 'bg-purple-500/20 text-purple-300'
                              : 'bg-yellow-500/20 text-yellow-300'
                          }`}>
                            {alert.severity}
                          </span>
                        </div>

                        {/* Status + Description */}
                        <div className="space-y-2 flex-1">
                          <p className="text-white text-xl font-bold">{alert.status}</p>
                          <p className="text-gray-400 text-sm leading-relaxed">{alert.description}</p>
                          <div className="pt-3 border-t border-cyan-500/10 text-xs text-gray-500">
                            Last Updated: {alert.last}
                          </div>
                        </div>

                        {/* Contact label */}
                        <div className="mt-4 px-1 text-xs text-gray-500 flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-cyan-500/60 inline-block" />
                          Notify: <span className="text-cyan-400 font-medium">{contact?.name}</span>
                          <span className="text-gray-600">·</span>
                          <span className="font-mono text-gray-500">{contact?.phone}</span>
                        </div>

                        {/* Action buttons */}
                        <div className="flex gap-2 mt-3">
                          {/* SMS button */}
                          <button
                            onClick={() => sendSMS(alert)}
                            disabled={state === 'sending' || state === 'sent'}
                            className={`flex-1 text-xs py-2 px-3 rounded-lg border font-semibold transition-all ${
                              state === 'sent'
                                ? 'bg-green-500/20 border-green-500/40 text-green-400 cursor-default'
                                : state === 'error'
                                ? 'bg-red-500/20 border-red-500/40 text-red-400'
                                : state === 'sending'
                                ? 'bg-cyan-500/10 border-cyan-500/20 text-cyan-500 cursor-wait'
                                : 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/30'
                            }`}
                          >
                            {state === 'sending' ? '⏳ Sending...'
                              : state === 'sent' ? '✓ SMS Sent'
                              : state === 'error' ? '✗ Retry SMS'
                              : '📨 Send SMS'}
                          </button>

                          {/* Call button */}
                          <a
                            href={`tel:+91${contact?.phone}`}
                            className="text-xs py-2 px-3 rounded-lg border bg-green-500/20 border-green-500/40 text-green-300 hover:bg-green-500/30 transition-all font-semibold"
                          >
                            📞 Call
                          </a>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
