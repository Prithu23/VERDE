"""
AEGIS Sensor Fusion Decision Engine (SFDE)
==========================================
Translates raw sensor readings into classified threat assessments using
domain-knowledge rules — no ML required.

The pipeline:
  1. classify_all()         — per-sensor status (NORMAL/CAUTION/ELEVATED/WARNING/CRITICAL)
  2. detect_threats()       — compound multi-sensor rules → active threat list
  3. aggregate_zone_status()— overall zone status (CLEAR → CATASTROPHIC)
  4. recommend_action()     — actionable response instruction

Usage:
  python fusion_engine.py               # continuous mode (default interval: 1s)
  python fusion_engine.py --interval 2  # poll every 2 seconds
  python fusion_engine.py --once        # single pass, print JSON, exit
  python fusion_engine.py --test        # run built-in scenario tests
"""

import json, math, time, argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent


# ─── Status Levels ─────────────────────────────────────────────────────────────

LEVELS   = ['NORMAL', 'CAUTION', 'ELEVATED', 'WARNING', 'CRITICAL']
RANK     = {s: i for i, s in enumerate(LEVELS)}

SEV_LVLS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
SEV_RANK = {s: i for i, s in enumerate(SEV_LVLS)}

ZONE_STATUS = ['CLEAR', 'ELEVATED', 'WARNING', 'CRITICAL', 'CATASTROPHIC']


# ─── Per-Sensor Rule Tables ─────────────────────────────────────────────────────
# Each table: [(threshold, status, label), ...] sorted highest-threshold first.
# _classify() iterates top-down; first entry where value > threshold wins.
# The last entry uses -inf as a guaranteed catch-all.

TEMP_RULES = [
    ( 55,       'CRITICAL', 'Extreme Heat — Danger to Life'),
    ( 45,       'WARNING',  'High Heat — Fire Risk Zone'),
    ( 38,       'ELEVATED', 'Above Normal — Monitor Closely'),
    ( 20,       'NORMAL',   'Within Safe Range'),
    ( 10,       'CAUTION',  'Cool — Monitor Exposure'),
    (  0,       'ELEVATED', 'Cold — Exposure Risk'),
    (-math.inf, 'WARNING',  'Extreme Cold — Hypothermia Risk'),
]

HUM_RULES = [
    ( 90,       'WARNING',  'Saturated — Slip & Structural Risk'),
    ( 80,       'ELEVATED', 'High Humidity'),
    ( 30,       'NORMAL',   'Within Safe Range'),
    ( 20,       'CAUTION',  'Low Humidity — Fire Risk'),
    ( 10,       'WARNING',  'Very Dry — High Combustion Risk'),
    (-math.inf, 'CRITICAL', 'Extremely Dry — Immediate Fire Risk'),
]

PRESS_RULES = [
    (1040,      'CAUTION',  'High Pressure — Monitor'),
    ( 990,      'NORMAL',   'Normal Range'),
    ( 975,      'CAUTION',  'Low — Possible Structural Event'),
    ( 960,      'WARNING',  'Very Low — Structural Stress'),
    (-math.inf, 'CRITICAL', 'Extreme Low — Structural Failure Risk'),
]

MQ2_RULES = [
    ( 40,       'CRITICAL', 'Explosive Gas — Evacuate Immediately'),
    ( 25,       'WARNING',  'Combustible Gas — High Concentration'),
    ( 15,       'ELEVATED', 'Gas Trace Detected'),
    (  8,       'CAUTION',  'Low Gas Trace — Monitor'),
    (-math.inf, 'NORMAL',   'No Gas Detected'),
]

MQ4_RULES = [
    ( 30,       'CRITICAL', 'High Methane — Explosive Risk'),
    ( 20,       'WARNING',  'Methane Elevated — Ventilate'),
    ( 12,       'ELEVATED', 'Methane Trace Detected'),
    (  6,       'CAUTION',  'Low Methane Trace'),
    (-math.inf, 'NORMAL',   'No Methane Detected'),
]

TOXIC_RULES = [
    ( 60,       'CRITICAL', 'Lethal Toxicity — Immediate Evacuation'),
    ( 40,       'WARNING',  'Dangerous — PPE Required'),
    ( 25,       'ELEVATED', 'Elevated Toxins — Monitor Closely'),
    ( 15,       'CAUTION',  'Mild Toxin Trace'),
    (-math.inf, 'NORMAL',   'Within Safe Limits'),
]

