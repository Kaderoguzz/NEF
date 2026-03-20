from __future__ import annotations

from typing import Any
import requests
from pydantic import BaseModel, Field
import time

from core_crowler.utils.logger import setup_logger
from core_crowler.utils.log_fetcher_helper import format_timestamp
from core_crowler.middleware.o5gs import O5GSMiddleware

logger = setup_logger(logger_name="ue_info_parser")

class Snssai(BaseModel):
    sst: int
    sd: str | None = None


class GnbInfo(BaseModel):
    ostream_id: int
    amf_ue_ngap_id: int
    ran_ue_ngap_id: int
    gnb_id: int
    cell_id: int


class NrTai(BaseModel):
    plmn: str
    tac_hex: str
    tac: int


class NrCgi(BaseModel):
    plmn: str
    nci: int
    gnb_id: int
    cell_id: int


class Location(BaseModel):
    timestamp: int
    nr_tai: NrTai
    nr_cgi: NrCgi
    last_visited_plmn_id: str

class SecurityInfo(BaseModel):
    valid: int
    enc: str
    int: str


class Ambr(BaseModel):
    downlink: int
    uplink: int


class PduSession(BaseModel):
    psi: int
    dnn: str
    snssai: Snssai
    lbo_roaming_allowed: bool
    resource_status: int
    n1_released: bool
    n2_released: bool


class AmPolicyFeaturesInfo(BaseModel):
    hex: str
    bits: list[int]
    labels: list[str]

class PlmnId(BaseModel):
    mcc: str 
    mnc: str 
class UeInfoItem(BaseModel):
    supi: str
    suci: str | None = None
    pei: str | None = None
    cm_state: str
    guti: str | None = None
    m_tmsi: int | None = None
    gnb: GnbInfo
    location: Location
    msisdn: list[str] = Field(default_factory=list)
    security: SecurityInfo
    ambr: Ambr
    pdu_sessions: list[PduSession] = Field(default_factory=list)
    pdu_sessions_count: int
    requested_slices: list[Snssai] = Field(default_factory=list)
    allowed_slices: list[Snssai] = Field(default_factory=list)
    requested_slices_count: int
    allowed_slices_count: int
    am_policy_features: int | None = None
    am_policy_features_info: AmPolicyFeaturesInfo | None = None


class Pager(BaseModel):
    page: int
    page_size: int
    count: int


class UeInfoResponse(BaseModel):
    items: list[UeInfoItem]
    pager: Pager

class UEInfoParser:
    def __init__(self, connection_url: str, poll_interval: int = 2, mongo_uri="mongodb://localhost:27017", db_name="amf_logs"):
        self.connection_url = connection_url
        self.poll_interval = poll_interval
        self.mdlw = O5GSMiddleware(mongo_uri, db_name)

    def _parse_plmn(self,plmn: str) -> PlmnId:
        return PlmnId(mcc=plmn[:3], mnc=plmn[3:])

    def fetch_ue_info(self, base_url: str) -> UeInfoResponse:
        url = f"{base_url.rstrip('/')}/ue-info?page=-1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return UeInfoResponse.model_validate(response.json())


    def build_ue_index(self, ue_response: UeInfoResponse) -> dict[str, UeInfoItem]:
        '''
        Dict of UE info items indexed by IMSI (without "imsi-" prefix)
        
        {
            "999700000000001": UeInfoItem(...)
        }
        '''
        return {ue.supi.removeprefix("imsi-"): ue for ue in ue_response.items}


# def get_ue_by_imsi(
#     ue_response: UeInfoResponse,
#     imsi: str,
# ) -> UeInfoItem | None:
#     supi = imsi if imsi.startswith("imsi-") else f"imsi-{imsi}"
#     return next((ue for ue in ue_response.items if ue.supi == supi), None)

# '''
#     imsi: "ue.supi"
#     cellId: "ue.nr_cgi.cell_id"
#     trackingAreaId: "ue.nr_tai.tac"
#     plmnId: "ue.nr_cgi.plmn"
#     routingAreaId: null
#     enodeBId: null
#     twanId: null
#     UELocationTimestamp: "ue.location.timestamp"
# '''
    def build_location_info_from_ue(self, ue: UeInfoItem) -> dict[str, Any]:
        return {
            "_id": ue.supi.removeprefix("imsi-"),
            "cellId": str(ue.location.nr_cgi.cell_id),
            "trackingAreaId": str(ue.location.nr_tai.tac),
            "plmnId": self._parse_plmn(ue.location.nr_cgi.plmn).model_dump(),
            "routingAreaId": None,
            "enodeBId": None,
            "twanId": None,
            "UELocationTimestamp": format_timestamp(ue.location.timestamp)
        }

    def run(self):
        while True:
            try:
                ue_response = self.fetch_ue_info(self.connection_url)
                # ue_index = self.build_ue_index(ue_response)
                for ue in ue_response.items:
                    location_info = self.build_location_info_from_ue(ue)
                    self.mdlw.write_location_info_from_amf_endpoint(location_info)
            except Exception as e:
                logger.error(f"Error fetching or processing UE info: {e}")
            time.sleep(self.poll_interval)

# if __name__ == "__main__":
#     base_url = "http://127.0.0.5:9090"

#     ue_response = fetch_ue_info(base_url)

#     # Option 1: direct lookup by scan
#     ue = get_ue_by_imsi(ue_response, "999700000000001")
#     if ue:
#         print("Found UE by scan:")
#         print(f"SUPI: {ue.supi}")
#         print(f"Cell ID: {ue.gnb.cell_id}")
#         print(f"CM state: {ue.cm_state}")
#         print(f"PDU sessions: {ue.pdu_sessions_count}")

#     # Option 2: indexed lookup
#     ue_index = build_ue_index(ue_response)
#     ue2 = ue_index.get("imsi-999700000000002")
#     if ue2:
#         print("\nFound UE by index:")
#         print(f"SUPI: {ue2.supi}")
#         print(f"gNB ID: {ue2.gnb.gnb_id}")
#         print(f"NCI: {ue2.location.nr_cgi.nci}")
