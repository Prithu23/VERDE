# VERDE — Environmental Monitoring & Disaster Response Rover

**V**isual **E**nvironmental **R**econnaissance and **D**isaster **E**valuation

A rover base-station system that combines computer vision, audio classification and sensor fusion to monitor disaster zones, detect hazards and locate survivors. The operator dashboard is called **AEGIS**.

---

## How it fits together

```
 Camera (laptop / phone / ESP32-CAM) ──▶ detect.py ──▶ mission_log.json
                                             │          detection_state.json
                                             └────────▶ MJPEG stream :8765/video_feed

 Sensor board (HTTP) or simulator ──▶ coordinator.py
                                        ├─ anomaly_detector  ──▶ anomaly_log.json
                                        ├─ fusion_engine     ──▶ fusion_log.json
                                        ├─ ehs_calculator    ──▶ ehs_log.json
                                        ├─ sensor log        ──▶ sensor_log.json
                                        └─ SMS alerts (Fast2SMS, optional)

 Microphone ──▶ audio_detect.py   (prints predictions only, see Known gaps)

 app/ (React + Vite dashboard) polls the JSON files above and embeds the video stream
```

All Python scripts write their JSON logs into the repo root. The Vite dev server in `app/` serves those files to the dashboard.

---

## Repository layout

```
.
├── detect.py              # YOLOv8 people / rubble / spill detection + MJPEG stream
├── audio_detect.py        # YAMNet audio classification from the laptop mic
├── sensor_reader.py       # Polls the sensor board over HTTP → sensor_log.json
├── anomaly_detector.py    # CUSUM, rolling z-score, trend and burst detection; also the simulator
├── fusion_engine.py       # Rule-based sensor fusion → threats, zone status, recommended action
├── ehs_calculator.py      # Environmental Health Score (0–100, graded)
├── coordinator.py         # Runs anomaly + fusion + EHS in one process, fires SMS alerts
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

To enable SMS alerts, create `app/.env.local` (it is git-ignored):

```
FAST2SMS_API_KEY=your_key
```

Without a key the coordinator runs alerts in dry-run mode and the dashboard's "Send SMS" buttons return an error.

---

## Running

Open three terminals in the repo root.

**1. Sensor pipeline**

```bash
python coordinator.py                    # simulated sensors, no alerts
python coordinator.py --mode http        # live sensor board
python coordinator.py --alerts           # arm SMS on CRITICAL / CATASTROPHIC
python coordinator.py --zone "Zone B-7" --interval 2 --scenario-interval 30
```

**2. Vision**

```bash
python detect.py                         # laptop webcam (default)
python detect.py --source phone --ip 192.168.43.1    # Android "IP Webcam" app
python detect.py --source esp32 --ip 192.168.0.11    # ESP32-CAM /capture endpoint
python detect.py --cam-index 0 --port 8765
```

Press `Q` in the OpenCV window to stop.

**3. Dashboard**

```bash
cd app
npm run dev
```

Then open the URL Vite prints (normally http://localhost:5173).

**Optional**

```bash
python audio_detect.py                   # live YAMNet top-5 predictions
python fusion_engine.py --test           # built-in fusion scenario tests
python sensor_reader.py --interval 2     # log the sensor board without the other engines
```

The individual engines (`anomaly_detector.py`, `fusion_engine.py`, `ehs_calculator.py`) can also be run on their own; `coordinator.py` replaces running all three.

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

---

## Sensor pipeline

**Inputs** (from the sensor board, or simulated): temperature, humidity, pressure, MQ-2 (flammable gas / LPG), MQ-4 (methane), MQ-135 (air quality), MPU-6050 roll / pitch / yaw, water sensor, GPS.

`sensor_reader.py` accepts JSON or CSV from the board and tries the endpoints `/data`, `/csv`, `/sensor`, `/sensors`, `/all`, `/readings`, `/`.

**Fusion engine** classifies each sensor as NORMAL / CAUTION / ELEVATED / WARNING / CRITICAL, then applies multi-sensor rules to raise threats:

`FIRE_RISK`, `GAS_LEAK`, `TOXIC_EXPOSURE`, `MASS_CASUALTY_RISK`, `STRUCTURAL_STRESS`, `FLOOD_RISK`, `TILT_HAZARD`, `COMPOUND_EMERGENCY`

Zone status is one of CLEAR, ELEVATED, WARNING, CRITICAL, CATASTROPHIC, with a recommended action.

**Environmental Health Score** is a weighted score out of 100: climate 30%, visual 30%, audio 20%, anomaly 20%.

**Alerts**: with `--alerts`, the coordinator sends an SMS to the contacts routed to the active threats when the zone escalates to CRITICAL or CATASTROPHIC, with a 300-second cooldown per contact.

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

`sensor_log.json`, `anomaly_log.json`, `fusion_log.json`, `ehs_log.json` and `detection_state.json` are generated at runtime and git-ignored.

---

## Known gaps

- **Audio logging**: `audio_detect.py` only prints its top-5 predictions. It does not yet write `audio_log.json`, so the dashboard and the EHS audio score read the sample file.
- **Dev server only**: the JSON feeds and the `/api/*` endpoints are Vite dev-server middleware. A production build (`npm run build`) has no data source.
- **Hardcoded values**: the sensor board IP (`10.161.238.74`) is set in `sensor_reader.py` and `anomaly_detector.py`; alert contacts and phone numbers are set in `coordinator.py` and `app/src/app/App.tsx`.
- **Windows webcam**: `detect.py` opens the laptop webcam with DirectShow (`cv2.CAP_DSHOW`), which only works on Windows.
- **Static panels**: the emergency-agency cards, threat level badge, alerts history and criticality status in the dashboard are not wired to live data.
- **No firmware**: the ESP32 / ESP32-CAM sketches are not in this repo.

---

## License

MIT — see `LICENSE`. Third-party attributions are in `ATTRIBUTIONS.md`.
