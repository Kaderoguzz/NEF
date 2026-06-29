from shapely.geometry import Point, Polygon
from .utils import safe_get, extract_centroid_from_event

class GeoAnalyzer:
    def __init__(self):
        self.last_locations = {}

    def analyze(self, event: dict, geo_db: dict):
        msisdn = safe_get(event, "msisdn")
        location_info = safe_get(event, "locationInfo", {})
        cell_id = safe_get(location_info, "cellId")
        lat, lon = extract_centroid_from_event(event)

        anomalies = []
        risk = 0

        allowed_polygon_coords = geo_db.get(cell_id)
        if allowed_polygon_coords and lat is not None and lon is not None:
            point = Point(lon, lat)
            polygon = Polygon([(c["lon"], c["lat"]) for c in allowed_polygon_coords])
            if not polygon.contains(point):
                risk += 60
                anomalies.append("OUTSIDE_ALLOWED_CELL_AREA")

        if lat is None or lon is None:
            risk += 40
            anomalies.append("MISSING_GEOLOCATION")

        last = self.last_locations.get(msisdn)
        if last and cell_id and last["cell_id"] != cell_id:
            risk += 20
            anomalies.append("RAPID_CELL_CHANGE")

        self.last_locations[msisdn] = {"cell_id": cell_id, "lat": lat, "lon": lon}

        return {
            "msisdn": msisdn,
            "risk": min(risk, 100),
            "anomalies": anomalies,
            "cell_id": cell_id,
            "centroid": {"lat": lat, "lon": lon}
        }
