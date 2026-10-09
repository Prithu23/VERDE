"""
AEGIS Detection Engine
======================
Runs all three YOLO models on a live camera source and:
  - Streams annotated MJPEG  →  http://localhost:8765/video_feed
  - Writes detection_state.json  (polled by dashboard every second)
  - Writes mission_log.json      (events with GPS from sensor_log.json)

Sources
-------
  laptop   : built-in / USB webcam via cv2.VideoCapture(0)
  esp32    : ESP32-CAM HTTP snapshot  --ip <camera-ip>

Usage
-----
  python detect.py                          # laptop webcam
  python detect.py --source esp32 --ip 192.168.1.50
"""

import json
import time
import threading
import argparse
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import cv2
import numpy as np
import urllib.request
from ultralytics import YOLO

# ── CLI ───────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description="AEGIS Detection Engine")
ap.add_argument("--source", default="laptop",
                choices=["laptop", "esp32"],
                help="Camera source: laptop webcam or ESP32-CAM (default: laptop)")
ap.add_argument("--ip", default=None,
                help="ESP32-CAM IP address (required when --source esp32)")
ap.add_argument("--cam-index", type=int, default=0,
                help="Webcam device index (default: 0)")
ap.add_argument("--port", type=int, default=8765,
                help="MJPEG stream port (default: 8765)")
args = ap.parse_args()

SOURCE      = args.source
ESP32_IP    = args.ip or "192.168.1.50"
CAPTURE_URL = f"http://{ESP32_IP}/capture"

# ── MJPEG broadcast server ─────────────────────────────────────────────────
_frame_lock  = threading.Lock()
_current_jpg = None

class _MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/video_feed"):
            self.send_response(404); self.end_headers(); return

        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                with _frame_lock:
                    jpg = _current_jpg
                if jpg:
                    self.wfile.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                    )
                    self.wfile.write(jpg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(1 / 20)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *_):
        pass

threading.Thread(
    target=ThreadingHTTPServer(("0.0.0.0", args.port), _MJPEGHandler).serve_forever,
    daemon=True,
).start()

# ── Load models ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  AEGIS Detection Engine")
print(f"  Source : {SOURCE.upper()}" + (f"  ({CAPTURE_URL})" if SOURCE == "esp32" else "  (cv2.VideoCapture(0))"))
print(f"  Stream : http://localhost:{args.port}/video_feed")
print("=" * 60)
print("\n[VERDE] Loading models...")

people_model  = YOLO("yolov8n.pt")   # general COCO — class 0 = person
rubble_model  = YOLO("rubble.pt")    # structural damage
spill_model   = YOLO("oil.pt")       # oil / chemical spills

print(f"[VERDE] ✓ People   — yolov8n.pt")
print(f"[VERDE] ✓ Rubble   — rubble.pt   classes: {list(rubble_model.names.values())}")
print(f"[VERDE] ✓ Spills   — oil.pt      classes: {list(spill_model.names.values())}")
print(f"[VERDE] All models ready. Press Q to quit.\n")

# ── Camera init ───────────────────────────────────────────────────────────
cap = None
if SOURCE == "laptop":
    cap = cv2.VideoCapture(args.cam_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(args.cam_index)   # fallback without DSHOW
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            h, w = frame.shape[:2]
            print(f"[VERDE] Webcam opened  index={args.cam_index}  {w}×{h}")
        else:
            print("[VERDE] WARNING: Webcam opened but no frame — check camera index")
    else:
        print(f"[VERDE] ERROR: Could not open webcam at index {args.cam_index}")

# ── Helpers ───────────────────────────────────────────────────────────────
def _get_frame() -> np.ndarray | None:
    if SOURCE == "laptop":
        if cap is None or not cap.isOpened():
            return None
        ret, frame = cap.read()
        return frame if ret else None

    # ESP32-CAM — JPEG snapshot per frame
    try:
        resp = urllib.request.urlopen(CAPTURE_URL, timeout=2)
        data = resp.read()
        arr  = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR) if len(arr) > 0 else None
    except Exception:
        return None


