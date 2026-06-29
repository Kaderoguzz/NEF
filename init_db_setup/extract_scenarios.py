"""
extract_scenarios.py
====================
Reads yjmob100k-dataset1.csv.gz and yjmob100k-dataset2.csv.gz,
builds the impossible-travel scenario exactly like simulate_yjmob_anomaly.py,
and writes scenarios.json for the Leaflet simulation frontend.

Run this script ONCE from the same folder as the .gz files:
    cd ~/NEF/init_db_setup
    python extract_scenarios.py

Then open simulation.html in the same folder (or serve with: python -m http.server 8080).
"""

import gzip
import csv
import json
import math
import os
import sys

# ── Constants (must match simulate_yjmob_anomaly.py) ────────────────────────
GRID_SIZE_DEG = 500 / 111320
ORIGIN_LAT    = 35.50
ORIGIN_LON    = 139.50
MIN_ANOMALY_KM = 30       # minimum distance for anomaly point
NORMAL_POINTS  = 4        # how many normal points to take from dataset1
OUTPUT_FILE    = "scenarios.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

def grid_to_latlon(x, y):
    lat = ORIGIN_LAT + (int(y) + 0.5) * GRID_SIZE_DEG
    lon = ORIGIN_LON + (int(x) + 0.5) * GRID_SIZE_DEG
    return round(lat, 6), round(lon, 6)

def grid_to_polygon(x, y):
    x, y = int(x), int(y)
    lat0 = ORIGIN_LAT + y * GRID_SIZE_DEG
    lon0 = ORIGIN_LON + x * GRID_SIZE_DEG
    lat1 = lat0 + GRID_SIZE_DEG
    lon1 = lon0 + GRID_SIZE_DEG
    return [
        {"lon": lon0, "lat": lat0},
        {"lon": lon1, "lat": lat0},
        {"lon": lon1, "lat": lat1},
        {"lon": lon0, "lat": lat1},
    ]

