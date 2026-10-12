"""
VERDE Time-Series Anomaly Detector
==================================
Catches what a threshold on the current value misses: slow creeps, sudden
jumps, steady trends, bursts of camera detections and several sensors drifting
together.

Nothing here assumes what "normal" is. Each sensor's normal level and noise are
learned from its own first readings (so 912 hPa in Bengaluru and 1013 hPa at
the coast are both simply "the baseline"), and the baseline is re-learned after
each alarm so a sensor that has settled at a new level stops alarming.

Gas sensors are fed in as the fusion engine's calibrated gas index, not the raw
analog value, so their scale is the same on every board.

Driven by coordinator.py. `python anomaly_detector.py` on its own runs the
detector against the built-in simulator, for demonstration.
"""

from __future__ import annotations

import math
import random
import statistics
import time
import argparse
from collections import deque
from datetime import datetime

from sensor_source import load_json, write_json


# =============================================================================
# SIMULATOR  (explicit --mode sim only)
# =============================================================================

class SimulatedSensorInput:
    """
    Synthetic sensor data with injected anomaly scenarios, for demonstrating the
    pipeline without hardware. Only used when --mode sim is asked for explicitly;
    the dashboard labels everything derived from it as SIMULATED.
    """

    origin = "simulation"

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
        mq135=15.0,
        air_toxicity=15.0,
        water_detected=False,
        roll=0.0,
        pitch=0.0,
        yaw=0.0,
        gps_valid=True,
        gps_satellites=7,
        lat=12.971599,
        lon=77.594563,
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
        toxicity = B["mq135"]        + self._n(0.5)
        people   = max(0, round(self._n(0.3)))
        evt_rate = max(0.0, B["event_rate"] + self._n(0.1))
        roll     = self._n(0.5)
        pitch    = self._n(0.5)
        water    = False
        # Simulate slow rover drift in GPS position
        lat = B["lat"] + self._t * 0.000002
        lon = B["lon"] + self._t * 0.000003

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
                water    = random.random() > 0.7
                roll     = self._n(3.0)
                pitch    = self._n(3.0)
        elif scenario == "multi_sensor_drift":
            drift     = math.sin(p * math.pi) * 12
            temp     += drift * 0.4  + self._n(0.2)
            mq2      += drift * 1.2  + self._n(0.5)
            toxicity += drift * 1.8  + self._n(0.5)

        return {
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temperature":      round(max(0.0, temp),               2),
            "humidity":         round(max(0.0, min(100, humidity)),  2),
            "pressure":         round(pressure,                      2),
            "lat":              round(lat, 6),
            "lon":              round(lon, 6),
            "gps_valid":        True,
            "gps_satellites":   random.randint(6, 10),
            "roll":             round(roll,  2),
            "pitch":            round(pitch, 2),
            "yaw":              round(self._n(1.0), 2),
            "water_detected":   water,
            "mq2":              round(max(0.0, mq2),                 2),
            "mq4":              round(max(0.0, mq4),                 2),
            "mq135":            round(max(0.0, min(100, toxicity)),  2),
            "air_toxicity":     round(max(0.0, min(100, toxicity)),  2),
            "people_detected":  int(people),
            "event_rate":       round(evt_rate, 3),
            "_scenario":        scenario,
        }


# =============================================================================
# DETECTION ALGORITHMS
# =============================================================================

class CUSUM:
    """Cumulative-sum drift detector around a target level."""

    def __init__(self, target: float, k: float, h: float):
        self.target, self.k, self.h = target, k, h
        self.S_pos = self.S_neg = 0.0

    def update(self, value: float) -> tuple:
        dev = value - self.target
        self.S_pos = max(0.0, self.S_pos + dev - self.k)
        self.S_neg = max(0.0, self.S_neg - dev - self.k)
        if self.S_pos > self.h:
            return True, "rising", self.S_pos
        if self.S_neg > self.h:
            return True, "falling", self.S_neg
        return False, None, 0.0

    def recentre(self, target: float):
        self.target = target
        self.S_pos = self.S_neg = 0.0


def rolling_zscore(history, current: float, floor: float, window: int = 30) -> float:
    """z-score against the previous `window` readings (current one excluded)."""
    arr = list(history)[-window - 1:-1]
    if len(arr) < 10:
        return 0.0
    mean = sum(arr) / len(arr)
    std = max(math.sqrt(sum((x - mean) ** 2 for x in arr) / len(arr)), floor)
    return (current - mean) / std