PEOPLE_RULES = [
    (  8,       'CRITICAL', 'Mass Gathering in Hazard Zone'),
    (  5,       'WARNING',  'Multiple Persons at Risk'),
    (  2,       'ELEVATED', 'Personnel Present in Zone'),
    (  0,       'CAUTION',  'Individual Present — Monitor'),
    (-math.inf, 'NORMAL',   'Zone Clear'),
]

EVRATE_RULES = [
    (  5.0,     'CRITICAL', 'Extreme Event Surge'),
    (  3.0,     'WARNING',  'High Anomaly Rate'),
    (  1.5,     'ELEVATED', 'Elevated Activity'),
    (  0.5,     'CAUTION',  'Slight Elevated Activity'),
    (-math.inf, 'NORMAL',   'Baseline Activity'),
]

CLASSIFIERS = {
    'temperature':     TEMP_RULES,
    'humidity':        HUM_RULES,
    'pressure':        PRESS_RULES,
    'mq2':             MQ2_RULES,
    'mq4':             MQ4_RULES,
    'air_toxicity':    TOXIC_RULES,
    'people_detected': PEOPLE_RULES,
    'event_rate':      EVRATE_RULES,
}


# ─── Per-Sensor Classification ─────────────────────────────────────────────────

def _classify(rules: list, value: float) -> tuple:
    for threshold, status, label in rules:
        if value > threshold:
            return status, label
    return rules[-1][1], rules[-1][2]  # guaranteed by -inf sentinel


def classify_all(reading: dict) -> dict:
    """Return sensor_classes: {sensor → {value, status, label, rank}}."""
    result = {}
    for sensor, rules in CLASSIFIERS.items():
        val = float(reading.get(sensor, 0))
        status, label = _classify(rules, val)
        result[sensor] = {'value': val, 'status': status, 'label': label, 'rank': RANK[status]}
    return result


# ─── Helpers for Threat Detection ──────────────────────────────────────────────

def _r(sc: dict, sensor: str) -> int:
    """Rank of a classified sensor (0-4)."""
    return sc.get(sensor, {}).get('rank', 0)

def _v(reading: dict, sensor: str) -> float:
    return float(reading.get(sensor, 0))


# ─── Compound Threat Detection ─────────────────────────────────────────────────

