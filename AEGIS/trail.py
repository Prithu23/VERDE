from ultralytics import YOLO
model = YOLO("rubble.pt")

# test on a still image instead of webcam
results = model("test.png", conf=0.1)  # super low conf to catch anything
results[0].show()
print(results[0].boxes)
