from .utils import haversine_km, time_diff_seconds, calculate_speed_kmh, safe_get, parse_timestamp, extract_centroid_from_event

class MobilityAnalyzer:
    def __init__(self):
        self.last_state = {}
        self.MAX_SPEED_KMH = 900
        self.MAX_DISTANCE_KM = 200

    def analyze(self, event: dict):
        msisdn = safe_get(event, "msisdn")
        ts = parse_timestamp(safe_get(event, "timestamp"))
        lat, lon = extract_centroid_from_event(event)

        anomalies = []
        risk = 0

        if lat is None or lon is None:
            return {"msisdn": msisdn, "risk": 20, "anomalies": ["MISSING_COORDINATES"], "speed_kmh": 0, "distance_km": 0}

        if msisdn not in self.last_state:
            self.last_state[msisdn] = {"lat": lat, "lon": lon, "timestamp": ts}
            return {"msisdn": msisdn, "risk": 0, "anomalies": [], "speed_kmh": 0, "distance_km": 0}

        last = self.last_state[msisdn]
        distance = haversine_km(lat, lon, last["lat"], last["lon"])
        time_sec = time_diff_seconds(ts, last["timestamp"])
        speed = calculate_speed_kmh(distance, time_sec)

        if speed > self.MAX_SPEED_KMH:
            risk += 80
            anomalies.append("IMPOSSIBLE_TRAVEL_DETECTED")

        if distance > self.MAX_DISTANCE_KM and time_sec < 600:
            risk += 50
            anomalies.append("FAST_GEOGRAPHIC_JUMP")

        self.last_state[msisdn] = {"lat": lat, "lon": lon, "timestamp": ts}

        return {
            "msisdn": msisdn,
            "risk": min(risk, 100),
            "anomalies": anomalies,
            "speed_kmh": round(speed, 2),
            "distance_km": round(distance, 2)
        }
