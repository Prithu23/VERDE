"""
VERDE Coordinator
=================
The one process that turns live inputs into the dashboard's data:

    sensor board ─┐
    detect.py  ───┼─▶ fusion engine ─▶ fusion_log.json      (model: fusion_model.json)
    audio_detect ─┘        │
                           ├─▶ sensor_log.json   (readings, gas as % rise over clean air)
                           ├─▶ anomaly detector ─▶ anomaly_log.json
                           ├─▶ health score     ─▶ ehs_log.json
                           └─▶ Telegram alerts (optional)

Live by default. If the sensor board, camera or microphone is not delivering
data, that source is shown as offline; nothing is simulated unless you ask.

Usage:
  python coordinator.py                              # live
  python coordinator.py --sensor-ip 192.168.1.50     # board at another address
  python coordinator.py --alerts                     # arm Telegram alerts on CRITICAL / CATASTROPHIC
  python coordinator.py --telegram-setup             # check bot token, list chat IDs
  python coordinator.py --test-sms                   # send one test message and exit
  python coordinator.py --mode sim                   # simulated sensors (labelled SIMULATED)

Run detect.py and audio_detect.py alongside it for the camera and microphone.
"""

import json, os, re, sys, time, argparse, threading, urllib.request, urllib.error, urllib.parse
from pathlib import Path

# ── Fix Windows console encoding so ANSI + Unicode print correctly ──────────
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Always resolve paths relative to the repo root ──────────────────────────
ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from sensor_source    import BoardSensor, DEFAULT_SENSOR_IP, read_vision, read_audio, write_json
from fusion_engine    import FusionEngine
from anomaly_detector import AnomalyDetector, SimulatedSensorInput
from ehs_calculator   import EHSCalculator


# ── Contact list and alert routing ──────────────────────────────────────────
# Each contact is notified when any of their listed threat IDs is active.
# CATASTROPHIC zone notifies all contacts regardless of threat routing.

CONTACTS = [
    {
        'name':    'Prithika',
        'phone':   '9108307690',
        'role':    'Fire Dept',
        'threats': {'FIRE_RISK', 'SPILL_HAZARD', 'COMPOUND_EMERGENCY'},
    },
    {
        'name':    'Kovidh',
        'phone':   '9108307690',
        'role':    'EMS',
        'threats': {'TOXIC_EXPOSURE', 'MASS_CASUALTY_RISK', 'SURVIVOR_SIGNAL', 'COMPOUND_EMERGENCY'},
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
        'threats': {'GAS_LEAK', 'STRUCTURAL_STRESS', 'FLOOD_RISK', 'COMPOUND_EMERGENCY'},
    },
]

ZONE_RANK  = {'CLEAR': 0, 'ELEVATED': 1, 'WARNING': 2, 'CRITICAL': 3, 'CATASTROPHIC': 4}
ALERT_THRESHOLD = 3    # CRITICAL (3) and CATASTROPHIC (4) trigger SMS
ALERT_COOLDOWN  = 300  # seconds before re-alerting the same contact


# ── Telegram helpers ─────────────────────────────────────────────────────────
# One bot for everyone; each contact presses Start on the bot once, then their
# chat ID is mapped to their phone number in app/.env.local:
#   TELEGRAM_BOT_TOKEN=123456789:AAH...
#   TELEGRAM_CHAT_IDS=9108307690:111111111,9284955662:222222222

def _read_env() -> dict[str, str]:
    env = ROOT / 'app' / '.env.local'
    if not env.exists():
        return {}
    out = {}
    for line in env.read_text(encoding='utf-8').splitlines():
        k, sep, v = line.partition('=')
        if sep:
            out[k.strip()] = v.strip()
    return out


def _load_api_key() -> dict[str, tuple[str, str]]:
    """Read Telegram config from app/.env.local → {phone: (bot_token, chat_id)}."""
    env   = _read_env()
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    if not token or token == 'your_bot_token_here':
        return {}
    chats = {}
    for pair in env.get('TELEGRAM_CHAT_IDS', '').split(','):
        phone, _, chat_id = pair.strip().partition(':')
        if phone and chat_id and chat_id != 'your_chat_id_here':
            chats[phone.strip()] = (token, chat_id.strip())
    return chats


