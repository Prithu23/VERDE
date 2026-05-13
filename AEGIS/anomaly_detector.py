"""
AEGIS Time-Series Anomaly Detector
===================================
Detects slow creeps, statistical outliers, trend shifts, event bursts, and
correlated multi-sensor anomalies — things static thresholds will miss.

Run (simulation):  python anomaly_detector.py --mode sim
Run (real HW):     python anomaly_detector.py --mode real --port COM3
                   python anomaly_detector.py --mode real --port /dev/ttyUSB0

To swap in real sensors: implement RealSensorInput.read()
Everything else (detection, logging, frontend) stays unchanged.
"""

import json
import math
import time
import random
import argparse
from datetime import datetime
from collections import deque


# =============================================================================
# SENSOR INTERFACE  — swap SimulatedSensorInput for RealSensorInput in prod
# =============================================================================

class SensorInput:
    """Abstract base. Subclass and implement read() for real hardware."""

    def read(self) -> dict:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SIMULATION  — 6 scenarios that cycle automatically
# ---------------------------------------------------------------------------

class SimulatedSensorInput(SensorInput):
    """
    Generates realistic multi-sensor data with injected anomaly scenarios.
    Each scenario runs for `scenario_interval` seconds then cycles.
    """

    SCENARIOS = [
        "normal",
        "temperature_creep",
        "gas_leak_buildup",
        "humidity_drop",
        "burst_events",
        "multi_sensor_drift",
    ]

    BASE = dict(
        temperature=28.5,
        humidity=65.0,
        pressure=1013.0,
        mq2=12.0,
        mq4=8.0,
        air_toxicity=15.0,
        people_detected=0,
        event_rate=0.5,
    )

    def __init__(self, scenario_interval: int = 60):
        self._t = 0
        self._scenario_idx = 0
        self._scenario_start = 0
        self._interval = scenario_interval

    def _n(self, sigma: float = 1.0) -> float:
        return random.gauss(0, sigma)

    def read(self) -> dict:
        self._t += 1
        elapsed = self._t - self._scenario_start

        if elapsed >= self._interval:
            self._scenario_idx = (self._scenario_idx + 1) % len(self.SCENARIOS)
            self._scenario_start = self._t
            elapsed = 0
            print(f"\n  [SIM] ▶ Scenario → {self.SCENARIOS[self._scenario_idx]}")

        scenario = self.SCENARIOS[self._scenario_idx]
        p = elapsed / max(self._interval, 1)
        B = self.BASE

        temp     = B["temperature"]  + self._n(0.3)
        humidity = B["humidity"]     + self._n(0.5)
        pressure = B["pressure"]     + self._n(0.4)
        mq2      = B["mq2"]          + self._n(0.8)
        mq4      = B["mq4"]          + self._n(0.6)
        toxicity = B["air_toxicity"] + self._n(0.5)
        people   = max(0, round(self._n(0.3)))
        evt_rate = max(0.0, B["event_rate"] + self._n(0.1))

        if scenario == "temperature_creep":
            temp     += p * 8.0  + self._n(0.2)
            humidity -= p * 5.0
        elif scenario == "gas_leak_buildup":
            mq2      += p * 22.0 + self._n(1.0)
            mq4      += p * 15.0 + self._n(0.8)
            toxicity += p * 30.0 + self._n(1.5)
        elif scenario == "humidity_drop":
            drop      = min(p * 42.0, 38.0)
            humidity -= drop     + self._n(1.0)
            temp     += p * 3.0  + self._n(0.3)
        elif scenario == "burst_events":
            if p > 0.3:
                evt_rate = 5.5   + self._n(0.5)
                people   = random.randint(2, 5)
        elif scenario == "multi_sensor_drift":
            drift     = math.sin(p * math.pi) * 12
            temp     += drift * 0.4  + self._n(0.2)
            mq2      += drift * 1.2  + self._n(0.5)
            toxicity += drift * 1.8  + self._n(0.5)

        return {
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temperature":      round(max(0.0, temp),          2),
            "humidity":         round(max(0.0, min(100, humidity)), 2),
            "pressure":         round(pressure,                2),
            "mq2":              round(max(0.0, mq2),           2),
            "mq4":              round(max(0.0, mq4),           2),
            "air_toxicity":     round(max(0.0, min(100, toxicity)), 2),
            "people_detected":  int(people),
            "event_rate":       round(evt_rate, 3),
            "_scenario":        scenario,
        }


