import math
from datetime import datetime, timezone

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def parse_timestamp(ts):
    if ts is None:
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts
    try:
        if isinstance(ts, str) and ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except:
        return datetime.now(timezone.utc)

def time_diff_seconds(t1, t2):
    t1 = parse_timestamp(t1)
    t2 = parse_timestamp(t2)
    return abs((t2 - t1).total_seconds())

def calculate_speed_kmh(distance_km, time_seconds):
    if time_seconds <= 0:
        return 0
    return (distance_km / time_seconds) * 3600

def safe_get(data: dict, key: str, default=None):
    if not isinstance(data, dict):
        return default
    return data.get(key, default)

def normalize_location(lat, lon):
    try:
        return float(lat), float(lon)
    except:
        return None, None

def polygon_centroid(coords: list) -> tuple:
    if not coords:
        return None, None
    lat_sum = sum(c["lat"] for c in coords)
    lon_sum = sum(c["lon"] for c in coords)
    n = len(coords)
    return lat_sum / n, lon_sum / n

def extract_centroid_from_event(event: dict) -> tuple:
    try:
        coords = (
            event["locationInfo"]["geographicArea"]
            ["polygon"]["point_list"]["geographical_coords"]
        )
        return polygon_centroid(coords)
    except (KeyError, TypeError):
        return None, None
