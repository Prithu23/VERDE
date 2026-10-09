"""
VERDE trial recorder
====================
Records what the real sensors, camera and microphone report while you produce
a hazard, so the fusion model can be fitted to it.

One run = one trial:

    python record_trials.py --label gas --sensor-ip 192.168.1.50

  1. Baseline (60 s): leave everything calm. The gas sensors learn clean air.
  2. "Apply the hazard, then press Enter" – press Enter at the moment you start.
  3. "Press Enter when you stop"          – press Enter at the moment you stop.
  4. Recovery (20 s) is recorded and the trial is saved to trials/.

For a calm reference trial:

    python record_trials.py --label clear --seconds 180

Run detect.py and audio_detect.py alongside for every trial, including the calm
ones, so each row has all three sources. Record at least 3 trials per hazard,
on separate runs, plus at least 3 clear trials in between. Vary them: distance,
amount, angle, background noise. Then run train_fusion.py.

Rows are labelled by phase: before = calm, active = hazard present,
after = recovery (not used for training, because leftover gas or heat makes
it neither calm nor active).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from features import ALL_FEATURES, FeatureExtractor
from hazards import CLEAR, HAZARDS, LABELS
from sensor_source import BoardSensor, DEFAULT_SENSOR_IP, read_audio, read_vision

TRIALS = ROOT / "trials"
RAW_FIELDS = ["temperature", "humidity", "pressure", "mq2", "mq4", "mq135", "roll", "pitch"]
COLUMNS = (["trial", "label", "phase", "t", "timestamp", "live_board", "live_camera", "live_audio"]
           + list(ALL_FEATURES) + [f"raw_{k}" for k in RAW_FIELDS])


class Recorder:
    def __init__(self, label: str, sensor_ip: str, interval: float):
        self.label, self.interval = label, interval
        self.trial = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.board = BoardSensor(ip=sensor_ip)
        self.fx = FeatureExtractor()
        self.phase = "before"
        self.rows: list[dict] = []
        self.stop = False
        self.last: dict = {}
        self._reading = None
        self._lock = threading.Lock()
        self.t0 = time.monotonic()

    def _poll_board(self):
        while not self.stop:
            t = time.monotonic()
            r = self.board.read()
            if r is not None:
                with self._lock:
                    self._reading = r
            time.sleep(max(0.05, self.interval - (time.monotonic() - t)))

    def _loop(self):
        while not self.stop:
            t = time.monotonic()
            with self._lock:
                reading, self._reading = self._reading, None
            out = self.fx.update(reading, read_vision(), read_audio())
            raw = out["reading"] or {}
            row = {"trial": self.trial, "label": self.label, "phase": self.phase,
                   "t": round(t - self.t0, 2), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "live_board": int(out["live"]["board"]), "live_camera": int(out["live"]["camera"]),
                   "live_audio": int(out["live"]["audio"])}
            row.update({k: ("" if v is None else v) for k, v in out["features"].items()})
            row.update({f"raw_{k}": ("" if raw.get(k) is None else raw[k]) for k in RAW_FIELDS})
            self.rows.append(row)
            self.last = out
            time.sleep(max(0.0, self.interval - (time.monotonic() - t)))

    def start(self):
        threading.Thread(target=self._poll_board, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()

    def save(self) -> Path:
        TRIALS.mkdir(exist_ok=True)
        path = TRIALS / f"{self.trial}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(self.rows)
        return path


def _status(rec: Recorder) -> str:
    out = rec.last
    if not out:
        return "starting…"
    live = out["live"]
    f = out["features"]
    src = " ".join(n if live[k] else f"{n.lower()}:OFF" for k, n in
                   (("board", "BOARD"), ("camera", "CAM"), ("audio", "MIC")))
    show = lambda k, fmt: "--" if f.get(k) is None else format(f[k], fmt)
    return (f"{src} | mq2 {show('mq2_rise', '+.0%')} mq4 {show('mq4_rise', '+.0%')} "
            f"mq135 {show('mq135_rise', '+.0%')} T {show('temp', '.1f')} water {show('water', '.0f')} "
            f"rubble {show('cam_rubble_frac', '.0%')} distress {show('aud_distress', '.2f')} "
            f"crash {show('aud_collapse', '.2f')}")


def _wait(rec: Recorder, seconds: float, what: str):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        left = int(end - time.monotonic())
        print(f"\r  {what} {left:3d}s | {_status(rec)}".ljust(150), end="", flush=True)
        time.sleep(0.5)
    print()


def main():
    ap = argparse.ArgumentParser(description="Record one labelled trial for the fusion model")
    ap.add_argument("--label", required=True, choices=LABELS, help="What you will produce in this trial")
    ap.add_argument("--sensor-ip", default=DEFAULT_SENSOR_IP)
    ap.add_argument("--interval", type=float, default=1.0, help="Seconds between rows (default 1)")
    ap.add_argument("--baseline", type=float, default=60.0, help="Calm seconds before the hazard (default 60)")
    ap.add_argument("--seconds", type=float, default=180.0, help="Length of a clear trial (default 180)")
    ap.add_argument("--recovery", type=float, default=20.0, help="Seconds recorded after the hazard (default 20)")
    ap.add_argument("--auto-active", type=float, default=0.0, help=argparse.SUPPRESS)   # for tests
    args = ap.parse_args()

    rec = Recorder(args.label, args.sensor_ip, args.interval)
    print(f"\nTrial {rec.trial}")
    if args.label != CLEAR:
        print(f"Hazard: {HAZARDS[args.label]['name']} — {HAZARDS[args.label]['how']}")
    print("Keep everything calm for the baseline. Gas sensors are learning clean air.\n")
    rec.start()

    if args.label == CLEAR:
        _wait(rec, args.seconds, "calm")
    else:
        _wait(rec, args.baseline, "baseline")
        if args.auto_active:
            rec.phase = "active"
            _wait(rec, args.auto_active, "ACTIVE")
        else:
            input("\n  >>> Apply the hazard now, and press Enter at the moment you start... ")
            rec.phase = "active"
            print("  Recording ACTIVE. Keep the hazard going for at least 30 seconds.")
            input("  >>> Press Enter at the moment you stop / remove it... ")
        rec.phase = "after"
        _wait(rec, args.recovery, "recovery")

    rec.stop = True
    time.sleep(args.interval + 0.2)
    path = rec.save()

    n = {p: sum(1 for r in rec.rows if r["phase"] == p) for p in ("before", "active", "after")}
    off = [name for key, name in (("live_board", "sensor board"), ("live_camera", "camera"),
                                  ("live_audio", "microphone"))
           if sum(r[key] for r in rec.rows) < 0.9 * len(rec.rows)]
    print(f"\nSaved {path}  ({n['before']} calm, {n['active']} active, {n['after']} recovery rows)")
    if off:
        print(f"WARNING: {', '.join(off)} was offline for part of this trial. "
              f"Those measurements are blank and cannot be learned from it.")
    if args.label != CLEAR and n["active"] < 20:
        print("WARNING: fewer than 20 active rows. Keep the hazard going longer next time.")


if __name__ == "__main__":
    main()
