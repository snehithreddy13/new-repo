from __future__ import annotations

import random
import time

import requests

API = "http://localhost:5000/api/incidents"

# Rough San Francisco bounding box
LAT_MIN, LAT_MAX = 37.752, 37.792
LNG_MIN, LNG_MAX = -122.446, -122.395


SEVERITIES = ["high", "medium", "low"]
WEIGHTS = [0.25, 0.45, 0.30]


def generate_event() -> dict:
    return {
        "lat": round(random.uniform(LAT_MIN, LAT_MAX), 6),
        "lng": round(random.uniform(LNG_MIN, LNG_MAX), 6),
        "severity": random.choices(SEVERITIES, weights=WEIGHTS, k=1)[0],
    }


def main():
    print("Starting incident simulator. Ctrl+C to stop.")
    while True:
        payload = generate_event()
        try:
            res = requests.post(API, json=payload, timeout=5)
            print(f"{res.status_code} -> {payload}")
        except requests.RequestException as exc:
            print(f"Failed to send incident: {exc}")
        time.sleep(random.uniform(1.0, 3.0))


if __name__ == "__main__":
    main()
