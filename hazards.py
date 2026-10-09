"""
The hazards VERDE can be trained to recognise.

For each hazard this lists which measurements can physically respond to it
(a gas leak cannot change the tilt sensor). That mapping is the only thing
decided by hand. How much each measurement counts, and where the detection
threshold sits, are fitted from your recorded trials by train_fusion.py.
"""

HAZARDS = {
    "gas": {
        "id": "GAS_LEAK", "name": "Gas Leak",
        "features": ["mq2_rise", "mq4_rise", "mq135_rise", "aud_gas"],
        "how": "release lighter gas (unlit) near the MQ sensors",
    },
    "fire": {
        "id": "FIRE_RISK", "name": "Fire / Heat",
        "features": ["temp", "temp_rate", "mq2_rise", "mq135_rise", "aud_fire"],
        "how": "warm the temperature sensor (hair dryer / hot object), smoke, or play fire sounds",
    },
    "water": {
        "id": "FLOOD_RISK", "name": "Flood / Water",
        "features": ["water"],
        "how": "wet the water sensor",
    },
    "structural": {
        "id": "STRUCTURAL_STRESS", "name": "Structural Damage",
        "features": ["cam_rubble_frac", "aud_collapse", "vibration_deg"],
        "how": "hold rubble images in front of the camera and / or play crash and collapse sounds",
    },
    "spill": {
        "id": "SPILL_HAZARD", "name": "Hazardous Spill",
        "features": ["cam_spill_frac", "mq135_rise"],
        "how": "hold spill images in front of the camera",
    },
    "distress": {
        "id": "SURVIVOR_SIGNAL", "name": "Human Distress Heard",
        "features": ["aud_distress"],
        "how": "play screaming / crying / shouting at the microphone",
    },
    "tilt": {
        "id": "TILT_HAZARD", "name": "Unstable Ground",
        "features": ["tilt_deg"],
        "how": "tilt the rover",
    },
}

CLEAR = "clear"
LABELS = [CLEAR] + list(HAZARDS)
