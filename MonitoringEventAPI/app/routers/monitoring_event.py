from typing import Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from fastapi import APIRouter, Response, status, Request, Depends, HTTPException

from app.utils.db_data_handler import DbDataHandler, get_db_data_handler
from app.schemas.monitoring_event import (
    MonitoringEventSubscriptionRequest, MonitoringEventSubscriptionResponse,
    MonitoringEventReport, MonitoringNotification, MonitoringNotificationResponse, ErrorResponse
)
from app.services import monitoring_event_service as sub_service
from app.services.security_brain.analyzer import SecurityBrainAnalyzer
from app.auth import get_authentication_dependency

router = APIRouter()
invoices_callback_router = APIRouter()
verify_token = get_authentication_dependency()

location_history: dict[str, list] = {}
security_analyzer = SecurityBrainAnalyzer()

class PlmnId(BaseModel):
    mcc: str
    mnc: str

class LocationEntry(BaseModel):
    cellId: str
    location_name: str
    trackingAreaId: Optional[str] = None
    plmnId: Optional[PlmnId] = None
    coordinates: List[dict] = []
    timestamp: str

class SecurityDetails(BaseModel):
    distance_km: float
    speed_kmh: float
    geo_risk: float
    mobility_risk: float
    subscription_risk: float

class LocationAnalysisResponse(BaseModel):
    msisdn: str
    subscription_id: str
    subscription_active: bool
    current_location: LocationEntry
    location_history: List[LocationEntry] = []
    suspicious: bool
    risk_score: float
    decision: str
    anomalies: List[str] = []
    message: str
    details: SecurityDetails

@invoices_callback_router.post("{$request.body.notificationDestination}", description="No Content (successful notification)", response_model=MonitoringNotificationResponse)
async def send_notification(callback_url: str, monitoring_notification: MonitoringNotification) -> None:
    pass

@router.get("/{scsAsId}/subscriptions",
            description="Read all of the active subscriptions for the AF",
            tags=["MonitoringEvent API AF level GET Operation"],
            responses={
                status.HTTP_200_OK: {"model": list[MonitoringEventSubscriptionResponse], "description": "200 OK"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "401 Unauthorized"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "404 Not Found"}
            },
            response_model=list[MonitoringEventSubscriptionResponse],
            response_model_exclude_defaults=True,
            dependencies=[Depends(verify_token)])
async def get_subscriptions(scsAsId: str, request: Request, db_data_handler: DbDataHandler = Depends(get_db_data_handler)) -> list[MonitoringEventSubscriptionResponse]:
    return await sub_service.get_subscriptions_per_af(scsAsId, str(request.url), db_data_handler)

@router.post("/{scsAsId}/subscriptions",
        description="Creates a new subscription resource for monitoring event notification",
        tags=["MonitoringEvent API Subscription level POST Operation"],
        responses={
            status.HTTP_200_OK: {"model": MonitoringEventReport, "description": "200 OK"},
            status.HTTP_201_CREATED: {"model": MonitoringEventSubscriptionResponse, "description": "201 Created"},
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "400 Bad Request"},
            status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "401 Unauthorized"},
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "404 Not Found"}
        },
        response_model_exclude_unset=True,
        callbacks=invoices_callback_router.routes,
        dependencies=[Depends(verify_token)])
async def create_subscription(request: Request, scsAsId: str, sub_req: MonitoringEventSubscriptionRequest, response: Response, db_data_handler: DbDataHandler = Depends(get_db_data_handler)) -> MonitoringEventReport | MonitoringEventSubscriptionResponse:
    post_result = await sub_service.register_subscription_pef_af(scsAsId, sub_req, str(request.url), db_data_handler)
    if isinstance(post_result, MonitoringEventReport):
        response.status_code = status.HTTP_200_OK
        return post_result
    else:
        response.headers["Location"] = str(post_result.self_link)
        response.status_code = status.HTTP_201_CREATED
        return post_result

@router.get("/{scsAsId}/subscriptions/{subscriptionId}",
            description="Read an active subscription for the AF and the subscription Id",
            tags=["MonitoringEvent API Subscription level GET Operation"],
            responses={
                status.HTTP_200_OK: {"model": MonitoringEventSubscriptionResponse, "description": "200 OK"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "401 Unauthorized"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "404 Not Found"}
            },
            response_model=MonitoringEventSubscriptionResponse,
            response_model_exclude_unset=True,
            dependencies=[Depends(verify_token)])
async def get_subscription_by_id(scsAsId: str, subscriptionId: str, request: Request, db_data_handler: DbDataHandler = Depends(get_db_data_handler)) -> MonitoringEventSubscriptionResponse:
    return await sub_service.get_subscription_per_sub_id(scsAsId, subscriptionId, str(request.url), db_data_handler)

@router.put("/{scsAsId}/subscriptions/{subscriptionId}",
            description="Updates/replaces an existing subscription resource",
            tags=["MonitoringEvent API subscription level PUT Operation"],
            response_model=MonitoringEventSubscriptionResponse,
            response_model_exclude_unset=True)
async def modify_subscription_by_id(scsAsId: str, subscriptionId: str) -> Any:
    pass