def cell_id(x, y):
    return f"{int(x):04d}{int(y):04d}"

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ── File discovery ────────────────────────────────────────────────────────────
def find_file(name):
    """Look in current dir and common locations."""
    candidates = [
        name,
        os.path.join(os.path.dirname(__file__), name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

ds1_path = find_file("yjmob100k-dataset1.csv.gz")
ds2_path = find_file("yjmob100k-dataset2.csv.gz")

if not ds1_path or not ds2_path:
    print("ERROR: Dataset files not found.")
    print("  Expected: yjmob100k-dataset1.csv.gz and yjmob100k-dataset2.csv.gz")
    print(f"  Run this script from the folder containing those files.")
    sys.exit(1)

print(f"Dataset1: {ds1_path}")
print(f"Dataset2: {ds2_path}")

# ── Step 1: Read normal points from dataset1 ──────────────────────────────────
print(f"\nReading dataset1 — taking first {NORMAL_POINTS} positions of first user...")
normal_rows = []
target_uid = None

with gzip.open(ds1_path, "rt") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if target_uid is None:
            target_uid = row["uid"]
        if row["uid"] != target_uid:
            break
        if len(normal_rows) < NORMAL_POINTS:
            normal_rows.append(row)

if len(normal_rows) == 0:
    print("ERROR: No rows read from dataset1.")
    sys.exit(1)

print(f"  uid={target_uid}, {len(normal_rows)} normal points")

# Reference point = last normal position
x_ref = int(normal_rows[-1]["x"])
y_ref = int(normal_rows[-1]["y"])
lat_ref, lon_ref = grid_to_latlon(x_ref, y_ref)

# ── Step 2: Find anomaly point from dataset2 ──────────────────────────────────
print(f"\nReading dataset2 — looking for a point >= {MIN_ANOMALY_KM} km from reference...")
anomaly_row = None

with gzip.open(ds2_path, "rt") as f:
    reader = csv.DictReader(f)
    for row in reader:
        x2, y2 = int(row["x"]), int(row["y"])
        lat2, lon2 = grid_to_latlon(x2, y2)
        dist = haversine_km(lat_ref, lon_ref, lat2, lon2)
        if dist >= MIN_ANOMALY_KM:
            anomaly_row = row
            anomaly_row["_dist"] = dist
            break

if anomaly_row is None:
    print(f"ERROR: No point found >= {MIN_ANOMALY_KM} km in dataset2.")
    sys.exit(1)

x_anom = int(anomaly_row["x"])
y_anom = int(anomaly_row["y"])
lat_anom, lon_anom = grid_to_latlon(x_anom, y_anom)
dist_anom = anomaly_row["_dist"]
print(f"  Anomaly point: x={x_anom} y={y_anom} -> lat={lat_anom} lon={lon_anom} ({dist_anom:.1f} km away)")

# ── Step 3: MSISDN ───────────────────────────────────────────────────────────
msisdn = f"81{int(target_uid):010d}"
print(f"\nMSISDN: {msisdn}")

# ── Step 4: Build scenario list ───────────────────────────────────────────────
scenarios = []
prev_lat, prev_lon = None, None

for i, row in enumerate(normal_rows):
    x, y = int(row["x"]), int(row["y"])
    lat, lon = grid_to_latlon(x, y)
    cid = cell_id(x, y)
    dist = 0.0
    if prev_lat is not None:
        dist = haversine_km(prev_lat, prev_lon, lat, lon)
    scenarios.append({
        "step":    i + 1,
        "label":   f"Normal Movement #{i + 1}",
        "type":    "NORMAL",
        "cellId":  cid,
        "x": x, "y": y,
        "lat": lat, "lon": lon,
        "dist_km": round(dist, 4),
        "day": int(row["d"]),
        "timeslot": int(row["t"]),
        "msisdn": msisdn,
        "polygon": grid_to_polygon(x, y),
        "dataset": "dataset1",
        "uid": target_uid,
        "suspicious": False,
        "decision": "ALLOW",
    })
    prev_lat, prev_lon = lat, lon

# Anomaly point
cid_anom = cell_id(x_anom, y_anom)
scenarios.append({
    "step":    len(scenarios) + 1,
    "label":   "ANOMALY — Distant Location (Dataset2)",
    "type":    "ANOMALY",
    "cellId":  cid_anom,
    "x": x_anom, "y": y_anom,
    "lat": lat_anom, "lon": lon_anom,
    "dist_km": round(dist_anom, 4),
    "day": int(anomaly_row["d"]),
    "timeslot": int(anomaly_row["t"]),
    "msisdn": msisdn,
    "polygon": grid_to_polygon(x_anom, y_anom),
    "dataset": "dataset2",
    "uid": anomaly_row["uid"],
    "suspicious": True,
    "decision": "BLOCK",
})

# Return to last normal position (simultaneous location — impossible travel)
last_normal = scenarios[-2]
scenarios.append({
    "step":    len(scenarios) + 1,
    "label":   "Return — Simultaneous Location",
    "type":    "ANOMALY",
    "cellId":  last_normal["cellId"],
    "x": last_normal["x"], "y": last_normal["y"],
    "lat": last_normal["lat"], "lon": last_normal["lon"],
    "dist_km": round(dist_anom, 4),
    "day": last_normal["day"],
    "timeslot": last_normal["timeslot"],
    "msisdn": msisdn,
    "polygon": last_normal["polygon"],
    "dataset": "dataset1+dataset2",
    "uid": target_uid,
    "suspicious": True,
    "decision": "BLOCK",
})

# ── Step 5: Write JSON ────────────────────────────────────────────────────────
output = {
    "msisdn": msisdn,
    "target_uid": target_uid,
    "mcc": "440",
    "mnc": "10",
    "origin_lat": ORIGIN_LAT,
    "origin_lon": ORIGIN_LON,
    "grid_size_deg": GRID_SIZE_DEG,
    "min_anomaly_km": MIN_ANOMALY_KM,
    "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    "scenarios": scenarios,
}

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nWrote {len(scenarios)} scenarios to: {out_path}")
print("\nSummary:")
for sc in scenarios:
    flag = "ANOMALY 🚨" if sc["type"] == "ANOMALY" else "normal  ✅"
    print(f"  [{sc['step']}] {flag}  lat={sc['lat']:.5f} lon={sc['lon']:.5f}  dist={sc['dist_km']:.2f} km")

print("\nDone. Open simulation.html in a browser (same folder), or:")
print("  python -m http.server 8080")
print("  then go to http://localhost:8080/simulation.html")