# ---------------------------------------------------------------------------
# REAL HARDWARE STUB
# ---------------------------------------------------------------------------

class RealSensorInput(SensorInput):
    """
    Replace read() with actual hardware reads.
    Expected firmware JSON line on serial:
    {"temperature":29.1,"humidity":63.4,"pressure":1012.8,
     "mq2":13.2,"mq4":9.1,"air_toxicity":16.0,
     "people_detected":0,"event_rate":0.5}
    """

    def __init__(self, serial_port: str = "/dev/ttyUSB0", baud: int = 9600):
        # TODO(REAL_SENSORS): import serial; self.ser = serial.Serial(...)
        raise NotImplementedError(
            "RealSensorInput: wire up your hardware in __init__ and read()"
        )

    def read(self) -> dict:
        # TODO(REAL_SENSORS):
        # line = self.ser.readline().decode("utf-8").strip()
        # data = json.loads(line)
        # data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # return data
        raise NotImplementedError


# =============================================================================
# DETECTION ALGORITHMS
# =============================================================================

class CUSUM:
    def __init__(self, target: float, k: float = 1.0, h: float = 8.0):
        self.target = target
        self.k = k
        self.h = h
        self.S_pos = 0.0
        self.S_neg = 0.0

    def update(self, value: float) -> tuple:
        dev = value - self.target
        self.S_pos = max(0.0, self.S_pos + dev   - self.k)
        self.S_neg = max(0.0, self.S_neg - dev   - self.k)
        if self.S_pos > self.h:
            return True, "rising",  self.S_pos
        if self.S_neg > self.h:
            return True, "falling", self.S_neg
        return False, None, 0.0

    def reset(self):
        self.S_pos = 0.0
        self.S_neg = 0.0


def rolling_zscore(history: deque, current: float, window: int = 30) -> float:
    arr = list(history)[-window:]
    if len(arr) < 5:
        return 0.0
    n    = len(arr)
    mean = sum(arr) / n
    var  = sum((x - mean) ** 2 for x in arr) / n
    std  = math.sqrt(var) if var > 0 else 0.0
    return (current - mean) / std if std > 0 else 0.0


def trend_slope(history: deque, window: int = 15) -> float:
    arr = list(history)[-window:]
    n   = len(arr)
    if n < 3:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(arr) / n
    num    = sum((i - x_mean) * (arr[i] - y_mean) for i in range(n))
    den    = sum((i - x_mean) ** 2               for i in range(n))
    return num / den if den > 0 else 0.0


def burst_ratio(history: deque, short: int = 10, long: int = 20) -> float:
    arr = list(history)
    if len(arr) < short + long:
        return 1.0
    short_mean = sum(arr[-short:])        / short
    long_mean  = sum(arr[-short-long:-short]) / long
    return short_mean / long_mean if long_mean > 0 else 1.0


# =============================================================================
# SENSOR CONFIG
# =============================================================================

SENSOR_CFG = {
    "temperature":  (28.5,  0.8, 7.0,  2.5, 0.15),
    "humidity":     (65.0,  1.0, 8.0,  2.5, 0.20),
    "pressure":     (1013.0,0.5, 6.0,  3.0, 0.05),
    "mq2":          (12.0,  0.8, 6.0,  2.0, 0.20),
    "mq4":          (8.0,   0.6, 5.0,  2.0, 0.15),
    "air_toxicity": (15.0,  0.8, 6.0,  2.0, 0.25),
    "event_rate":   (0.5,   0.3, 4.0,  2.5, 0.10),
}

ANOMALY_TYPE = {
    "temperature":  {"rising": "HEAT_RISE",   "falling": "COOLING"},
    "humidity":     {"rising": "FLOOD_RISK",  "falling": "FIRE_RISK"},
    "mq2":          {"rising": "GAS_LEAK",    "falling": "CLEARING"},
    "mq4":          {"rising": "GAS_LEAK",    "falling": "CLEARING"},
    "air_toxicity": {"rising": "TOXIC_BUILD", "falling": "CLEARING"},
    "event_rate":   {"rising": "SURGE",       "falling": "QUIET"},
    "pressure":     {"rising": "PRESSURE",    "falling": "PRESSURE"},
    "multi":        {"rising": "COMPOUND",    "falling": "COMPOUND"},
}


