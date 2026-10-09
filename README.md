# VERDE — Environmental Monitoring & Disaster Response Rover

**V**isual **E**nvironmental **R**econnaissance and **D**isaster **E**valuation

A rover base-station system that combines computer vision, audio classification and sensor fusion to monitor disaster zones, detect hazards and locate survivors. The operator dashboard is called **AEGIS**.

---

## How it fits together

```
 Sensor board (HTTP) ───────────┐
                                │
 Camera ──▶ detect.py ──────────┼──▶ coordinator.py
   (people / rubble / spills)   │       ├─ fusion engine     ──▶ fusion_log.json
                                │       ├─ sensor log        ──▶ sensor_log.json
 Microphone ──▶ audio_detect.py ┘       ├─ anomaly detector  ──▶ anomaly_log.json
   (fire / collapse / distress)         ├─ health score      ──▶ ehs_log.json
                                        └─ Telegram alerts (optional)

 app/ (React + Vite dashboard) polls the JSON files and embeds detect.py's video stream
```

Everything runs on the laptop. The three models (YOLOv8 ×3, YAMNet) run locally; the only
network calls are the map tiles, the map's location lookup and the optional Telegram alert.

**No made-up values.** Hazard weights and thresholds are fitted from trials recorded on the
rover (see below). A sensor the board does not report shows as "—", a source that stops
updating shows as OFFLINE, and with nothing connected the zone status is `NO_DATA`.
Simulated sensors exist only behind `--mode sim` and are labelled SIMULATED on the dashboard.

---

## Repository layout

```
.
├── detect.py              # YOLOv8 people / rubble / spill detection + MJPEG stream
├── audio_detect.py        # YAMNet audio classification from the laptop mic
├── sensor_source.py       # Reads the sensor board, camera state and audio state (with freshness checks)
├── features.py            # Turns board + camera + audio into one row of measurements per tick
├── hazards.py             # The hazards that can be trained, and which measurements each may use
├── record_trials.py       # Records a labelled trial from the real hardware → trials/*.csv
├── train_fusion.py        # Fits the fusion model from the trials → fusion_model.json
├── fusion_engine.py       # Applies the fitted model live → threats, zone status, action
├── response_policy.json   # Your team's decision on how serious each detected hazard is
├── anomaly_detector.py    # Drift, jump, trend and burst detection on learned baselines; also the simulator
├── ehs_calculator.py      # Environmental Health Score: P(no hazard) from the fitted model
├── coordinator.py         # Runs fusion + anomaly + EHS in one process, fires SMS alerts
├── sensor_reader.py       # Older standalone board logger (not needed; the coordinator reads the board)
├── trail.py               # Scratch script: run rubble.pt on test.png
│
├── yolov8n.pt             # People detection (COCO pretrained)
├── rubble.pt              # Damage detection (level1 / level2 / level3)
├── oil.pt                 # Spill detection
├── garbage_model_1.pt     # Not used by any script
├── yamnet.tflite          # Audio classification
├── yamnet_classes.csv     # YAMNet class labels
│
├── app/                   # AEGIS dashboard (React 18, Vite 6, Tailwind 4, Leaflet, Recharts)
│   ├── src/app/components # Dashboard panels
│   ├── src/app/hooks      # Polling hooks for the JSON logs
│   └── vite.config.ts     # Dev-server middleware: JSON logs, /api/notify, /api/location, /api/address
│
├── docs/VERDE_Presentation.html
├── mission_log.json       # Sample / last detection log
└── audio_log.json         # Sample audio log
```

---

## Setup

### Python (3.10+)

```bash
pip install ultralytics opencv-python numpy tensorflow sounddevice requests
```

### Dashboard (Node 18+)

```bash
cd app
npm install
```

To enable Telegram alerts, create a bot with @BotFather and put its token in `app/.env.local`
(it is git-ignored). Each recipient presses Start on the bot once; `python coordinator.py --telegram-setup`
then lists their chat IDs, which are mapped to the contacts' phone numbers:

```
TELEGRAM_BOT_TOKEN=123456789:AAH...
TELEGRAM_CHAT_IDS=9100000000:111111111,9200000000:222222222
```