def trend_slope(history, window: int = 15) -> float:
    arr = list(history)[-window:]
    n = len(arr)
    if n < 3:
        return 0.0
    x_mean, y_mean = (n - 1) / 2.0, sum(arr) / n
    num = sum((i - x_mean) * (arr[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den > 0 else 0.0


def burst_ratio(history, short: int = 10, long: int = 20) -> float:
    arr = list(history)
    if len(arr) < short + long:
        return 1.0
    short_mean = sum(arr[-short:]) / short
    long_mean = sum(arr[-short - long:-short]) / long
    return short_mean / long_mean if long_mean > 0 else 1.0


# =============================================================================
# SENSOR CONFIG
# =============================================================================
# sensor: (noise floor, z-score threshold, slope threshold per reading)
# The noise floor is the smallest spread treated as real, so a sensor that
# reports in whole steps (a DHT11 moving 28 → 29 °C) does not look like an outlier.

SENSOR_CFG = {
    "temperature": (0.6, 3.5, 0.15),
    "humidity":    (1.5, 3.5, 0.25),
    "pressure":    (0.3, 4.0, 0.08),
    "mq2":         (1.0, 3.5, 0.25),     # gas index, 0 = clean-air baseline
    "mq4":         (1.0, 3.5, 0.25),
    "mq135":       (1.0, 3.5, 0.25),
    "event_rate":  (0.2, 3.5, 0.10),
}

WARMUP = 30          # readings used to learn a sensor's baseline
COOLDOWN = 20        # readings before the same sensor + method may report again
CUSUM_K = 1.0        # slack, in units of the sensor's noise
CUSUM_H = 6.0        # alarm threshold, in units of the sensor's noise

ANOMALY_TYPE = {
    "temperature": {"rising": "HEAT_RISE",   "falling": "COOLING"},
    "humidity":    {"rising": "HUMID",       "falling": "DRYING"},
    "mq2":         {"rising": "GAS_LEAK",    "falling": "CLEARING"},
    "mq4":         {"rising": "GAS_LEAK",    "falling": "CLEARING"},
    "mq135":       {"rising": "TOXIC_BUILD", "falling": "CLEARING"},
    "event_rate":  {"rising": "SURGE",       "falling": "QUIET"},
    "pressure":    {"rising": "PRESSURE",    "falling": "PRESSURE"},
    "multi":       {"rising": "COMPOUND",    "falling": "COMPOUND"},
}


# =============================================================================
# ANOMALY DETECTOR
# =============================================================================

class AnomalyDetector:

    def __init__(self, history_len: int = 200, fresh: bool = True):
        self.histories = {k: deque(maxlen=history_len) for k in SENSOR_CFG}
        self.cusums: dict = {}                 # created once a sensor's baseline is known
        self.sigma: dict = {}
        self._tick = 0
        self._last: dict = {}                  # (sensor, method) → tick of the last report
        self.anomaly_log: list = [] if fresh else (load_json("anomaly_log.json", []) or [])
        if fresh:
            self._save()

    def _save(self):
        write_json("anomaly_log.json", self.anomaly_log[-500:])

    def _learn(self, sensor: str) -> None:
        arr = list(self.histories[sensor])[-WARMUP:]
        med = statistics.median(arr)
        mad = statistics.median(abs(x - med) for x in arr)
        sigma = max(1.4826 * mad, SENSOR_CFG[sensor][0])
        self.sigma[sensor] = sigma
        if sensor in self.cusums:
            self.cusums[sensor].recentre(med)
            self.cusums[sensor].k, self.cusums[sensor].h = CUSUM_K * sigma, CUSUM_H * sigma
        else:
            self.cusums[sensor] = CUSUM(med, CUSUM_K * sigma, CUSUM_H * sigma)

    def process(self, reading: dict) -> list:
        detected = []
        self._tick += 1
        ts = reading.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        for sensor, (floor, z_thresh, slope_thresh) in SENSOR_CFG.items():
            val = reading.get(sensor)
            if val is None or isinstance(val, bool):
                continue                         # sensor absent or still calibrating
            val = float(val)
            hist = self.histories[sensor]
            hist.append(val)
            if len(hist) < WARMUP:
                continue
            if sensor not in self.cusums:
                self._learn(sensor)
                continue
            name = sensor.replace("_", " ").title()

            alarm, direction, magnitude = self.cusums[sensor].update(val)
            if alarm:
                base, h = self.cusums[sensor].target, self.cusums[sensor].h
                detected.append(self._anomaly(
                    ts=ts, sensor=sensor, value=val, method="CUSUM",
                    atype=ANOMALY_TYPE[sensor][direction], direction=direction,
                    score=round(magnitude / self.sigma[sensor], 2),
                    detail=(f"Persistent {direction} drift: {name} is now {val:g}, "
                            f"learned baseline {base:.4g}. The change built up gradually, "
                            f"so no single reading stood out."),
                    severity=self._cusum_sev(magnitude, h),
                ))
                self._learn(sensor)              # settle on the new level

            z = rolling_zscore(hist, val, floor)
            if abs(z) > z_thresh:
                dir_z = "rising" if z > 0 else "falling"
                detected.append(self._anomaly(
                    ts=ts, sensor=sensor, value=val, method="Z-SCORE",
                    atype=ANOMALY_TYPE[sensor][dir_z], direction=dir_z, score=round(abs(z), 2),
                    detail=(f"Sudden jump: {name} = {val:g} is {abs(z):.1f}σ from its "
                            f"recent average (threshold {z_thresh}σ)."),
                    severity="HIGH" if abs(z) > z_thresh * 1.5 else "MEDIUM",
                ))

            slope = trend_slope(hist)
            if abs(slope) > slope_thresh:
                dir_s = "rising" if slope > 0 else "falling"
                detected.append(self._anomaly(
                    ts=ts, sensor=sensor, value=val, method="TREND",
                    atype="CREEP", direction=dir_s, score=round(abs(slope), 4),
                    detail=(f"Steady {dir_s} trend: {name} changing {slope:+.3f} per reading "
                            f"over the last 15 readings."),
                    severity="LOW",
                ))

        if reading.get("event_rate") is not None and len(self.histories["event_rate"]) >= 30:
            ratio = burst_ratio(self.histories["event_rate"])
            if ratio > 4.0 and float(reading["event_rate"]) >= 0.3:
                detected.append(self._anomaly(
                    ts=ts, sensor="event_rate", value=reading["event_rate"],
                    method="BURST", atype="SURGE", direction="rising", score=round(ratio, 2),
                    detail=(f"Burst of rubble / spill detections: now in "
                            f"{float(reading['event_rate']):.0%} of camera frames, "
                            f"{ratio:.1f}× the earlier rate."),
                    severity="HIGH",
                ))

        drifting = [s for s in ("temperature", "mq2", "mq4", "mq135")
                    if len(self.histories[s]) >= WARMUP
                    and trend_slope(self.histories[s]) > SENSOR_CFG[s][2] * 0.65]
        if len(drifting) >= 2:
            detected.append(self._anomaly(
                ts=ts, sensor="multi", value=None, method="CORRELATION", atype="COMPOUND",
                direction="rising", score=len(drifting),
                detail=(f"{len(drifting)} sensors rising together: {', '.join(drifting)}. "
                        f"Consistent with a developing fire or gas release, though none "
                        f"has crossed its own threshold."),
                severity="HIGH" if len(drifting) >= 3 else "MEDIUM",
            ))

        # One report per sensor and method every COOLDOWN readings, so a long ramp
        # is a handful of entries rather than one per reading.
        fresh = []
        for a in detected:
            key = (a["sensor"], a["method"])
            if self._tick - self._last.get(key, -COOLDOWN) >= COOLDOWN:
                self._last[key] = self._tick
                fresh.append(a)
        detected = fresh

        for a in detected:
            self.anomaly_log.append(a)
        if detected:
            self.anomaly_log = self.anomaly_log[-500:]
            self._save()
        return detected

    @staticmethod
    def _anomaly(ts, sensor, value, method, atype, direction, score, detail, severity) -> dict:
        return {
            "id":        f"{sensor}_{method}_{int(time.time() * 1000)}_{random.randint(0, 999)}",
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
        return "CRITICAL" if r > 3.0 else "HIGH" if r > 2.0 else "MEDIUM" if r > 1.5 else "LOW"


# =============================================================================
# STANDALONE DEMO (simulator only)
# =============================================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="VERDE anomaly detector — simulator demo")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--scenario-interval", type=int, default=60)
    args = ap.parse_args()

    print("Simulator demo. For live data run:  python coordinator.py\n")
    src, det, n = SimulatedSensorInput(args.scenario_interval), AnomalyDetector(), 0
    try:
        while True:
            reading = src.read()
            n += 1
            for a in det.process(reading):
                print(f"[{a['severity']:8}] [{a['method']:11}] {a['sensor']:12} {a['detail']}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\nStopped after {n} readings, {len(det.anomaly_log)} anomalies.")
