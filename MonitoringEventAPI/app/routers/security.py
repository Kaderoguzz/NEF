from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from app.utils.db_data_handler import DbDataHandler, get_db_data_handler
from app.services.security_brain.analyzer import SecurityBrainAnalyzer
from app.auth import get_authentication_dependency

router = APIRouter()
verify_token = get_authentication_dependency()

location_history: dict[str, list] = {}
analyzer = SecurityBrainAnalyzer()

@router.get(
    "/security/{msisdn}/location-analysis",
    tags=["Security Analysis"],
    summary="Analyze location history and detect suspicious movement",
    dependencies=[Depends(verify_token)]
)
async def analyze_location(
    msisdn: str,
    db_data_handler: DbDataHandler = Depends(get_db_data_handler)
):
    # 1. location_info'dan güncel konumu çek
    doc = await db_data_handler.find_location_by_imsi(msisdn)
    if doc is None:
        return {"msisdn": msisdn, "error": "No location data found for this MSISDN"}

    cell_id = doc.get("cellId")
    ts = doc.get("UELocationTimestamp", datetime.now(timezone.utc))
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

    # 2. cell_to_polygons'dan bu hücrenin koordinatlarını çek
    polygon_doc = await db_data_handler.fetch_mapping_from_cell_id_to_polygon(cell_id)
    coords = []
    location_name = f"Unknown ({cell_id})"

    if polygon_doc:
        try:
            coords = (
                polygon_doc["geographicArea"]["polygon"]
                ["point_list"]["geographical_coords"]
            )
            # Centroid'den yaklaşık şehir adı bul
            lat_avg = sum(c["lat"] for c in coords) / len(coords)
            lon_avg = sum(c["lon"] for c in coords) / len(coords)
            location_name = f"lat:{round(lat_avg,4)}, lon:{round(lon_avg,4)}"
        except (KeyError, TypeError, ZeroDivisionError):
            coords = []

    # 3. Geçmişe ekle (sadece hücre değişince)
    if msisdn not in location_history:
        location_history[msisdn] = []

    last = location_history[msisdn][-1] if location_history[msisdn] else None
    if last is None or last["cellId"] != cell_id:
        location_history[msisdn].append({
            "cellId": cell_id,
            "location_name": location_name,
            "trackingAreaId": doc.get("trackingAreaId"),
            "plmnId": doc.get("plmnId"),
            "coordinates": coords,
            "timestamp": ts_str
        })

    # 4. Event'i DB'den gelen gerçek polygon ile oluştur
    event = {
        "msisdn": msisdn,
        "timestamp": ts_str,
        "locationInfo": {
            "cellId": cell_id,
            "geographicArea": {
                "polygon": {
                    "point_list": {
                        "geographical_coords": coords  # DB'den gelen gerçek koordinatlar
                    }
                }
            }
        }
    }

    # 5. Güvenlik analizi yap
    result = analyzer.analyze(event)
    security = result["security"]
    mobility = result["analysis"]["mobility"]

    # 6. Mesaj üret
    suspicious = security["risk_score"] >= 45
    message = "✅ Normal movement detected."

    if "IMPOSSIBLE_TRAVEL_DETECTED" in security["anomalies"]:
        message = (
            f"🚨 IMPOSSIBLE TRAVEL DETECTED: "
            f"{mobility.get('distance_km', 0)} km covered at "
            f"{mobility.get('speed_kmh', 0)} km/h. "
            f"Physical travel at this speed is impossible."
        )
    elif "FAST_GEOGRAPHIC_JUMP" in security["anomalies"]:
        message = (
            f"⚠️ SUSPICIOUS LOCATION JUMP: "
            f"{mobility.get('distance_km', 0)} km in under 10 minutes."
        )
    elif "RAPID_CELL_CHANGE" in security["anomalies"]:
        message = "⚠️ Rapid cell change detected. Monitoring..."

    return {
        "msisdn": msisdn,
        "current_location": {
            "cellId": cell_id,
            "location_name": location_name,
            "trackingAreaId": doc.get("trackingAreaId"),
            "plmnId": doc.get("plmnId"),
            "coordinates": coords,
            "timestamp": ts_str
        },
        "location_history": location_history[msisdn][-10:],
        "suspicious": suspicious,
        "risk_score": security["risk_score"],
        "decision": security["decision"],
        "anomalies": security["anomalies"],
        "message": message,
        "details": {
            "distance_km": mobility.get("distance_km", 0),
            "speed_kmh": mobility.get("speed_kmh", 0),
            "geo_risk": result["analysis"]["geo"]["risk"],
            "mobility_risk": result["analysis"]["mobility"]["risk"],
            "subscription_risk": result["analysis"]["subscription"]["risk"]
        }
    }