Without these the coordinator runs alerts in dry-run mode. Check the path with
`python coordinator.py --test-sms`.

---

## Train the fusion model first

The fusion engine has no built-in hazard weights or thresholds. Until it is trained on
recordings from your rover it reports `UNTRAINED` and detects nothing.

**1. Record trials.** With `detect.py` and `audio_detect.py` running, one run per trial:

```bash
python record_trials.py --label gas --sensor-ip <board-ip>     # then follow the prompts
python record_trials.py --label clear --seconds 180            # a calm reference trial
```

Labels: `clear`, `gas`, `fire`, `water`, `structural`, `spill`, `distress`, `tilt`. Each hazard
trial records 60 s calm, then you press Enter when you start the hazard and again when you stop.
Record at least 3 trials per hazard and 3 clear ones, and vary them (distance, amount, angle,
background noise). Trials are saved in `trials/`.

**2. Fit and test.**

```bash
pip install scikit-learn
python train_fusion.py
```

This fits one logistic regression per hazard and prints its results on held-out trials: each
trial is predicted by a model fitted without it. A hazard with fewer than 2 trials, or whose
model does no better than guessing on held-out trials, is not trained and stays off.

**3. Run.** `coordinator.py` loads `fusion_model.json` at start and prints what it loaded.

Retrain whenever the sensors, the room or the camera set-up change.

---

## Running

Open four terminals in the repo root.

**1. Coordinator** (start it with the rover in clean air: the gas sensors calibrate on the first 30 readings)

```bash
python coordinator.py                           # live, board at the default address
python coordinator.py --sensor-ip 192.168.1.50  # board at another address
python coordinator.py --alerts                  # arm Telegram alerts on CRITICAL / CATASTROPHIC
python coordinator.py --mode sim                # simulated sensors, labelled SIMULATED
```

**2. Camera**

```bash
python detect.py                                     # laptop webcam (default)
python detect.py --source phone --ip 192.168.43.1    # Android "IP Webcam" app
python detect.py --source esp32 --ip 192.168.0.11    # ESP32-CAM /capture endpoint
```

**3. Microphone**

```bash
python audio_detect.py                  # default input device
python audio_detect.py --list-devices   # then: --device N
```

**4. Dashboard**

```bash
cd app
npm run dev
```

Then open the URL Vite prints (normally http://localhost:5173).

Any of 2 and 3 can be left out; the coordinator shows that source as offline and works
with the rest. Do not run `sensor_reader.py` or another script that writes
`sensor_log.json` at the same time as the coordinator.

**Tests**

```bash
python fusion_engine.py --test          # engine behaviour tests (untrained, offline, policy)
```

---

## ML models

| Model | File | Task | Dataset | mAP50 |
|-------|------|------|---------|-------|
| YOLOv8n | `yolov8n.pt` | Human detection | COCO (pretrained) | N/A |
| Rubble / damage | `rubble.pt` | Disaster damage (level1/2/3) | disasterthesis (1,404 imgs) | 55.1% |
| Spillage | `oil.pt` | Oil / chemical spill detection | spills-filtered (1,739 imgs) | 96.4% |
| YAMNet | `yamnet.tflite` | Audio classification | Google AudioSet | pretrained |

**Rubble / damage (`rubble.pt`)** — Precision 43.8%, Recall 72.8%, mAP50-95 54.9%. Per class: level1 35.5%, level2 42.6%, level3 86.7%. Best at severe structural damage.

**Spillage (`oil.pt`)** — Precision 97.0%, Recall 92.9%, mAP50-95 81.9%. Single class.

Detection thresholds in `detect.py`: people 0.50, rubble 0.90, spills 0.30.

**Audio (YAMNet)** — 521 AudioSet classes, of which about 30 are mapped to Human, Fire, Explosion/Collapse, Gas Leak and Siren, each with its own minimum score.

---

## How the fusion engine decides

| What | Where it comes from |
|------|---------------------|
| Measurements | `features.py`: what the board, camera and microphone report |
| Weight of each measurement, detection threshold | `fusion_model.json`: fitted from your recorded trials |
| How serious a detected hazard is | `response_policy.json`: your team's decision |

**Measurements.** Per tick: each MQ sensor's rise over its own clean-air level (learned from its
first 30 readings, so raw analog values from any board work), temperature and its rate of change,
humidity, pressure change, tilt, shaking, water; people in view and the share of recent camera
frames showing rubble or a spill; and the highest raw YAMNet score in the last 10 s for fire,
collapse, gas, siren, distress and speech sounds. A measurement is empty when its source is
offline.

