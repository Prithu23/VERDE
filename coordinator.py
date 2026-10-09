"""
AEGIS System Coordinator
========================
Single process that runs all three detection engines in lockstep on the same
sensor reading, writes outputs in correct dependency order, and auto-fires SMS
when a zone escalates to CRITICAL or CATASTROPHIC.

Replaces running three separate terminals:
  Before: python anomaly_detector.py
          python fusion_engine.py
          python ehs_calculator.py

  After:  python coordinator.py

Usage:
  python coordinator.py                         # simulate, no alerts
  python coordinator.py --alerts                # arm auto-SMS on escalation
  python coordinator.py --interval 2            # tick every 2s (default 1)
  python coordinator.py --scenario-interval 30  # scenario cycle in seconds
  python coordinator.py --zone "Zone B-7"
"""

import json, os, re, sys, time, argparse, urllib.request, urllib.error, urllib.parse
from pathlib import Path

# ── Fix Windows console encoding so ANSI + Unicode print correctly ──────────
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Always resolve paths relative to AEGIS root ─────────────────────────────
ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# ── Import from existing engine modules ─────────────────────────────────────
from anomaly_detector import SimulatedSensorInput, HttpSensorInput, AnomalyDetector, _write_sensor_log, SENSOR_IP
from fusion_engine    import decide  as fusion_decide
from ehs_calculator   import compute as ehs_compute


# ── Contact list and alert routing ──────────────────────────────────────────
# Each contact is notified when any of their listed threat IDs is active.
# CATASTROPHIC zone notifies all contacts regardless of threat routing.

CONTACTS = [
    {
        'name':    'Prithika',
        'phone':   '9108307690',
        'role':    'Fire Dept',
        'threats': {'FIRE_RISK', 'COMPOUND_EMERGENCY'},
    },
    {
        'name':    'Kovidh',
        'phone':   '9108307690',
        'role':    'EMS',
        'threats': {'TOXIC_EXPOSURE', 'MASS_CASUALTY_RISK', 'COMPOUND_EMERGENCY'},
    },
    {
        'name':    'Likitha',
        'phone':   '9108307690',
        'role':    'Police',
        'threats': {'MASS_CASUALTY_RISK', 'COMPOUND_EMERGENCY'},
    },
    {
        'name':    'Barath',
        'phone':   '9108307690',
        'role':    'Control Room',
        'threats': {'GAS_LEAK', 'STRUCTURAL_STRESS', 'COMPOUND_EMERGENCY'},
    },
]

ZONE_RANK  = {'CLEAR': 0, 'ELEVATED': 1, 'WARNING': 2, 'CRITICAL': 3, 'CATASTROPHIC': 4}
ALERT_THRESHOLD = 3    # CRITICAL (3) and CATASTROPHIC (4) trigger SMS
ALERT_COOLDOWN  = 300  # seconds before re-alerting the same contact


# ── WhatsApp helpers (CallMeBot) ─────────────────────────────────────────────
# Each recipient registers once with CallMeBot and gets their own API key.
# app/.env.local:  CALLMEBOT_KEYS=9108307690:123456,9284955662:654321

def _load_api_key() -> dict[str, str]:
    """Read CALLMEBOT_KEYS from app/.env.local → {phone: apikey}."""
    env = ROOT / 'app' / '.env.local'
    if not env.exists():
        return {}
    keys = {}
    for line in env.read_text(encoding='utf-8').splitlines():
        if line.startswith('CALLMEBOT_KEYS='):
            for pair in line.split('=', 1)[1].split(','):
                phone, _, key = pair.strip().partition(':')
                if phone and key and key != 'your_api_key_here':
                    keys[phone.strip()] = key.strip()
    return keys


def _send_sms(api_keys: dict[str, str], phone: str, message: str) -> bool:
    key = api_keys.get(phone)
    if not key:
        print(f'\n  [WA ERR] No CallMeBot key for {phone} in app/.env.local')
        return False
    url = 'https://api.callmebot.com/whatsapp.php?' + urllib.parse.urlencode({
        'phone': f'+91{phone}', 'text': message, 'apikey': key,
    })
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            body = r.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'\n  [WA ERR] {e}')
        return False
    if 'queued' in body.lower() or 'sent' in body.lower():
        return True
    text = ' '.join(re.sub(r'<[^>]+>', ' ', body).split())[:200]
    print(f'\n  [WA ERR] CallMeBot: {text}')
    return False


