"""
AEGIS Environmental Health Score (EHS) Calculator
===================================================
Reads all four sensor/detection logs and produces a single defensible
composite score per zone. Writes ehs_log.json every cycle.

Run alongside anomaly_detector.py:
    python ehs_calculator.py
    python ehs_calculator.py --interval 5 --zone "Zone A-12"
"""

import json
import time
import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path


# =============================================================================
# WEIGHTS  — must sum to 1.0
# =============================================================================

WEIGHTS = {
    "climate": 0.30,
    "visual":  0.30,
    "audio":   0.20,
    "anomaly": 0.20,
}


# =============================================================================
# PENALTY HELPERS
# =============================================================================

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def climate_subscore(sensor_readings: list) -> tuple[float, dict]:
    """
    0 = catastrophic environment, 100 = perfect.
    Uses the most recent sensor reading.
    """
    if not sensor_readings:
        return 100.0, {}

    r = sensor_readings[-1]
    penalties: dict = {}
    score = 100.0

    # Temperature  (safe 20–35 °C)
    temp = r.get("temperature", 28.5)
    if temp > 35:
        p = min((temp - 35) * 3.0, 30.0)
    elif temp < 20:
        p = min((20 - temp) * 2.0, 20.0)
    else:
        p = 0.0
    penalties["temperature"] = round(p, 2)
    score -= p

    # Humidity (safe 35–75 %)
    hum = r.get("humidity", 65.0)
    if hum < 35:
        p = min((35 - hum) * 1.5, 25.0)
    elif hum > 75:
        p = min((hum - 75) * 0.8, 12.0)
    else:
        p = 0.0
    penalties["humidity"] = round(p, 2)
    score -= p

    # MQ2 flammable gas (safe < 15 %)
    mq2 = r.get("mq2", 12.0)
    if mq2 > 15:
        p = min((mq2 - 15) * 2.0, 40.0)
    else:
        p = 0.0
    penalties["mq2"] = round(p, 2)
    score -= p

    # MQ4 methane (safe < 10 %)
    mq4 = r.get("mq4", 8.0)
    if mq4 > 10:
        p = min((mq4 - 10) * 1.5, 25.0)
    else:
        p = 0.0
    penalties["mq4"] = round(p, 2)
    score -= p

    # Air toxicity (safe < 20 %)
    tox = r.get("air_toxicity", 15.0)
    if tox > 20:
        p = min((tox - 20) * 1.2, 35.0)
    else:
        p = 0.0
    penalties["air_toxicity"] = round(p, 2)
    score -= p

    return _clamp(score), penalties


def visual_subscore(mission_log: list) -> tuple[float, dict]:
    """Based on last 10 mission_log entries."""
    if not mission_log:
        return 100.0, {}

    recent = mission_log[-10:]
    score = 100.0
    penalties: dict = {}

    max_people = max((e.get("people", 0) for e in recent), default=0)
    p = min(max_people * 15.0, 45.0)
    penalties["people"] = round(p, 2)
    score -= p

    damage_count = sum(len(e.get("damage", [])) for e in recent)
    p = min(damage_count * 3.0, 30.0)
    penalties["damage"] = round(p, 2)
    score -= p

    spill_count = sum(len(e.get("spills", [])) for e in recent)
    p = min(spill_count * 5.0, 20.0)
    penalties["spills"] = round(p, 2)
    score -= p

    return _clamp(score), penalties


def audio_subscore(audio_log: list) -> tuple[float, dict]:
    """Based on last 20 audio events."""
    if not audio_log:
        return 100.0, {}

    recent = audio_log[-20:]
    score = 100.0
    penalties: dict = {}

    categories = [e.get("category", "") for e in recent]
    specifics  = [e.get("specific", "")  for e in recent]

    fire_count = categories.count("Fire")
    p = min(fire_count * 25.0, 35.0)
    penalties["fire_sounds"] = round(p, 2)
    score -= p

    explosion_count = categories.count("Explosion/Collapse")
    p = min(explosion_count * 30.0, 40.0)
    penalties["explosion_sounds"] = round(p, 2)
    score -= p

    gas_count = categories.count("Gas Leak")
    p = min(gas_count * 20.0, 30.0)
    penalties["gas_sounds"] = round(p, 2)
    score -= p

    siren_count = categories.count("Siren")
    p = min(siren_count * 8.0, 15.0)
    penalties["sirens"] = round(p, 2)
    score -= p

    distress_keywords = {"Screaming", "Crying, sobbing", "Groan", "Whimper", "Shout"}
    distress = sum(1 for s in specifics if s in distress_keywords)
    p = min(distress * 8.0, 25.0)
    penalties["human_distress"] = round(p, 2)
    score -= p

    return _clamp(score), penalties


def _parse_dt(ts: str):
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.min


def anomaly_subscore(anomaly_log: list) -> tuple[float, dict]:
    """Based on anomalies logged in the last 5 minutes."""
    if not anomaly_log:
        return 100.0, {}

    cutoff = datetime.now() - timedelta(minutes=5)
    recent = [a for a in anomaly_log if _parse_dt(a.get("timestamp", "")) >= cutoff]

    score = 100.0
    penalties: dict = {}

    critical = sum(1 for a in recent if a.get("severity") == "CRITICAL")
    p = min(critical * 25.0, 55.0)
    penalties["critical_anomalies"] = round(p, 2)
    score -= p

    high = sum(1 for a in recent if a.get("severity") == "HIGH")
    p = min(high * 12.0, 35.0)
    penalties["high_anomalies"] = round(p, 2)
    score -= p

    medium = sum(1 for a in recent if a.get("severity") == "MEDIUM")
    p = min(medium * 5.0, 20.0)
    penalties["medium_anomalies"] = round(p, 2)
    score -= p

    compound = sum(1 for a in recent if a.get("method") == "CORRELATION")
    p = min(compound * 15.0, 25.0)
    penalties["compound_anomalies"] = round(p, 2)
    score -= p

    return _clamp(score), penalties