def _telegram(token: str, method: str, params: dict) -> dict:
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/{method}',
        data=json.dumps(params).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {'ok': False, 'description': f'HTTP {e.code}'}
    except Exception as e:
        return {'ok': False, 'description': str(e)}


def _send_sms(api_keys: dict[str, tuple[str, str]], phone: str, message: str,
              reading: dict | None = None) -> bool:
    """Send a Telegram message (plus a map pin when GPS is valid) to a contact."""
    if phone not in api_keys:
        print(f'\n  [TG ERR] No Telegram chat ID for {phone} in TELEGRAM_CHAT_IDS (app/.env.local)')
        return False
    token, chat_id = api_keys[phone]
    data = _telegram(token, 'sendMessage', {'chat_id': chat_id, 'text': message})
    if not data.get('ok'):
        print(f'\n  [TG ERR] Telegram: {data.get("description", data)}')
        return False
    lat, lon = (reading or {}).get('lat'), (reading or {}).get('lon')
    if (reading or {}).get('gps_valid') and lat is not None and lon is not None:
        _telegram(token, 'sendLocation', {'chat_id': chat_id, 'latitude': lat, 'longitude': lon})
    return True


def telegram_setup() -> int:
    """List chats that have messaged the bot, so their chat IDs can go in .env.local."""
    token = _read_env().get('TELEGRAM_BOT_TOKEN', '')
    if not token or token == 'your_bot_token_here':
        print('  [TG] Put TELEGRAM_BOT_TOKEN in app/.env.local first')
        return 1
    me = _telegram(token, 'getMe', {})
    if not me.get('ok'):
        print(f'  [TG] Token rejected: {me.get("description")}')
        return 1
    print(f'  [TG] Bot: @{me["result"]["username"]}')
    data = _telegram(token, 'getUpdates', {})
    chats = {}
    for u in data.get('result', []):
        c = (u.get('message') or u.get('my_chat_member') or {}).get('chat')
        if c:
            chats[c['id']] = c.get('first_name') or c.get('title') or ''
            if c.get('username'):
                chats[c['id']] += f' (@{c["username"]})'
    if not chats:
        print(f'  [TG] No chats yet — open t.me/{me["result"]["username"]}, press Start, then rerun this.')
        return 1
    for cid, name in chats.items():
        print(f'  [TG] chat ID {cid}  →  {name}')
    return 0


def _location_text(reading: dict) -> str:
    lat, lon = reading.get('lat'), reading.get('lon')
    if reading.get('gps_valid') and lat is not None and lon is not None:
        return f"Loc: {lat:.5f},{lon:.5f}\nhttps://maps.google.com/?q={lat:.6f},{lon:.6f}"
    return "Loc: GPS unavailable"


def _build_sms(fusion: dict, contact: dict, reading: dict) -> str:
    top = ', '.join(t['label'] for t in fusion['threats'][:3]) or 'none'
    why = fusion['threats'][0]['description'] if fusion['threats'] else ''
    return (
        f"AEGIS ALERT -- {fusion['zone']}\n"
        f"Status: {fusion['zone_status']} (Level {fusion['threat_level']}/4)\n"
        f"Threats: {top}\n"
        f"{why}\n"
        f"Action: {fusion['action_label']}\n"
        f"{_location_text(reading)}\n"
        f"-- VERDE Emergency Response System"
    )


def send_test_sms() -> int:
    """Send one test SMS to every unique contact number, then exit."""
    api_key = _load_api_key()
    if not api_key:
        print('  [TEST-SMS] No TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS in app/.env.local')
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
    print(f'  [TEST-SMS] Sending Telegram to {", ".join(numbers)}\n{message}\n')
    ok = True
    for phone in numbers:
        sent = _send_sms(api_key, phone, message, reading)
        print(f'  [TEST-SMS] {phone}  →  {"SENT" if sent else "FAILED"}')
        ok = ok and sent
    return 0 if ok else 1


# ── Alert manager ────────────────────────────────────────────────────────────

