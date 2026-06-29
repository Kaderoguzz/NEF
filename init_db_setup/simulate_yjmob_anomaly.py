"""
YJMob100K dataset'inden anomali simülasyonu.
- Dataset1: normal kullanıcı hareketi
- Dataset2: acil dönem (anormal hareket)
- Aynı MSISDN üzerinde birleştirip impossible travel simüle eder.

Kullanım:
    python simulate_yjmob_anomaly.py
"""

import gzip
import csv
import time
import math
from datetime import datetime, timezone
from pymongo import MongoClient

# ─── Bağlantı ───────────────────────────────────────────────────────────────
client = MongoClient("mongodb://0.0.0.0:27018/")
db = client["amf_logs"]

# ─── Sabitler ───────────────────────────────────────────────────────────────
GRID_SIZE_DEG = 500 / 111320
ORIGIN_LAT    = 35.50
ORIGIN_LON    = 139.50
SLEEP_BETWEEN = 12   # saniye — GET atmak için yeterli süre

# ─── Yardımcı fonksiyonlar ──────────────────────────────────────────────────

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

def ensure_polygon(cid, x, y):
    """cell_to_polygons'da yoksa ekle."""
    if db.cell_to_polygons.find_one({"_id": cid}) is None:
        db.cell_to_polygons.insert_one({
            "_id": cid,
            "geographicArea": {
                "polygon": {
                    "point_list": {
                        "geographical_coords": grid_to_polygon(x, y)
                    }
                }
            }
        })

def update_location(msisdn, cid, x, y):
    """location_info'yu güncelle."""
    db.location_info.update_one(
        {"_id": msisdn},
        {"$set": {
            "cellId": cid,
            "trackingAreaId": f"TA-{cid}",
            "enodeBId": f"ENB-{cid}",
            "routingAreaId": f"RA-{cid}",
            "plmnId": {"mcc": "440", "mnc": "10"},
            "twanId": None,
            "UELocationTimestamp": datetime.now(timezone.utc)
        }},
        upsert=True
    )

def print_separator():
    print("─" * 65)

# ─── Dataset1'den normal noktalar al ────────────────────────────────────────
print("📂 Dataset1 okunuyor (normal hareket)...")
normal_points = []
target_uid = None

with gzip.open("yjmob100k-dataset1.csv.gz", "rt") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if target_uid is None:
            target_uid = row["uid"]
        if row["uid"] != target_uid:
            break
        if len(normal_points) < 4:   # ilk günün ilk 4 konumu
            normal_points.append(row)

print(f"   uid={target_uid} için {len(normal_points)} normal nokta alındı.")

# ─── Dataset2'den uzak nokta al ─────────────────────────────────────────────
print("📂 Dataset2 okunuyor (anormal hareket)...")
anomaly_point = None
x1_ref = int(normal_points[-1]["x"])
y1_ref = int(normal_points[-1]["y"])
lat1_ref, lon1_ref = grid_to_latlon(x1_ref, y1_ref)

with gzip.open("yjmob100k-dataset2.csv.gz", "rt") as f:
    reader = csv.DictReader(f)
    for row in reader:
        x2, y2 = int(row["x"]), int(row["y"])
        lat2, lon2 = grid_to_latlon(x2, y2)
        dist = haversine_km(lat1_ref, lon1_ref, lat2, lon2)
        # En az 30 km uzak bir nokta seç (grid'de ~60 hücre)
        if dist >= 30:
            anomaly_point = row
            break

if anomaly_point is None:
    print("❌ Yeterince uzak anomali noktası bulunamadı!")
    client.close()
    exit()

x_anom = int(anomaly_point["x"])
y_anom = int(anomaly_point["y"])
lat_anom, lon_anom = grid_to_latlon(x_anom, y_anom)
cid_anom = cell_id(x_anom, y_anom)
dist_anom = haversine_km(lat1_ref, lon1_ref, lat_anom, lon_anom)

print(f"   Anomali noktası: x={x_anom} y={y_anom} → "
      f"lat={lat_anom} lon={lon_anom} (mesafe={dist_anom:.1f} km)")

# ─── MSISDN belirle ─────────────────────────────────────────────────────────
msisdn = f"81{int(target_uid):010d}"
print(f"\n🔑 MSISDN: {msisdn}")
print(f"   Bu MSISDN için subscription oluşturduysan hazırsın.")
print_separator()

