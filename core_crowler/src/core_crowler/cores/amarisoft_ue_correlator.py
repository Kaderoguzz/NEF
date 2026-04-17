from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core_crowler.middleware.o5gs import O5GSMiddleware
from core_crowler.utils.amarisoft_client import AmarisoftUE, AmarisoftUEGetResponse
from core_crowler.utils.logger import setup_logger

logger = setup_logger(logger_name="amarisoft_ue_correlator")


class AmarisoftUECorrelator:
    """
    Correlates O5GS ue-info records with Amarisoft ue_get records.

    Assumption:
    - ue-info.gnb.amf_ue_ngap_id == amarisoft.amf_ue_id
    - ue-info.gnb.ran_ue_ngap_id == amarisoft.ran_ue_id

    The class keeps ue-info as the identity source and uses Amarisoft
    only to enrich the Mongo location record with a newer cell ID and
    timestamp.
    """

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017",
        db_name: str = "amf_logs",
    ):
        self.mdlw = O5GSMiddleware(mongo_uri, db_name)

    def _format_utc_timestamp(self, utc_seconds: float | int) -> str:
        dt = datetime.fromtimestamp(float(utc_seconds), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def build_ue_info_correlation(self, ue_info_items: list[Any]) -> dict[tuple[int, int], str]:
        """
        Builds:
            (amf_ue_ngap_id, ran_ue_ngap_id) -> imsi
        """
        correlation: dict[tuple[int, int], str] = {}

        for ue in ue_info_items:
            gnb = ue.gnb
            if gnb.amf_ue_ngap_id is None or gnb.ran_ue_ngap_id is None:
                continue

            imsi = ue.supi.removeprefix("imsi-")
            key = (gnb.amf_ue_ngap_id, gnb.ran_ue_ngap_id)
            correlation[key] = imsi

        return correlation

    def build_mongo_update_from_amari(
        self,
        mongo_id: str,
        existing_doc: dict[str, Any],
        amari_ue: AmarisoftUE,
        utc: float | int,
    ) -> dict[str, Any] | None:
        cells = amari_ue.cells
        if not cells:
            logger.info("No cells found for Amarisoft UE mapped to IMSI %s", mongo_id)
            return None

        first_cell = cells[0]
        cell_id = first_cell.cell_id
        if cell_id is None:
            logger.info("No cell_id found for Amarisoft UE mapped to IMSI %s", mongo_id)
            return None

        updated_doc = dict(existing_doc)
        updated_doc["cellId"] = str(cell_id)
        updated_doc["UELocationTimestamp"] = self._format_utc_timestamp(utc)

        return updated_doc

    def correlate_and_build_updates(
        self,
        ue_info_items: list[Any],
        amari_response: AmarisoftUEGetResponse,
        existing_docs_by_imsi: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Returns Mongo location documents ready to be written through
        O5GSMiddleware.write_location_info_from_amf_endpoint().
        """
        correlation = self.build_ue_info_correlation(ue_info_items)

        ue_list = amari_response.ue_list
        utc = amari_response.utc
        if utc is None:
            logger.warning("Amarisoft response has no utc field")
            return []

        updates: list[dict[str, Any]] = []

        for amari_ue in ue_list:
            amf_ue_id = amari_ue.amf_ue_id
            ran_ue_id = amari_ue.ran_ue_id
            if amf_ue_id is None or ran_ue_id is None:
                continue

            correlated_mongo_imsi_id = correlation.get((amf_ue_id, ran_ue_id))
            if correlated_mongo_imsi_id is None:
                logger.info(
                    "No ue-info match for Amarisoft UE (amf_ue_id=%s, ran_ue_id=%s)",
                    amf_ue_id,
                    ran_ue_id,
                )
                continue
            logger.info("Amarisoft UE (amf_ue_id=%s, ran_ue_id=%s) correlated to IMSI %s",
                        amf_ue_id, ran_ue_id, correlated_mongo_imsi_id)
            existing_doc = existing_docs_by_imsi.get(correlated_mongo_imsi_id)
            if not existing_doc:
                logger.info("No existing Mongo document found for IMSI %s", correlated_mongo_imsi_id)
                continue

            updated_doc = self.build_mongo_update_from_amari(
                mongo_id=correlated_mongo_imsi_id,
                existing_doc=existing_doc,
                amari_ue=amari_ue,
                utc=utc,
            )
            logger.info("Built updated Mongo document for IMSI %s: %s", correlated_mongo_imsi_id, updated_doc)
            if updated_doc is not None:
                updates.append(updated_doc)

        return updates

    def persist_updates(self, updates: list[dict[str, Any]]) -> None:
        for doc in updates:
            self.mdlw.write_location_info_from_amf_endpoint(doc)
