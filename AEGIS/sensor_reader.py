"""
AEGIS Sensor Reader
===================
Polls the sensor board at 10.161.238.74 every <interval> seconds,
normalises the JSON response, and writes sensor_log.json.

Sensors read:
  Temperature, Humidity, Pressure
  GPS (lat/lon/fix/satellites)
  MPU-6050 (roll, pitch, yaw)
  Water sensor (digital)
  MQ-2  (flammable gas / LPG)
  MQ-4  (methane)
  MQ-135 (SO2 / air quality)

Run alongside detect.py, fusion_engine.py, ehs_calculator.py:
    python sensor_reader.py
    python sensor_reader.py --interval 1 --max-records 200
"""

import json
import math
import time
import argparse
from datetime import datetime
from pathlib import Path
import urllib.request

SENSOR_IP   = "10.161.238.74"
LOG_PATH    = Path("sensor_log.json")
# Try these endpoints in order
ENDPOINTS   = ["/data", "/csv", "/sensor", "/sensors", "/all", "/readings", "/"]

# Field name aliases for positional CSV (order ESP32 sketches typically emit)
_POSITIONAL_FIELDS = [
    "temperature", "humidity", "pressure",
    "mq2", "mq4", "mq135",
    "lat", "lon",
]

# Known CSV header synonyms → canonical key
_CSV_ALIASES = {
    "temp": "temperature", "t": "temperature",
    "hum": "humidity",    "h": "humidity", "rh": "humidity",
    "press": "pressure",  "p": "pressure",
    "mq-2": "mq2",        "mq_2": "mq2",
    "mq-4": "mq4",        "mq_4": "mq4",
    "mq-135": "mq135",    "mq_135": "mq135",
    "so2": "mq135",       "air_quality": "mq135", "airquality": "mq135",
    "latitude": "lat",    "lat_deg": "lat",
    "longitude": "lon",   "lng": "lon",  "lon_deg": "lon",
    "roll_angle": "roll", "pitch_angle": "pitch", "yaw_angle": "yaw",
    "water": "water_detected", "water_sensor": "water_detected", "flood": "water_detected",
    "gps_fix": "gpsFix",  "fix": "gpsFix",
    "sats": "gpsSats",    "satellites": "gpsSats", "num_sats": "gpsSats",
}


def _parse_csv(text: str) -> dict | None:
    """Parse CSV, key=value, or header+data rows into a plain dict."""
    text = text.strip()
    if not text:
        return None

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ── key=value or key:value pairs on a single line (T=28.5,H=65) ──────────
    if len(lines) == 1 and ("=" in lines[0] or ":" in lines[0]):
        sep = "=" if "=" in lines[0] else ":"
        d: dict = {}
        for part in lines[0].split(","):
            if sep in part:
                k, v = part.split(sep, 1)
                key = _CSV_ALIASES.get(k.strip().lower(), k.strip().lower())
                try:
                    d[key] = float(v.strip())
                except ValueError:
                    d[key] = v.strip()
        return d if d else None

    # ── header row + data row ─────────────────────────────────────────────────
    if len(lines) >= 2:
        headers = [h.strip().lower() for h in lines[0].split(",")]
        values  = [v.strip()         for v  in lines[1].split(",")]
        if len(headers) == len(values):
            d = {}
            for h, v in zip(headers, values):
                key = _CSV_ALIASES.get(h, h)
                try:
                    d[key] = float(v)
                except ValueError:
                    d[key] = v
            if d:
                return d

    # ── single line of bare numbers — assume positional order ─────────────────
    if len(lines) == 1:
        parts = lines[0].split(",")
        if all(p.replace(".", "").replace("-", "").isdigit() for p in parts[:3]):
            d = {}
            for i, v in enumerate(parts):
                key = _POSITIONAL_FIELDS[i] if i < len(_POSITIONAL_FIELDS) else f"field{i}"
                try:
                    d[key] = float(v)
                except ValueError:
                    d[key] = v
            return d if d else None

    return None


# ── HTTP fetch ─────────────────────────────────────────────────────────────────

def _fetch(timeout: float = 4.0) -> dict | None:
    for ep in ENDPOINTS:
        try:
            with urllib.request.urlopen(f"http://{SENSOR_IP}{ep}", timeout=timeout) as r:
                raw_bytes = r.read()
                text = raw_bytes.decode(errors="replace")

                # Try JSON first
                try:
                    data = json.loads(text)
                    if isinstance(data, dict) and data:
                        return data
                except (json.JSONDecodeError, ValueError):
                    pass

                # Try CSV
                data = _parse_csv(text)
                if data:
                    print(f"\n[sensor_reader] CSV parsed from {ep}: {list(data.keys())}")
                    return data
        except Exception:
            continue
    return None


# ── Key-normalisation helpers ──────────────────────────────────────────────────

def _f(d: dict, *keys, default: float = 0.0) -> float:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return default


def _b(d: dict, *keys) -> bool:
    for k in keys:
        v = d.get(k)
        if v is not None:
            if isinstance(v, bool):
                return v
            try:
                return int(v) != 0
            except (ValueError, TypeError):
                return str(v).lower() not in ('0', 'false', 'no', 'none')
    return False


def _gps_valid(d: dict, lat: float, lon: float) -> bool:
    for key in ("gpsFix", "gps_fix", "gps_valid", "fix", "gps_lock", "hasFix"):
        v = d.get(key)
        if v is not None:
            try:
                return bool(int(v))
            except (ValueError, TypeError):
                return bool(v)
    # Fall back to non-zero coordinates
    return abs(lat) > 0.001 and abs(lon) > 0.001