def detect_threats(reading: dict, sc: dict) -> tuple:
    """
    Apply multi-sensor compound rules to identify threat scenarios.
    Evidence weights accumulate; corroboration from multiple sensors
    boosts confidence. Threats below 0.20 confidence are suppressed.

    Returns (threats: list, decision_log: list[str])
    """
    threats = []
    log     = []

    temp  = _v(reading, 'temperature')
    hum   = _v(reading, 'humidity')
    mq2   = _v(reading, 'mq2')
    mq4   = _v(reading, 'mq4')
    tox   = _v(reading, 'air_toxicity')
    ppl   = _v(reading, 'people_detected')
    evr   = _v(reading, 'event_rate')
    press = _v(reading, 'pressure')

    # ── FIRE RISK ──────────────────────────────────────────────────────────────
    fe, fc = 0.0, []
    if   temp > 55: fe += 0.90; fc.append('temperature'); log.append(f"Temp {temp:.1f}°C > 55 — critical heat (+0.90)")
    elif temp > 45: fe += 0.65; fc.append('temperature'); log.append(f"Temp {temp:.1f}°C > 45 — fire zone (+0.65)")
    elif temp > 38: fe += 0.30; fc.append('temperature'); log.append(f"Temp {temp:.1f}°C > 38 — elevated (+0.30)")

    if   mq2 > 35: fe += 0.55; fc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 35 — explosive gas (+0.55)")
    elif mq2 > 20: fe += 0.35; fc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 20 — combustible gas (+0.35)")
    elif mq2 > 12: fe += 0.15; fc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 12 — gas trace (+0.15)")

    if   hum < 20: fe += 0.35; fc.append('humidity'); log.append(f"Humidity {hum:.1f}% < 20 — extreme dryness (+0.35)")
    elif hum < 30: fe += 0.20; fc.append('humidity'); log.append(f"Humidity {hum:.1f}% < 30 — low humidity (+0.20)")

    if len(set(fc)) >= 3:
        fe = min(fe * 1.15, 1.0)
        log.append(f"Multi-sensor corroboration ({len(set(fc))} sensors) → confidence boosted")

    fe = min(fe, 1.0)
    if fe >= 0.25:
        sev = 'CRITICAL' if fe >= 0.85 else 'HIGH' if fe >= 0.55 else 'MEDIUM' if fe >= 0.35 else 'LOW'
        desc_parts = []
        if temp > 38: desc_parts.append(f"temp {temp:.1f}°C")
        if mq2  > 12: desc_parts.append(f"MQ2 gas {mq2:.1f}%")
        if hum  < 30: desc_parts.append(f"low humidity {hum:.1f}%")
        threats.append({'id': 'FIRE_RISK', 'label': 'Fire Risk', 'severity': sev,
                         'confidence': round(fe, 3), 'contributing': list(set(fc)),
                         'description': 'Fire risk conditions: ' + ', '.join(desc_parts) + '.' if desc_parts else 'Elevated fire risk.'})

    # ── GAS LEAK ───────────────────────────────────────────────────────────────
    ge, gc = 0.0, []
    if   mq2 > 40: ge += 0.95; gc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 40 — explosive (+0.95)")
    elif mq2 > 25: ge += 0.75; gc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 25 — dangerous (+0.75)")
    elif mq2 > 15: ge += 0.45; gc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 15 — significant trace (+0.45)")
    elif mq2 >  8: ge += 0.20; gc.append('mq2'); log.append(f"MQ2 {mq2:.1f}% > 8 — low trace (+0.20)")

    if   mq4 > 30: ge += 0.90; gc.append('mq4'); log.append(f"MQ4 {mq4:.1f}% > 30 — explosive methane (+0.90)")
    elif mq4 > 20: ge += 0.65; gc.append('mq4'); log.append(f"MQ4 {mq4:.1f}% > 20 — high methane (+0.65)")
    elif mq4 > 12: ge += 0.35; gc.append('mq4'); log.append(f"MQ4 {mq4:.1f}% > 12 — methane trace (+0.35)")
    elif mq4 >  6: ge += 0.15; gc.append('mq4'); log.append(f"MQ4 {mq4:.1f}% > 6 — low methane (+0.15)")

    if tox > 25 and ge > 0.2:
        ge += 0.20; gc.append('air_toxicity')
        log.append(f"Toxicity {tox:.1f}% corroborates gas leak (+0.20)")

    ge = min(ge, 1.0)
    if ge >= 0.20:
        sev = 'CRITICAL' if ge >= 0.85 else 'HIGH' if ge >= 0.55 else 'MEDIUM' if ge >= 0.30 else 'LOW'
        gas_parts = []
        if mq2 > 8:  gas_parts.append(f"MQ2 {mq2:.1f}% (LPG/smoke)")
        if mq4 > 6:  gas_parts.append(f"MQ4 {mq4:.1f}% (methane)")
        threats.append({'id': 'GAS_LEAK', 'label': 'Gas Leak', 'severity': sev,
                         'confidence': round(ge, 3), 'contributing': list(set(gc)),
                         'description': 'Gas leak indicators: ' + ', '.join(gas_parts) + '.' if gas_parts else 'Gas detected.'})

    # ── TOXIC EXPOSURE ─────────────────────────────────────────────────────────
    te, tc = 0.0, []
    if   tox > 60: te += 0.95; tc.append('air_toxicity'); log.append(f"Toxicity {tox:.1f}% > 60 — lethal (+0.95)")
    elif tox > 40: te += 0.75; tc.append('air_toxicity'); log.append(f"Toxicity {tox:.1f}% > 40 — dangerous (+0.75)")
    elif tox > 25: te += 0.45; tc.append('air_toxicity'); log.append(f"Toxicity {tox:.1f}% > 25 — elevated (+0.45)")
    elif tox > 15: te += 0.20; tc.append('air_toxicity'); log.append(f"Toxicity {tox:.1f}% > 15 — mild trace (+0.20)")

    if ppl > 0 and te >= 0.20:
        boost = 0.15 * min(ppl / 5, 1.0)
        te += boost; tc.append('people_detected')
        log.append(f"{int(ppl)} person(s) in toxic zone — exposure amplified (+{boost:.2f})")

    te = min(te, 1.0)
    if te >= 0.20:
        sev = 'CRITICAL' if te >= 0.85 else 'HIGH' if te >= 0.55 else 'MEDIUM' if te >= 0.30 else 'LOW'
        desc = f"Air toxicity at {tox:.1f}%"
        if ppl > 0: desc += f" with {int(ppl)} person(s) exposed"
        threats.append({'id': 'TOXIC_EXPOSURE', 'label': 'Toxic Exposure', 'severity': sev,
                         'confidence': round(te, 3), 'contributing': list(set(tc)),
                         'description': desc + '.'})

    # ── MASS CASUALTY RISK ─────────────────────────────────────────────────────
    if ppl > 0:
        hazard_rank = max(_r(sc, s) for s in ['temperature', 'mq2', 'mq4', 'air_toxicity'])
        if hazard_rank >= RANK['ELEVATED']:
            ce = min(ppl / 8, 1.0) * 0.70 + (hazard_rank / 4) * 0.30
            ce = min(ce, 1.0)
            if ce >= 0.25:
                sev = ('CRITICAL' if ppl > 5 and hazard_rank >= RANK['WARNING'] else
                       'HIGH'     if ppl > 2  or hazard_rank >= RANK['WARNING'] else 'MEDIUM')
                contrib = ['people_detected'] + [s for s in ['temperature', 'mq2', 'mq4', 'air_toxicity']
                                                  if _r(sc, s) >= RANK['ELEVATED']]
                threats.append({'id': 'MASS_CASUALTY_RISK', 'label': 'Mass Casualty Risk', 'severity': sev,
                                 'confidence': round(ce, 3), 'contributing': contrib,
                                 'description': f"{int(ppl)} person(s) in hazard zone with {LEVELS[hazard_rank]} conditions."})
                log.append(f"Mass casualty: {int(ppl)} people × hazard rank {hazard_rank} → {sev}")

    # ── STRUCTURAL STRESS ──────────────────────────────────────────────────────
    se, sc2 = 0.0, []
    if   press < 960:  se += 0.80; sc2.append('pressure'); log.append(f"Pressure {press:.0f} hPa < 960 — critical structural stress (+0.80)")
    elif press < 975:  se += 0.50; sc2.append('pressure'); log.append(f"Pressure {press:.0f} hPa < 975 — significant stress (+0.50)")
    elif press < 990:  se += 0.25; sc2.append('pressure'); log.append(f"Pressure {press:.0f} hPa < 990 — low pressure (+0.25)")
    elif press > 1040: se += 0.20; sc2.append('pressure'); log.append(f"Pressure {press:.0f} hPa > 1040 — high pressure (+0.20)")

    if   evr > 3.0: se += 0.40; sc2.append('event_rate'); log.append(f"Event rate {evr:.2f} > 3.0 — high structural events (+0.40)")
    elif evr > 1.5: se += 0.20; sc2.append('event_rate'); log.append(f"Event rate {evr:.2f} > 1.5 — elevated events (+0.20)")

    se = min(se, 1.0)
    if se >= 0.25:
        sev = 'CRITICAL' if se >= 0.75 else 'HIGH' if se >= 0.50 else 'MEDIUM' if se >= 0.30 else 'LOW'
        threats.append({'id': 'STRUCTURAL_STRESS', 'label': 'Structural Stress', 'severity': sev,
                         'confidence': round(se, 3), 'contributing': list(set(sc2)),
                         'description': f"Pressure {press:.0f} hPa, event rate {evr:.1f}/s — structural or seismic stress indicated."})

    # ── COMPOUND EMERGENCY — three or more simultaneous HIGH+ threats ──────────
    high_threats = [t for t in threats if SEV_RANK[t['severity']] >= SEV_RANK['HIGH']]
    if len(high_threats) >= 3:
        compound_conf = min(0.65 + 0.10 * (len(high_threats) - 2), 1.0)
        all_contrib   = list({s for t in high_threats for s in t['contributing']})
        threats.append({'id': 'COMPOUND_EMERGENCY', 'label': 'Compound Emergency', 'severity': 'CRITICAL',
                         'confidence': round(compound_conf, 3), 'contributing': all_contrib,
                         'description': f"{len(high_threats)} simultaneous HIGH+ threats — multi-agency response required."})
        log.append(f"Compound emergency triggered: {len(high_threats)} concurrent HIGH+ threats")

    threats.sort(key=lambda t: (SEV_RANK[t['severity']], t['confidence']), reverse=True)
    return threats, log