def _location_text(reading: dict) -> str:
    lat, lon = reading.get('lat'), reading.get('lon')
    if reading.get('gps_valid') and lat is not None and lon is not None:
        return f"Loc: {lat:.5f},{lon:.5f}\nhttps://maps.google.com/?q={lat:.6f},{lon:.6f}"
    return "Loc: GPS unavailable"


def _build_sms(fusion: dict, contact: dict, reading: dict) -> str:
    top = ', '.join(t['id'] for t in fusion['threats'][:3]) or 'NONE'
    sc  = fusion['sensor_classes']
    return (
        f"AEGIS ALERT -- {fusion['zone']}\n"
        f"Status: {fusion['zone_status']} (Level {fusion['threat_level']})\n"
        f"Threats: {top}\n"
        f"Action: {fusion['action_label']}\n"
        f"T={sc.get('temperature',{}).get('value',0):.1f}C "
        f"MQ2={sc.get('mq2',{}).get('value',0):.1f}% "
        f"Tox={sc.get('air_toxicity',{}).get('value',0):.1f}%\n"
        f"{_location_text(reading)}\n"
        f"-- VERDE Emergency Response System"
    )


def send_test_sms() -> int:
    """Send one test SMS to every unique contact number, then exit."""
    api_key = _load_api_key()
    if not api_key:
        print('  [TEST-SMS] No CALLMEBOT_KEYS in app/.env.local')
        return 1
    try:
        reading = json.loads((ROOT / 'sensor_log.json').read_text(encoding='utf-8'))[-1]
    except Exception:
        reading = {}
    message = (
        "AEGIS TEST -- SMS path check, no emergency.\n"
        f"{_location_text(reading)}\n"
        "-- VERDE Emergency Response System"
    )
    numbers = sorted({c['phone'] for c in CONTACTS})
    print(f'  [TEST-SMS] Sending WhatsApp to {", ".join(numbers)}\n{message}\n')
    ok = True
    for phone in numbers:
        sent = _send_sms(api_key, phone, message)
        print(f'  [TEST-SMS] {phone}  →  {"SENT" if sent else "FAILED"}')
        ok = ok and sent
    return 0 if ok else 1


# ── Alert manager ────────────────────────────────────────────────────────────

class AlertManager:
    """Fires SMS when zone escalates into CRITICAL/CATASTROPHIC territory."""

    def __init__(self, api_key: dict[str, str], enabled: bool):
        self.api_key    = api_key
        self.enabled    = enabled
        self.live       = enabled and bool(api_key)   # True = real SMS sent
        self.cooldowns: dict[str, float] = {}
        self.prev_level = 0

        if enabled and not api_key:
            print('  [ALERTS] No CALLMEBOT_KEYS in app/.env.local — running in DRY RUN mode')
        elif enabled and api_key:
            print(f'  [ALERTS] ARMED — WhatsApp keys for {len(api_key)} number(s)  cooldown {ALERT_COOLDOWN}s')
        else:
            print('  [ALERTS] disabled (pass --alerts to arm)')

    def check(self, fusion: dict, reading: dict):
        level = ZONE_RANK.get(fusion['zone_status'], 0)

        if level < ALERT_THRESHOLD or level <= self.prev_level:
            self.prev_level = level
            return

        # Zone just escalated into dangerous territory
        active_threats = {t['id'] for t in fusion['threats']}
        now = time.time()

        for contact in CONTACTS:
            relevant = contact['threats'] & active_threats or level == 4  # all on CATASTROPHIC
            if not relevant:
                continue

            phone     = contact['phone']
            last_sent = self.cooldowns.get(phone, 0)
            if now - last_sent < ALERT_COOLDOWN:
                remaining = int(ALERT_COOLDOWN - (now - last_sent))
                print(f'\n  [ALERT] {contact["role"]:12} cooldown {remaining}s remaining — skip')
                continue

            if self.live:
                ok     = _send_sms(self.api_key, phone, _build_sms(fusion, contact, reading))
                status = 'SENT' if ok else 'FAILED'
            else:
                status = 'DRY-RUN'

            print(f'\n  [ALERT] {contact["role"]:12} {contact["name"]:10} '
                  f'{phone}  →  {status}  ({fusion["zone_status"]})')
            self.cooldowns[phone] = now

        self.prev_level = level


# ── Terminal output ──────────────────────────────────────────────────────────

_ZONE_COLOR = {
    'CLEAR':        '\033[92m',
    'ELEVATED':     '\033[96m',
    'WARNING':      '\033[93m',
    'CRITICAL':     '\033[91m',
    'CATASTROPHIC': '\033[95m',
}
_R = '\033[0m'

