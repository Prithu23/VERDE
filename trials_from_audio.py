r"""
VERDE trials from sound files
=============================
Builds fusion trials from recorded sound clips instead of the live microphone,
so the audio hazards can be trained and measured without a quiet room.

Each clip goes through the same YAMNet model, in the same one-second windows,
as audio_detect.py. The measurements written are the same aud_* scores the
live engine sees.

With the ESC-50 dataset (https://github.com/karolpiczak/ESC-50, 2,000 labelled
5-second clips):

    python trials_from_audio.py --esc50 C:\path\to\ESC-50-master

  crying_baby     → distress
  glass_breaking  → collapse
  crackling_fire  → fire
  every other category (rain, dog, keyboard, fireworks, siren, ...) → clear

ESC-50 comes split into 5 folds; each fold becomes one trial per label, so the
held-out test in train_fusion.py is on clips the model never heard.

With your own folders of .wav files (any sample rate, mono or stereo):

    python trials_from_audio.py --folder distress=sounds\screams --folder collapse=sounds\crashes --folder clear=sounds\normal

Labels: clear, distress, collapse, fire, gas. Always include a `clear` folder:
without ordinary sounds there is nothing to measure false alarms against.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from audio_detect import SAMPLE_RATE, SILENCE_RMS, _load_interpreter, group_scores, load_class_names
from features import ALL_FEATURES, AUDIO_KEYS
from record_trials import COLUMNS, TRIALS

ESC50_LABELS = {"crying_baby": "distress", "glass_breaking": "collapse", "crackling_fire": "fire"}
AUDIO_LABELS = ("clear", "distress", "collapse", "fire", "gas")
WINDOW = 10          # one-second windows in the rolling maximum, as in features.py
CLIPS_PER_TRIAL = 8


def load_wav(path: Path) -> np.ndarray:
    """PCM .wav → mono float32 at 16 kHz."""
    with wave.open(str(path), "rb") as w:
        n, ch, width, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / 8388608.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != SAMPLE_RATE and len(x):
        t = np.arange(0, len(x) * SAMPLE_RATE // rate) * (rate / SAMPLE_RATE)
        x = np.interp(t, np.arange(len(x)), x).astype(np.float32)
    return x.astype(np.float32)


class Scorer:
    def __init__(self):
        self.names = load_class_names()
        self.interp = _load_interpreter("yamnet.tflite")
        self.i = self.interp.get_input_details()[0]["index"]
        self.o = self.interp.get_output_details()[0]["index"]

    def windows(self, x: np.ndarray) -> list[dict]:
        """Group scores for each one-second window of a clip."""
        out = []
        for a in range(0, len(x), SAMPLE_RATE):
            w = x[a:a + SAMPLE_RATE]
            if len(w) < SAMPLE_RATE // 2:
                break
            if len(w) < SAMPLE_RATE:
                w = np.pad(w, (0, SAMPLE_RATE - len(w)))
            if float(np.sqrt(np.mean(w ** 2))) < SILENCE_RMS:      # same silence rule as live
                out.append({k: 0.0 for k in AUDIO_KEYS})
                continue
            self.interp.resize_tensor_input(self.i, w.shape)
            self.interp.allocate_tensors()
            self.interp.set_tensor(self.i, w)
            self.interp.invoke()
            out.append(group_scores(self.interp.get_tensor(self.o).mean(axis=0), self.names))
        return out


def write_trial(name: str, label: str, clips: list[Path], scorer: Scorer) -> int:
    rows, recent, t = [], [], 0
    for clip in clips:
        try:
            wins = scorer.windows(load_wav(clip))
        except Exception as e:
            print(f"    skipped {clip.name}: {e}")
            continue
        for s in wins:
            recent = (recent + [s])[-WINDOW:]
            row = {c: "" for c in COLUMNS}
            row.update({"trial": name, "label": label, "t": t, "timestamp": clip.name,
                        "phase": "before" if label == "clear" else "active",
                        "live_board": 0, "live_camera": 0, "live_audio": 1})
            for k in AUDIO_KEYS:
                row[f"aud_{k}"] = round(max(r[k] for r in recent), 4)
            rows.append(row)
            t += 1
    if rows:
        TRIALS.mkdir(exist_ok=True)
        with open(TRIALS / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Build fusion trials from sound files")
    ap.add_argument("--esc50", help="Path to the ESC-50 dataset folder (contains audio/ and meta/esc50.csv)")
    ap.add_argument("--folder", action="append", default=[], metavar="LABEL=DIR",
                    help=f"A folder of .wav files for one label ({', '.join(AUDIO_LABELS)}). Repeatable.")
    ap.add_argument("--max-clear-per-category", type=int, default=10,
                    help="ESC-50: clips taken from each ordinary category (default 10 of 40)")
    args = ap.parse_args()
    if not args.esc50 and not args.folder:
        ap.error("give --esc50 PATH and / or --folder LABEL=DIR")

    trials: dict = defaultdict(list)          # (label, group) → [clip paths]

    if args.esc50:
        base = Path(args.esc50)
        meta = base / "meta" / "esc50.csv"
        if not meta.exists():
            raise SystemExit(f"{meta} not found. --esc50 should point at the folder holding audio/ and meta/.")
        taken: dict = defaultdict(int)
        with open(meta, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                label = ESC50_LABELS.get(r["category"], "clear")
                if label == "clear":
                    key = (r["category"], r["fold"])
                    if taken[key] >= max(1, args.max_clear_per_category // 5):
                        continue
                    taken[key] += 1
                path = base / "audio" / r["filename"]
                if path.exists():
                    trials[(label, f"esc50_fold{r['fold']}")].append(path)

    for spec in args.folder:
        label, _, folder = spec.partition("=")
        label = label.strip().lower()
        if label not in AUDIO_LABELS or not folder:
            raise SystemExit(f"--folder expects LABEL=DIR with LABEL one of {', '.join(AUDIO_LABELS)}; got {spec!r}")
        clips = sorted(Path(folder).rglob("*.wav"))
        if not clips:
            raise SystemExit(f"no .wav files under {folder}")
        for i in range(0, len(clips), CLIPS_PER_TRIAL):
            trials[(label, f"files{i // CLIPS_PER_TRIAL + 1:03d}")] += clips[i:i + CLIPS_PER_TRIAL]

    if not any(label == "clear" for label, _ in trials):
        print("WARNING: no clear sounds given. False alarms cannot be measured without them.")

    scorer = Scorer()
    per_label: dict = defaultdict(lambda: [0, 0, 0])
    for (label, group), clips in sorted(trials.items()):
        n = write_trial(f"audio_{label}_{group}", label, clips, scorer)
        per_label[label][0] += 1; per_label[label][1] += len(clips); per_label[label][2] += n
        print(f"  audio_{label}_{group}: {len(clips)} clips, {n} seconds")

    print("\nWritten to trials/:")
    for label, (nt, nc, ns) in sorted(per_label.items()):
        print(f"  {label:<10} {nt} trials, {nc} clips, {ns} seconds")
    print("\nNext:  python train_fusion.py")


if __name__ == "__main__":
    main()
