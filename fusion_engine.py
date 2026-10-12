"""
VERDE Sensor Fusion Engine
==========================
Decides which hazards are present from the live sensor board, camera and
microphone, using a model fitted to trials recorded on this rover.

Where every number comes from
-----------------------------
  measurements        features.py          (what the sensors, camera and mic report)
  weights, thresholds fusion_model.json    (fitted by train_fusion.py from your trials)
  response levels     response_policy.json (your team's decision, not learned)

There are no hand-set hazard weights or thresholds in this file. For each
trained hazard the engine evaluates

    p = sigmoid( intercept + Σ coef_i × (x_i − mean_i) / scale_i )

and reports the hazard when p reaches the threshold that scored best on
held-out trials.

What it will not do
-------------------
  * no model file              → status UNTRAINED, no verdict
  * hazard never recorded      → listed as not trained, never reported
  * a needed source is offline → that hazard is "cannot evaluate", not "clear"
  * nothing live               → status NO_DATA

Run `python fusion_engine.py --test` for the engine tests.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

from features import FeatureExtractor, GAS_SENSORS, SOURCE_OF
from hazards import HAZARDS
from sensor_source import TS_FMT

ROOT = Path(__file__).parent
MODEL_PATH = ROOT / "fusion_model.json"
POLICY_PATH = ROOT / "response_policy.json"
RULES_PATH = ROOT / "fallback_rules.json"

_OPS = {'>=': lambda a, b: a >= b, '>': lambda a, b: a > b,
        '<=': lambda a, b: a <= b, '<': lambda a, b: a < b}

ZONE_STATUS = ['CLEAR', 'ELEVATED', 'WARNING', 'CRITICAL', 'CATASTROPHIC']
ZONE_RANK = {z: i for i, z in enumerate(ZONE_STATUS)}
# Dashboard colour for a threat card, from the zone level the policy gives it
SEVERITY_OF_ZONE = {'ELEVATED': 'LOW', 'WARNING': 'MEDIUM', 'CRITICAL': 'HIGH', 'CATASTROPHIC': 'CRITICAL'}

SOURCE_NAME = {'board': 'sensor board', 'camera': 'camera', 'audio': 'microphone'}


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _fmt(feature: str, value: float) -> str:
    """Readable form of one measurement, for threat descriptions."""
    if feature.endswith('_rise'):
        return f"{feature[:-5].upper()} {round(value * 100) + 0:+d}% vs clean air"
    return {
        'temp':            f"temperature {value:.1f} °C",
        'temp_rate':       f"temperature changing {value:+.1f} °C/min",
        'humidity':        f"humidity {value:.0f}%",
        'pressure_d1':     f"pressure changing {value:+.2f} hPa/min",
        'tilt_deg':        f"tilt {value:.0f}°",
        'vibration_deg':   f"shaking ±{value:.1f}°",
        'water':           "water sensor wet" if value else "water sensor dry",
        'cam_people':      f"{value:.0f} person(s) in view",
        'cam_rubble_frac': f"rubble in {value:.0%} of camera frames",
        'cam_spill_frac':  f"spill in {value:.0%} of camera frames",
    }.get(feature, f"{feature.replace('aud_', '')} sound score {value:.2f}")


class FusionEngine:

    def __init__(self, model: dict | None = None, policy: dict | None = None,
                 rules: dict | None = None):
        self.fx = FeatureExtractor()
        self.model = model if model is not None else load_json(MODEL_PATH)
        self.policy = policy if policy is not None else (load_json(POLICY_PATH) or {})
        if rules is None:
            rules = (load_json(RULES_PATH) or {}).get('rules', {})
        self.rules = {k: r for k, r in rules.items() if k in HAZARDS}
        self.published: dict | None = None

    # ── model evaluation ───────────────────────────────────────────────────────

    @staticmethod
    def _evaluate(m: dict, f: dict) -> tuple[float, list]:
        """Probability and each measurement's share of the log-odds."""
        logit, parts = m['intercept'], []
        for name, mean, scale, coef in zip(m['features'], m['mean'], m['scale'], m['coef']):
            c = coef * (f[name] - mean) / (scale or 1.0)
            logit += c
            parts.append((name, c))
        p = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, logit))))
        return p, sorted(parts, key=lambda x: -x[1])

    # ── main entry point ───────────────────────────────────────────────────────

    def decide(self, reading: dict | None, vision: dict, audio: dict,
               zone: str = 'Zone A-12', now: datetime | None = None,
               origin: str = 'board') -> dict:
        t0 = time.monotonic()
        now = now or datetime.now()
        fx = self.fx.update(reading, vision, audio, now)
        f, live, cur = fx['features'], fx['live'], fx['reading'] or {}
        any_live = any(live.values())
        log: list[str] = []
        threats: list[dict] = []
        states: dict = {}

        trained = (self.model or {}).get('hazards', {})
        zones = self.policy.get('zone_when_detected', {})

        for key, m in trained.items():
            missing = [n for n in m['features'] if f.get(n) is None]
            if missing:
                why = sorted({SOURCE_NAME[SOURCE_OF[n]] for n in missing if not live[SOURCE_OF[n]]})
                reason = (f"{', '.join(why)} offline" if why
                          else f"waiting for {', '.join(missing)}")
                states[key] = {'state': 'unavailable', 'name': m['name'], 'reason': reason}
                log.append(f"{m['name']}: cannot evaluate — {reason}")
                continue
            p, parts = self._evaluate(m, f)
            detected = p >= m['threshold']
            states[key] = {'state': 'detected' if detected else 'clear', 'name': m['name'],
                           'p': round(p, 3), 'threshold': m['threshold']}
            if not detected:
                continue
            drivers = [n for n, c in parts if c > 0][:3] or [parts[0][0]]
            level = zones.get(m['id'], 'WARNING')
            h = m['held_out']
            threats.append({
                'id': m['id'], 'label': m['name'], 'severity': SEVERITY_OF_ZONE.get(level, 'MEDIUM'),
                'zone': level, 'confidence': round(p, 3), 'contributing': drivers,
                'description': '; '.join(_fmt(n, f[n]) for n in drivers)
                               + f". Model: {h['precision']:.0%} precision, {h['recall']:.0%} recall "
                                 f"on held-out data from {m['data']['trials']} trials.",
            })
            log.append(f"{m['name']}: p = {p:.2f} ≥ threshold {m['threshold']} "
                       f"({', '.join(f'{n} {c:+.2f}' for n, c in parts)})")

        # Fallback rules for hazards with no trained model (fallback_rules.json)
        ruled = {k: r for k, r in self.rules.items() if k not in trained}
        for key, rule in ruled.items():
            hz = HAZARDS[key]
            conds = [c for c in rule.get('any', []) if len(c) == 3 and c[1] in _OPS]
            avail = [c for c in conds if f.get(c[0]) is not None]
            if not avail:
                names = [c[0] for c in conds]
                why = sorted({SOURCE_NAME[SOURCE_OF[n]] for n in names if not live[SOURCE_OF[n]]})
                reason = (f"{', '.join(why)} offline" if why
                          else f"waiting for {', '.join(names)}")
                states[key] = {'state': 'unavailable', 'name': hz['name'], 'reason': reason,
                               'method': 'rule'}
                log.append(f"{hz['name']} (rule): cannot evaluate — {reason}")
                continue
            hits = [c for c in avail if _OPS[c[1]](f[c[0]], c[2])]
            # p is 1/0 for a rule (fired or not) so the health score can use it
            states[key] = {'state': 'detected' if hits else 'clear', 'name': hz['name'],
                           'method': 'rule', 'p': 1.0 if hits else 0.0,
                           'rule': ' or '.join(f"{n} {op} {th}" for n, op, th in conds)}
            if not hits:
                continue
            level = zones.get(hz['id'], 'WARNING')
            threats.append({
                'id': hz['id'], 'label': hz['name'], 'severity': SEVERITY_OF_ZONE.get(level, 'MEDIUM'),
                'zone': level, 'confidence': 1.0, 'contributing': [c[0] for c in hits],
                'description': '; '.join(_fmt(c[0], f[c[0]]) for c in hits)
                               + '. Fallback rule (fallback_rules.json), not a trained model.',
            })
            log.append(f"{hz['name']} (rule): " + ', '.join(f"{n} {f[n]:.2f} {op} {th}" for n, op, th in hits))

        for key, why in (self.model or {}).get('not_trained', {}).items():
            if key not in states:
                states[key] = {'state': 'untrained', 'reason': why}

        # People in view while a hazard is detected (count comes from the camera model)
        people = int(f['cam_people'] or 0)
        if people and threats:
            top = max(threats, key=lambda t: t['confidence'])
            threats.append({
                'id': 'MASS_CASUALTY_RISK', 'label': 'People at Risk', 'severity': top['severity'],
                'zone': top['zone'], 'confidence': top['confidence'],
                'contributing': ['cam_people'] + top['contributing'][:2],
                'description': f"{people} person(s) in camera view while {top['label'].lower()} is detected.",
            })
            log.append(f"People at Risk: {people} in view + {top['label']}")

        # ── zone status ────────────────────────────────────────────────────────
        evaluable = [s for s in states.values() if s['state'] in ('clear', 'detected')]
        if not trained and not ruled:
            status, level = 'UNTRAINED', 0
            action = ('No Model', 'The fusion model has not been trained. Record trials with '
                                  'record_trials.py, then run train_fusion.py.')
            log.insert(0, 'No trained hazard models — no verdict')
        elif not any_live or not evaluable:
            status, level = 'NO_DATA', 0
            action = ('No Live Data', 'No trained hazard can be evaluated from the sources that are live. '
                                      'Check the sensor board, detect.py and audio_detect.py.')
        else:
            level = max((ZONE_RANK.get(t['zone'], 2) for t in threats), default=0)
            esc = self.policy.get('escalate_to_catastrophic', {})
            critical = [t for t in threats if t['zone'] == 'CRITICAL' and t['id'] != 'MASS_CASUALTY_RISK']
            if critical and ((esc.get('people_in_view_during_critical_hazard') and people) or
                             (esc.get('two_or_more_critical_hazards') and len(critical) >= 2)):
                level = 4
            status = ZONE_STATUS[level]
            label, detail = self.policy.get('actions', {}).get(status, [status.title(), ''])
            tips = [self.policy.get('guidance', {}).get(t['id']) for t in threats[:4]]
            tips = [t for t in tips if t]
            action = (label, detail + (' ' + '. '.join(tips) + '.' if tips else ''))
            unchecked = [f"{s['name']} ({s['reason']})" for s in states.values()
                         if s['state'] == 'unavailable']
            if unchecked:
                action = (action[0], action[1] + ' Not checked right now: ' + '; '.join(unchecked) + '.')

        if fx['calibrating']:
            pct = min(b.progress for s, b in self.fx.gas.items() if cur.get(s) is not None)
            log.insert(0, f'Gas sensors learning their clean-air level ({pct:.0%})')
        for src, on in live.items():
            if not on:
                log.append(f'{SOURCE_NAME[src]} offline')

        threats.sort(key=lambda t: (ZONE_RANK.get(t['zone'], 0), t['confidence']), reverse=True)
        self.published = self._publish(cur, f, now) if live['board'] else None
        missing = sorted(k for k in ('temperature', 'humidity', 'pressure', 'mq2', 'mq4', 'mq135',
                                     'roll', 'pitch', 'water_detected')
                         if live['board'] and cur.get(k) is None)

        return {
            'timestamp':          now.strftime(TS_FMT),
            'zone':               zone,
            'data_mode':          'SIMULATED' if origin == 'simulation' else 'LIVE',
            'sources': {
                'sensors': {'live': live['board'], 'origin': origin if live['board'] else None,
                            'age_s': fx['board_age_s'], 'calibrating': fx['calibrating'],
                            'missing': missing},
                'camera':  {'live': live['camera'], 'age_s': vision.get('age_s'),
                            'source': vision.get('source')},
                'audio':   {'live': live['audio'], 'age_s': audio.get('age_s')},
            },
            'model': None if not self.model else {
                'trained_at': self.model.get('trained_at'),
                'trials':     self.model.get('trials'),
                'evaluation': self.model.get('evaluation'),
                'hazards':    {k: {'name': m['name'], 'threshold': m['threshold'],
                                   'trials': m['data']['trials'], **m['held_out']}
                               for k, m in trained.items()},
            },
            'hazard_states':      states,
            'features':           f,
            'sensor_classes':     self._inputs(cur, f, live),
            'threats':            threats,
            'zone_status':        status,
            'threat_level':       level,
            'recommended_action': action[0].upper().replace(' ', '_'),
            'action_label':       action[0],
            'action_detail':      action[1],
            'confidence':         round(len(evaluable) / (len(trained) + len(ruled)), 2)
                                  if (trained or ruled) else 0.0,
            'rules':              sorted(ruled),
            'decision_log':       log,
            'processing_time_ms': round((time.monotonic() - t0) * 1000, 2),
        }

    # ── what the dashboard's "Live Inputs" table shows: values only, no grading ─

    def _inputs(self, cur: dict, f: dict, live: dict) -> dict:
        def row(value, display, source, note=''):
            if not live[source] or value is None:
                return {'value': None, 'status': 'OFFLINE', 'label': note or 'No data',
                        'rank': 0, 'display': '—'}
            return {'value': value, 'status': 'LIVE', 'label': note, 'rank': 0, 'display': display}

        sc = {
            'temperature': row(f['temp'], f"{f['temp'] or 0:.1f} °C", 'board'),
            'humidity':    row(f['humidity'], f"{f['humidity'] or 0:.0f} %", 'board'),
            'pressure':    row(cur.get('pressure'), f"{cur.get('pressure') or 0:.0f} hPa", 'board'),
        }
        for s in GAS_SENSORS:
            rise = f[f'{s}_rise']
            if live['board'] and cur.get(s) is not None and rise is None:
                sc[s] = {'value': None, 'status': 'CALIBRATING', 'label': 'Learning clean-air level',
                         'rank': 0, 'display': f'{self.fx.gas[s].progress:.0%}'}
            else:
                sc[s] = row(rise, f"{(rise or 0) * 100:+.0f} %", 'board')
        sc['tilt'] = row(f['tilt_deg'], f"{f['tilt_deg'] or 0:.0f}°", 'board')
        sc['water_detected'] = row(f['water'], 'WET' if f['water'] else 'DRY', 'board')
        sc['people_detected'] = row(f['cam_people'], f"{f['cam_people'] or 0:.0f}", 'camera')
        sc['rubble'] = row(f['cam_rubble_frac'], f"{f['cam_rubble_frac'] or 0:.0%} of frames", 'camera')
        sc['spills'] = row(f['cam_spill_frac'], f"{f['cam_spill_frac'] or 0:.0%} of frames", 'camera')
        aud = {k[4:]: v for k, v in f.items() if k.startswith('aud_') and v is not None}
        top = max(aud.items(), key=lambda kv: kv[1]) if aud else None
        sc['audio'] = row(top[1] if top else None,
                          f"{top[0]} {top[1]:.2f}" if top else '—', 'audio',
                          note='' if top else 'Waiting for audio scores')
        return sc

    # ── reading published to sensor_log.json ───────────────────────────────────

    def _publish(self, cur: dict, f: dict, now: datetime) -> dict:
        """
        The reading the dashboard shows. mq2 / mq4 / mq135 are the percent rise
        over the sensor's clean-air level (0 = clean air, 100 = double), never
        below 0. The board's raw numbers are kept as *_raw.
        """
        out = {k: v for k, v in cur.items() if not k.startswith('_')}
        out['timestamp'] = now.strftime(TS_FMT)
        for s in GAS_SENSORS:
            rise = f[f'{s}_rise']
            out[f'{s}_raw'] = cur.get(s)
            out[s] = None if rise is None else round(max(rise, 0.0) * 100, 1)
        out['air_toxicity'] = out['mq135']
        out['gas_calibrating'] = any(cur.get(s) is not None and not self.fx.gas[s].calibrated
                                     for s in GAS_SENSORS)
        out['people_detected'] = int(f['cam_people'] or 0)
        frac = [v for v in (f['cam_rubble_frac'], f['cam_spill_frac']) if v is not None]
        out['event_rate'] = round(max(frac), 2) if frac else 0.0
        return out


