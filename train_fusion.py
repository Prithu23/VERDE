"""
VERDE fusion trainer
====================
Fits the fusion model from the trials recorded with record_trials.py and
writes fusion_model.json, which the fusion engine loads.

    pip install scikit-learn
    python train_fusion.py

For each hazard it fits a logistic regression on the measurements listed for
that hazard in hazards.py:

  positives  rows recorded while that hazard was active
  negatives  calm rows from every trial, and active rows of the other hazards
             (a gas trial is evidence of what "not water" looks like)

Everything numeric is taken from the data:

  * the weight of each measurement      – fitted
  * the regularisation strength         – chosen by held-out log-loss
  * the detection threshold             – the one with the best F1 on held-out rows

Accuracy is measured leave-one-trial-out: the model is fitted with one whole
trial removed and then asked about that trial, for every trial in turn. Rows
from the same recording are never in both the training and the test side, so
the figures say how it does on a recording it has not seen.

A hazard with fewer than 2 recorded trials is not trained and stays switched
off in the engine. 3 or more trials per hazard is the practical minimum for
the held-out figures to mean much.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from features import ALL_FEATURES
from hazards import CLEAR, HAZARDS

C_GRID = [0.01, 0.1, 1.0, 10.0, 100.0]
MIN_TRIALS = 2
MIN_AVAILABLE = 0.90         # a measurement must be present in this share of a hazard's active rows


def load_trials(folder: Path) -> list[dict]:
    rows = []
    for path in sorted(folder.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                row = {"trial": r["trial"], "label": r["label"], "phase": r["phase"],
                       "t": float(r["t"] or 0)}
                for k in ALL_FEATURES:
                    v = r.get(k, "")
                    row[k] = float(v) if v not in ("", None) else math.nan
                rows.append(row)
    return rows


def _fit(X, y, C):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000)).fit(X, y)


def _oof(X, y, groups, C) -> np.ndarray:
    """Held-out probability for every row, leaving out one whole trial at a time."""
    p = np.full(len(y), np.nan)
    for g in np.unique(groups):
        test = groups == g
        if len(np.unique(y[~test])) < 2:
            continue
        p[test] = _fit(X[~test], y[~test], C).predict_proba(X[test])[:, 1]
    return p


def train_hazard(key: str, rows: list[dict]) -> tuple[dict | None, str]:
    spec = HAZARDS[key]
    use = [r for r in rows if r["phase"] in ("before", "active")]
    if sum(1 for t in {r["trial"] for r in use if r["label"] == key}) < MIN_TRIALS:
        n = len({r["trial"] for r in rows if r["label"] == key})
        return None, f"{n} trial(s) recorded, need at least {MIN_TRIALS}"

    # Measurements that were actually recorded while this hazard was active.
    # (Calm rows from before a sensor was ready are simply left out below.)
    active = [r for r in use if r["label"] == key and r["phase"] == "active"]
    feats, dropped = [], []
    for f in spec["features"]:
        have = sum(1 for r in active if not math.isnan(r[f])) / max(len(active), 1)
        (feats if have >= MIN_AVAILABLE else dropped).append(f)
    use = [r for r in use if not any(math.isnan(r[f]) for f in feats)]
    feats = [f for f in feats if len({r[f] for r in use}) > 1]          # constant columns say nothing
    if not feats:
        return None, f"none of its measurements were recorded ({', '.join(spec['features'])})"

    X = np.array([[r[f] for f in feats] for r in use], dtype=float)
    y = np.array([1 if (r["label"] == key and r["phase"] == "active") else 0 for r in use])
    groups = np.array([r["trial"] for r in use])
    t = np.array([r["t"] for r in use])
    pos_trials = sorted({g for g, yy in zip(groups, y) if yy})
    if len(pos_trials) < MIN_TRIALS or y.sum() < 10 or (1 - y).sum() < 10:
        return None, f"not enough usable rows ({int(y.sum())} active, {int((1 - y).sum())} calm)"

    # Regularisation strength: lowest held-out log-loss
    best = None
    for C in C_GRID:
        p = _oof(X, y, groups, C)
        ok = ~np.isnan(p)
        q = np.clip(p[ok], 1e-6, 1 - 1e-6)
        loss = float(-np.mean(y[ok] * np.log(q) + (1 - y[ok]) * np.log(1 - q)))
        if best is None or loss < best[0]:
            best = (loss, C, p)
    loss, C, p = best
    ok = ~np.isnan(p)

    # A model must beat "always answer the base rate" on held-out rows. If it
    # does not, these measurements did not respond to the hazard in your trials.
    rate = float(y[ok].mean())
    chance = -(rate * math.log(rate) + (1 - rate) * math.log(1 - rate))
    if loss >= chance:
        return None, (f"no better than guessing on held-out trials (log-loss {loss:.3f} vs "
                      f"{chance:.3f} for the base rate) using {', '.join(feats)}"
                      + (f"; not recorded: {', '.join(dropped)}" if dropped else ""))

    # Detection threshold: best F1 on held-out rows
    def prf(th):
        pred = p[ok] >= th
        tp = int((pred & (y[ok] == 1)).sum()); fp = int((pred & (y[ok] == 0)).sum())
        fn = int((~pred & (y[ok] == 1)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return prec, rec, f1, fp
    grid = [round(x, 2) for x in np.arange(0.05, 0.96, 0.01)]
    top = max(prf(th)[2] for th in grid)
    ties = [th for th in grid if prf(th)[2] >= top - 1e-9]
    threshold = ties[len(ties) // 2]
    prec, rec, f1, fp = prf(threshold)

    # Trial-level figures
    detected, delays, false_alarm_trials, neg_trials = 0, [], 0, 0
    for g in np.unique(groups):
        m = (groups == g) & ok
        act, calm = m & (y == 1), m & (y == 0)
        if act.any():
            hit = act & (p >= threshold)
            if hit.any():
                detected += 1
                delays.append(float(t[hit].min() - t[act].min()))
        if calm.any():
            neg_trials += 1
            false_alarm_trials += int((p[calm] >= threshold).any())

    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y[ok], p[ok]))
    except Exception:
        auc = None

    model = _fit(X, y, C)
    scaler, lr = model.steps[0][1], model.steps[1][1]
    return {
        "id": spec["id"], "name": spec["name"],
        "features": feats,
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "coef": [float(v) for v in lr.coef_[0]],
        "intercept": float(lr.intercept_[0]),
        "C": C,
        "threshold": threshold,
        "not_recorded": dropped,
        "data": {"trials": len(pos_trials), "active_rows": int(y.sum()), "calm_rows": int((1 - y).sum())},
        "held_out": {
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "auc": None if auc is None else round(auc, 3),
            "log_loss": round(loss, 4), "base_rate_log_loss": round(chance, 4),
            "false_alarm_rate": round(fp / max(int((y[ok] == 0).sum()), 1), 4),
            "trials_detected": f"{detected}/{len(pos_trials)}",
            "trials_with_false_alarm": f"{false_alarm_trials}/{neg_trials}",
            "median_delay_s": None if not delays else round(statistics.median(delays), 1),
        },
    }, "ok"


def main():
    ap = argparse.ArgumentParser(description="Fit the VERDE fusion model from recorded trials")
    ap.add_argument("--trials", default=str(ROOT / "trials"))
    ap.add_argument("--out", default=str(ROOT / "fusion_model.json"))
    args = ap.parse_args()

    try:
        import sklearn  # noqa: F401
    except ImportError:
        raise SystemExit("scikit-learn is needed for training:  pip install scikit-learn")

    rows = load_trials(Path(args.trials))
    if not rows:
        raise SystemExit(f"No trials found in {args.trials}. Record some with record_trials.py first.")

    per_label = defaultdict(set)
    for r in rows:
        per_label[r["label"]].add(r["trial"])
    print(f"\n{len(rows)} rows from {sum(len(v) for v in per_label.values())} trials: "
          + ", ".join(f"{k} ×{len(v)}" for k, v in sorted(per_label.items())))
    if len(per_label.get(CLEAR, ())) == 0:
        print("NOTE: no clear trials. Calm rows come only from the baselines of hazard trials.")

    hazards, skipped = {}, {}
    for key in HAZARDS:
        model, why = train_hazard(key, rows)
        if model is None:
            skipped[key] = why
        else:
            hazards[key] = model

    out = {
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trials": {k: len(v) for k, v in sorted(per_label.items())},
        "rows": len(rows),
        "evaluation": "leave-one-trial-out",
        "hazards": hazards,
        "not_trained": skipped,
    }
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\nHeld-out results (each trial predicted by a model that never saw it)\n")
    print(f"  {'hazard':<12}{'trials':>7}{'precision':>11}{'recall':>8}{'F1':>7}{'detected':>10}"
          f"{'false-alarm trials':>20}{'delay':>8}  threshold  measurements (fitted weight)")
    for key, m in hazards.items():
        h = m["held_out"]
        w = ", ".join(f"{f} {c:+.2f}" for f, c in zip(m["features"], m["coef"]))
        delay = "-" if h["median_delay_s"] is None else f"{h['median_delay_s']:.0f}s"
        print(f"  {key:<12}{m['data']['trials']:>7}{h['precision']:>11.2f}{h['recall']:>8.2f}{h['f1']:>7.2f}"
              f"{h['trials_detected']:>10}{h['trials_with_false_alarm']:>20}{delay:>8}"
              f"  {m['threshold']:<9}  {w}")
        if m["not_recorded"]:
            print(f"  {'':<12}not recorded, so not used: {', '.join(m['not_recorded'])}")
    for key, why in skipped.items():
        print(f"  {key:<12}NOT TRAINED — {why}")
    print(f"\nSaved {args.out}. Restart coordinator.py to load it.\n")


if __name__ == "__main__":
    main()