# ─── Zone Status Aggregation ────────────────────────────────────────────────────

def aggregate_zone_status(sc: dict, threats: list) -> tuple:
    """Returns (zone_status: str, threat_level: int 0-4)."""
    max_sensor_rank = max((v['rank'] for v in sc.values()), default=0)
    threat_esc      = SEV_RANK[threats[0]['severity']] if threats else 0
    effective       = max(max_sensor_rank, threat_esc)
    if any(t['id'] == 'COMPOUND_EMERGENCY' for t in threats):
        effective = 4
    effective = min(effective, 4)
    return ZONE_STATUS[effective], effective


# ─── Action Recommendation ─────────────────────────────────────────────────────

_ACTIONS = {
    0: ('MONITOR',              'Monitor',             'All parameters within normal range. Continue routine monitoring.'),
    1: ('HEIGHTENED_WATCH',     'Heightened Watch',    'Readings outside optimal range. Increase monitoring frequency and check equipment.'),
    2: ('PREPARE_RESPONSE',     'Prepare Response',    'Multiple elevated readings. Alert response teams and prepare resources for deployment.'),
    3: ('EVACUATE_PERSONNEL',   'Evacuate Personnel',  'Hazardous conditions confirmed. Evacuate non-essential personnel. Dispatch emergency response.'),
    4: ('IMMEDIATE_EVACUATION', 'Immediate Evacuation','Catastrophic multi-hazard event. Full evacuation. All agencies notified. Incident command established.'),
}

