"""
VERDE feature extraction
========================
Turns the three live inputs (sensor board, camera state, audio state) into one
flat row of measurements per tick. The recorder (record_trials.py) and the live
engine (fusion_engine.py) both use this class, so the model is trained on
exactly what it later sees.

There are no hazard thresholds in this file. It only measures:

  mq2_rise, mq4_rise, mq135_rise   fractional rise over the sensor's clean-air level
  temp, temp_rate                  °C, and °C per minute
  humidity                         %
  pressure_d1                      hPa change per minute
  tilt_deg, vibration_deg          degrees, and spread of roll/pitch over 10 s
  water                            0 / 1
  cam_people                       people in view (max of last 3 samples)
  cam_rubble_frac, cam_spill_frac  share of camera samples in the last 10 s showing it
  aud_fire, aud_collapse, aud_gas, aud_siren, aud_distress, aud_speech
                                   highest raw YAMNet score in the last 10 s

A feature is None when its source is offline or has not gathered enough
history yet. What the features mean for a hazard is decided by the trained
model, not here.

Signal-processing settings (not hazard thresholds): the clean-air level of each
gas sensor is the median of its first 30 readings; gas and temperature use a
median of the last three readings; windows are 10 s.
"""

from __future__ import annotations

import statistics
from collections import deque
from datetime import datetime, timedelta

SENSOR_MAX_AGE = 10.0        # s without a board reading before the board counts as offline
GAS_SENSORS = ("mq2", "mq4", "mq135")
GAS_WARMUP = 30              # readings used to learn the clean-air level
WINDOW = 10.0                # s, for camera fractions, audio maxima and vibration

AUDIO_KEYS = ("fire", "collapse", "gas", "siren", "distress", "speech")

BOARD_FEATURES = ("mq2_rise", "mq4_rise", "mq135_rise", "temp", "temp_rate", "humidity",
                  "pressure_d1", "tilt_deg", "vibration_deg", "water")
CAMERA_FEATURES = ("cam_people", "cam_rubble_frac", "cam_spill_frac")
AUDIO_FEATURES = tuple(f"aud_{k}" for k in AUDIO_KEYS)
ALL_FEATURES = BOARD_FEATURES + CAMERA_FEATURES + AUDIO_FEATURES

SOURCE_OF = {**{f: "board" for f in BOARD_FEATURES},
             **{f: "camera" for f in CAMERA_FEATURES},
             **{f: "audio" for f in AUDIO_FEATURES}}

UNITS = {"mq2_rise": "×100 %", "mq4_rise": "×100 %", "mq135_rise": "×100 %", "temp": "°C",
         "temp_rate": "°C/min", "humidity": "%", "pressure_d1": "hPa/min", "tilt_deg": "°",
         "vibration_deg": "°", "water": "", "cam_people": "", "cam_rubble_frac": "",
         "cam_spill_frac": ""}


class GasBaseline:
    """
    One MQ sensor's clean-air level. Learned from the first GAS_WARMUP readings,
    then follows the signal down quickly (clean air is the floor) and up very
    slowly while the reading stays close to it (sensor drift).
    """

    def __init__(self):
        self._warm: list[float] = []
        self.baseline: float | None = None

    @property
    def calibrated(self) -> bool:
        return self.baseline is not None

    @property
    def progress(self) -> float:
        return 1.0 if self.calibrated else len(self._warm) / GAS_WARMUP

    def update(self, value: float) -> float | None:
        """Feed one reading; returns (value − baseline) / baseline, or None while learning."""
        if self.baseline is None:
            self._warm.append(value)
            if len(self._warm) < GAS_WARMUP:
                return None
            self.baseline = statistics.median(self._warm)
            self._warm = []
            return 0.0
        scale = max(abs(self.baseline), 1.0)
        delta = value - self.baseline
        if delta < 0:
            self.baseline += 0.05 * delta
        elif delta / scale < 0.10:
            self.baseline += 0.002 * delta
        return delta / scale


