import time
import re
import json
from datetime import datetime
from pymongo import MongoClient

from core_crowler.utils.log_fetcher_helper import clean_ansi_codes
from core_crowler.utils.logger import setup_logger
from core_crowler.middleware.o5gs import O5GSMiddleware

logger = setup_logger(logger_name="amf_log_parser")

KEYS = [
    "supi",
    "pei",
    "ueLocation",
    "ueTimeZone",
]

class LogParser:
    def __init__(self, mongo_uri="mongodb://localhost:27017",
                 db_name="amf_logs",
                 collection_name="ue_events"):

        self.in_json = False
        self.json_buffer = []
        try:
          self.mongo_client = MongoClient(mongo_uri)
          self.mongo_db = self.mongo_client[db_name]
          self.mongo_collection = self.mongo_db[collection_name]
          logger.info("[MONGODB] Connected to MongoDB")
        except Exception as e:
            logger.error(f"[MONGODB] Failed to connect: {e}")
            self.mongo_collection = None

        self.mdlw = O5GSMiddleware(mongo_uri, db_name)

    def process_line(self, raw: bytes) -> None:
        raw = clean_ansi_codes(raw)
        line = raw.decode("utf-8", errors="replace").strip()

        if "Content-Type: application/json" in line:
            self.in_json = True
            self.json_buffer = []
            return

        if self.in_json:
            if line.startswith("--="):
                self._flush_json()
                self.in_json = False
                self.json_buffer = []
                return

            self.json_buffer.append(line)

    def _flush_json(self) -> None:
        try:
            data = json.loads("\n".join(self.json_buffer))
            if any(k not in data for k in KEYS):
                return
            self._handle_registration(data)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON block skipped")

    def _handle_registration(self, data) -> None:
        supi = data.get("supi")
        if not supi:
            return

        imsi = supi.replace("imsi-", "")

        new_ts = datetime.fromisoformat(
            data["ueLocation"]["nrLocation"]["ueLocationTimestamp"].replace("Z", "+00:00")
        )

        existing = self.mongo_collection.find_one({"_id": imsi})
        if existing:
            old_ts = datetime.fromisoformat(
                existing["amf_info"]["ueLocation"]["nrLocation"]["ueLocationTimestamp"].replace("Z", "+00:00")
            )
            if new_ts <= old_ts:
                logger.info("The data in mongo is more recent for IMSI %s."
                            "\nExisted timestamp is %s while timestamp_to_insert is %s", imsi, old_ts, new_ts)
                return  # stale

        event = {"_id": imsi, "amf_info": data}
        self.mongo_collection.replace_one({"_id": imsi}, event, upsert=True)
        logger.info(f"[MONGODB] Stored registration for IMSI: {imsi}")
        logger.info(json.dumps(event, indent=4))
        self.mdlw.write_location_info(event)

# class LogParser:
#     def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="amf_logs", collection_name="ue_events"):
#         self.event_history = []

#         try:
#             self.mongo_client = MongoClient(mongo_uri)
#             self.mongo_db = self.mongo_client[db_name]
#             self.mongo_collection = self.mongo_db[collection_name]
#             logger.info("[MONGODB] Connected to MongoDB")
#         except Exception as e:
#             logger.error(f"[MONGODB] Failed to connect: {e}")
#             self.mongo_collection = None

#         # Regex to match a complete JSON object in a line
#         self.json_pattern = re.compile(r'(\{.*\})', re.DOTALL)

#         self.mdlw = O5GSMiddleware(mongo_uri=mongo_uri, db_name=db_name)

#     def process_line(self, line):
#         line = line.strip()

#         # Attempt to extract JSON from the line
#         match = self.json_pattern.search(line)
#         if match:
#             json_str = match.group(1)
#             try:
#                 json_data = json.loads(json_str)

#                 # Check if all required keys are present
#                 missing_keys = [key for key in KEYS if key not in json_data]
#                 if missing_keys:
#                     return    
#                 self.handle_registration_json(json_data)
#             except json.JSONDecodeError:
#                 pass
#             return

#     def handle_registration_json(self, json_data):
#         supi = json_data.get("supi")
#         if not supi:
#             return

#         imsi = supi.replace("imsi-", "")

#         event = {
#             "_id": imsi,
#             "amf_info": json_data
#         }

#         #self.event_history.append(event)

