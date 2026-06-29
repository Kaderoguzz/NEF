from pymongo import MongoClient
import time
from datetime import datetime, timezone

client = MongoClient("mongodb://0.0.0.0:27018/")
db = client["amf_logs"]
collection = db["location_info"]

msisdn = "001010143245445"

# Movement pattern (repeatable loop)
locations = [
    {
        "name": "İstanbul Merkez",
        "cellId": "000000010",
        "trackingAreaId": "TA-IST-001",
        "enodeBId": "ENB-IST-001",
        "routingAreaId": "RA-IST-001",
        "plmnId": {"mcc": "286", "mnc": "01"},
    },
    {
        "name": "İstanbul Kuzey",
        "cellId": "000000011",
        "trackingAreaId": "TA-IST-002",
        "enodeBId": "ENB-IST-002",
        "routingAreaId": "RA-IST-002",
        "plmnId": {"mcc": "286", "mnc": "01"},
    },
    {
        "name": "LONDRA (IMPOSIBLE TRAVEL)",
        "cellId": "000000020",
        "trackingAreaId": "TA-LON-001",
        "enodeBId": "ENB-LON-001",
        "routingAreaId": "RA-LON-001",
        "plmnId": {"mcc": "234", "mnc": "30"},
    }
]

# Timing tuned for frontend visibility
SLEEP_SECONDS = 30

print("🚀 Continuous Suspicious Travel Simulation STARTED")
print("=" * 60)

cycle = 0

while True:
    cycle += 1
    print(f"\n🔁 Cycle {cycle}")
    print("=" * 60)

    for loc in locations:
        now = datetime.now(timezone.utc)

        print(f"\n📍 {loc['name']}")
        print(f"   cellId: {loc['cellId']}")
        print(f"   time: {now.isoformat()}")

        collection.update_one(
            {"_id": msisdn},
            {"$set": {
                "cellId": loc["cellId"],
                "trackingAreaId": loc["trackingAreaId"],
                "enodeBId": loc["enodeBId"],
                "routingAreaId": loc["routingAreaId"],
                "plmnId": loc["plmnId"],
                "UELocationTimestamp": now
            }},
            upsert=True
        )

        print("   ✅ DB updated")
        print(f"   ⏳ waiting {SLEEP_SECONDS}s...")

        time.sleep(SLEEP_SECONDS)