class FeatureExtractor:

    def __init__(self):
        self.gas = {s: GasBaseline() for s in GAS_SENSORS}
        self._rises = {s: deque(maxlen=3) for s in GAS_SENSORS}
        self._hist: deque = deque(maxlen=1500)       # (datetime, reading)
        self._vis: deque = deque(maxlen=400)         # (datetime, people, rubble, spills)
        self._aud: deque = deque(maxlen=400)         # (datetime, {key: score})
        self._last_audio_ts = None
        self._last_at: datetime | None = None
        self._last: dict | None = None

    # ── helpers ────────────────────────────────────────────────────────────────

    def _recent(self, field: str, now: datetime, seconds: float) -> list[float]:
        cut = now - timedelta(seconds=seconds)
        return [r[field] for t, r in self._hist if t >= cut and r.get(field) is not None]

    def _smoothed(self, field: str, now: datetime) -> float | None:
        vals = self._recent(field, now, SENSOR_MAX_AGE)[-3:]
        return statistics.median(vals) if vals else None

    def _per_minute(self, field: str, now: datetime) -> float | None:
        cur = self._smoothed(field, now)
        if cur is None:
            return None
        lo, hi = now - timedelta(seconds=90), now - timedelta(seconds=45)
        past = [(t, r[field]) for t, r in self._hist if lo <= t <= hi and r.get(field) is not None]
        if not past:
            return None
        span = (now - past[len(past) // 2][0]).total_seconds()
        return (cur - statistics.median(v for _, v in past)) * 60.0 / span if span > 0 else None

    # ── main ───────────────────────────────────────────────────────────────────

    def update(self, reading: dict | None, vision: dict, audio: dict,
               now: datetime | None = None) -> dict:
        """
        Returns {"features": {...}, "live": {"board", "camera", "audio"},
                 "reading": latest board reading or None, "calibrating": bool,
                 "board_age_s": float | None}
        """
        now = now or datetime.now()
        f: dict = {k: None for k in ALL_FEATURES}

        # ── board ──────────────────────────────────────────────────────────────
        if reading is not None:
            self._last, self._last_at = reading, now
            self._hist.append((now, reading))
            for s in GAS_SENSORS:
                if reading.get(s) is not None:
                    rise = self.gas[s].update(float(reading[s]))
                    if rise is None:
                        self._rises[s].clear()
                    else:
                        self._rises[s].append(rise)
        age = None if self._last_at is None else (now - self._last_at).total_seconds()
        board = age is not None and age <= SENSOR_MAX_AGE
        cur = self._last if board else None

        if board:
            for s in GAS_SENSORS:
                if cur.get(s) is not None and self._rises[s]:
                    f[f"{s}_rise"] = round(statistics.median(self._rises[s]), 4)
            f["temp"] = self._smoothed("temperature", now)
            f["temp_rate"] = self._per_minute("temperature", now)
            f["humidity"] = self._smoothed("humidity", now)
            f["pressure_d1"] = self._per_minute("pressure", now)
            roll, pitch = self._smoothed("roll", now), self._smoothed("pitch", now)
            if roll is not None or pitch is not None:
                f["tilt_deg"] = max(abs(roll or 0.0), abs(pitch or 0.0))
            shake = None
            for axis in ("roll", "pitch"):
                vals = self._recent(axis, now, WINDOW)
                if len(vals) >= 5:
                    shake = max(shake or 0.0, statistics.pstdev(vals))
            f["vibration_deg"] = shake
            if cur.get("water_detected") is not None:
                f["water"] = 1.0 if cur["water_detected"] else 0.0

        # ── camera ─────────────────────────────────────────────────────────────
        camera = bool(vision.get("live"))
        if camera:
            self._vis.append((now, vision.get("people", 0), vision.get("rubble", 0),
                              vision.get("spills", 0)))
            win = [v for v in self._vis if v[0] >= now - timedelta(seconds=WINDOW)]
            n = len(win)
            f["cam_people"] = float(max((v[1] for v in win[-3:]), default=0))
            f["cam_rubble_frac"] = sum(1 for v in win if v[2] > 0) / n
            f["cam_spill_frac"] = sum(1 for v in win if v[3] > 0) / n

        # ── audio ──────────────────────────────────────────────────────────────
        mic = bool(audio.get("live"))
        if mic:
            ts = audio.get("state_ts")
            if ts != self._last_audio_ts and isinstance(audio.get("scores"), dict):
                self._last_audio_ts = ts
                self._aud.append((now, audio["scores"]))
            win = [s for t, s in self._aud if t >= now - timedelta(seconds=WINDOW)]
            if win:
                for k in AUDIO_KEYS:
                    f[f"aud_{k}"] = max(float(s.get(k, 0.0) or 0.0) for s in win)

        for k, v in f.items():
            if v is not None:
                f[k] = round(float(v), 4)

        return {
            "features": f,
            "live": {"board": board, "camera": camera, "audio": mic},
            "reading": cur,
            "board_age_s": None if age is None else round(age, 1),
            "calibrating": bool(board and any(
                cur.get(s) is not None and not self.gas[s].calibrated for s in GAS_SENSORS)),
        }