#         if self.mongo_collection is not None:
#             try:
#                 self.mongo_collection.replace_one({"_id": imsi}, event, upsert=True)
#                 logger.info(f"[MONGODB] Stored registration for IMSI: {imsi}")
#                 logger.info(json.dumps(event, indent=4))
#                 self.mdlw.write_location_info(event)
#             except Exception as e:
#                 logger.error(f"[MONGODB] Failed to insert registration: {e}")



"""

PATTERNS:

Add a UE:

[32m04/08 10:15:44.239[0m: [[33mamf[0m] [1;37mDEBUG[0m: [imsi-001010143245445] Registration accept (../src/amf/nas-path.c:91)
[32m04/08 10:15:44.239[0m: [[33mgmm[0m] [1;37mDEBUG[0m: [imsi-001010143245445]    5G-S_GUTI[AMF_ID:0x20040,M_TMSI:0xc00003aa] (../src/amf/gmm-build.c:76)
[32m04/08 10:15:44.240[0m: [[33mgmm[0m] [1;37mDEBUG[0m: [imsi-001010143245445]    TAI[PLMN_ID:00f110,TAC:1] (../src/amf/gmm-build.c:90)
[32m04/08 10:15:44.240[0m: [[33mgmm[0m] [1;37mDEBUG[0m: [imsi-001010143245445]    NR_CGI[PLMN_ID:00f110,CELL_ID:0x10] (../src/amf/gmm-build.c:92)
[32m04/08 10:15:44.240[0m: [[33mgmm[0m] [1;37mDEBUG[0m: [imsi-001010143245445]    SERVED_TAI_INDEX[0] (../src/amf/gmm-build.c:97)
[32m04/08 10:15:44.240[0m: [[33mamf[0m] [1;37mDEBUG[0m: InitialContextSetupRequest(UE) (../src/amf/ngap-build.c:476)
[32m04/08 10:15:44.241[0m: [[33mamf[0m] [1;37mDEBUG[0m:     RAN_UE_NGAP_ID[1] AMF_UE_NGAP_ID[1] (../src/amf/ngap-build.c:625)
[32m04/08 10:15:44.241[0m: [[33mamf[0m] [1;37mDEBUG[0m:     IP[10.220.2.166] RAN_ID[1] (../src/amf/ngap-path.c:64)
[32m04/08 10:15:44.242[0m: [[33mamf[0m] [1;37mDEBUG[0m: amf_state_operational(): AMF_EVENT_NGAP_MESSAGE (../src/amf/amf-sm.c:81)
[32m04/08 10:15:44.242[0m: [[33mamf[0m] [1;37mDEBUG[0m: ngap_state_operational(): AMF_EVENT_NGAP_MESSAGE (../src/amf/ngap-sm.c:55)
[32m04/08 10:15:44.242[0m: [[33mamf[0m] [1;37mDEBUG[0m: InitialContextSetupResponse (../src/amf/ngap-handler.c:913)
[32m04/08 10:15:44.242[0m: [[33mamf[0m] [1;37mDEBUG[0m:     IP[10.220.2.166] RAN_ID[1] (../src/amf/ngap-handler.c:933)
[32m04/08 10:15:44.242[0m: [[33mamf[0m] [1;37mDEBUG[0m:     RAN_UE_NGAP_ID[1] AMF_UE_NGAP_ID[1] (../src/amf/ngap-handler.c:967)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m: amf_state_operational(): AMF_EVENT_NGAP_MESSAGE (../src/amf/amf-sm.c:81)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m: ngap_state_operational(): AMF_EVENT_NGAP_MESSAGE (../src/amf/ngap-sm.c:55)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m: UplinkNASTransport (../src/amf/ngap-handler.c:643)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m:     IP[10.220.2.166] RAN_ID[1] (../src/amf/ngap-handler.c:665)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m:     SERVED_TAI_INDEX[0] (../src/amf/ngap-handler.c:759)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m:     RAN_UE_NGAP_ID[1] AMF_UE_NGAP_ID[1] TAC[1] CellID[0x10] (../src/amf/ngap-handler.c:766)
[32m04/08 10:15:44.445[0m: [[33mamf[0m] [1;37mDEBUG[0m: amf_state_operational(): AMF_EVENT_5GMM_MESSAGE (../src/amf/amf-sm.c:81)
[32m04/08 10:15:44.445[0m: [[33mgmm[0m] [1;37mDEBUG[0m: gmm_state_initial_context_setup(): AMF_EVENT_5GMM_MESSAGE (../src/amf/gmm-sm.c:2114)
[32m04/08 10:15:44.445[0m: [[33mgmm[0m] [1;32mINFO[0m: [imsi-001010143245445] Registration complete (../src/amf/gmm-sm.c:2288)

...

INFO:

[32m04/08 10:15:44.449[0m: [[33msbi[0m] [1;37mDEBUG[0m: --=-m1Zv9ReL7+6srN3pcZ3tvA==
Content-Type: application/json

{
    "supi":"imsi-001010143245445",
    "pei":"imeisv-4370816125816151",
    "pduSessionId":1,
    "dnn":"internet",
    "sNssai":{"sst":1},
    "servingNfId":"ffbfd238-1461-41f0-8f96-19a342ebb0f2",
    "guami":{"plmnId":{"mcc":"001","mnc":"01"},"amfId":"020040"},"servingNetwork":{"mcc":"001","mnc":"01"},
    "n1SmMsg":{"contentId":"5gnas-sm"},
    "anType":"3GPP_ACCESS",
    "ratType":"NR",
    "ueLocation":{"nrLocation":{"tai":{"plmnId":{"mcc":"001","mnc":"01"},"tac":"000001"},
    "ncgi":{"plmnId":{"mcc":"001","mnc":"01"},"nrCellId":"000000010"},
    "ueLocationTimestamp":"2025-04-08T10:15:44.137593Z"}},"ueTimeZone":"+00:00",
    "smContextStatusUri":"http://amf.open5gs.org/namf-callback/v1/imsi-001010143245445/sm-context-status/1","pcfId":"10ad956a-0bc7-41f0-8934-53bd37770e11"}
--=-m1Zv9ReL7+6srN3pcZ3tvA==
Content-Id: 5gnas-sm
Content-Type: application/vnd.3gpp.5gnas

›
Remove a UE: 

[32m04/08 10:18:27.018[0m: [[33mgmm[0m] [1;37mDEBUG[0m: [imsi-001010000000001] Security mode complete (../src/amf/gmm-sm.c:1934)
[32m04/08 10:18:27.018[0m: [[33mgmm[0m] [1;36mWARNING[0m: [suci-0-001-01-0000-0-0-0000000001] Clear NG Context (../src/amf/gmm-sm.c:1968)

"""