# ─── Senaryo hazırla ────────────────────────────────────────────────────────
# Normal noktalar (dataset1'den)
scenarios = []
for i, pt in enumerate(normal_points):
    x, y = int(pt["x"]), int(pt["y"])
    lat, lon = grid_to_latlon(x, y)
    cid = cell_id(x, y)
    dist_from_prev = 0
    if i > 0:
        px, py = int(normal_points[i-1]["x"]), int(normal_points[i-1]["y"])
        plat, plon = grid_to_latlon(px, py)
        dist_from_prev = haversine_km(plat, plon, lat, lon)
    scenarios.append({
        "label": f"Normal Hareket #{i+1}",
        "type": "NORMAL",
        "cid": cid, "x": x, "y": y,
        "lat": lat, "lon": lon,
        "dist": dist_from_prev,
        "d": pt["d"], "t": pt["t"]
    })

# Anomali noktası
scenarios.append({
    "label": "🚨 ANOMALİ — Uzak Konum (Dataset2)",
    "type": "ANOMALY",
    "cid": cid_anom, "x": x_anom, "y": y_anom,
    "lat": lat_anom, "lon": lon_anom,
    "dist": dist_anom,
    "d": anomaly_point["d"], "t": anomaly_point["t"]
})

# Geri dön (impossible travel: aynı anda iki yerde)
last_normal = scenarios[-2]
scenarios.append({
    "label": "⚠️  Geri Dönüş — Simultaneous Location",
    "type": "ANOMALY",
    "cid": last_normal["cid"], "x": last_normal["x"], "y": last_normal["y"],
    "lat": last_normal["lat"], "lon": last_normal["lon"],
    "dist": dist_anom,
    "d": last_normal["d"], "t": last_normal["t"]
})

# ─── Simülasyon döngüsü ──────────────────────────────────────────────────────
print(f"\n🚀 Simülasyon başlıyor — {len(scenarios)} adım")
print(f"   Her adım arası bekleme: {SLEEP_BETWEEN} saniye")
print(f"   Bu sürede Swagger'dan GET at:\n")
print(f"   GET /3gpp-monitoring-event-envelope/v1/{msisdn}/subscriptions/{{subscriptionId}}/location-analysis\n")
print_separator()

prev_lat, prev_lon, prev_ts = None, None, None

for i, sc in enumerate(scenarios):
    now = datetime.now(timezone.utc)

    # Polygon ekle (yoksa)
    ensure_polygon(sc["cid"], sc["x"], sc["y"])

    # Konum güncelle
    update_location(msisdn, sc["cid"], sc["x"], sc["y"])

    # Hız tahmini (simülasyon için)
    speed_est = 0
    time_diff_s = SLEEP_BETWEEN if i > 0 else 0
    if prev_lat is not None and time_diff_s > 0:
        dist_km = haversine_km(prev_lat, prev_lon, sc["lat"], sc["lon"])
        speed_est = (dist_km / time_diff_s) * 3600

    # Terminal çıktısı
    print(f"\n[{i+1}/{len(scenarios)}] {sc['label']}")
    print(f"   cellId    : {sc['cid']}")
    print(f"   Konum     : lat={sc['lat']:.5f}, lon={sc['lon']:.5f}")
    print(f"   Dataset   : gün={sc['d']}, dilim={sc['t']}")
    print(f"   Mesafe    : {sc['dist']:.2f} km (önceki konumdan)")
    if speed_est > 0:
        flag = "🚨 IMPOSSIBLE!" if speed_est > 900 else "✅ Normal"
        print(f"   Tahmini hız: {speed_est:.0f} km/h  {flag}")
    print(f"   Tip       : {sc['type']}")
    print(f"   Zaman     : {now.strftime('%H:%M:%S')}")

    if sc["type"] == "ANOMALY":
        print(f"\n   ⚡ Şimdi GET isteği at — anomali görünmeli!")
        print(f"   Beklenen: suspicious=true, decision=BLOCK")
    else:
        print(f"   → GET isteği atabilirsin (normal bekleniyor)")

    prev_lat, prev_lon, prev_ts = sc["lat"], sc["lon"], now

    if i < len(scenarios) - 1:
        print(f"\n   ⏳ {SLEEP_BETWEEN} saniye bekleniyor...")
        for remaining in range(SLEEP_BETWEEN, 0, -1):
            print(f"\r   ⏳ {remaining:2d} saniye...", end="", flush=True)
            time.sleep(1)
        print()

print_separator()
print("\n✅ Simülasyon tamamlandı!")
print(f"   MSISDN: {msisdn}")
print(f"   Son konum: {scenarios[-1]['label']}")
print(f"\n📊 Özet:")
for sc in scenarios:
    tip = "🚨" if sc["type"] == "ANOMALY" else "✅"
    print(f"   {tip} {sc['label'][:40]:<40} lat={sc['lat']:.4f} lon={sc['lon']:.4f}")

client.close()
