"""
VERDE Audio Monitor
===================
Listens on the laptop microphone, classifies each second of sound with YAMNet
(runs locally, no network once the model file is present) and writes:

  audio_state.json  every second: the raw YAMNet score for each sound group
                    (fire, collapse, gas, siren, distress, speech). This is what
                    the fusion model reads; no threshold is applied to it.
  audio_log.json    a readable log of notable sounds for the dashboard's alert
                    feed. Its thresholds only decide what gets listed there.

Usage:
  python audio_detect.py
  python audio_detect.py --list-devices
  python audio_detect.py --device 2
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
os.chdir(ROOT)

from sensor_source import TS_FMT, write_json

TFLITE_URL = "https://tfhub.dev/google/lite-model/yamnet/tflite/1?lite-format=tflite"
CLASSES_URL = ("https://raw.githubusercontent.com/tensorflow/models/master/"
               "research/audioset/yamnet/yamnet_class_map.csv")

SAMPLE_RATE = 16000
WINDOW_S = 1.0
LOG_MAX = 200
SPEECH_EVERY_S = 10          # ordinary speech is logged at most this often
SILENCE_RMS = 0.002          # below this the window is treated as silence

# YAMNet class → category used by the fusion engine
SOUND_MAP = {
    # human distress
    "Screaming": "Human", "Shout": "Human", "Yell": "Human", "Crying, sobbing": "Human",
    "Wail, moan": "Human", "Whimper": "Human", "Groan": "Human", "Baby cry, infant cry": "Human",
    # human presence
    "Speech": "Human", "Child speech, kid speaking": "Human", "Cough": "Human",
    # fire
    "Fire": "Fire", "Crackle": "Fire", "Fire alarm": "Fire", "Smoke detector, smoke alarm": "Fire",
    # explosion / collapse
    "Explosion": "Explosion/Collapse", "Boom": "Explosion/Collapse", "Bang": "Explosion/Collapse",
    "Smash, crash": "Explosion/Collapse", "Breaking": "Explosion/Collapse",
    "Shatter": "Explosion/Collapse", "Rumble": "Explosion/Collapse",
    "Thump, thud": "Explosion/Collapse",
    # gas
    "Hiss": "Gas Leak", "Steam": "Gas Leak",
    # sirens
    "Alarm": "Siren", "Siren": "Siren", "Civil defense siren": "Siren",
    "Fire engine, fire truck (siren)": "Siren", "Ambulance (siren)": "Siren",
}

# Minimum score per class. Rare, important sounds are kept sensitive; everyday
# sounds that would otherwise fire constantly (speech, thuds, hiss) need more.
THRESHOLDS = {
    "Speech": 0.85, "Child speech, kid speaking": 0.50, "Cough": 0.50,
    "Screaming": 0.40, "Shout": 0.40, "Yell": 0.40, "Crying, sobbing": 0.40,
    "Wail, moan": 0.40, "Whimper": 0.40, "Groan": 0.40, "Baby cry, infant cry": 0.30,
    "Thump, thud": 0.40, "Bang": 0.30, "Rumble": 0.30, "Hiss": 0.30, "Steam": 0.30,
    "Alarm": 0.30,
}
DEFAULT_THRESHOLD = 0.20

PRESENCE_ONLY = {"Speech", "Child speech, kid speaking", "Cough"}

# Raw-score groups published every second for the fusion model. No thresholds
# are applied to these: the trained model decides what a score means.
_GROUP_OF = {"Fire": "fire", "Explosion/Collapse": "collapse", "Gas Leak": "gas", "Siren": "siren"}


def group_scores(mean_scores, class_names: list[str]) -> dict:
    """Highest raw YAMNet score per group: fire, collapse, gas, siren, distress, speech."""
    out = {"fire": 0.0, "collapse": 0.0, "gas": 0.0, "siren": 0.0, "distress": 0.0, "speech": 0.0}
    for name, category in SOUND_MAP.items():
        try:
            score = float(mean_scores[class_names.index(name)])
        except ValueError:
            continue
        key = _GROUP_OF.get(category) or ("speech" if name in PRESENCE_ONLY else "distress")
        out[key] = max(out[key], score)
    return {k: round(v, 4) for k, v in out.items()}


def classify(mean_scores, class_names: list[str], max_events: int = 2) -> list[dict]:
    """Scores for one window → the hazard-relevant sounds in it, strongest first."""
    hits = []
    for name, category in SOUND_MAP.items():
        try:
            score = float(mean_scores[class_names.index(name)])
        except ValueError:
            continue
        if score >= THRESHOLDS.get(name, DEFAULT_THRESHOLD):
            hits.append({"category": category, "specific": name, "confidence": round(score, 3)})
    # hazard sounds first, then ordinary speech; strongest first within each
    hits.sort(key=lambda h: (h["specific"] in PRESENCE_ONLY, -h["confidence"]))
    return hits[:max_events]


def _download(url: str, dest: str):
    import requests
    print(f"Downloading {dest} ...")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def _load_interpreter(path: str):
    try:
        import tensorflow as tf
        return tf.lite.Interpreter(model_path=path)
    except ImportError:
        pass
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tflite_runtime.interpreter import Interpreter
    return Interpreter(model_path=path)


def load_class_names() -> list[str]:
    with open("yamnet_classes.csv", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        return [row[2] for row in reader]


def main():
    ap = argparse.ArgumentParser(description="VERDE audio monitor (YAMNet)")
    ap.add_argument("--device", type=int, default=None, help="Input device index (default: system default)")
    ap.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    ap.add_argument("--keep-log", action="store_true", help="Keep entries already in audio_log.json")
    args = ap.parse_args()

    import sounddevice as sd
    if args.list_devices:
        print(sd.query_devices())
        return

    if not os.path.exists("yamnet.tflite"):
        _download(TFLITE_URL, "yamnet.tflite")
    if not os.path.exists("yamnet_classes.csv"):
        _download(CLASSES_URL, "yamnet_classes.csv")

    class_names = load_class_names()
    unknown = [n for n in SOUND_MAP if n not in class_names]
    if unknown:
        print(f"Note: not in this YAMNet label file, ignored: {unknown}")

    interpreter = _load_interpreter("yamnet.tflite")
    in_idx = interpreter.get_input_details()[0]["index"]
    out_idx = interpreter.get_output_details()[0]["index"]

    audio_log: list = []
    if args.keep_log:
        try:
            import json
            audio_log = json.loads(Path("audio_log.json").read_text(encoding="utf-8"))
        except Exception:
            audio_log = []
    write_json("audio_log.json", audio_log)        # start clean: old sounds are not current

    print("\nVERDE Audio Monitor — listening. Ctrl+C to stop.\n")
    print(f"{'TIME':<10}{'LEVEL':<8}{'LOGGED':<44}TOP GUESSES")
    print("-" * 110)

    n = int(SAMPLE_RATE * WINDOW_S)
    last_speech = 0.0
    try:
        while True:
            audio = sd.rec(n, samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=args.device)
            sd.wait()
            waveform = audio.flatten().astype(np.float32)
            rms = float(np.sqrt(np.mean(waveform ** 2)))
            now = datetime.now()

            events, top3 = [], []
            scores = {"fire": 0.0, "collapse": 0.0, "gas": 0.0, "siren": 0.0, "distress": 0.0, "speech": 0.0}
            if rms >= SILENCE_RMS:
                interpreter.resize_tensor_input(in_idx, waveform.shape)
                interpreter.allocate_tensors()
                interpreter.set_tensor(in_idx, waveform)
                interpreter.invoke()
                mean_scores = interpreter.get_tensor(out_idx).mean(axis=0)
                scores = group_scores(mean_scores, class_names)
                top3 = [(class_names[i], float(mean_scores[i])) for i in np.argsort(mean_scores)[::-1][:3]]
                for ev in classify(mean_scores, class_names):
                    if ev["specific"] in PRESENCE_ONLY:
                        if time.monotonic() - last_speech < SPEECH_EVERY_S:
                            continue
                        last_speech = time.monotonic()
                    events.append({"time": now.strftime(TS_FMT), **ev, "lat": None, "lon": None})

            if events:
                audio_log = (audio_log + events)[-LOG_MAX:]
                write_json("audio_log.json", audio_log)

            write_json("audio_state.json", {
                "timestamp": now.strftime(TS_FMT),
                "rms": round(rms, 4),
                "scores": scores,
                "top": [{"class": c, "score": round(s, 3)} for c, s in top3],
                "events_logged": len(audio_log),
            })

            logged = ", ".join(f"{e['specific']} {e['confidence']:.2f}" for e in events) or "-"
            guesses = " | ".join(f"{c} {s:.2f}" for c, s in top3) or "(silence)"
            print(f"{now.strftime('%H:%M:%S'):<10}{rms:<8.3f}{logged:<44.43}{guesses}")

    except KeyboardInterrupt:
        print(f"\nStopped. {len(audio_log)} events in audio_log.json")


if __name__ == "__main__":
    main()
