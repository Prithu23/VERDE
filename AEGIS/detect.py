from ultralytics import YOLO
import cv2
import urllib.request
import numpy as np
from datetime import datetime
import json

# ESP32-CAM
ESP32_IP = "192.168.0.11"
CAPTURE_URL = f"http://{ESP32_IP}/capture"

# Load all models
human_model = YOLO("yolov8n.pt")
disaster_model = YOLO("rubble.pt")
spill_model = YOLO("oil.pt")

# Master log - everything goes here
mission_log = []

def get_gps():
    return {"lat": None, "lon": None}

while True:
    try:
        img_resp = urllib.request.urlopen(CAPTURE_URL, timeout=5)
        img_array = np.array(bytearray(img_resp.read()), dtype=np.uint8)
        frame = cv2.imdecode(img_array, -1)
        if frame is None:
            continue

        frame = cv2.resize(frame, (640, 480))
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gps = get_gps()

        # --- HUMANS (green) ---
        human_results = human_model(frame, classes=[0], conf=0.5, verbose=False)
        people_count = len(human_results[0].boxes)
        for box in human_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"Person {conf:.2f}", (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # --- DISASTER/RUBBLE (red) ---
        disaster_detections = []
        disaster_results = disaster_model(frame, conf=0.5, verbose=False)
        for box in disaster_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            label = disaster_model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            disaster_detections.append({"type": label, "confidence": round(conf, 3)})
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # --- SPILLS (yellow) ---
        spill_detections = []
        spill_results = spill_model(frame, conf=0.5, verbose=False)
        for box in spill_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            spill_detections.append({"type": "spillage", "confidence": round(conf, 3)})
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(frame, f"Spill {conf:.2f}", (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        # --- LOG ONLY WHEN SOMETHING IS DETECTED ---
        if people_count  or disaster_detections or spill_detections:
            entry = {
                "time": timestamp,
                "lat": gps["lat"],
                "lon": gps["lon"],
                "people": people_count,
                "damage": disaster_detections,
                "spills": spill_detections
            }
            mission_log.append(entry)
            print(f"[{timestamp}] People: {people_count} | Damage: {len(disaster_detections)} | Spills: {len(spill_detections)}")

            # Save immediately
            with open("mission_log.json", "w") as f:
                json.dump(mission_log, f, indent=2)

        # --- DISPLAY ---
        cv2.putText(frame, f"People: {people_count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, f"Damage: {len(disaster_detections)}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(frame, f"Spills: {len(spill_detections)}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, f"Log: {len(mission_log)} events", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("VERDE Rover", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except Exception as e:
        print(f"Frame error: {e}")
        continue

cv2.destroyAllWindows()

# Save mission log
with open("mission_log.json", "w") as f:
    json.dump(mission_log, f, indent=2)

print(f"\n{'='*50}")
print(f"VERDE MISSION COMPLETE")
print(f"{'='*50}")
print(f"Total events logged: {len(mission_log)}")
print(f"Saved to mission_log.json")