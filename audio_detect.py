import tensorflow as tf
import numpy as np
import sounddevice as sd
import csv
from datetime import datetime
import json
import os
import requests

TFLITE_URL = "https://tfhub.dev/google/lite-model/yamnet/tflite/1?lite-format=tflite"
CLASSES_URL = "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"

_HEADERS = {"User-Agent": "Mozilla/5.0"}

def _download(url, dest):
    print(f"Downloading {dest} ...")
    r = requests.get(url, headers=_HEADERS, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print("Done.")

if not os.path.exists("yamnet.tflite"):
    _download(TFLITE_URL, "yamnet.tflite")

if not os.path.exists("yamnet_classes.csv"):
    _download(CLASSES_URL, "yamnet_classes.csv")

# Verify files exist
print(f"Model file size: {os.path.getsize('yamnet.tflite')} bytes")
print(f"Classes file size: {os.path.getsize('yamnet_classes.csv')} bytes")

# Load TFLite model
interpreter = tf.lite.Interpreter(model_path="yamnet.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Load class names
with open("yamnet_classes.csv") as f:
    reader = csv.reader(f)
    next(reader)
    class_names = [row[2] for row in reader]

print(f"Loaded {len(class_names)} sound classes")

# Different confidence thresholds per category
CONFIDENCE_THRESHOLDS = {
    "Speech": 0.85,           # high - too noisy otherwise
    "Screaming": 0.4,         # keep sensitive - important
    "Shout": 0.4,
    "Crying, sobbing": 0.4,
    "Whimper": 0.4,
    "Groan": 0.4,
    "Baby cry, infant cry": 0.3,  # keep very sensitive
    "Child speech, kid speaking": 0.5,
    "Cough": 0.5,
}

DEFAULT_THRESHOLD = 0.15  # everything else (fire, explosion, gas, etc.)

SOUND_MAP = {
    "Screaming": "Human", "Shout": "Human", "Crying, sobbing": "Human",
    "Whimper": "Human", "Groan": "Human", "Baby cry, infant cry": "Human",
    "Child speech, kid speaking": "Human", "Cough": "Human", "Speech": "Human",
    "Fire": "Fire", "Crackle": "Fire",
    "Fire alarm": "Fire", "Smoke detector, smoke alarm": "Fire",
    "Explosion": "Explosion/Collapse", "Boom": "Explosion/Collapse",
    "Crash": "Explosion/Collapse", "Thump, thud": "Explosion/Collapse",
    "Breaking": "Explosion/Collapse", "Shatter": "Explosion/Collapse",
    "Hiss": "Gas Leak", "Steam": "Gas Leak",
    "Alarm": "Siren", "Siren": "Siren", "Civil defense siren": "Siren",
    "Fire engine, fire truck (siren)": "Siren", "Ambulance (siren)": "Siren",
    "Dog": "Animal", "Cat": "Animal", "Bark": "Animal", "Meow": "Animal",
    "Thunder": "Weather", "Rain": "Weather", "Wind": "Weather",
    "Helicopter": "Vehicle", "Engine": "Vehicle",
}

audio_log = []

def get_gps():
    return {"lat": None, "lon": None}

SAMPLE_RATE = 16000
DURATION = 1

print("\nVERDE Audio Monitor running... Press Ctrl+C to stop\n")
print(f"{'TIME':<22} {'DETECTED':<25} {'SPECIFIC SOUND':<30} {'CONF':<8}")
print("-" * 85)

# Replace the detection loop with this debug version first
try:
    while True:
        audio = sd.rec(int(SAMPLE_RATE * DURATION), samplerate=SAMPLE_RATE,
                       channels=1, dtype='float32')
        sd.wait()
        waveform = audio.flatten().astype(np.float32)

        interpreter.resize_tensor_input(input_details[0]['index'], waveform.shape)
        interpreter.allocate_tensors()
        interpreter.set_tensor(input_details[0]['index'], waveform)
        interpreter.invoke()

        scores = interpreter.get_tensor(output_details[0]['index'])
        top_indices = np.argsort(scores.mean(axis=0))[::-1]

        # Show TOP 5 predictions regardless of filter
        timestamp = datetime.now().strftime("%H:%M:%S")
        top5 = []
        for idx in top_indices[:5]:
            name = class_names[idx]
            conf = float(scores.mean(axis=0)[idx])
            top5.append(f"{name}({conf:.2f})")

        print(f"{timestamp} | {' | '.join(top5)}")

except KeyboardInterrupt:
    print("Done")