_THREAT_GUIDANCE = {
    'FIRE_RISK':          lambda t: 'Fire Dept: deploy immediately' if SEV_RANK[t['severity']] >= 2 else None,
    'GAS_LEAK':           lambda t: 'shut off gas supply, no ignition sources' if SEV_RANK[t['severity']] >= 2 else None,
    'TOXIC_EXPOSURE':     lambda t: 'EMS: PPE required for entry' if SEV_RANK[t['severity']] >= 2 else None,
    'MASS_CASUALTY_RISK': lambda t: 'EMS: mass casualty protocol',
    'STRUCTURAL_STRESS':  lambda t: 'clear structure, await assessment' if SEV_RANK[t['severity']] >= 2 else None,
    'COMPOUND_EMERGENCY': lambda t: 'Control Room: all agencies',
}

def recommend_action(threat_level: int, threats: list) -> dict:
    action_id, action_label, detail = _ACTIONS.get(threat_level, _ACTIONS[0])
    guidance = [g for t in threats[:4]
                if (g := _THREAT_GUIDANCE.get(t['id'], lambda _: None)(t)) is not None]
    if guidance:
        detail += ' Specific: ' + '; '.join(guidance) + '.'
    return {'id': action_id, 'label': action_label, 'detail': detail}


# ─── Overall Confidence ────────────────────────────────────────────────────────

def overall_confidence(sc: dict, threats: list) -> float:
    if not threats:
        return 0.95
    avg_conf       = sum(t['confidence'] for t in threats) / len(threats)
    sensor_agree   = sum(1 for v in sc.values() if v['rank'] >= 2) / len(sc)
    return round(min(avg_conf * 0.7 + sensor_agree * 0.3, 1.0), 3)


# ─── Main Decision Entry Point ─────────────────────────────────────────────────

def decide(reading: dict, zone: str = 'Zone A-12') -> dict:
    """Full SFDE pipeline. reading must contain the standard sensor keys."""
    t0 = time.monotonic()

    sensor_classes            = classify_all(reading)
    threats, decision_log     = detect_threats(reading, sensor_classes)
    zone_status, threat_level = aggregate_zone_status(sensor_classes, threats)
    action                    = recommend_action(threat_level, threats)
    confidence                = overall_confidence(sensor_classes, threats)

    return {
        'timestamp':          reading.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        'zone':               zone,
        'sensor_classes':     sensor_classes,
        'threats':            threats,
        'zone_status':        zone_status,
        'threat_level':       threat_level,
        'recommended_action': action['id'],
        'action_label':       action['label'],
        'action_detail':      action['detail'],
        'confidence':         confidence,
        'decision_log':       decision_log,
        'processing_time_ms': round((time.monotonic() - t0) * 1000, 2),
    }


# ─── Built-in Self-Test Scenarios ──────────────────────────────────────────────

