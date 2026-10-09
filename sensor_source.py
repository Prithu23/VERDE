"""
VERDE sensor sources
====================
Everything the fusion engine knows about the world comes through this file:

  BoardSensor      – the rover's sensor board over HTTP (JSON or CSV)
  read_vision()    – what detect.py currently sees (detection_state.json, mission_log.json)
  read_audio()     – what audio_detect.py currently hears (audio_state.json, audio_log.json)

Rule for this module: never invent a value. A sensor that is missing from the
board's reply is reported as None, and a source that has gone quiet is reported
as offline. Nothing is filled in with a "typical" number.
"""

from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent

DEFAULT_SENSOR_IP = os.environ.get("VERDE_SENSOR_IP", "10.161.238.74")
ENDPOINTS = ["/data", "/csv", "/sensor", "/sensors", "/all", "/readings", "/"]

TS_FMT = "%Y-%m-%d %H:%M:%S"

# How old a source's last update may be before it counts as offline (seconds)
VISION_MAX_AGE = 5.0
AUDIO_MAX_AGE = 5.0

# Numeric fields a reading can carry. Any of them may be None.
NUMERIC_FIELDS = ("temperature", "humidity", "pressure", "mq2", "mq4", "mq135",
                  "roll", "pitch", "yaw")

# Aliases seen in ESP32 sketches → canonical key (compared lower-case)
_ALIASES = {
    "temperature": "temperature", "temp": "temperature", "t": "temperature",
    "humidity": "humidity", "hum": "humidity", "h": "humidity", "rh": "humidity",
    "pressure": "pressure", "press": "pressure", "p": "pressure",
    "mq2": "mq2", "mq-2": "mq2", "mq_2": "mq2",
    "mq4": "mq4", "mq-4": "mq4", "mq_4": "mq4",
    "mq135": "mq135", "mq-135": "mq135", "mq_135": "mq135", "so2": "mq135",
    "air_quality": "mq135", "airquality": "mq135", "air_toxicity": "mq135",
    "lat": "lat", "latitude": "lat", "lat_deg": "lat", "gps_lat": "lat",
    "lon": "lon", "lng": "lon", "longitude": "lon", "lon_deg": "lon", "gps_lon": "lon",
    "roll": "roll", "rollangle": "roll", "roll_angle": "roll",
    "pitch": "pitch", "pitchangle": "pitch", "pitch_angle": "pitch",
    "yaw": "yaw", "yawangle": "yaw", "yaw_angle": "yaw", "heading": "yaw",
    "accelx": "ax", "ax": "ax", "accx": "ax", "accel_x": "ax",
    "accely": "ay", "ay": "ay", "accy": "ay", "accel_y": "ay",
    "accelz": "az", "az": "az", "accz": "az", "accel_z": "az",
    "water": "water", "waterdetected": "water", "water_detected": "water",
    "watersensor": "water", "water_sensor": "water", "flood": "water",
    "gpsfix": "gps_fix", "gps_fix": "gps_fix", "gps_valid": "gps_fix", "fix": "gps_fix",
    "gps_lock": "gps_fix", "hasfix": "gps_fix",
    "gpssats": "gps_sats", "gps_sats": "gps_sats", "sats": "gps_sats",
    "satellites": "gps_sats", "numsats": "gps_sats", "num_sats": "gps_sats",
}

# Order assumed when the board sends one bare line of numbers
_POSITIONAL = ["temperature", "humidity", "pressure", "mq2", "mq4", "mq135", "lat", "lon"]


def now_str() -> str:
    return datetime.now().strftime(TS_FMT)


def parse_ts(ts) -> datetime | None:
    try:
        return datetime.strptime(str(ts), TS_FMT)
    except Exception:
        return None


def age_seconds(ts, now: datetime | None = None) -> float | None:
    """Seconds since timestamp `ts`, or None if it cannot be parsed."""
    dt = parse_ts(ts)
    if dt is None:
        return None
    return ((now or datetime.now()) - dt).total_seconds()