# ─── Engine tests ──────────────────────────────────────────────────────────────

def _run_tests() -> bool:
    """
    Tests the engine's behaviour with a small stand-in model. They check the
    machinery (untrained, offline, unavailable, policy), not detection accuracy:
    accuracy is whatever train_fusion.py measures on your recorded trials.
    """
    from datetime import timedelta
    T0 = datetime(2026, 10, 9, 10, 0, 0)
    held = {'precision': 1.0, 'recall': 1.0, 'f1': 1.0}
    model = {'trained_at': 'test', 'hazards': {
        'gas': {'id': 'GAS_LEAK', 'name': 'Gas Leak', 'features': ['mq2_rise'], 'mean': [0.5],
                'scale': [0.5], 'coef': [6.0], 'intercept': 0.0, 'threshold': 0.5,
                'data': {'trials': 3}, 'held_out': held},
        'structural': {'id': 'STRUCTURAL_STRESS', 'name': 'Structural Damage',
                       'features': ['cam_rubble_frac'], 'mean': [0.4], 'scale': [0.3], 'coef': [5.0],
                       'intercept': 0.0, 'threshold': 0.5, 'data': {'trials': 3}, 'held_out': held},
    }, 'not_trained': {'water': '0 trial(s) recorded, need at least 2'}}
    policy = load_json(POLICY_PATH) or {}
    OFF = {'live': False}
    CAM = lambda **kw: {'live': True, 'people': 0, 'rubble': 0, 'spills': 0, **kw}
    calm = lambda i, **kw: {'temperature': 27.0, 'humidity': 60.0, 'pressure': 912.0,
                            'mq2': 410 + i % 3, 'water_detected': False, **kw}

    def play(steps, mdl=model, rules=None):
        eng, out = FusionEngine(model=mdl, policy=policy, rules=rules or {}), None
        for i, (r, cam, mic) in enumerate(steps):
            out = eng.decide(r, cam, mic, now=T0 + timedelta(seconds=i))
        return out

    results = []

    def check(name, out, zone, has=(), lacks=(), state=None):
        ids = {t['id'] for t in out['threats']}
        ok = (out['zone_status'] == zone and all(h in ids for h in has)
              and not any(l in ids for l in lacks)
              and (state is None or out['hazard_states'][state[0]]['state'] == state[1]))
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  →  {out['zone_status']}"
              f"  [{', '.join(sorted(ids)) or 'no threats'}]")

    warm = [(calm(i), CAM(), OFF) for i in range(40)]
    leak = warm + [(calm(i, mq2=410 + 40 * (i - 40)), CAM(), OFF) for i in range(40, 60)]

    check('No model file', play(warm, mdl={}), 'UNTRAINED')
    check('Calm, model loaded', play(warm), 'CLEAR')
    check('Gas rises', play(leak), 'CRITICAL', has=['GAS_LEAK'])
    check('Gas rises with people in view (policy escalates)',
          play(leak[:-10] + [(r, CAM(people=2), m) for r, _, m in leak[-10:]]), 'CATASTROPHIC',
          has=['GAS_LEAK', 'MASS_CASUALTY_RISK'])
    check('People in view, nothing detected', play(warm + [(calm(i), CAM(people=3), OFF) for i in range(10)]),
          'CLEAR', lacks=['MASS_CASUALTY_RISK'])
    check('Camera offline → structural cannot be evaluated, gas still can',
          play([(calm(i), OFF, OFF) for i in range(40)]), 'CLEAR', state=('structural', 'unavailable'))
    check('Board offline during a leak → gas not reported from an old reading',
          play(leak + [(None, CAM(), OFF) for _ in range(15)]), 'CLEAR', lacks=['GAS_LEAK'],
          state=('gas', 'unavailable'))
    check('Gas still calibrating → gas cannot be evaluated yet',
          play([(calm(i, mq2=3000), CAM(), OFF) for i in range(5)]), 'CLEAR', state=('gas', 'unavailable'))
    check('Hazard never recorded stays untrained', play(warm), 'CLEAR', state=('water', 'untrained'))
    check('Nothing connected', play([(None, OFF, OFF)] * 3), 'NO_DATA')
    check('Rubble held in view', play(warm + [(calm(i), CAM(rubble=1), OFF) for i in range(12)]),
          'CRITICAL', has=['STRUCTURAL_STRESS'])

    rules = {'gas':   {'any': [['mq2_rise', '>=', 0.5]]},
             'water': {'any': [['water', '>=', 1]]},
             'tilt':  {'any': [['tilt_deg', '>=', 25]]}}
    check('Rules only, calm', play(warm, mdl={}, rules=rules), 'CLEAR', state=('water', 'clear'))
    check('Rules only, gas rises', play(leak, mdl={}, rules=rules), 'CRITICAL', has=['GAS_LEAK'])
    check('Rule for untrained water fires', play(warm + [(calm(i, water_detected=True), CAM(), OFF)
                                                         for i in range(3)], rules=rules),
          'WARNING', has=['FLOOD_RISK'])
    check('Trained model beats its rule', play(warm, rules={'gas': {'any': [['mq2_rise', '>=', -5]]}}),
          'CLEAR', lacks=['GAS_LEAK'])
    check('Rule with no sensor (tilt) is unavailable, not clear', play(warm, mdl={}, rules=rules),
          'CLEAR', state=('tilt', 'unavailable'))

    print(f"\n  {sum(results)}/{len(results)} passed\n")
    return all(results)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='VERDE Sensor Fusion Engine')
    ap.add_argument('--test', action='store_true', help='Run the engine tests')
    args = ap.parse_args()
    if args.test:
        print('\n=== Fusion engine tests ===\n')
        raise SystemExit(0 if _run_tests() else 1)
    m = load_json(MODEL_PATH)
    if not m:
        print('No fusion_model.json yet. Record trials (record_trials.py), then run train_fusion.py.')
    else:
        print(f"Model trained {m.get('trained_at')} on trials {m.get('trials')}")
        for k, h in m.get('hazards', {}).items():
            print(f"  {k:<12} precision {h['held_out']['precision']:.2f}  recall {h['held_out']['recall']:.2f}"
                  f"  trials {h['data']['trials']}")
        for k, why in m.get('not_trained', {}).items():
            print(f"  {k:<12} not trained — {why}")
    print('\nThe engine is driven by:  python coordinator.py')