# =============================================================================
# ANOMALY DETECTOR
# =============================================================================

class AnomalyDetector:

    def __init__(self, history_len: int = 200):
        self.histories = {k: deque(maxlen=history_len) for k in SENSOR_CFG}
        self.cusums    = {k: CUSUM(cfg[0], cfg[1], cfg[2])
                          for k, cfg in SENSOR_CFG.items()}
        self.anomaly_log: list = []
        self._load_existing()

    def _load_existing(self):
        try:
            with open("anomaly_log.json") as f:
                self.anomaly_log = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.anomaly_log = []

    def _save(self):
        with open("anomaly_log.json", "w") as f:
            json.dump(self.anomaly_log[-500:], f, indent=2)

    def process(self, reading: dict) -> list:
        detected = []
        ts = reading.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        for sensor, cfg in SENSOR_CFG.items():
            if sensor not in reading:
                continue

            val = float(reading[sensor])
            target, k, h, z_thresh, slope_thresh = cfg
            hist = self.histories[sensor]
            hist.append(val)

            alarm, direction, magnitude = self.cusums[sensor].update(val)
            if alarm:
                atype = ANOMALY_TYPE.get(sensor, {}).get(direction, "DRIFT")
                detected.append(self._anomaly(
                    ts=ts, sensor=sensor, value=val, method="CUSUM",
                    atype=atype, direction=direction, score=round(magnitude, 2),
                    detail=(f"Persistent {direction} drift accumulated "
                            f"(CUSUM score {magnitude:.1f}, threshold {h}). "
                            f"Current {sensor}: {val} | Baseline: {target}. "
                            f"This pattern would evade static thresholds."),
                    severity=self._cusum_sev(magnitude, h),
                ))
                self.cusums[sensor].reset()

            z = rolling_zscore(hist, val)
            if abs(z) > z_thresh and len(hist) >= 10:
                dir_z  = "rising" if z > 0 else "falling"
                atype  = ANOMALY_TYPE.get(sensor, {}).get(dir_z, "SPIKE")
                detected.append(self._anomaly(
                    ts=ts, sensor=sensor, value=val, method="Z-SCORE",
                    atype=atype, direction=dir_z, score=round(abs(z), 2),
                    detail=(f"Statistical outlier: z = {z:+.2f} "
                            f"(threshold ±{z_thresh}). "
                            f"{sensor.replace('_',' ').title()} = {val} "
                            f"is {abs(z):.1f}σ from rolling mean."),
                    severity="HIGH" if abs(z) > z_thresh * 1.5 else "MEDIUM",
                ))

            slope = trend_slope(hist)
            if abs(slope) > slope_thresh and len(hist) >= 15:
                dir_s = "rising" if slope > 0 else "falling"
                detected.append(self._anomaly(
                    ts=ts, sensor=sensor, value=val, method="TREND",
                    atype="CREEP", direction=dir_s, score=round(abs(slope), 4),
                    detail=(f"Slow {dir_s} creep detected — "
                            f"slope {slope:+.4f} per sample "
                            f"(threshold ±{slope_thresh}). "
                            f"{sensor.replace('_',' ').title()} is "
                            f"{'rising' if slope > 0 else 'falling'} gradually."),
                    severity="LOW",
                ))

        if "event_rate" in reading and len(self.histories["event_rate"]) >= 30:
            ratio = burst_ratio(self.histories["event_rate"])
            if ratio > 4.0:
                detected.append(self._anomaly(
                    ts=ts, sensor="event_rate", value=reading["event_rate"],
                    method="BURST", atype="SURGE", direction="rising",
                    score=round(ratio, 2),
                    detail=(f"Detection event burst: {ratio:.1f}× normal rate. "
                            f"Possible mass-casualty event or structural collapse. "
                            f"Immediate area assessment required."),
                    severity="CRITICAL",
                ))

        drift_sensors = [
            s for s in ["temperature", "mq2", "air_toxicity"]
            if (len(self.histories[s]) >= 15
                and abs(trend_slope(self.histories[s]))
                    > SENSOR_CFG[s][4] * 0.65)
        ]
        if len(drift_sensors) >= 2:
            detected.append(self._anomaly(
                ts=ts, sensor="multi", value=None,
                method="CORRELATION", atype="COMPOUND", direction="rising",
                score=len(drift_sensors),
                detail=(f"Correlated drift across {len(drift_sensors)} sensors: "
                        f"{', '.join(drift_sensors)}. "
                        f"Pattern consistent with developing fire or chemical event. "
                        f"No single sensor exceeded its threshold."),
                severity="HIGH" if len(drift_sensors) >= 3 else "MEDIUM",
            ))

        for a in detected:
            self.anomaly_log.append(a)
            self._print(a)
        if detected:
            self._save()

        return detected

    def _anomaly(self, ts, sensor, value, method, atype,
                 direction, score, detail, severity) -> dict:
        return {
            "id":        f"{sensor}_{method}_{int(time.time()*1000)}",
            "timestamp": ts,
            "sensor":    sensor,
            "method":    method,
            "type":      atype,
            "direction": direction,
            "value":     value,
            "score":     score,
            "detail":    detail,
            "severity":  severity,
        }

    @staticmethod
    def _cusum_sev(magnitude: float, h: float) -> str:
        r = magnitude / h
        if r > 3.0: return "CRITICAL"
        if r > 2.0: return "HIGH"
        if r > 1.5: return "MEDIUM"
        return "LOW"

    @staticmethod
    def _print(a: dict):
        _C = {"CRITICAL": "\033[91m", "HIGH": "\033[93m",
              "MEDIUM": "\033[94m", "LOW": "\033[92m"}
        R = "\033[0m"
        c = _C.get(a["severity"], "")
        print(f"\n  {c}[{a['severity']:8}] [{a['method']:11}] "
              f"{a['sensor']:14} {a['type']:14}  {a['detail'][:80]}{R}")