class AlertManager:
    """Fires SMS when zone escalates into CRITICAL/CATASTROPHIC territory."""

    def __init__(self, api_key: dict[str, tuple[str, str]], enabled: bool):
        self.api_key    = api_key
        self.enabled    = enabled
        self.live       = enabled and bool(api_key)   # True = real SMS sent
        self.cooldowns: dict[str, float] = {}
        self.prev_level = 0

        if enabled and not api_key:
            print('  [ALERTS] No Telegram config in app/.env.local — running in DRY RUN mode')
        elif enabled and api_key:
            print(f'  [ALERTS] ARMED — Telegram chats for {len(api_key)} number(s)  cooldown {ALERT_COOLDOWN}s')
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
                ok     = _send_sms(self.api_key, phone, _build_sms(fusion, contact, reading), reading)
                status = 'SENT' if ok else 'FAILED'
            else:
                status = 'DRY-RUN'

            print(f'\n  [ALERT] {contact["role"]:12} {contact["name"]:10} '
                  f'{phone}  →  {status}  ({fusion["zone_status"]})')
            self.cooldowns[phone] = now

        self.prev_level = level


# ── Sensor board polling (background, so a dead board never stalls the loop) ─

class BoardPoller(threading.Thread):
    """Keeps the newest reading from the source. take() hands each one out once."""

    def __init__(self, source, interval: float):
        super().__init__(daemon=True)
        self.source, self.interval = source, interval
        self._lock = threading.Lock()
        self._reading = None
        self.ok = False

    def run(self):
        while True:
            t0 = time.monotonic()
            try:
                reading = self.source.read()
            except Exception:
                reading = None
            with self._lock:
                self.ok = reading is not None
                if reading is not None:
                    self._reading = reading
            time.sleep(max(0.05, self.interval - (time.monotonic() - t0)))

    def take(self):
        with self._lock:
            reading, self._reading = self._reading, None
            return reading


# ── Terminal output ──────────────────────────────────────────────────────────

_ZONE_COLOR = {
    'CLEAR':        '\033[92m',
    'ELEVATED':     '\033[96m',
    'WARNING':      '\033[93m',
    'CRITICAL':     '\033[91m',
    'CATASTROPHIC': '\033[95m',
    'NO_DATA':      '\033[90m',
    'UNTRAINED':    '\033[90m',
}
_R = '\033[0m'


def _print_status(n: int, fusion: dict, ehs: dict):
    zone = fusion['zone_status']
    src  = fusion['sources']
    flag = lambda k, name: (name if src[k]['live'] else name.lower() + ':off')
    cal  = ' (calibrating gas)' if src['sensors']['calibrating'] else ''
    top  = fusion['threats'][0]['label'] if fusion['threats'] else '-'
    score = ehs.get('score')
    ehs_s = f"{score:5.1f}{ehs.get('grade', '')}" if score is not None else '  n/a '
    line = (f"  [{fusion['timestamp'][11:]}] #{n:05d} | "
            f"{_ZONE_COLOR.get(zone, '')}{zone:12}{_R} | {top:22.22} | EHS {ehs_s} | "
            f"{flag('sensors', 'BOARD')} {flag('camera', 'CAM')} {flag('audio', 'MIC')}{cal}")
    print('\r' + line.ljust(118), end='', flush=True)


# ── Main loop ────────────────────────────────────────────────────────────────

SENSOR_LOG_MAX = 100