**Model.** For each trained hazard, `p = sigmoid(intercept + Σ coef × (x − mean) / scale)`. The
hazard is reported when `p` reaches the threshold that gave the best F1 on held-out trials. The
dashboard shows each model's live `p`, its threshold and its held-out precision and recall.
`hazards.py` lists which measurements each hazard may use (a gas leak cannot move the tilt
sensor); nothing else is set by hand.

**What it will not do.** No model → `UNTRAINED`. Hazard never recorded → never reported. A
needed source offline → that hazard is "cannot evaluate", not "clear". Nothing live → `NO_DATA`.

**Response policy.** How a detected hazard maps to ELEVATED / WARNING / CRITICAL / CATASTROPHIC,
and what action text is shown, cannot be measured: it is a decision. It lives in
`response_policy.json` for your team to edit. People in view matter only when a hazard is
detected at the same time.

**Environmental Health Score** = `100 × Π(1 − p)` over the hazards the model can evaluate: the
model's probability that none of them is present.

**Anomaly detector**: learns each sensor's normal level and noise from its own readings, then
reports drift (CUSUM), jumps (z-score), trends and several sensors rising together. It is shown
on the dashboard and is not an input to the fusion model or the score. Its sensitivity settings
are standard statistical defaults, not fitted.

**Alerts**: with `--alerts`, the coordinator sends a Telegram message (plus a map pin of the rover's GPS position when it has a fix) to the contacts routed to the active
threats when the zone escalates to CRITICAL or CATASTROPHIC, with a 300-second cooldown per contact.

---

## Log formats

`mission_log.json` (written by `detect.py` when anything is detected)

```json
[
  {
    "time": "2026-05-10 14:32:05",
    "lat": null,
    "lon": null,
    "people": 1,
    "damage": [{"type": "level3", "confidence": 0.871}],
    "spills": [{"type": "spillage", "confidence": 0.945}]
  }
]
```

`detection_state.json` (overwritten every frame)

```json
{"timestamp": "2026-05-10 14:32:05", "source": "LAPTOP", "people": 1, "rubble": 0, "spills": 0, "fps": 12.4}
```

`audio_log.json`

```json
[
  {"time": "2026-05-08 14:43:00", "category": "Human", "specific": "Speech", "confidence": 0.964, "lat": null, "lon": null}
]
```

`sensor_log.json`, `anomaly_log.json`, `fusion_log.json`, `ehs_log.json`, `detection_state.json` and `audio_state.json` are generated at runtime and git-ignored. The coordinator and `audio_detect.py` start their logs empty on each run.

---

## Known gaps

- **The model is only as good as the trials.** A few trials in one room give figures for that
  room. Held-out precision and recall are measured on staged hazards, not real incidents.
- **Gas readings are relative** to each sensor's clean-air level, not ppm, and the level is
  learned at start-up: start the coordinator and each trial in clean air.
- **People are not told apart.** The camera cannot distinguish a survivor from a rescuer.
- **Camera thresholds** in `detect.py` (people 0.50, rubble 0.90, spills 0.30) are set by hand
  and decide what the camera reports to the model.
- **Reports page and some panels are still static**: the Reports page's coordinates and readings,
  the emergency-agency cards, the threat level badge, alerts history and criticality status.
- **Dev server only**: the JSON feeds and the `/api/*` endpoints are Vite dev-server middleware.
- **Hardcoded values**: alert contacts and phone numbers in `coordinator.py` and `App.tsx`.
- **Windows webcam**: `detect.py` opens the laptop webcam with DirectShow (`cv2.CAP_DSHOW`).
- **No firmware**: the ESP32 / ESP32-CAM sketches are not in this repo.

---

## License

MIT — see `LICENSE`. Third-party attributions are in `ATTRIBUTIONS.md`.
