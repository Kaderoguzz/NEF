import gzip
import csv
from pymongo import MongoClient
from datetime import datetime, timedelta
import random

# ─── Bağlantı ───────────────────────────────────────────────
client = MongoClient("mongodb://0.0.0.0:27018/")
db = client["amf_logs"]

# ─── Sabitler ───────────────────────────────────────────────
GRID_SIZE_DEG  = 500 / 111320        # 500m → derece (~0.00449°)
ORIGIN_LAT     = 35.50               # Grid (0,0) başlangıç enlemi
ORIGIN_LON     = 139.50              # Grid (0,0) başlangıç boylamı
BASE_DATE      = datetime(2024, 1, 1) # d=0 → bu tarih
INTERVAL_MIN   = 30                  # Her t dilimi 30 dakika

# Kaç kullanıcı yüklenecek (test için küçük tut)
MAX_USERS      = 50
# Her kullanıcıdan kaç kayıt (son konumu location_info'ya yaz)
MAX_RECORDS_PER_USER = 48  # 1 günlük veri


def grid_to_latlon(x, y):
    """Grid hücresini merkez lat/lon'a çevir."""
    lat = ORIGIN_LAT + (y + 0.5) * GRID_SIZE_DEG
    lon = ORIGIN_LON + (x + 0.5) * GRID_SIZE_DEG
    return round(lat, 6), round(lon, 6)


def grid_to_polygon(x, y):
    """Grid hücresinin 4 köşesini döndür."""
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


def t_to_timestamp(d, t):
    """Gün ve zaman dilimini ISO timestamp'e çevir."""
    return BASE_DATE + timedelta(days=int(d), minutes=int(t) * INTERVAL_MIN)


def uid_to_msisdn(uid):
    """uid'yi sahte MSISDN'e çevir (81 = Japonya ülke kodu)."""
    return f"81{int(uid):010d}"


def cell_id(x, y):
    """x,y grid koordinatından benzersiz cellId üret."""
    return f"{int(x):04d}{int(y):04d}"


# ─── Collections temizle ────────────────────────────────────
print("Collections temizleniyor...")
db.location_info.delete_many({})
db.cell_to_polygons.delete_many({})
db.imsi_to_phone_number.delete_many({})

# ─── Dataset oku ────────────────────────────────────────────
print("Dataset okunuyor...")

# uid → son konum (location_info için)
user_last_location = {}
# uid → tüm kayıtlar (trajectory analizi için)
user_trajectories = {}
# Unique cell_id → polygon (cell_to_polygons için)
cell_polygons = {}

with gzip.open("yjmob100k-dataset1.csv.gz", "rt") as f:
    reader = csv.DictReader(f)
    user_count = 0
    prev_uid = None

    for row in reader:
        uid = row["uid"]

        # Yeni kullanıcı kontrolü
        if uid != prev_uid:
            if user_count >= MAX_USERS:
                break
            user_count += 1
            prev_uid = uid
            user_trajectories[uid] = []
            print(f"  Kullanıcı {user_count}/{MAX_USERS}: uid={uid}")

        x, y = int(row["x"]), int(row["y"])
        d, t = row["d"], row["t"]
        ts   = t_to_timestamp(d, t)
        cid  = cell_id(x, y)
        lat, lon = grid_to_latlon(x, y)

        # Son konum güncelle
        user_last_location[uid] = {
            "_id": uid_to_msisdn(uid),
            "cellId": cid,
            "trackingAreaId": f"TA-{cid}",
            "enodeBId": f"ENB-{cid}",
            "routingAreaId": f"RA-{cid}",
            "plmnId": {"mcc": "440", "mnc": "10"},  # NTT Docomo Japonya
            "twanId": None,
            "UELocationTimestamp": ts,
            "lat": lat,
            "lon": lon
        }

        # Trajectory kaydet (max kayıt sınırı)
        if len(user_trajectories[uid]) < MAX_RECORDS_PER_USER:
            user_trajectories[uid].append({
                "uid": uid,
                "msisdn": uid_to_msisdn(uid),
                "cellId": cid,
                "lat": lat,
                "lon": lon,
                "timestamp": ts,
                "d": int(d),
                "t": int(t)
            })

        # Polygon kaydet
        if cid not in cell_polygons:
            cell_polygons[cid] = {
                "_id": cid,
                "geographicArea": {
                    "polygon": {
                        "point_list": {
                            "geographical_coords": grid_to_polygon(x, y)
                        }
                    }
                }
            }

# ─── MongoDB'ye yaz ─────────────────────────────────────────
print(f"\nMongoDB'ye yazılıyor...")

# location_info
loc_docs = list(user_last_location.values())
if loc_docs:
    db.location_info.insert_many(loc_docs)
    print(f"  location_info: {len(loc_docs)} kayıt")

# cell_to_polygons
poly_docs = list(cell_polygons.values())
if poly_docs:
    db.cell_to_polygons.insert_many(poly_docs)
    print(f"  cell_to_polygons: {len(poly_docs)} hücre")

# imsi_to_phone_number
imsi_docs = [
    {"_id": uid_to_msisdn(uid), "af_id": "1", "msisdn": uid_to_msisdn(uid)}
    for uid in user_last_location.keys()
]
if imsi_docs:
    db.imsi_to_phone_number.insert_many(imsi_docs)
    print(f"  imsi_to_phone_number: {len(imsi_docs)} eşleme")

# Trajectory'leri ayrı bir koleksiyona kaydet (analiz için)
traj_docs = []
for uid, records in user_trajectories.items():
    traj_docs.append({
        "_id": uid_to_msisdn(uid),
        "uid": uid,
        "trajectory": records
    })
if traj_docs:
    db.trajectories.drop()
    db.trajectories.insert_many(traj_docs)
    print(f"  trajectories: {len(traj_docs)} kullanıcı")

print("\nTamamlandı!")
print(f"  Toplam kullanıcı : {len(user_last_location)}")
print(f"  Toplam hücre     : {len(cell_polygons)}")
print(f"\nÖrnek MSISDN'ler:")
for msisdn in list(user_last_location.keys())[:5]:
    doc = user_last_location[msisdn]
    print(f"  {doc['_id']} → cellId:{doc['cellId']} lat:{doc['lat']} lon:{doc['lon']}")

client.close()
