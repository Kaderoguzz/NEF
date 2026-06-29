"""
MongoDB → InfluxDB Bridge
MongoDB'deki location_info değişikliklerini izler,
InfluxDB'ye yazar. Grafana bu veriyi Geomap'te gösterir.

Çalıştır: python bridge.py
"""

import math
import time
import logging
from datetime import datetime, timezone

from pymongo import MongoClient
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bridge")

# ─── Konfigürasyon ───────────────────────────────────────────────────────────
MONGO_URI    = "mongodb://0.0.0.0:27018/"
MONGO_DB     = "amf_logs"

INFLUX_URL   = "http://localhost:8086"
INFLUX_TOKEN = "nef-super-secret-token"
INFLUX_ORG   = "nef"
INFLUX_BUCKET= "location_events"

POLL_INTERVAL = 3   # saniye

# ─── Sabitler ────────────────────────────────────────────────────────────────
GRID_SIZE_DEG = 500 / 111320
ORIGIN_LAT    = 35.50
ORIGIN_LON    = 139.50
IMPOSSIBLE_KMH= 900

def grid_to_latlon(x, y):
    lat = ORIGIN_LAT + (int(y) + 0.5) * GRID_SIZE_DEG
    lon = ORIGIN_LON + (int(x) + 0.5) * GRID_SIZE_DEG
    return round(lat, 6), round(lon, 6)

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def extract_latlon(doc):
    """Dokümandan lat/lon al — doğrudan varsa kullan, yoksa cellId'den türet."""
    if "lat" in doc and "lon" in doc:
        return doc["lat"], doc["lon"]
    cid = doc.get("cellId", "")
    if len(cid) == 8:
        return grid_to_latlon(int(cid[:4]), int(cid[4:]))
    return None, None

# ─── Bağlantılar ─────────────────────────────────────────────────────────────
log.info("MongoDB bağlanıyor: %s", MONGO_URI)
mongo  = MongoClient(MONGO_URI)
mdb    = mongo[MONGO_DB]

log.info("InfluxDB bağlanıyor: %s", INFLUX_URL)
influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write  = influx.write_api(write_options=SYNCHRONOUS)

# ─── State: önceki konumlar (hız hesabı için) ────────────────────────────────
prev_state: dict[str, dict] = {}   # msisdn → {lat, lon, ts}

# ─── Ana döngü ───────────────────────────────────────────────────────────────
log.info("Bridge başladı — her %ds MongoDB sorgulanıyor", POLL_INTERVAL)
log.info("─" * 55)

while True:
    try:
        docs = list(mdb.location_info.find({}))
    except Exception as e:
        log.error("MongoDB okuma hatası: %s", e)
        time.sleep(POLL_INTERVAL)
        continue

    points = []

    for doc in docs:
        msisdn = str(doc["_id"])
        lat, lon = extract_latlon(doc)
        if lat is None:
            continue

        ts       = doc.get("UELocationTimestamp", datetime.now(timezone.utc))
        is_anomaly = bool(doc.get("anomaly", False))
        cell_id  = doc.get("cellId", "unknown")

        # Hız hesapla
        speed_kmh = 0.0
        prev = prev_state.get(msisdn)
        if prev:
            dist_km = haversine_km(prev["lat"], prev["lon"], lat, lon)
            dt_s    = (ts - prev["ts"]).total_seconds() if hasattr(ts, 'total_seconds') else POLL_INTERVAL
            if dt_s is None or dt_s <= 0:
                dt_s = POLL_INTERVAL
            speed_kmh = (dist_km / dt_s) * 3600 if dt_s > 0 else 0.0

            # Hız anomalisi override
            if speed_kmh > IMPOSSIBLE_KMH:
                is_anomaly = True

        prev_state[msisdn] = {"lat": lat, "lon": lon, "ts": ts}

        # InfluxDB point oluştur
        p = (
            Point("location")
            .tag("msisdn",  msisdn)
            .tag("cellId",  cell_id)
            .field("lat",       float(lat))
            .field("lon",       float(lon))
            .field("anomaly",   1.0 if is_anomaly else 0.0)
            .field("speed_kmh", round(speed_kmh, 1))
            .time(ts, WritePrecision.S)
        )
        points.append(p)

        status = "🚨 ANOMALİ" if is_anomaly else "✅ normal "
        log.info("%s  msisdn=%-20s  lat=%.5f  lon=%.5f  hız=%6.0f km/h",
                 status, msisdn, lat, lon, speed_kmh)

    if points:
        try:
            write.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
        except Exception as e:
            log.error("InfluxDB yazma hatası: %s", e)

    time.sleep(POLL_INTERVAL)
