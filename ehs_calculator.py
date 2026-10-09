"""
VERDE Environmental Health Score (EHS)
======================================
One 0–100 number derived only from the trained fusion model:

    score = 100 × Π (1 − p_h)        over every hazard the model can evaluate now

where p_h is the model's probability that hazard h is present. In words: the
probability, according to the trained models, that none of the hazards it can
currently check is present. There are no hand-set weights or penalties.

The dashboard groups the hazards into three sub-scores, each computed the same
way over its own group:

  Climate   gas, fire / heat, water, tilt     (sensor board)
  Visual    structural damage, spill          (camera, plus sound for structural)
  Audio     human distress, collapse sounds   (microphone)

A group with no evaluable hazard (not trained, or its source is offline) is
shown as offline. With nothing evaluable there is no score. The anomaly
detector is shown on the dashboard but is not part of this score.

Driven by coordinator.py, which passes in the fusion engine's result.
"""

from __future__ import annotations

from datetime import datetime

from sensor_source import TS_FMT, write_json

GROUPS = {
    "climate": ["gas", "fire", "water", "tilt"],
    "visual":  ["structural", "spill"],
    "audio":   ["distress", "collapse"],
}


def grade(score: float) -> tuple[str, str]:
    """Letter for display only: equal 20-point bands."""
    for floor, letter in ((80, "A"), (60, "B"), (40, "C"), (20, "D")):
        if score >= floor:
            return letter, "P(NO HAZARD)"
    return "F", "P(NO HAZARD)"


def trend(history: list) -> str:
    """Direction of the last 8 scores: sign of the least-squares slope."""
    arr = history[-8:]
    n = len(arr)
    if n < 3:
        return "STABLE"
    x_mean, y_mean = (n - 1) / 2.0, sum(arr) / n
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = sum((i - x_mean) * (arr[i] - y_mean) for i in range(n)) / den if den else 0.0
    return "IMPROVING" if slope > 0 else "DEGRADING" if slope < 0 else "STABLE"


class EHSCalculator:

    def __init__(self):
        self.history: list[float] = []

    def compute(self, zone: str, fusion: dict, now: datetime | None = None,
                write: bool = True) -> dict:
        now = now or datetime.now()
        states = fusion.get("hazard_states", {})
        p = {k: s["p"] for k, s in states.items() if s.get("state") in ("clear", "detected")}

        def no_hazard(keys) -> float | None:
            vals = [p[k] for k in keys if k in p]
            if not vals:
                return None
            out = 1.0
            for v in vals:
                out *= (1.0 - v)
            return round(100.0 * out, 1)

        composite = no_hazard(list(p))
        sub_scores = {}
        for name, keys in GROUPS.items():
            s = no_hazard(keys)
            sub_scores[name] = {"score": s, "weight": 0.0, "live": s is not None,
                                "hazards": [k for k in keys if k in p]}
        sub_scores["anomaly"] = {"score": None, "weight": 0.0, "live": False, "hazards": []}

        if composite is not None:
            self.history = (self.history + [composite])[-50:]
            g, status = grade(composite)
        else:
            g = "—"
            status = "NOT TRAINED" if fusion.get("zone_status") == "UNTRAINED" else "NO DATA"

        result = {
            "timestamp":     now.strftime(TS_FMT),
            "zone":          zone,
            "score":         composite,
            "grade":         g,
            "status":        status,
            "trend":         trend(self.history) if composite is not None else "STABLE",
            "coverage":      round(len(p) / len(states), 2) if states else 0.0,
            "method":        "100 × Π(1 − p) over evaluable trained hazards",
            "weights":       {},
            "sub_scores":    sub_scores,
            "penalties":     {k: round(v, 3) for k, v in p.items()},
            "score_history": self.history,
        }
        if write:
            write_json("ehs_log.json", result)
        return result


if __name__ == "__main__":
    print("The health score is driven by the coordinator:\n\n    python coordinator.py")
