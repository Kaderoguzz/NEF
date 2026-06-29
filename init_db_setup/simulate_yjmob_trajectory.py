from pymongo import MongoClient
import time
from datetime import datetime, timezone

client = MongoClient("mongodb://0.0.0.0:27018/")
db = client["amf_logs"]

# Simüle edilecek kullanıcı — DB'deki ilk kullanıcıyı al
traj_doc = db.trajectories.find_one()
if not traj_doc:
    print("Önce yjmob_to_mongo.py çalıştır!")
    exit()

msisdn    = traj_doc["_id"]
trajectory = traj_doc["trajectory"]

print(f"Simülasyon başlıyor: MSISDN={msisdn}")
print(f"Toplam {len(trajectory)} konum noktası")
print(f"API'den izle: GET /{msisdn}/subscriptions/{{subscriptionId}}/location-analysis")
print("=" * 60)

for i, point in enumerate(trajectory):
    now = datetime.now(timezone.utc)

    db.location_info.update_one(
        {"_id": msisdn},
        {"$set": {
            "cellId": point["cellId"],
            "trackingAreaId": f"TA-{point['cellId']}",
            "enodeBId": f"ENB-{point['cellId']}",
            "routingAreaId": f"RA-{point['cellId']}",
            "plmnId": {"mcc": "440", "mnc": "10"},
            "UELocationTimestamp": now
        }},
        upsert=True
    )

    print(f"[{i+1:3d}/{len(trajectory)}] "
          f"cellId={point['cellId']} "
          f"lat={point['lat']:.4f} lon={point['lon']:.4f} "
          f"(gün={point['d']}, dilim={point['t']})")

    time.sleep(5)  # 5 saniyede bir güncelle

print("Simülasyon tamamlandı!")
client.close()