def _print_status(n: int, reading: dict, fusion: dict, ehs: dict, ms: float):
    zone = fusion['zone_status']
    col  = _ZONE_COLOR.get(zone, '')
    top  = fusion['threats'][0]['id'] if fusion['threats'] else '-'
    ehs_score = ehs.get('score', 0)
    ehs_grade = ehs.get('grade', '?')
    print(
        f"\r  [{reading['timestamp']}] #{n:04d} | "
        f"{col}{zone:12}{_R} L{fusion['threat_level']} | "
        f"{top:22} | "
        f"EHS {ehs_score:5.1f}{ehs_grade} | "
        f"T={reading.get('temperature', 0):5.1f} "
        f"MQ2={reading.get('mq2', 0):5.1f} "
        f"Tox={reading.get('air_toxicity', 0):5.1f} | "
        f"{ms:.1f}ms",
        end='', flush=True,
    )


# ── Main loop ────────────────────────────────────────────────────────────────

def run(zone: str, interval: float, scenario_interval: int, alerts_enabled: bool, mode: str = 'sim'):
    api_key   = _load_api_key()
    if mode == 'http':
        sim = HttpSensorInput()
    else:
        sim = SimulatedSensorInput(scenario_interval=scenario_interval)
    detector  = AnomalyDetector()
    alert_mgr = AlertManager(api_key, alerts_enabled)

    print()
    print('=' * 72)
    print('  AEGIS COORDINATOR  --  VERDE Emergency Response Platform')
    print('=' * 72)
    print(f'  Zone              : {zone}')
    print(f'  Mode              : {"HTTP — board at " + SENSOR_IP if mode == "http" else "simulation"}')
    print(f'  Tick interval     : {interval}s')
    print(f'  Scenario cycle    : {scenario_interval}s (sim only)')
    print(f'  Engines active    : Anomaly Detector | Sensor Fusion | EHS Calculator')
    print(f'  Dashboard outputs : sensor_log.json | anomaly_log.json | '
          f'fusion_log.json | ehs_log.json')
    print('=' * 72)
    print()
    print('  Timestamp               Tick   Zone          L  Top Threat             '
          '        EHS     T      MQ2   Tox    ms')
    print('  ' + '-' * 110)

    n = 0
    while True:
        t0 = time.monotonic()
        try:
            reading = sim.read()
            n += 1

            # ── Pipeline (order matters — each step depends on the previous) ──

            # 1. Sensor log first — ehs_compute reads it from disk
            _write_sensor_log(reading)

            # 2. Anomaly detection — writes anomaly_log.json (ehs reads this too)
            detector.process(reading)

            # 3. Sensor fusion — direct call, no disk round-trip needed
            fusion = fusion_decide(reading, zone)

            # 4. Persist fusion result for dashboard
            (ROOT / 'fusion_log.json').write_text(
                json.dumps(fusion, indent=2), encoding='utf-8'
            )

            # 5. EHS — reads all four logs from disk, writes ehs_log.json
            ehs = ehs_compute(zone)

            # 6. Auto-alert check
            alert_mgr.check(fusion, reading)

            # 7. Status line
            ms = (time.monotonic() - t0) * 1000
            _print_status(n, reading, fusion, ehs, ms)

            # Sleep for the remainder of the tick interval
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))

        except KeyboardInterrupt:
            print(f'\n\n  Coordinator stopped after {n} ticks.')
            print(f'  Anomalies logged : {len(detector.anomaly_log)}')
            break
        except Exception as e:
            print(f'\n  [ERR] tick {n}: {e}')
            time.sleep(interval)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='AEGIS System Coordinator')
    ap.add_argument('--zone',              default='Zone A-12',
                    help='Zone identifier shown in all outputs')
    ap.add_argument('--interval',          type=float, default=1.0,
                    help='Seconds between sensor ticks (default 1)')
    ap.add_argument('--scenario-interval', type=int,   default=60,
                    help='Seconds per simulation scenario (default 60)')
    ap.add_argument('--alerts',            action='store_true',
                    help='Arm auto-SMS when zone hits CRITICAL or CATASTROPHIC')
    ap.add_argument('--mode',              choices=['sim', 'http'], default='sim',
                    help='"sim" = simulation (default), "http" = live board at 10.161.238.74')
    ap.add_argument('--test-sms',          action='store_true',
                    help='Send one test SMS to the contact number(s) and exit')
    args = ap.parse_args()

    if args.test_sms:
        sys.exit(send_test_sms())

    run(
        zone=args.zone,
        interval=args.interval,
        scenario_interval=args.scenario_interval,
        alerts_enabled=args.alerts,
        mode=args.mode,
    )