def run(zone: str, interval: float, mode: str, sensor_ip: str,
        scenario_interval: int, alerts_enabled: bool, ticks: int = 0):
    if mode == 'sim':
        source = SimulatedSensorInput(scenario_interval=scenario_interval)
    else:
        source = BoardSensor(ip=sensor_ip)
    origin = getattr(source, 'origin', 'board')

    engine    = FusionEngine()
    detector  = AnomalyDetector(fresh=True)
    ehs_calc  = EHSCalculator()
    alert_mgr = AlertManager(_load_api_key(), alerts_enabled)
    poller    = BoardPoller(source, interval)
    poller.start()

    # Start from empty logs so nothing from an earlier run is shown as current
    sensor_log: list = []
    write_json('sensor_log.json', sensor_log)

    print()
    print('=' * 78)
    print('  VERDE COORDINATOR')
    print('=' * 78)
    print(f'  Zone     : {zone}')
    if mode == 'sim':
        print('  Sensors  : SIMULATED  (not real data — dashboard is labelled accordingly)')
    else:
        print(f'  Sensors  : board at http://{sensor_ip}')
        print('             gas sensors calibrate to clean air for the first 30 readings')
    trained = (engine.model or {}).get('hazards', {})
    if trained:
        print(f"  Model    : fusion_model.json, trained {engine.model.get('trained_at')}")
        for key, m in trained.items():
            h = m['held_out']
            print(f"             {m['name']:<22} precision {h['precision']:.2f}  recall {h['recall']:.2f}"
                  f"  ({m['data']['trials']} trials)")
        for key, why in (engine.model or {}).get('not_trained', {}).items():
            print(f"             {key:<22} not trained — {why}")
    else:
        print('  Model    : NONE — no hazard will be reported until you record trials')
        print('             (record_trials.py) and run train_fusion.py')
    print('  Camera   : from detect.py        (detection_state.json)')
    print('  Audio    : from audio_detect.py  (audio_state.json, audio_log.json)')
    print('  Outputs  : sensor_log.json | fusion_log.json | anomaly_log.json | ehs_log.json')
    print('=' * 78)
    print()

    n = 0
    while True:
        t0 = time.monotonic()
        try:
            n += 1
            reading = poller.take()
            fusion  = engine.decide(reading, read_vision(), read_audio(), zone=zone, origin=origin)

            # Sensor log and anomaly detection only advance on a real new reading
            if reading is not None and engine.published is not None:
                sensor_log = (sensor_log + [engine.published])[-SENSOR_LOG_MAX:]
                write_json('sensor_log.json', sensor_log)
                for a in detector.process(engine.published):
                    print(f"\n  [{a['severity']:8}] [{a['method']:11}] {a['sensor']:11} {a['detail'][:90]}")

            write_json('fusion_log.json', fusion)
            ehs = ehs_calc.compute(zone, fusion)
            alert_mgr.check(fusion, engine.published or {})
            _print_status(n, fusion, ehs)

            if ticks and n >= ticks:
                print()
                return
            time.sleep(max(0.0, interval - (time.monotonic() - t0)))

        except KeyboardInterrupt:
            print(f'\n\n  Coordinator stopped after {n} ticks, '
                  f'{len(detector.anomaly_log)} anomalies logged.')
            break
        except Exception as e:
            print(f'\n  [ERR] tick {n}: {type(e).__name__}: {e}')
            time.sleep(interval)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='VERDE Coordinator')
    ap.add_argument('--zone',      default='Zone A-12', help='Zone name shown in all outputs')
    ap.add_argument('--interval',  type=float, default=1.0, help='Seconds between ticks (default 1)')
    ap.add_argument('--mode',      choices=['live', 'sim'], default='live',
                    help='"live" = real sensor board (default); "sim" = simulated sensors')
    ap.add_argument('--sensor-ip', default=DEFAULT_SENSOR_IP,
                    help=f'Sensor board address (default {DEFAULT_SENSOR_IP}, or env VERDE_SENSOR_IP)')
    ap.add_argument('--scenario-interval', type=int, default=60,
                    help='Seconds per scenario in sim mode (default 60)')
    ap.add_argument('--alerts',    action='store_true',
                    help='Arm auto-SMS when the zone reaches CRITICAL or CATASTROPHIC')
    ap.add_argument('--test-sms',  action='store_true',
                    help='Send one test Telegram message to the contact(s) and exit')
    ap.add_argument('--telegram-setup', action='store_true',
                    help='Check the bot token and list chat IDs that have pressed Start, then exit')
    ap.add_argument('--ticks',     type=int, default=0, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.telegram_setup:
        sys.exit(telegram_setup())
    if args.test_sms:
        sys.exit(send_test_sms())

    run(zone=args.zone, interval=args.interval, mode=args.mode, sensor_ip=args.sensor_ip,
        scenario_interval=args.scenario_interval, alerts_enabled=args.alerts, ticks=args.ticks)