def load_json(name: str, default):
    try:
        return json.loads((ROOT / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(name: str, data) -> None:
    """Write via a temp file so the dashboard never reads a half-written file."""
    path = ROOT / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:                       # Windows: target briefly locked by a reader
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ─── Sensor board ──────────────────────────────────────────────────────────────

def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _truthy(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    n = _num(v)
    if n is not None:
        return n != 0
    return str(v).strip().lower() not in ("", "0", "false", "no", "none", "off", "dry")


def _canon(raw: dict) -> dict:
    """Map whatever keys the board used onto canonical ones (first one wins)."""
    out: dict = {}
    for k, v in raw.items():
        key = _ALIASES.get(str(k).strip().lower())
        if key and key not in out:
            out[key] = v
    return out


def parse_payload(text: str) -> dict | None:
    """Accept JSON, `key=value,...`, header+row CSV, or one bare CSV row."""
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data:
            return data
    except ValueError:
        pass

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None

    if len(lines) == 1 and ("=" in lines[0] or ":" in lines[0]):
        sep = "=" if "=" in lines[0] else ":"
        d = {}
        for part in lines[0].split(","):
            if sep in part:
                k, v = part.split(sep, 1)
                d[k.strip()] = v.strip()
        return d or None

    if len(lines) >= 2:
        headers = [h.strip() for h in lines[0].split(",")]
        values = [v.strip() for v in lines[-1].split(",")]
        if len(headers) == len(values) and any(_num(h) is None for h in headers):
            return dict(zip(headers, values))

    parts = [p.strip() for p in lines[-1].split(",")]
    if len(parts) >= 3 and all(_num(p) is not None for p in parts[:3]):
        return {(_POSITIONAL[i] if i < len(_POSITIONAL) else f"field{i}"): p
                for i, p in enumerate(parts)}
    return None


def normalise(raw: dict) -> dict:
    """Board payload → standard reading. Missing sensors stay None."""
    c = _canon(raw)

    roll, pitch, yaw = _num(c.get("roll")), _num(c.get("pitch")), _num(c.get("yaw"))
    if roll is None and pitch is None:
        ax, ay, az = _num(c.get("ax")), _num(c.get("ay")), _num(c.get("az"))
        if ax is not None and ay is not None and az is not None and (ax or ay or az):
            roll = math.degrees(math.atan2(ay, az))
            pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))

    lat, lon = _num(c.get("lat")), _num(c.get("lon"))
    fix = _truthy(c.get("gps_fix"))
    has_coords = lat is not None and lon is not None and (abs(lat) > 0.001 or abs(lon) > 0.001)
    gps_ok = bool(has_coords and (fix is None or fix))
    sats = _num(c.get("gps_sats"))

    def r(v, nd=2):
        return None if v is None else round(v, nd)

    return {
        "timestamp":      now_str(),
        "temperature":    r(_num(c.get("temperature"))),
        "humidity":       r(_num(c.get("humidity"))),
        "pressure":       r(_num(c.get("pressure"))),
        "mq2":            r(_num(c.get("mq2"))),
        "mq4":            r(_num(c.get("mq4"))),
        "mq135":          r(_num(c.get("mq135"))),
        "roll":           r(roll),
        "pitch":          r(pitch),
        "yaw":            r(yaw),
        "water_detected": _truthy(c.get("water")),
        "lat":            round(lat, 6) if gps_ok else None,
        "lon":            round(lon, 6) if gps_ok else None,
        "gps_valid":      gps_ok,
        "gps_satellites": int(sats) if sats is not None else None,
    }


class BoardSensor:
    """Polls the rover's sensor board. read() returns None when it is unreachable."""

    origin = "board"

    def __init__(self, ip: str = DEFAULT_SENSOR_IP, timeout: float = 2.0):
        self.ip = ip
        self.timeout = timeout
        self._endpoint: str | None = None      # remembered once one answers

    def _get(self, ep: str) -> dict | None:
        try:
            with urllib.request.urlopen(f"http://{self.ip}{ep}", timeout=self.timeout) as r:
                return parse_payload(r.read().decode(errors="replace"))
        except Exception:
            return None

    def read(self) -> dict | None:
        candidates = [self._endpoint] if self._endpoint else ENDPOINTS
        for ep in candidates:
            raw = self._get(ep)
            if raw:
                reading = normalise(raw)
                if any(reading[k] is not None for k in NUMERIC_FIELDS) \
                        or reading["water_detected"] is not None:
                    self._endpoint = ep
                    return reading
        self._endpoint = None                  # re-probe all endpoints next time
        return None


# ─── Camera (detect.py) ────────────────────────────────────────────────────────

def read_vision(now: datetime | None = None) -> dict:
    """Current camera state. `live` is False if detect.py has stopped updating."""
    now = now or datetime.now()
    state = load_json("detection_state.json", None)
    out = {"live": False, "age_s": None, "source": None,
           "people": 0, "rubble": 0, "spills": 0, "fps": None, "damage_levels": []}
    if not isinstance(state, dict):
        return out

    age = age_seconds(state.get("timestamp"), now)
    out["age_s"] = None if age is None else round(age, 1)
    out["source"] = state.get("source")
    if age is None or age > VISION_MAX_AGE or age < -VISION_MAX_AGE:
        return out

    out.update(live=True,
               people=int(_num(state.get("people")) or 0),
               rubble=int(_num(state.get("rubble")) or 0),
               spills=int(_num(state.get("spills")) or 0),
               fps=_num(state.get("fps")))

    # Damage classes (level1/2/3) are only in the mission log
    log = load_json("mission_log.json", [])
    if isinstance(log, list):
        for e in log[-30:]:
            a = age_seconds(e.get("time"), now) if isinstance(e, dict) else None
            if a is not None and 0 <= a <= 15:
                out["damage_levels"] += [str(d.get("type", "")) for d in e.get("damage", [])
                                         if isinstance(d, dict)]
    return out


# ─── Microphone (audio_detect.py) ──────────────────────────────────────────────

def read_audio(now: datetime | None = None, window_s: float = 30.0) -> dict:
    """Recent audio events. `live` comes from audio_detect.py's heartbeat file."""
    now = now or datetime.now()
    out = {"live": False, "age_s": None, "events": [], "scores": None, "state_ts": None}

    state = load_json("audio_state.json", None)
    if isinstance(state, dict):
        age = age_seconds(state.get("timestamp"), now)
        out["age_s"] = None if age is None else round(age, 1)
        out["live"] = age is not None and -AUDIO_MAX_AGE <= age <= AUDIO_MAX_AGE
        out["state_ts"] = state.get("timestamp")
        if isinstance(state.get("scores"), dict):
            out["scores"] = state["scores"]

    if not out["live"]:
        return out                              # old log entries are not evidence

    log = load_json("audio_log.json", [])
    if isinstance(log, list):
        for e in log[-200:]:
            if not isinstance(e, dict):
                continue
            a = age_seconds(e.get("time"), now)
            if a is not None and 0 <= a <= window_s:
                out["events"].append({
                    "age_s": a,
                    "category": str(e.get("category", "")),
                    "specific": str(e.get("specific", "")),
                    "confidence": float(_num(e.get("confidence")) or 0.0),
                })
    return out
