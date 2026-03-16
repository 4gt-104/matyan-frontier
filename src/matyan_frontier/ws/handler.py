from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime

from aiokafka.errors import KafkaError
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from matyan_api_models.kafka import IngestionMessage
from matyan_api_models.ws import (
    AddTagWsRequest,
    BlobRefWsRequest,
    CreateRunWsRequest,
    FinishRunWsRequest,
    LogCustomObjectWsRequest,
    LogHParamsWsRequest,
    LogMetricWsRequest,
    LogRecordWsRequest,
    LogTerminalLineWsRequest,
    RemoveTagWsRequest,
    SetRunPropertyWsRequest,
    WsRequestTAdapter,
    WsResponse,
)
from pydantic import ValidationError

from matyan_frontier.kafka.producer import get_producer
from matyan_frontier.log_context import set_connection_id, set_run_id
from matyan_frontier.metrics import WS_CONNECTION_DURATION, WS_CONNECTIONS_ACTIVE, WS_MESSAGES_TOTAL

ws_router = APIRouter(prefix="/ws")


def _build_ingestion_message(  # noqa: C901, PLR0912
    request: CreateRunWsRequest
    | LogMetricWsRequest
    | LogHParamsWsRequest
    | FinishRunWsRequest
    | SetRunPropertyWsRequest
    | AddTagWsRequest
    | RemoveTagWsRequest
    | LogCustomObjectWsRequest
    | LogTerminalLineWsRequest
    | LogRecordWsRequest
    | BlobRefWsRequest,
) -> IngestionMessage:
    now = datetime.now(UTC)

    if isinstance(request, CreateRunWsRequest):
        payload = {
            "client_datetime": request.client_datetime.isoformat(),
            "force_resume": request.force_resume,
        }
    elif isinstance(request, LogMetricWsRequest):
        payload = {
            "name": request.name,
            "value": request.value,
            "step": request.step,
            "epoch": request.epoch,
            "context": request.context,
            "dtype": request.dtype,
            "client_datetime": request.client_datetime.isoformat(),
        }
    elif isinstance(request, LogHParamsWsRequest):
        payload = {"value": request.value}
    elif isinstance(request, FinishRunWsRequest):
        payload = {}
    elif isinstance(request, SetRunPropertyWsRequest):
        payload = {}
        if request.name is not None:
            payload["name"] = request.name
        if request.description is not None:
            payload["description"] = request.description
        if request.archived is not None:
            payload["archived"] = request.archived
        if request.experiment is not None:
            payload["experiment"] = request.experiment
    elif isinstance(request, LogCustomObjectWsRequest):
        payload = {
            "name": request.name,
            "value": request.value,
            "step": request.step,
            "epoch": request.epoch,
            "context": request.context,
            "dtype": request.dtype,
        }
    elif isinstance(request, (AddTagWsRequest, RemoveTagWsRequest)):
        payload = {"tag_name": request.tag_name}
    elif isinstance(request, LogTerminalLineWsRequest):
        payload = {"line": request.line, "step": request.step}
    elif isinstance(request, LogRecordWsRequest):
        payload: dict = {
            "message": request.message,
            "level": request.level,
            "timestamp": request.timestamp,
        }
        if request.logger_info is not None:
            payload["logger_info"] = request.logger_info
        if request.extra_args is not None:
            payload["extra_args"] = request.extra_args
    elif isinstance(request, BlobRefWsRequest):
        payload = {
            "s3_key": request.s3_key,
            "artifact_path": request.artifact_path,
            "content_type": request.content_type,
        }
    else:
        msg = f"Unhandled request type: {type(request)}"
        raise TypeError(msg)

    return IngestionMessage(
        type=request.type,
        run_id=request.run_id,
        timestamp=now,
        payload=payload,
    )


@ws_router.websocket("/runs/{run_id}")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    conn_id = str(uuid.uuid4())
    set_run_id(run_id)
    set_connection_id(conn_id)

    producer = get_producer()
    logger.info("WS connected: run_id={}", run_id)

    WS_CONNECTIONS_ACTIVE.inc()
    connect_time = time.monotonic()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid JSON on run_id={}: {}", run_id, exc)
                await websocket.send_text(
                    WsResponse(status="error", error=str(exc)).model_dump_json(),
                )
                continue

            items: list[dict] = parsed if isinstance(parsed, list) else [parsed]

            error_msg: str | None = None
            for data in items:
                data["run_id"] = run_id
                try:
                    validated = WsRequestTAdapter.validate_python(data)
                except ValidationError as exc:
                    logger.warning("Invalid message on run_id={}: {}", run_id, exc)
                    error_msg = str(exc)
                    break

                WS_MESSAGES_TOTAL.labels(message_type=validated.type).inc()
                message = _build_ingestion_message(validated)
                try:
                    await producer.publish(message)
                except KafkaError:
                    logger.exception("Kafka publish failed", run_id=run_id)
                    error_msg = "internal publish error"
                    break

            if error_msg:
                await websocket.send_text(
                    WsResponse(status="error", error=error_msg).model_dump_json(),
                )
            else:
                await websocket.send_text(WsResponse(status="ok").model_dump_json())
    except WebSocketDisconnect:
        logger.info("WS disconnected: run_id={}", run_id)
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error on WS handler", run_id=run_id)
        await websocket.close()
    finally:
        WS_CONNECTIONS_ACTIVE.dec()
        WS_CONNECTION_DURATION.observe(time.monotonic() - connect_time)