_TESTS = [
    {'name': 'All Clear',
     'reading': {'timestamp': '2024-01-15 10:00:00', 'temperature': 27.0, 'humidity': 58.0,
                 'pressure': 1013.0, 'mq2': 5.0, 'mq4': 3.0, 'air_toxicity': 8.0,
                 'people_detected': 0, 'event_rate': 0.3},
     'expect': 'CLEAR'},

    {'name': 'Gas Leak — High MQ2 + Personnel',
     'reading': {'timestamp': '2024-01-15 10:01:00', 'temperature': 29.0, 'humidity': 55.0,
                 'pressure': 1012.0, 'mq2': 30.0, 'mq4': 8.0, 'air_toxicity': 20.0,
                 'people_detected': 2, 'event_rate': 1.8},
     'expect': 'CRITICAL'},

    {'name': 'Fire Risk — High Temp + Dry + Gas + Personnel',
     'reading': {'timestamp': '2024-01-15 10:02:00', 'temperature': 50.0, 'humidity': 18.0,
                 'pressure': 1010.0, 'mq2': 28.0, 'mq4': 5.0, 'air_toxicity': 22.0,
                 'people_detected': 4, 'event_rate': 2.5},
     'expect': 'CATASTROPHIC'},

    {'name': 'Toxic Exposure + Mass Casualty',
     'reading': {'timestamp': '2024-01-15 10:03:00', 'temperature': 32.0, 'humidity': 60.0,
                 'pressure': 1011.0, 'mq2': 8.0, 'mq4': 4.0, 'air_toxicity': 52.0,
                 'people_detected': 6, 'event_rate': 1.2},
     'expect': 'CRITICAL'},

    {'name': 'Compound Emergency',
     'reading': {'timestamp': '2024-01-15 10:04:00', 'temperature': 48.0, 'humidity': 15.0,
                 'pressure': 978.0, 'mq2': 32.0, 'mq4': 22.0, 'air_toxicity': 45.0,
                 'people_detected': 8, 'event_rate': 4.5},
     'expect': 'CATASTROPHIC'},
]

def run_tests():
    print('\n=== SFDE Self-Test ===\n')
    passed = 0
    for s in _TESTS:
        result = decide(s['reading'])
        ok = result['zone_status'] == s['expect']
        if ok: passed += 1
        mark = 'PASS' if ok else 'FAIL'
        threat_summary = [f"{t['id']}({t['severity']}:{t['confidence']:.0%})" for t in result['threats']]
        print(f"  {mark} [{s['name']}]")
        print(f"      Zone:    {result['zone_status']:12s}  (expected {s['expect']})")
        print(f"      Threats: {threat_summary}")
        print(f"      Action:  {result['action_label']}")
        print(f"      Conf:    {result['confidence']:.0%}  ({result['processing_time_ms']:.1f}ms)")
        print()
    print(f"  {passed}/{len(_TESTS)} passed\n")


# ─── Continuous Runner ─────────────────────────────────────────────────────────

def run_continuous(interval: float, zone: str):
    sensor_path = ROOT / 'sensor_log.json'
    out_path    = ROOT / 'fusion_log.json'
    last_ts     = None

    print(f'[SFDE] {sensor_path.name} -> {out_path.name}  (interval {interval}s, zone: {zone})')
    print(f'[SFDE] Status: CLEAR | ELEVATED | WARNING | CRITICAL | CATASTROPHIC\n')

    while True:
        try:
            if not sensor_path.exists():
                time.sleep(interval); continue

            raw  = json.loads(sensor_path.read_text())
            data = raw[-1] if isinstance(raw, list) and raw else (raw if isinstance(raw, dict) else None)
            if not data:
                time.sleep(interval); continue

            ts = data.get('timestamp')
            if ts == last_ts:
                time.sleep(interval); continue

            last_ts = ts
            result  = decide(data, zone)
            out_path.write_text(json.dumps(result, indent=2))

            n_threats = len(result['threats'])
            top = result['threats'][0]['id'] if n_threats else '—'
            print(f"  [{result['timestamp']}]  {result['zone_status']:12s}  L{result['threat_level']}"
                  f"  {result['action_label']:25s}  threats:{n_threats}  top:{top}")

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f'[SFDE] Parse error: {e}')
        except Exception as e:
            print(f'[SFDE] Error: {e}')

        time.sleep(interval)


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='AEGIS Sensor Fusion Decision Engine')
    ap.add_argument('--interval', type=float, default=1.0,          help='Poll interval in seconds (default 1)')
    ap.add_argument('--zone',     default='Zone A-12',              help='Zone label')
    ap.add_argument('--once',     action='store_true',              help='Single pass then exit')
    ap.add_argument('--test',     action='store_true',              help='Run self-test scenarios')
    args = ap.parse_args()

    if args.test:
        run_tests()
    elif args.once:
        raw  = json.loads((ROOT / 'sensor_log.json').read_text())
        data = raw[-1] if isinstance(raw, list) else raw
        print(json.dumps(decide(data, args.zone), indent=2))
    else:
        run_continuous(args.interval, args.zone)