def _tilt(d: dict) -> tuple[float, float, float]:
    """Return (roll, pitch, yaw) in degrees. Computes from raw accel if needed."""
    roll  = _f(d, "roll",  "Roll",  "ROLL",  "rollAngle")
    pitch = _f(d, "pitch", "Pitch", "PITCH", "pitchAngle")
    yaw   = _f(d, "yaw",   "Yaw",   "YAW",   "yawAngle", "heading")

    if roll == 0.0 and pitch == 0.0:
        ax = _f(d, "accelX", "ax", "AccX", "aX", "accel_x")
        ay = _f(d, "accelY", "ay", "AccY", "aY", "accel_y")
        az = _f(d, "accelZ", "az", "AccZ", "aZ", "accel_z", default=9.81)
        if ax != 0.0 or ay != 0.0:
            roll  = math.degrees(math.atan2(ay, az))
            pitch = math.degrees(math.atan2(-ax, math.sqrt(ay ** 2 + az ** 2)))

    return round(roll, 2), round(pitch, 2), round(yaw, 2)


# ── Normalise raw ESP32 JSON → standard reading ────────────────────────────────

def normalise(raw: dict, prev_people: int = 0, prev_event_rate: float = 0.5) -> dict:
    lat    = _f(raw, "lat", "latitude",  "Lat",  "latitude_deg",  "gps_lat")
    lon    = _f(raw, "lon", "lng", "longitude", "Lon", "longitude_deg", "gps_lon")
    gps_ok = _gps_valid(raw, lat, lon)
    roll, pitch, yaw = _tilt(raw)

    mq135 = _f(raw, "mq135", "MQ135", "so2", "SO2", "air_quality", "airQuality")

    return {
        "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "temperature":     round(_f(raw, "temperature", "temp",  "Temp",  "Temperature"), 2),
        "humidity":        round(_f(raw, "humidity",    "hum",   "Hum",   "Humidity"),    2),
        "pressure":        round(_f(raw, "pressure",    "press", "Press", "Pressure",
                                        default=1013.25), 2),
        "lat":             round(lat, 6) if gps_ok else None,
        "lon":             round(lon, 6) if gps_ok else None,
        "gps_valid":       gps_ok,
        "gps_satellites":  int(_f(raw, "gpsSats", "gps_sats", "satellites", "sats", "numSats")),
        "roll":            roll,
        "pitch":           pitch,
        "yaw":             yaw,
        "water_detected":  _b(raw, "waterDetected", "water_detected", "water",
                                   "waterSensor", "flood", "water_sensor"),
        "mq2":             round(_f(raw, "mq2",  "MQ2"),  2),
        "mq4":             round(_f(raw, "mq4",  "MQ4"),  2),
        "mq135":           round(mq135, 2),
        "air_toxicity":    round(mq135, 2),   # kept for backward compatibility
        "people_detected": prev_people,        # filled by detect.py via detection_state.json
        "event_rate":      prev_event_rate,    # filled by anomaly_detector.py
    }


# ── Log helpers ────────────────────────────────────────────────────────────────

def _load_log() -> list:
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_log(records: list, max_records: int):
    LOG_PATH.write_text(json.dumps(records[-max_records:], indent=2), encoding="utf-8")


def _last_people_and_rate() -> tuple[int, float]:
    try:
        records = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        if records:
            last = records[-1]
            return int(last.get("people_detected", 0)), float(last.get("event_rate", 0.5))
    except Exception:
        pass
    return 0, 0.5


# ── Main loop ──────────────────────────────────────────────────────────────────

def run(interval: float, max_records: int):
    print()
    print("=" * 68)
    print("  AEGIS Sensor Reader")
    print(f"  Board  : http://{SENSOR_IP}")
    print(f"  Log    : {LOG_PATH}")
    print(f"  Poll   : every {interval}s  |  keep {max_records} records")
    print("=" * 68)
    print()

    errors = 0

    while True:
        raw = _fetch()
        ts  = datetime.now().strftime("%H:%M:%S")

        if raw is None:
            errors += 1
            print(
                f"\r[{ts}]  Board unreachable (attempt {errors})           ",
                end="", flush=True,
            )
            time.sleep(interval)
            continue

        errors = 0
        prev_ppl, prev_evr = _last_people_and_rate()
        reading = normalise(raw, prev_ppl, prev_evr)

        records = _load_log()
        records.append(reading)
        _write_log(records, max_records)

        gps_str   = (
            f"GPS:{reading['lat']:.5f},{reading['lon']:.5f}({reading['gps_satellites']}sat)"
            if reading["gps_valid"] else "GPS:no-fix"
        )
        water_str = "WATER:YES" if reading["water_detected"] else "water:no"

        print(
            f"\r[{reading['timestamp']}]  "
            f"T:{reading['temperature']:.1f}°  "
            f"H:{reading['humidity']:.0f}%  "
            f"P:{reading['pressure']:.0f}hPa  "
            f"MQ2:{reading['mq2']:.1f}  "
            f"MQ4:{reading['mq4']:.1f}  "
            f"SO2:{reading['mq135']:.1f}  "
            f"R:{reading['roll']:.1f}° Pt:{reading['pitch']:.1f}°  "
            f"{gps_str}  {water_str}",
            end="", flush=True,
        )

        if reading["mq2"] >= 40:
            print(
                f"\n  *** CRITICAL — MQ2 EXPLOSIVE GAS {reading['mq2']:.1f}% — EVACUATE IMMEDIATELY ***",
                flush=True,
            )

        time.sleep(interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AEGIS Sensor Reader — polls http://10.161.238.74")
    ap.add_argument("--interval",    type=float, default=2.0,
                    help="Poll interval in seconds (default 2)")
    ap.add_argument("--max-records", type=int,   default=200,
                    help="Max readings to keep in sensor_log.json (default 200)")
    args = ap.parse_args()
    run(interval=args.interval, max_records=args.max_records)
