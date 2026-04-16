from __future__ import annotations

import asyncio
import json
import os

import websockets
from pydantic import BaseModel, Field

from core_crowler.utils.logger import setup_logger

logger = setup_logger(logger_name="amarisoft_client")


class AmarisoftClientError(RuntimeError):
    """Base error for Amarisoft websocket failures."""


class AmarisoftClientTimeout(AmarisoftClientError):
    """Raised when Amarisoft websocket communication times out."""


class AmarisoftCell(BaseModel):
    cell_id: int


class AmarisoftUE(BaseModel):
    ran_ue_id: int | None = None
    amf_ue_id: int | None = None
    rnti: int | None = None
    cells: list[AmarisoftCell] = Field(default_factory=list)


class AmarisoftUEGetResponse(BaseModel):
    message: str
    message_id: str | None = None
    ue_list: list[AmarisoftUE] = Field(default_factory=list)
    time: float | None = None
    utc: float | None = None


class AmarisoftClient:
    
    def __init__(
        self,
        server: str,
        connect_timeout: float = 5.0,
        recv_timeout: float = 5.0,
    ):
        self.server = server
        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout

    async def _recv_with_timeout(self, ws, timeout: float, operation: str) -> str:
        try:
            return await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise AmarisoftClientTimeout(
                f"Timed out waiting for Amarisoft {operation} after {timeout}s"
            ) from exc

    async def ue_get(
        self,
        stats: bool = False,
        connect_timeout: float | None = None,
        recv_timeout: float | None = None,
    ) -> AmarisoftUEGetResponse:
        uri = f"ws://{self.server}"
        connect_timeout = connect_timeout if connect_timeout is not None else self.connect_timeout
        recv_timeout = recv_timeout if recv_timeout is not None else self.recv_timeout

        logger.info("Connecting to Amarisoft websocket at %s", uri)

        try:
            async with websockets.connect(uri, origin="Test", open_timeout=connect_timeout) as ws:
                # Amarisoft example receives the initial "ready" first.
                ready_raw = await self._recv_with_timeout(ws, recv_timeout, "initial ready message")
                logger.debug("Amarisoft ready message: %s", ready_raw)

                payload = {"message": "ue_get"}
                if stats:
                    payload["stats"] = True

                msg = json.dumps(payload)
                logger.debug("Sending Amarisoft ue_get payload: %s", msg)
                await asyncio.wait_for(ws.send(msg), timeout=recv_timeout)

                while True:
                    raw = await self._recv_with_timeout(ws, recv_timeout, "ue_get response")
                    logger.debug("Received Amarisoft websocket message: %s", raw)
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise AmarisoftClientError("Amarisoft returned invalid JSON") from exc

                    if data.get("message") == "ready":
                        continue

                    return AmarisoftUEGetResponse.model_validate(data)
        except asyncio.TimeoutError as exc:
            raise AmarisoftClientTimeout(
                f"Timed out communicating with Amarisoft websocket at {uri}"
            ) from exc

if __name__ == "__main__":
    client = AmarisoftClient(os.getenv("AMARISOFT_SERVER", "10.220.2.10:9001"))
    response = asyncio.run(client.ue_get(stats=False))
    logger.info("RESPONSE: %s", response.model_dump_json(indent=2))
    