def _draw_box(frame, x1, y1, x2, y2, label, bgr):
    cv2.rectangle(frame, (x1, y1), (x2, y2), bgr, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
    ty = max(y1 - 4, th + 4)
    cv2.rectangle(frame, (x1, ty - th - 4), (x1 + tw + 6, ty + 2), bgr, -1)
    txt = (0, 0, 0) if sum(bgr) > 400 else (255, 255, 255)
    cv2.putText(frame, label, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.52, txt, 1, cv2.LINE_AA)


def _rover_gps() -> tuple:
    try:
        with open("sensor_log.json") as f:
            records = json.load(f)
        if records:
            last = records[-1]
            if last.get("gps_valid"):
                return last.get("lat"), last.get("lon")
    except Exception:
        pass
    return None, None


# ── Main detection loop ───────────────────────────────────────────────────
mission_log      = []
src_label        = "LAPTOP" if SOURCE == "laptop" else "ESP32"
t0               = time.time()
frame_n          = 0
_last_log_time   = 0.0   # rate-limit mission log to once per 2 s

print("[VERDE] Running headless — feed at http://localhost:8765/video_feed  |  Ctrl+C to stop\n")

try:
    while True:
        frame = _get_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        frame   = cv2.resize(frame, (640, 480))
        frame_n += 1
        fps      = frame_n / max(time.time() - t0, 1)
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Model 1: People  (green) ──────────────────────────────────────
        p_results    = people_model(frame, classes=[0], conf=0.50, iou=0.4, verbose=False)
        people_count = len(p_results[0].boxes)
        for box in p_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            _draw_box(frame, x1, y1, x2, y2, f"Person {float(box.conf[0]):.0%}", (0, 200, 0))

        # ── Model 2: Rubble  (red) ────────────────────────────────────────
        rubble_detections = []
        r_results = rubble_model(frame, conf=0.90, verbose=False)
        for box in r_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls  = rubble_model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            _draw_box(frame, x1, y1, x2, y2, f"{cls} {conf:.0%}", (0, 0, 220))
            rubble_detections.append({"type": cls, "confidence": round(conf, 3)})

        # ── Model 3: Oil spills  (yellow) ─────────────────────────────────
        spill_detections = []
        s_results = spill_model(frame, conf=0.80, verbose=False)
        for box in s_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            _draw_box(frame, x1, y1, x2, y2, f"Spill {conf:.0%}", (0, 220, 220))
            spill_detections.append({"type": "spillage", "confidence": round(conf, 3)})

        rubble_count = len(r_results[0].boxes)
        spill_count  = len(s_results[0].boxes)

        # ── HUD overlay ───────────────────────────────────────────────────
        cv2.rectangle(frame, (0, 0), (640, 28), (10, 10, 10), -1)
        cv2.putText(
            frame,
            f"[{src_label}]  People:{people_count}  Rubble:{rubble_count}  Spills:{spill_count}  {fps:.1f}fps",
            (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 200, 200), 1, cv2.LINE_AA,
        )

        # ── Push annotated frame to MJPEG stream ──────────────────────────
        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        with _frame_lock:
            _current_jpg = jpg.tobytes()

        # ── Write detection state for dashboard ───────────────────────────
        with open("detection_state.json", "w") as f:
            json.dump({
                "timestamp": ts,
                "source":    src_label,
                "people":    people_count,
                "rubble":    rubble_count,
                "spills":    spill_count,
                "fps":       round(fps, 1),
            }, f)

        # ── Mission log (rate-limited to once per 2 s) ───────────────────
        now = time.time()
        if (people_count or rubble_detections or spill_detections) and (now - _last_log_time >= 2.0):
            _last_log_time = now
            lat, lon = _rover_gps()
            mission_log.append({
                "time":   ts,
                "lat":    lat,
                "lon":    lon,
                "people": people_count,
                "damage": rubble_detections,
                "spills": spill_detections,
            })
            print(f"[{ts}]  People:{people_count}  Rubble:{len(rubble_detections)}  Spills:{len(spill_detections)}")
            with open("mission_log.json", "w") as f:
                json.dump(mission_log, f, indent=2)

except KeyboardInterrupt:
    pass
finally:
    if cap:
        cap.release()
    with open("mission_log.json", "w") as f:
        json.dump(mission_log, f, indent=2)
    print(f"\n{'='*50}\nMISSION COMPLETE  —  {len(mission_log)} events logged\n{'='*50}")
