"""
AEGIS Weather Sensor Bridge
============================
Gets the real GPS position from the browser via a tiny local HTTP server
(the dashboard calls navigator.geolocation and POSTs to localhost:8766/gps).

Once GPS arrives, fetches live weather from Open-Meteo for those coords.
Falls back to IP geolocation until the browser sends real coords.

Run:
    python weather_sensor.py
"""

import json
import random
import threading
import time
import argparse
import urllib.request
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

LOG_PATH    = Path("sensor_log.json")
WEATHER_TTL = 60.0   # seconds between weather re-fetches
GPS_PORT    = 8766

# ── Shared GPS state (updated by browser POST) ────────────────────────────────
_gps_lock   = threading.Lock()
_gps        = {"lat": None, "lon": None, "source": "waiting"}


def _set_gps(lat: float, lon: float, source: str = "browser"):
    with _gps_lock:
        _gps["lat"]    = lat
        _gps["lon"]    = lon
        _gps["source"] = source


def _get_gps() -> dict:
    with _gps_lock:
        return dict(_gps)


# ── Small GPS receiver server (browser POSTs here) ───────────────────────────

class _GPSHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/gps"):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data = json.loads(body)
            lat  = float(data["lat"])
            lon  = float(data["lon"])
            _set_gps(lat, lon, "browser")
            print(f"\n[GPS] Browser sent real coords → {lat:.5f}, {lon:.5f}")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            self.send_response(400); self.end_headers()

    def do_GET(self):
        if not self.path.startswith("/gps"):
            self.send_response(404); self.end_headers(); return
        gps = _get_gps()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(gps).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *_):
        pass


threading.Thread(
    target=HTTPServer(("0.0.0.0", GPS_PORT), _GPSHandler).serve_forever,
    daemon=True,
).start()


# ── IP geolocation fallback ───────────────────────────────────────────────────

def _ip_geolocation() -> tuple[float, float, str]:
    try:
        with urllib.request.urlopen("http://ip-api.com/json/", timeout=6) as r:
            data = json.loads(r.read().decode())
        if data.get("status") == "success":
            return float(data["lat"]), float(data["lon"]), data.get("city", "Unknown")
    except Exception:
        pass
    return 12.9202, 77.6016, "Bengaluru (default)"


# ── Open-Meteo weather fetch ──────────────────────────────────────────────────

def _fetch_weather(lat: float, lon: float) -> dict | None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,surface_pressure"
        "&timezone=auto"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read().decode())
        cur = data.get("current", {})
        t, h, p = cur.get("temperature_2m"), cur.get("relative_humidity_2m"), cur.get("surface_pressure")
        if None not in (t, h, p):
            return {"temperature": t, "humidity": h, "pressure": p}
    except Exception as e:
        print(f"\n[weather] Open-Meteo failed: {e}")
    return None


# ── Simulated sensors ─────────────────────────────────────────────────────────

def _gas():
    return {
        "mq2":   round(random.uniform(1.5, 5.0),  2),
        "mq4":   round(random.uniform(0.5, 3.0),  2),
        "mq135": round(random.uniform(18.0, 38.0), 2),
    }

def _gyro():
    return {
        "roll":  round(random.uniform(-1.2, 1.2), 2),
        "pitch": round(random.uniform(-0.8, 0.8), 2),
        "yaw":   round(random.uniform(-2.0, 2.0), 2),
    }


# ── Log helpers ───────────────────────────────────────────────────────────────

def _load_log() -> list:
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def _write_log(records, max_records):
    LOG_PATH.write_text(json.dumps(records[-max_records:], indent=2), encoding="utf-8")

def _last_people() -> int:
    try:
        recs = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        return int(recs[-1].get("people_detected", 0)) if recs else 0
    except Exception:
        return 0


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(interval: float, max_records: int):
    print()
    print("=" * 68)
    print("  AEGIS Weather Sensor Bridge")
    print(f"  GPS receiver : http://localhost:{GPS_PORT}/gps  (browser will POST here)")
    print("  Fetching IP-based location as fallback...")

    ip_lat, ip_lon, ip_city = _ip_geolocation()
    _set_gps(ip_lat, ip_lon, f"ip ({ip_city})")
    print(f"  IP location  : {ip_city}  ({ip_lat:.4f}, {ip_lon:.4f})")
    print(f"  Waiting for browser GPS — open the dashboard to send real coords")
    print(f"  Log          : {LOG_PATH}")
    print(f"  Poll         : every {interval}s  |  keep {max_records} records")
    print("=" * 68 + "\n")

    weather_cache: dict | None = None
    weather_ts   : float       = 0.0
    last_coords  : tuple       = (None, None)

    while True:
        gps = _get_gps()
        lat, lon = gps["lat"], gps["lon"]

        # Re-fetch weather if coords changed or TTL expired
        coords_changed = (lat, lon) != last_coords
        if weather_cache is None or coords_changed or (time.time() - weather_ts) > WEATHER_TTL:
            fresh = _fetch_weather(lat, lon)
            if fresh:
                weather_cache = fresh
                weather_ts    = time.time()
                last_coords   = (lat, lon)
            elif weather_cache is None:
                weather_cache = {"temperature": 28.5, "humidity": 65.0, "pressure": 1013.25}

        w     = weather_cache
        gas   = _gas()
        gyro  = _gyro()
        mq135 = gas["mq135"]

        reading = {
            "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temperature":     round(float(w["temperature"]), 2),
            "humidity":        round(float(w["humidity"]),    2),
            "pressure":        round(float(w["pressure"]),    2),
            "lat":             round(lat, 6),
            "lon":             round(lon, 6),
            "gps_valid":       True,
            "gps_satellites":  8,
            "roll":            gyro["roll"],
            "pitch":           gyro["pitch"],
            "yaw":             gyro["yaw"],
            "water_detected":  False,
            "mq2":             gas["mq2"],
            "mq4":             gas["mq4"],
            "mq135":           mq135,
            "air_toxicity":    mq135,
            "people_detected": _last_people(),
            "event_rate":      0.5,
        }

        records = _load_log()
        records.append(reading)
        _write_log(records, max_records)

        src = gps["source"]
        print(
            f"\r[{reading['timestamp']}]  "
            f"T:{reading['temperature']:.1f}°C  "
            f"H:{reading['humidity']:.0f}%  "
            f"P:{reading['pressure']:.1f}hPa  "
            f"MQ2:{reading['mq2']:.1f}  MQ4:{reading['mq4']:.1f}  SO2:{reading['mq135']:.1f}  "
            f"GPS({src}):{lat:.4f},{lon:.4f}",
            end="", flush=True,
        )

        time.sleep(interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AEGIS Weather Sensor Bridge")
    ap.add_argument("--interval",    type=float, default=2.0)
    ap.add_argument("--max-records", type=int,   default=200)
    args = ap.parse_args()
    run(interval=args.interval, max_records=args.max_records)
