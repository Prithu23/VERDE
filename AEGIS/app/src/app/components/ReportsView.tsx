import { FileText, Download, Clock, MapPin, AlertTriangle, Users, Layers, Waves, Mic } from 'lucide-react';
import { motion } from 'motion/react';
import { useState, useEffect } from 'react';
import jsPDF from 'jspdf';

interface MissionEntry {
  time: string;
  lat: number | null;
  lon: number | null;
  people: number;
  damage: { type: string; confidence: number }[];
  spills: { type: string; confidence: number }[];
}

interface AudioEntry {
  time: string;
  category: string;
  specific: string;
  confidence: number;
  lat: number | null;
  lon: number | null;
}

interface LiveData {
  totalFrames: number;
  maxPeople: number;
  damageEvents: number;
  avgDamageConfidence: number;
  spillEvents: number;
  audioEvents: number;
  avgAudioConfidence: number;
  latestTime: string;
}

export default function ReportsView() {
  const [isDownloading, setIsDownloading] = useState(false);
  const [liveData, setLiveData] = useState<LiveData | null>(null);

  useEffect(() => {
    Promise.all([
      fetch('/mission_log.json').then(r => r.json()).catch(() => [] as MissionEntry[]),
      fetch('/audio_log.json').then(r => r.json()).catch(() => [] as AudioEntry[]),
    ]).then(([mission, audio]: [MissionEntry[], AudioEntry[]]) => {
      const damageEntries = mission.filter(e => e.damage.length > 0);
      const avgDamageConf =
        damageEntries.length > 0
          ? (damageEntries.reduce((s, e) => s + e.damage[0].confidence, 0) / damageEntries.length) * 100
          : 0;
      const humanAudio = audio.filter(e => e.category === 'Human');
      const avgAudioConf =
        humanAudio.length > 0
          ? (humanAudio.reduce((s, e) => s + e.confidence, 0) / humanAudio.length) * 100
          : 0;
      setLiveData({
        totalFrames: mission.length,
        maxPeople: mission.length > 0 ? Math.max(...mission.map(e => e.people)) : 0,
        damageEvents: damageEntries.length,
        avgDamageConfidence: avgDamageConf,
        spillEvents: mission.filter(e => e.spills.length > 0).length,
        audioEvents: humanAudio.length,
        avgAudioConfidence: avgAudioConf,
        latestTime: mission.length > 0 ? mission[mission.length - 1].time : 'N/A',
      });
    });
  }, []);

  const reports = [
    { id: 'RPT-001', date: '13 May 2026', time: '09:15', severity: 'High', location: 'Zone A-12', status: 'Sent' },
    { id: 'RPT-002', date: '12 May 2026', time: '23:18', severity: 'High', location: 'Zone B-7', status: 'Downloaded' },
    { id: 'RPT-003', date: '12 May 2026', time: '22:05', severity: 'Medium', location: 'Zone C-3', status: 'Sent' },
  ];

  const staticReport = {
    latitude: '12.9716° N',
    longitude: '77.5946° E',
  };

  const handleDownloadPDF = async () => {
    setIsDownloading(true);
    try {
      const [mission, audio]: [MissionEntry[], AudioEntry[]] = await Promise.all([
        fetch('/mission_log.json').then(r => r.json()).catch(() => []),
        fetch('/audio_log.json').then(r => r.json()).catch(() => []),
      ]);

      const damageEntries = mission.filter(e => e.damage.length > 0);
      const avgDamageConf =
        damageEntries.length > 0
          ? (damageEntries.reduce((s, e) => s + e.damage[0].confidence, 0) / damageEntries.length) * 100
          : 0;
      const humanAudio = audio.filter(e => e.category === 'Human');
      const avgAudioConf =
        humanAudio.length > 0
          ? (humanAudio.reduce((s, e) => s + e.confidence, 0) / humanAudio.length) * 100
          : 0;
      const data: LiveData = {
        totalFrames: mission.length,
        maxPeople: mission.length > 0 ? Math.max(...mission.map(e => e.people)) : 0,
        damageEvents: damageEntries.length,
        avgDamageConfidence: avgDamageConf,
        spillEvents: mission.filter(e => e.spills.length > 0).length,
        audioEvents: humanAudio.length,
        avgAudioConfidence: avgAudioConf,
        latestTime: mission.length > 0 ? mission[mission.length - 1].time : 'N/A',
      };

      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      const PW = 210;
      const PH = 297;
      const ML = 14;
      const MR = 196;
      const CW = MR - ML;

      // ── HEADER ──────────────────────────────────────────────────────────────
      pdf.setFillColor(6, 18, 35);
      pdf.rect(0, 0, PW, 44, 'F');

      pdf.setFontSize(22);
      pdf.setTextColor(6, 182, 212);
      pdf.setFont('helvetica', 'bold');
      pdf.text('AEGIS EMERGENCY REPORT', ML, 17);

      pdf.setFontSize(9);
      pdf.setTextColor(134, 239, 172);
      pdf.setFont('helvetica', 'bold');
      pdf.text('VERDE PLATFORM  —  DISASTER RESPONSE INTELLIGENCE', ML, 25);

      pdf.setFontSize(8);
      pdf.setTextColor(130, 130, 130);
      pdf.setFont('helvetica', 'normal');
      const reportId = `RPT-${new Date().getTime().toString().slice(-6)}`;
      pdf.text(`Report ID: ${reportId}`, ML, 33);
      pdf.text(`Generated: ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`, ML + 52, 33);
      pdf.text('Classification: CONFIDENTIAL', ML + 128, 33);

      // Cyan accent line under header
      pdf.setFillColor(6, 182, 212);
      pdf.rect(0, 44, PW, 1.2, 'F');

      // ── SEVERITY BANNER ──────────────────────────────────────────────────────
      pdf.setFillColor(45, 8, 8);
      pdf.rect(ML, 50, CW, 13, 'F');
      pdf.setDrawColor(239, 68, 68);
      pdf.setLineWidth(0.5);
      pdf.rect(ML, 50, CW, 13, 'S');

      pdf.setFontSize(10.5);
      pdf.setTextColor(239, 68, 68);
      pdf.setFont('helvetica', 'bold');
      pdf.text('SEVERITY: HIGH   |   STATUS: ACTIVE EMERGENCY   |   THREAT LEVEL: RED', ML + 5, 58.5);

      let y = 74;

      // ── HELPERS ──────────────────────────────────────────────────────────────
      const sectionHeader = (title: string) => {
        pdf.setFillColor(6, 18, 35);
        pdf.rect(ML, y - 5, CW, 11, 'F');
        pdf.setFontSize(9.5);
        pdf.setTextColor(6, 182, 212);
        pdf.setFont('helvetica', 'bold');
        pdf.text(title, ML + 3, y + 2);
        y += 7;
        pdf.setFillColor(6, 182, 212);
        pdf.rect(ML, y, CW, 0.4, 'F');
        y += 6;
      };

      const row = (
        label: string,
        value: string,
        r = 210,
        g = 210,
        b = 210,
        altRow = false
      ) => {
        if (altRow) {
          pdf.setFillColor(8, 15, 28);
          pdf.rect(ML, y - 5, CW, 9, 'F');
        }
        pdf.setFontSize(9);
        pdf.setTextColor(110, 110, 110);
        pdf.setFont('helvetica', 'normal');
        pdf.text(label, ML + 4, y);
        pdf.setTextColor(r, g, b);
        pdf.setFont('helvetica', 'bold');
        pdf.text(value, ML + 82, y);
        y += 8;
      };

      // ── SECTION 1: LOCATION ──────────────────────────────────────────────────
      sectionHeader('1.  LOCATION INTELLIGENCE');
      row('Latitude', staticReport.latitude, 210, 210, 210, false);
      row('Longitude', staticReport.longitude, 210, 210, 210, true);
      row('Operational Zone', 'Zone A-12 / Sector B-12', 210, 210, 210, false);
      row('Last Detection Timestamp', data.latestTime, 34, 211, 238, true);
      y += 2;

      // ── SECTION 2: DETECTION ANALYSIS ───────────────────────────────────────
      sectionHeader('2.  DETECTION ANALYSIS  (from mission log)');
      row('Video Frames Analyzed', `${data.totalFrames} frames`, 210, 210, 210, false);
      row(
        'Max People Detected',
        `${data.maxPeople} individual(s)`,
        34, 211, 238,
        true
      );
      row(
        'Structural Damage Events',
        `${data.damageEvents} events   (avg confidence: ${data.avgDamageConfidence.toFixed(1)}%)`,
        239, 68, 68,
        false
      );
      row(
        'Spill / Hazard Incidents',
        `${data.spillEvents} incident(s) detected`,
        data.spillEvents > 0 ? 251 : 134,
        data.spillEvents > 0 ? 146 : 239,
        data.spillEvents > 0 ? 60 : 172,
        true
      );
      row(
        'Audio — Human Voice',
        data.audioEvents > 0
          ? `Detected   ${data.audioEvents} events   avg confidence: ${data.avgAudioConfidence.toFixed(1)}%`
          : 'Not detected',
        34, 211, 238,
        false
      );
      y += 2;

      // ── SECTION 3: CLIMATE PARAMETERS ───────────────────────────────────────
      sectionHeader('3.  CLIMATE PARAMETERS');
      row('Temperature', '28.5 °C', 210, 210, 210, false);
      row('Humidity', '65 %', 210, 210, 210, true);
      row('Atmospheric Pressure', '1013 hPa', 210, 210, 210, false);
      row('Air Toxicity Level', '37 %  — ELEVATED', 239, 68, 68, true);
      y += 2;

      // ── SECTION 4: GAS ANALYSIS ──────────────────────────────────────────────
      sectionHeader('4.  GAS ANALYSIS');
      row('MQ2 — Flammable Gas', '35 %   [ ELEVATED ]', 239, 68, 68, false);
      row('MQ4 — Methane', '28 %   [ MODERATE ]', 251, 146, 60, true);
      row('Overall Gas Risk Assessment', 'HIGH', 239, 68, 68, false);
      y += 2;

      // ── SECTION 5: AGENCY ALERTS TABLE ──────────────────────────────────────
      sectionHeader('5.  ACTIVE AGENCY ALERTS');

      // Table header row
      pdf.setFillColor(10, 25, 50);
      pdf.rect(ML, y - 4, CW, 9, 'F');
      pdf.setFontSize(8);
      pdf.setTextColor(90, 90, 90);
      pdf.setFont('helvetica', 'bold');
      pdf.text('AGENCY', ML + 4, y + 2);
      pdf.text('STATUS', ML + 70, y + 2);
      pdf.text('SEVERITY', ML + 112, y + 2);
      pdf.text('LAST UPDATE', ML + 152, y + 2);
      y += 11;

      type RGB = [number, number, number];
      const agencyAlerts: { agency: string; status: string; severity: string; last: string; sc: RGB; vc: RGB }[] = [
        { agency: 'Fire Department', status: 'ACTIVE', severity: 'RED', last: '2 min ago', sc: [239, 68, 68], vc: [239, 68, 68] },
        { agency: 'EMS / Ambulance', status: 'EN ROUTE', severity: 'RED', last: '1 min ago', sc: [34, 211, 238], vc: [239, 68, 68] },
        { agency: 'Police Coordination', status: 'MONITORING', severity: 'YELLOW', last: '3 min ago', sc: [251, 191, 36], vc: [251, 191, 36] },
        { agency: 'Government Control Room', status: 'ESCALATED', severity: 'BLACK', last: 'Just now', sc: [239, 68, 68], vc: [167, 139, 250] },
      ];

      agencyAlerts.forEach((alert, i) => {
        if (i % 2 === 0) {
          pdf.setFillColor(8, 16, 32);
          pdf.rect(ML, y - 5, CW, 9, 'F');
        }
        pdf.setFontSize(8.5);
        pdf.setTextColor(200, 200, 200);
        pdf.setFont('helvetica', 'normal');
        pdf.text(alert.agency, ML + 4, y);
        pdf.setTextColor(...alert.sc);
        pdf.setFont('helvetica', 'bold');
        pdf.text(alert.status, ML + 70, y);
        pdf.setTextColor(...alert.vc);
        pdf.text(alert.severity, ML + 112, y);
        pdf.setTextColor(120, 120, 120);
        pdf.setFont('helvetica', 'normal');
        pdf.text(alert.last, ML + 152, y);
        y += 9;
      });

      y += 6;

      // ── SUMMARY BOX ──────────────────────────────────────────────────────────
      if (y + 30 < PH - 22) {
        pdf.setFillColor(6, 18, 35);
        pdf.rect(ML, y, CW, 30, 'F');
        pdf.setDrawColor(6, 182, 212);
        pdf.setLineWidth(0.5);
        pdf.rect(ML, y, CW, 30, 'S');

        // Left cyan bar
        pdf.setFillColor(6, 182, 212);
        pdf.rect(ML, y, 2.5, 30, 'F');

        pdf.setFontSize(9);
        pdf.setTextColor(6, 182, 212);
        pdf.setFont('helvetica', 'bold');
        pdf.text('SUMMARY', ML + 6, y + 9);

        pdf.setFontSize(8.5);
        pdf.setTextColor(190, 190, 190);
        pdf.setFont('helvetica', 'normal');
        pdf.text(
          `Active emergency incident detected with ${data.maxPeople} individuals across ${data.totalFrames} analyzed frames.`,
          ML + 6, y + 18, { maxWidth: CW - 10 }
        );
        pdf.text(
          `${data.damageEvents} structural damage events and ${data.spillEvents} spill incident(s) recorded. Immediate response required.`,
          ML + 6, y + 25, { maxWidth: CW - 10 }
        );
      }

      // ── FOOTER ───────────────────────────────────────────────────────────────
      pdf.setFillColor(6, 18, 35);
      pdf.rect(0, PH - 18, PW, 18, 'F');
      pdf.setFillColor(6, 182, 212);
      pdf.rect(0, PH - 18, PW, 0.6, 'F');
      pdf.setFontSize(7.5);
      pdf.setTextColor(90, 90, 90);
      pdf.setFont('helvetica', 'normal');
      pdf.text(
        'VERDE Emergency Response System  |  AEGIS Platform  |  CONFIDENTIAL — FOR AUTHORIZED PERSONNEL ONLY',
        ML, PH - 9
      );
      pdf.text('Page 1 of 1', MR - 12, PH - 9);

      pdf.save(`AEGIS-Report-${reportId}.pdf`);
    } catch (error) {
      console.error('PDF generation failed:', error);
      alert('Failed to generate PDF. Please try again.');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Recent Reports */}
      <div>
        <h2 className="text-2xl font-bold text-cyan-400 mb-6 tracking-wide">Recent Reports</h2>
        <div className="grid grid-cols-3 gap-4 mb-8">
          {reports.map((report, index) => (
            <motion.div
              key={report.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className="p-6 rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 hover:border-cyan-400/50 transition-all duration-300"
              style={{ boxShadow: '0 0 15px rgba(6, 182, 212, 0.2)' }}
            >
              <div className="flex items-start justify-between mb-4">
                <FileText className="w-8 h-8 text-cyan-400" />
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                  report.severity === 'High'
                    ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                    : 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                }`}>
                  {report.severity}
                </span>
              </div>
              <h3 className="text-xl font-bold text-white mb-2">{report.id}</h3>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2 text-gray-400">
                  <Clock className="w-4 h-4" />
                  <span>{report.date} at {report.time}</span>
                </div>
                <div className="flex items-center gap-2 text-gray-400">
                  <MapPin className="w-4 h-4" />
                  <span>{report.location}</span>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-white/10">
                <span className="text-xs text-green-400">● {report.status}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Download Report Section */}
      <div
        className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-8"
        style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
      >
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-cyan-400 tracking-wide">Download Report</h2>
            <p className="text-xs text-gray-500 mt-1">Live data from mission log &amp; sensors</p>
          </div>
          <button
            onClick={handleDownloadPDF}
            disabled={isDownloading}
            className="px-6 py-3 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-white font-medium flex items-center gap-2 transition-all duration-300 shadow-[0_0_20px_rgba(6,182,212,0.4)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-5 h-5" />
            {isDownloading ? 'Generating...' : 'Download PDF'}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Left Column */}
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">Incident Timestamp</div>
              </div>
              <div className="text-white font-medium font-mono text-sm">
                {liveData ? liveData.latestTime : <span className="text-gray-600 animate-pulse">Loading...</span>}
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <MapPin className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">Location</div>
              </div>
              <div className="text-white font-medium font-mono text-sm">
                {staticReport.latitude} / {staticReport.longitude}
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">Severity Level</div>
              </div>
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-400" />
                <span className="text-red-400 font-bold">HIGH — ACTIVE</span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <Mic className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">Audio Detection</div>
              </div>
              <div className="text-cyan-400 font-medium text-sm">
                {liveData
                  ? liveData.audioEvents > 0
                    ? `Human Voice — ${liveData.audioEvents} events (${liveData.avgAudioConfidence.toFixed(1)}% avg)`
                    : 'None detected'
                  : <span className="text-gray-600 animate-pulse">Loading...</span>}
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <Users className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">People Detected</div>
              </div>
              <div className="flex items-end gap-2">
                <div className="text-3xl text-cyan-400 font-bold">
                  {liveData ? liveData.maxPeople : <span className="text-gray-600 animate-pulse">--</span>}
                </div>
                <span className="text-sm text-gray-500 mb-1">max across {liveData?.totalFrames ?? '--'} frames</span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <Layers className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">Damage Events</div>
              </div>
              <div className="flex items-end gap-2">
                <div className="text-3xl text-red-400 font-bold">
                  {liveData ? liveData.damageEvents : <span className="text-gray-600 animate-pulse">--</span>}
                </div>
                <span className="text-sm text-gray-500 mb-1">
                  {liveData ? `avg ${liveData.avgDamageConfidence.toFixed(1)}% confidence` : ''}
                </span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2 mb-1">
                <Waves className="w-3.5 h-3.5 text-gray-500" />
                <div className="text-sm text-gray-400">Spill Incidents</div>
              </div>
              <div className="text-3xl font-bold"
                style={{ color: liveData && liveData.spillEvents > 0 ? '#f97316' : '#34d399' }}>
                {liveData ? liveData.spillEvents : <span className="text-gray-600 animate-pulse">--</span>}
                <span className="text-sm text-gray-500 font-normal ml-2">detected</span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="text-sm text-gray-400 mb-2">Gas Analysis</div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">MQ2 Flammable</span>
                  <span className="text-red-400 font-bold">35%</span>
                </div>
                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-red-500 rounded-full" style={{ width: '35%' }} />
                </div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-xs text-gray-500">MQ4 Methane</span>
                  <span className="text-orange-400 font-bold">28%</span>
                </div>
                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-orange-500 rounded-full" style={{ width: '28%' }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* History Table */}
      <div
        className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 p-6"
        style={{ boxShadow: '0 0 20px rgba(6, 182, 212, 0.2)' }}
      >
        <h2 className="text-xl font-bold text-cyan-400 mb-4 tracking-wide">History of Reports</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Report ID</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Date</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Time</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Severity</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Status</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <motion.tr
                  key={report.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="border-b border-white/5 hover:bg-white/5 transition-colors"
                >
                  <td className="py-4 px-4 text-cyan-400 font-medium">{report.id}</td>
                  <td className="py-4 px-4 text-white">{report.date}</td>
                  <td className="py-4 px-4 text-white">{report.time}</td>
                  <td className="py-4 px-4">
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                      report.severity === 'High'
                        ? 'bg-red-500/20 text-red-400'
                        : 'bg-cyan-500/20 text-cyan-400'
                    }`}>
                      {report.severity}
                    </span>
                  </td>
                  <td className="py-4 px-4">
                    <span className="text-green-400 flex items-center gap-2">
                      <span className="w-2 h-2 bg-green-400 rounded-full" />
                      {report.status}
                    </span>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
