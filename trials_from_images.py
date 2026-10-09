r"""
VERDE trials from image folders
===============================
Builds fusion trials from folders of photos instead of the live camera, using
your existing camera models unchanged (yolov8n.pt, rubble.pt, oil.pt) with the
same settings as detect.py.

    python trials_from_images.py --damaged C:\data\broken_buildings --normal C:\data\normal_scenes

  --damaged  photos of damaged / collapsed buildings   → label structural
  --normal   photos with no damage (intact buildings, streets, rooms) → label clear
  --spill    optional, photos of spills                → label spill

--normal is required: without undamaged photos there is no way to measure how
often rubble.pt raises a false alarm.

Each photo is treated as one scene the rover is looking at. It also prints, for
rubble.pt on your photos, the share of damaged photos caught and the share of
normal photos wrongly flagged at each confidence setting. detect.py currently
uses 0.90; that table tells you what any other setting would do.

Then run:  python train_fusion.py
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from record_trials import COLUMNS, TRIALS

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PER_TRIAL = 50

# Same settings as detect.py
PEOPLE_CONF, PEOPLE_IOU = 0.50, 0.4
RUBBLE_CONF = 0.90
SPILL_CONF = 0.80
SCAN_CONF = 0.05          # models are run at this, then cut at the settings above


def images_in(folder: str) -> list[Path]:
    files = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in EXTS)
    if not files:
        raise SystemExit(f"no images found under {folder}")
    return files


def main():
    ap = argparse.ArgumentParser(description="Build fusion trials from image folders")
    ap.add_argument("--damaged", required=True, help="Folder of damaged-building photos")
    ap.add_argument("--normal", required=True, help="Folder of photos with no damage")
    ap.add_argument("--spill", help="Optional folder of spill photos")
    ap.add_argument("--rubble-conf", type=float, default=RUBBLE_CONF,
                    help=f"rubble.pt confidence used for the trials (default {RUBBLE_CONF}, as in detect.py)")
    ap.add_argument("--limit", type=int, default=0, help="Use at most this many photos per folder")
    args = ap.parse_args()

    import cv2
    from ultralytics import YOLO
    people_model, rubble_model, spill_model = YOLO("yolov8n.pt"), YOLO("rubble.pt"), YOLO("oil.pt")

    sets = [("structural", "damaged", images_in(args.damaged)), ("clear", "normal", images_in(args.normal))]
    if args.spill:
        sets.append(("spill", "spill", images_in(args.spill)))

    best = {}                                  # set name → [highest rubble confidence per photo]
    TRIALS.mkdir(exist_ok=True)
    for label, name, files in sets:
        if args.limit:
            files = files[:args.limit]
        best[name] = []
        rows, n_trials = [], 0

        def flush():
            nonlocal rows, n_trials
            if rows:
                n_trials += 1
                trial = f"images_{name}_{n_trials:03d}"
                for r in rows:
                    r["trial"] = trial
                with open(TRIALS / f"{trial}.csv", "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=COLUMNS)
                    w.writeheader()
                    w.writerows(rows)
                rows = []

        for i, path in enumerate(files):
            frame = cv2.imread(str(path))
            if frame is None:
                print(f"  skipped unreadable {path.name}")
                continue
            frame = cv2.resize(frame, (640, 480))                       # as detect.py
            people = len(people_model(frame, classes=[0], conf=PEOPLE_CONF, iou=PEOPLE_IOU, verbose=False)[0].boxes)
            r_conf = [float(b.conf[0]) for b in rubble_model(frame, conf=SCAN_CONF, verbose=False)[0].boxes]
            s_conf = [float(b.conf[0]) for b in spill_model(frame, conf=SCAN_CONF, verbose=False)[0].boxes]
            top = max(r_conf, default=0.0)
            best[name].append(top)

            row = {c: "" for c in COLUMNS}
            row.update({"label": label, "phase": "before" if label == "clear" else "active",
                        "t": len(rows), "timestamp": path.name,
                        "live_board": 0, "live_camera": 1, "live_audio": 0,
                        # one still scene held in view: the detector either fires on it or not
                        "cam_people": float(people),
                        "cam_rubble_frac": 1.0 if top >= args.rubble_conf else 0.0,
                        "cam_spill_frac": 1.0 if max(s_conf, default=0.0) >= SPILL_CONF else 0.0})
            rows.append(row)
            if len(rows) >= PER_TRIAL:
                flush()
            if (i + 1) % 50 == 0:
                print(f"  {name}: {i + 1}/{len(files)}")
        flush()
        print(f"  {name}: {len(best[name])} photos → {n_trials} trials")

    d, n = best["damaged"], best["normal"]
    print("\nrubble.pt on your photos (each photo counted once):\n")
    print(f"  {'confidence ≥':>13}{'damaged caught':>17}{'normal wrongly flagged':>25}")
    for c in (0.25, 0.50, 0.70, 0.80, 0.90, 0.95):
        caught = sum(1 for v in d if v >= c) / max(len(d), 1)
        wrong = sum(1 for v in n if v >= c) / max(len(n), 1)
        mark = "   ← detect.py" if abs(c - RUBBLE_CONF) < 1e-9 else ""
        print(f"  {c:>13.2f}{caught:>16.0%} {wrong:>24.0%}{mark}")
    print(f"\n  {len(d)} damaged photos, {len(n)} normal photos")
    print("\nNext:  python train_fusion.py")


if __name__ == "__main__":
    main()