# =============================================================================
# GRADE + TREND
# =============================================================================

def grade(score: float) -> tuple[str, str]:
    """Returns (letter, status_label)."""
    if score >= 90: return "A", "EXCELLENT"
    if score >= 75: return "B", "GOOD"
    if score >= 60: return "C", "MODERATE"
    if score >= 40: return "D", "POOR"
    return "F", "CRITICAL"


def trend(history: list) -> str:
    """OLS slope over last 8 scores → IMPROVING / STABLE / DEGRADING."""
    arr = history[-8:]
    n = len(arr)
    if n < 3:
        return "STABLE"
    x_mean = (n - 1) / 2.0
    y_mean = sum(arr) / n
    num = sum((i - x_mean) * (arr[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den > 0 else 0.0
    if slope > 0.4:  return "IMPROVING"
    if slope < -0.4: return "DEGRADING"
    return "STABLE"


# =============================================================================
# LOAD HELPERS
# =============================================================================

def _load(path: str) -> list | dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _load_ehs_history() -> list:
    try:
        with open("ehs_log.json") as f:
            existing = json.load(f)
            return existing.get("score_history", [])
    except Exception:
        return []


# =============================================================================
# MAIN COMPUTE + WRITE
# =============================================================================

def compute(zone: str) -> dict:
    sensor_readings = _load("sensor_log.json")
    mission_log     = _load("mission_log.json")
    audio_log       = _load("audio_log.json")
    anomaly_log     = _load("anomaly_log.json")

    c_score, c_pen = climate_subscore(sensor_readings)
    v_score, v_pen = visual_subscore(mission_log)
    a_score, a_pen = audio_subscore(audio_log)
    n_score, n_pen = anomaly_subscore(anomaly_log)

    composite = round(
        c_score * WEIGHTS["climate"] +
        v_score * WEIGHTS["visual"]  +
        a_score * WEIGHTS["audio"]   +
        n_score * WEIGHTS["anomaly"],
        1,
    )

    history = _load_ehs_history()
    history.append(composite)
    history = history[-50:]           # keep last 50

    g, status = grade(composite)
    t = trend(history)

    result = {
        "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "zone":         zone,
        "score":        composite,
        "grade":        g,
        "status":       status,
        "trend":        t,
        "weights":      WEIGHTS,
        "sub_scores": {
            "climate": {"score": round(c_score, 1), "weight": WEIGHTS["climate"]},
            "visual":  {"score": round(v_score, 1), "weight": WEIGHTS["visual"]},
            "audio":   {"score": round(a_score, 1), "weight": WEIGHTS["audio"]},
            "anomaly": {"score": round(n_score, 1), "weight": WEIGHTS["anomaly"]},
        },
        "penalties": {**c_pen, **v_pen, **a_pen, **n_pen},
        "score_history": history,
    }

    with open("ehs_log.json", "w") as f:
        json.dump(result, f, indent=2)

    return result


def _color(score: float) -> str:
    if score >= 75: return "\033[92m"
    if score >= 60: return "\033[93m"
    if score >= 40: return "\033[33m"
    return "\033[91m"


def run(zone: str, interval: float):
    print()
    print("=" * 60)
    print("  AEGIS Environmental Health Score Calculator")
    print("=" * 60)
    print(f"  Zone     : {zone}")
    print(f"  Weights  : Climate {WEIGHTS['climate']*100:.0f}%  "
          f"Visual {WEIGHTS['visual']*100:.0f}%  "
          f"Audio {WEIGHTS['audio']*100:.0f}%  "
          f"Anomaly {WEIGHTS['anomaly']*100:.0f}%")
    print(f"  Output   : ehs_log.json")
    print("=" * 60)
    print()

    while True:
        try:
            result = compute(zone)
            c = _color(result["score"])
            R = "\033[0m"
            trend_sym = {"IMPROVING": "↑", "DEGRADING": "↓", "STABLE": "→"}.get(result["trend"], "→")
            print(
                f"\r[{result['timestamp']}]  "
                f"EHS: {c}{result['score']:5.1f}  {result['grade']}  "
                f"{result['status']:10}{R}  "
                f"C={result['sub_scores']['climate']['score']:5.1f}  "
                f"V={result['sub_scores']['visual']['score']:5.1f}  "
                f"Au={result['sub_scores']['audio']['score']:5.1f}  "
                f"An={result['sub_scores']['anomaly']['score']:5.1f}  "
                f"{trend_sym} {result['trend']}",
                end="", flush=True,
            )
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\nEHS Calculator stopped.")
            break
        except Exception as e:
            print(f"\n  [ERR] {e}")
            time.sleep(interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AEGIS EHS Calculator")
    ap.add_argument("--zone",     default="Zone A-12")
    ap.add_argument("--interval", type=float, default=5.0,
                    help="Seconds between recalculations (default 5)")
    args = ap.parse_args()
    run(zone=args.zone, interval=args.interval)