@router.delete("/{scsAsId}/subscriptions/{subscriptionId}",
               description="Deletes an already existing monitoring event subscription",
               tags=["MonitoringEvent API Subscription level DELETE Operation"],
               responses={
                   status.HTTP_200_OK: {"model": list[MonitoringEventReport], "description": "200 OK"},
                   status.HTTP_204_NO_CONTENT: {"description": "204 No Content"},
                   status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "401 Unauthorized"},
                   status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "404 Not Found"}
               },
               response_model_exclude_unset=True,
               dependencies=[Depends(verify_token)])
async def delete_subscription_by_id(scsAsId: str, subscriptionId: str, response: Response, db_data_handler: DbDataHandler = Depends(get_db_data_handler)) -> MonitoringEventReport | None:
    result = await sub_service.delete_subscription_by_sub_id(scsAsId, subscriptionId, db_data_handler)
    if result:
        response.status_code = status.HTTP_200_OK
        return result
    else:
        response.status_code = status.HTTP_204_NO_CONTENT

@router.get("/{scsAsId}/subscriptions/{subscriptionId}/location-analysis",
            description=(
                "Analyzes the last two known locations of a UE and detects suspicious movement. "
                "Compares the centroid of each cell polygon to calculate distance and speed. "
                "Flags IMPOSSIBLE_TRAVEL if speed > 900 km/h, FAST_GEOGRAPHIC_JUMP if > 200 km in 10 min."
            ),
            tags=["Security Analysis"],
            response_model=LocationAnalysisResponse,
            responses={
                status.HTTP_200_OK: {"model": LocationAnalysisResponse, "description": "200 OK"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "401 Unauthorized"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "404 Not Found"}
            },
            dependencies=[Depends(verify_token)])
async def analyze_location(
    scsAsId: str,
    subscriptionId: str,
    db_data_handler: DbDataHandler = Depends(get_db_data_handler)
):
    msisdn = scsAsId

    # 1. Subscription var mı kontrol et
    subscription = await db_data_handler.fetch_unique_subscription_for_af_id(msisdn, subscriptionId)
    subscription_active = subscription is not None
    if not subscription_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscriptionId} not found for {msisdn}"
        )

    # 2. Güncel konumu DB'den çek
    doc = await db_data_handler.find_location_by_imsi(msisdn)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No location data found for this MSISDN"
        )

    cell_id = doc.get("cellId")
    ts = doc.get("UELocationTimestamp", datetime.now(timezone.utc))
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

    # 3. Hücre poligonunu DB'den çek
    polygon_doc = await db_data_handler.fetch_mapping_from_cell_id_to_polygon(cell_id)
    coords = []
    location_name = f"Unknown ({cell_id})"

    if polygon_doc:
        try:
            coords = polygon_doc["geographicArea"]["polygon"]["point_list"]["geographical_coords"]
            lat_avg = sum(c["lat"] for c in coords) / len(coords)
            lon_avg = sum(c["lon"] for c in coords) / len(coords)
            location_name = f"lat:{round(lat_avg,4)}, lon:{round(lon_avg,4)}"
        except (KeyError, TypeError, ZeroDivisionError):
            coords = []

    # 4. Geçmişe ekle — sadece hücre değiştiğinde
    history_key = f"{msisdn}_{subscriptionId}"
    if history_key not in location_history:
        location_history[history_key] = []

    last = location_history[history_key][-1] if location_history[history_key] else None
    if last is None or last["cellId"] != cell_id:
        location_history[history_key].append({
            "cellId": cell_id,
            "location_name": location_name,
            "trackingAreaId": doc.get("trackingAreaId"),
            "plmnId": doc.get("plmnId"),
            "coordinates": coords,
            "timestamp": ts_str
        })

    # 5. Event oluştur
    event = {
        "msisdn": msisdn,
        "timestamp": ts_str,
        "locationInfo": {
            "cellId": cell_id,
            "geographicArea": {"polygon": {"point_list": {"geographical_coords": coords}}}
        }
    }

    # 6. Security Brain analizi
    result = security_analyzer.analyze(event)
    security = result["security"]
    mobility = result["analysis"]["mobility"]

    suspicious = security["risk_score"] >= 45
    message = "✅ Normal movement detected."

    if "IMPOSSIBLE_TRAVEL_DETECTED" in security["anomalies"]:
        message = (
            f"🚨 IMPOSSIBLE TRAVEL DETECTED: "
            f"{mobility.get('distance_km', 0)} km at "
            f"{mobility.get('speed_kmh', 0)} km/h. "
            f"Physical travel at this speed is impossible."
        )
    elif "FAST_GEOGRAPHIC_JUMP" in security["anomalies"]:
        message = f"⚠️ SUSPICIOUS LOCATION JUMP: {mobility.get('distance_km', 0)} km in under 10 minutes."
    elif "RAPID_CELL_CHANGE" in security["anomalies"]:
        message = "⚠️ Rapid cell change detected. Monitoring..."

    return {
        "msisdn": msisdn,
        "subscription_id": subscriptionId,
        "subscription_active": subscription_active,
        "current_location": {
            "cellId": cell_id,
            "location_name": location_name,
            "trackingAreaId": doc.get("trackingAreaId"),
            "plmnId": doc.get("plmnId"),
            "coordinates": coords,
            "timestamp": ts_str
        },
        "location_history": location_history[history_key][-10:],
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
