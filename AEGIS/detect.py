from ultralytics import YOLO
import cv2
import urllib.request
import numpy as np
from datetime import datetime
import json
import argparse
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Args ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description='VERDE detection engine')
ap.add_argument('--source', default='esp32',
                help='"esp32" for rover camera (default), "laptop" for webcam')
ap.add_argument('--cam-index', type=int, default=-1,
                help='Webcam index to use. -1 = auto-detect best (default)')
ap.add_argument('--port', type=int, default=8765,
                help='MJPEG stream port (default 8765)')
args = ap.parse_args()

ESP32_IP    = "10.97.202.27"
CAPTURE_URL = f"http://{ESP32_IP}/capture"
USE_WEBCAM  = args.source.lower() in ('laptop', '0')

# ── MJPEG server ──────────────────────────────────────────────────────────────
_lock        = threading.Lock()
_current_jpg = None

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            while True:
                with _lock:
                    jpg = _current_jpg
                if jpg:
                    self.wfile.write(
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n'
                        b'Content-Length: ' + str(len(jpg)).encode() + b'\r\n'
                        b'\r\n'
                    )
                    self.wfile.write(jpg)
                    self.wfile.write(b'\r\n')
                    self.wfile.flush()
                time.sleep(1 / 20)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
    def log_message(self, *_): pass

threading.Thread(
    target=HTTPServer(('0.0.0.0', args.port), _Handler).serve_forever,
    daemon=True
).start()
print(f"[VERDE] Annotated stream  →  http://localhost:{args.port}")

# ── Models ────────────────────────────────────────────────────────────────────
print("[VERDE] Loading models...")
human_model    = YOLO("yolov8n.pt")
disaster_model = YOLO("rubble.pt")
spill_model    = YOLO("oil.pt")
print(f"[VERDE] Models ready  |  rubble classes: {list(disaster_model.names.values())}  |  oil classes: {list(spill_model.names.values())}")

mission_log = []

# ── Webcam setup ──────────────────────────────────────────────────────────────
cap = None
if USE_WEBCAM:
    indices = [args.cam_index] if args.cam_index >= 0 else [1, 0]
    for idx in indices:
        test = cv2.VideoCapture(idx)          # default backend — DSHOW fails by-index on this system
        if test.isOpened():
            ret, frame = test.read()
            if ret and frame is not None:
                cap = test
                h, w = frame.shape[:2]
                print(f"[VERDE] Webcam  index={idx}  {w}×{h}")
                break
        test.release()
    if cap is None:
        print("[VERDE] ERROR: No webcam found — run with --source esp32 or check camera")

# ── Frame getter ──────────────────────────────────────────────────────────────
def get_frame():
    if USE_WEBCAM:
        if cap is None:
            return None
        ret, frame = cap.read()
        return frame if ret else None
    try:
        resp = urllib.request.urlopen(CAPTURE_URL, timeout=5)
        arr  = np.frombuffer(resp.read(), dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[VERDE] ESP32 frame error: {e}")
        return None

# ── Drawing helpers ───────────────────────────────────────────────────────────
def draw_box(frame, x1, y1, x2, y2, label, color):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    ty = max(y1 - 4, th + 4)
    cv2.rectangle(frame, (x1, ty - th - 4), (x1 + tw + 6, ty + 2), color, -1)
    txt_color = (0, 0, 0) if sum(color) > 400 else (255, 255, 255)
    cv2.putText(frame, label, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, txt_color, 1, cv2.LINE_AA)

# ── Main loop ─────────────────────────────────────────────────────────────────
src_label  = "LAPTOP" if USE_WEBCAM else "ESP32"
t0         = time.time()
frame_n    = 0

print(f"[VERDE] Source: {src_label}  |  Press Q in the OpenCV window to quit")

while True:
    frame = get_frame()
    if frame is None:
        time.sleep(0.05)
        continue

    frame   = cv2.resize(frame, (640, 480))
    frame_n += 1
    fps      = frame_n / max(time.time() - t0, 1)
    ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── People (green) — iou=0.4 prevents merged boxes on grouped people ──
    h_results    = human_model(frame, classes=[0], conf=0.50, iou=0.4, verbose=False)
    people_count = len(h_results[0].boxes)
    for box in h_results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        draw_box(frame, x1, y1, x2, y2, f"Person {conf:.0%}", (0, 200, 0))

    # ── Rubble / damage (red) — draw at 0.30, log at 0.95 ────────────────
    disaster_detections = []
    d_results = disaster_model(frame, conf=0.90, verbose=False)
    for box in d_results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls_name = disaster_model.names[int(box.cls[0])]
        conf     = float(box.conf[0])
        draw_box(frame, x1, y1, x2, y2, f"{cls_name} {conf:.0%}", (0, 0, 220))
        if conf >= 0.90:
            disaster_detections.append({"type": cls_name, "confidence": round(conf, 3)})

    # ── Oil spills (yellow) ───────────────────────────────────────────────
    spill_detections = []
    s_results = spill_model(frame, conf=0.30, verbose=False)
    for box in s_results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        draw_box(frame, x1, y1, x2, y2, f"Spillage {conf:.0%}", (0, 220, 220))
        spill_detections.append({"type": "spillage", "confidence": round(conf, 3)})

    # ── HUD bar ───────────────────────────────────────────────────────────
    cv2.rectangle(frame, (0, 0), (640, 26), (10, 10, 10), -1)
    cv2.putText(
        frame,
        f"[{src_label}]  Person:{people_count}  Rubble:{len(d_results[0].boxes)}  Spill:{len(s_results[0].boxes)}  {fps:.1f}fps",
        (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, cv2.LINE_AA
    )

    # ── Push to MJPEG server ─────────────────────────────────────────────
    _, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    with _lock:
        _current_jpg = jpg.tobytes()

    # ── Real-time detection state (polled by dashboard every second) ──────
    with open("detection_state.json", "w") as f:
        json.dump({
            "timestamp": ts,
            "source":    src_label,
            "people":    people_count,
            "rubble":    len(d_results[0].boxes),
            "spills":    len(s_results[0].boxes),
            "fps":       round(fps, 1),
        }, f)

    # ── Mission log ───────────────────────────────────────────────────────
    if people_count or disaster_detections or spill_detections:
        entry = {
            "time":   ts,
            "lat":    None,
            "lon":    None,
            "people": people_count,
            "damage": disaster_detections,
            "spills": spill_detections,
        }
        mission_log.append(entry)
        print(f"[{ts}] Person:{people_count}  Rubble:{len(disaster_detections)}  Spill:{len(spill_detections)}")
        with open("mission_log.json", "w") as f:
            json.dump(mission_log, f, indent=2)

    cv2.imshow(f"VERDE — {src_label}", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ── Cleanup ───────────────────────────────────────────────────────────────────
if cap:
    cap.release()
cv2.destroyAllWindows()

with open("mission_log.json", "w") as f:
    json.dump(mission_log, f, indent=2)

print(f"\n{'='*50}\nMISSION COMPLETE  —  {len(mission_log)} events logged\n{'='*50}")