"""
run.py: Τρεχει τα πάντα.
log_sim.py: Τρεχει ενα simulation που διαβαζει ενα log file και προσομοιωνει την διαδικασια της αναγνωσης των logs καθε 2 δευτερα, στελνοντας τα πιο προσφατα για επεξεργασια.
info_parser.py: Η επεξεργασια των logs. Εκει εξαγεται και το πολυποθητο json και γραφεται στη mongo. Το object εχει τη μορφη:


{
    "_id": "001010143245445",
    "amf_info": {
        "supi": "imsi-001010143245445",
        "pei": "imeisv-4370816125816151",
        "pduSessionId": 1,
        "dnn": "internet",
        "sNssai": {
            "sst": 1
        },
        "servingNfId": "215bda8c-147a-41f0-9f31-052e80267e61",
        "guami": {
            "plmnId": {
                "mcc": "001",
                "mnc": "01"
            },
            "amfId": "020040"
        },
        "servingNetwork": {
            "mcc": "001",
            "mnc": "01"
        },
        "n1SmMsg": {
            "contentId": "5gnas-sm"
        },
        "anType": "3GPP_ACCESS",
        "ratType": "NR",
        "ueLocation": {
            "nrLocation": {
                "tai": {
                    "plmnId": {
                        "mcc": "001",
                        "mnc": "01"
                    },
                    "tac": "000001"
                },
                "ncgi": {
                    "plmnId": {
                        "mcc": "001",
                        "mnc": "01"
                    },
                    "nrCellId": "000000010"
                },
                "ueLocationTimestamp": "2025-04-08T13:06:42.904325Z"
            }
        },
        "ueTimeZone": "+00:00",
        "smContextStatusUri": "http://amf.open5gs.org/namf-callback/v1/imsi-001010143245445/sm-context-status/1",
        "pcfId": "10ad956a-0bc7-41f0-8934-53bd37770e11"
    }
}
"""