# =============================================================================
# SENSOR LOG  — rolling window written every reading
# =============================================================================

_sensor_history: list = []
_SENSOR_LOG_MAX = 100


def _write_sensor_log(reading: dict):
    """Write clean sensor reading (no _scenario key) to sensor_log.json."""
    global _sensor_history
    clean = {k: v for k, v in reading.items() if not k.startswith("_")}
    _sensor_history.append(clean)
    if len(_sensor_history) > _SENSOR_LOG_MAX:
        _sensor_history = _sensor_history[-_SENSOR_LOG_MAX:]
    with open("sensor_log.json", "w") as f:
        json.dump(_sensor_history, f, indent=2)


# =============================================================================
# MAIN LOOP
# =============================================================================

def run(source: SensorInput, interval: float = 1.0):
    detector = AnomalyDetector()

    print()
    print("=" * 72)
    print("  AEGIS TIME-SERIES ANOMALY DETECTOR  —  VERDE Emergency Platform")
    print("=" * 72)
    print(f"  Algorithms : CUSUM | Rolling Z-Score | Trend Slope | Burst | Correlation")
    print(f"  Sensors    : {', '.join(SENSOR_CFG.keys())}")
    print(f"  Output     : anomaly_log.json + sensor_log.json")
    print("=" * 72)
    print()

    n = 0
    while True:
        try:
            reading = source.read()
            n += 1
            scenario = reading.get("_scenario", "real")

            print(
                f"\r[{reading['timestamp']}] #{n:4d} | "
                f"T={reading.get('temperature', 0):5.1f}°C  "
                f"H={reading.get('humidity', 0):5.1f}%  "
                f"MQ2={reading.get('mq2', 0):5.1f}  "
                f"Tox={reading.get('air_toxicity', 0):5.1f}%  "
                f"[{scenario}]",
                end="", flush=True,
            )

            _write_sensor_log(reading)
            detector.process(reading)
            time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n\nStopped after {n} readings.")
            print(f"Anomalies logged : {len(detector.anomaly_log)}")
            print(f"Saved to         : anomaly_log.json, sensor_log.json")
            break
        except Exception as exc:
            print(f"\n  [ERR] {exc}")
            time.sleep(interval)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AEGIS Time-Series Anomaly Detector")
    ap.add_argument("--mode", choices=["sim", "real"], default="sim")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--scenario-interval", type=int, default=60)
    args = ap.parse_args()

    if args.mode == "real":
        src = RealSensorInput(serial_port=args.port)
        print(f"Real sensor mode — port: {args.port}")
    else:
        src = SimulatedSensorInput(scenario_interval=args.scenario_interval)
        print(f"Simulation mode — {len(SimulatedSensorInput.SCENARIOS)} "
              f"scenarios × {args.scenario_interval}s each")

    run(src, interval=args.interval)
