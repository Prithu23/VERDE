# 🌿 VERDE — Environmental Monitoring & Disaster Response Rover

**V**isual **E**nvironmental **R**econnaissance and **D**isaster **E**valuation

A climate-tech rover system that combines computer vision, audio classification, and sensor fusion to monitor disaster zones, detect hazards, and locate survivors.

---

## 🏗️ System Architecture

```
┌─────────────────┐     WiFi      ┌──────────────────────────────────┐
│   ESP32-CAM     │──────────────▶│                                  │
│  (People Count) │   video feed  │         LAPTOP (Base Station)    │
└─────────────────┘               │                                  │
                                  │  ┌─ YOLOv8 (People Detection)   │
┌─────────────────┐     WiFi      │  ├─ YOLOv8 (Rubble Detection)   │
│  Phone Camera   │──────────────▶│  ├─ YOLOv8 (Spill Detection)    │
│ (Hazard Detect) │  IP Webcam    │  ├─ YAMNet (Audio Classification)│
└─────────────────┘               │  ├─ Sensor Data Receiver        │
                                  │  ├─ Streamlit Dashboard         │
┌─────────────────┐     WiFi      │  └─ Mission Logger              │
│     ESP32       │──────────────▶│                                  │
│ (Sensors + GPS) │  JSON data    └──────────────────────────────────┘
└─────────────────┘
```

---

## 🤖 ML Models

| Model | File | Task | Dataset | mAP50 |
|-------|------|------|---------|-------|
| YOLOv8n | `yolov8n.pt` | Human Detection | COCO (pretrained) | N/A |
| Rubble/Damage | `rubble.pt` | Disaster Damage (level1/2/3) | disasterthesis (1,404 imgs) | 55.1% |
| Spillage | `oil.pt` | Oil/Chemical Spill Detection | spills-filtered (1,739 imgs) | **96.4%** |
| YAMNet | `yamnet.tflite` | Audio Classification | Google AudioSet | pretrained |

### Model Performance Details

**Rubble/Damage Detection (`rubble.pt`)**
- Precision: 43.8% | Recall: 72.8% | mAP50-95: 54.9%
- Per class: level1 (minor) 35.5%, level2 (moderate) 42.6%, level3 (severe) **86.7%**
- Best at detecting severe structural damage

**Spillage Detection (`oil.pt`)**
- Precision: **97.0%** | Recall: **92.9%** | mAP50-95: **81.9%**
- Single class (spillage) — highly reliable

**Audio Classification (YAMNet)**
- 7 broad categories: Human, Fire, Explosion/Collapse, Gas Leak, Siren, Animal, Weather
- Per-sound confidence thresholds to reduce false positives

---

## 📁 Project Structure

```
VERDE/
├── models/
│   ├── yolov8n.pt              # Human detection (pretrained)
│   ├── rubble.pt               # Disaster damage detection
│   ├── oil.pt                  # Spillage detection
│   ├── yamnet.tflite           # Audio classification
│   └── yamnet_classes.csv      # YAMNet class labels
│
├── scripts/
│   ├── people_detect.py        # ESP32-CAM → people counting
│   ├── hazard_detect.py        # Phone camera → rubble + spill detection
│   ├── audio_detect.py         # Laptop mic → YAMNet audio classification
│   └── sensor_receiver.py      # ESP32 sensor data over WiFi
│
├── arduino/
│   ├── esp32cam_stream/        # ESP32-CAM video streaming sketch
│   └── esp32_audio/            # ESP32 + INMP441 audio streaming sketch
│
├── logs/
│   ├── people_log.json         # People detection log
│   ├── hazard_log.json         # Rubble + spill detection log
│   └── audio_log.json          # Audio classification log
│
├── dashboard/                  # Streamlit dashboard (Phase 4)
│
└── README.md
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.10+
- Arduino IDE with ESP32 board support
- Android phone with IP Webcam app

### Python Dependencies
```bash
pip install ultralytics opencv-python numpy tensorflow sounddevice requests
```

### Hardware
- ESP32-CAM (AI Thinker) — people detection camera
- ESP32 Dev Module — sensors + optional INMP441 mic
- Android Phone — high-res hazard detection camera
- Sensors: MQ-2, MQ-4, MQ-135, DHT11, HW-611, MPU-6050
- Optional: INMP441 I2S Microphone, NEO-6M GPS Module

---

## 🏃 Running the System

### 1. Start ESP32-CAM
Upload the camera sketch via Arduino IDE. Note the IP from Serial Monitor.

### 2. Start Phone Camera
Open IP Webcam app on phone → Start Server → Note the URL.

### 3. Run Detection Scripts
Open three separate terminals:

```bash
# Terminal 1 — People counting (ESP32-CAM)
python people_detect.py

# Terminal 2 — Hazard detection (Phone camera)
python hazard_detect.py

# Terminal 3 — Audio classification (Laptop mic)
python audio_detect.py
```

### 4. Start Dashboard (when ready)
```bash
streamlit run dashboard.py
```

---

## 📊 Output Format

### people_log.json
```json
[
  {
    "time": "2026-05-10 14:32:01",
    "person_id": 1,
    "total_count": 1,
    "confidence": 0.891,
    "lat": null,
    "lon": null
  }
]
```

### hazard_log.json
```json
[
  {
    "time": "2026-05-10 14:32:05",
    "lat": null,
    "lon": null,
    "damage": [
      {"type": "level3", "confidence": 0.871}
    ],
    "spills": [
      {"type": "spillage", "confidence": 0.945}
    ]
  }
]
```

### audio_log.json
```json
[
  {
    "time": "2026-05-10 14:32:08",
    "category": "Human",
    "specific": "Screaming",
    "confidence": 0.782,
    "lat": null,
    "lon": null
  }
]
```

---

## 🔌 Sensor Data Format (from ESP32)

The ESP32 sends sensor readings as JSON over WiFi:

| Sensor | Measures | Alert Threshold |
|--------|----------|-----------------|
| MQ-2 | Smoke, LPG, CO | > 400 ppm |
| MQ-4 | Methane, Natural Gas | > 300 ppm |
| MQ-135 | Air Quality, VOCs, NH3 | > 500 ppm |
| DHT11 | Temperature & Humidity | Temp > 50°C |
| HW-611 (BMP280) | Barometric Pressure | < 980 hPa |
| MPU-6050 | Tilt / Vibration | Tilt > 15° |
