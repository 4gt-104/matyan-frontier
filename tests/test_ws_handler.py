"""Tests for ws/handler.py: WebSocket handler, _build_ingestion_message, all message types."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from aiokafka.errors import KafkaError
from fastapi.testclient import TestClient
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
)

from matyan_frontier.app import app
from matyan_frontier.ws.handler import _build_ingestion_message

if TYPE_CHECKING:
    from .conftest import MockKafkaProducer

WS_URL = "/api/v1/ws/runs/test_run_1"
NOW = datetime.now(UTC)


# ---------------------------------------------------------------------------
# _build_ingestion_message unit tests (covers all branches)
# ---------------------------------------------------------------------------


class TestBuildIngestionMessage:
    def test_create_run(self) -> None:
        req = CreateRunWsRequest(run_id="r1", client_datetime=NOW)
        msg = _build_ingestion_message(req)
        assert msg.type == "create_run"
        assert msg.run_id == "r1"
        assert "client_datetime" in msg.payload
        assert msg.payload["force_resume"] is False

    def test_log_metric(self) -> None:
        req = LogMetricWsRequest(
            run_id="r1",
            name="loss",
            value=0.5,
            step=1,
            epoch=0,
            context={"subset": "train"},
            dtype="float",
            client_datetime=NOW,
        )
        msg = _build_ingestion_message(req)
        assert msg.type == "log_metric"
        assert msg.payload["name"] == "loss"
        assert msg.payload["value"] == 0.5

    def test_log_hparams(self) -> None:
        req = LogHParamsWsRequest(run_id="r1", value={"lr": 0.01})
        msg = _build_ingestion_message(req)
        assert msg.type == "log_hparams"
        assert msg.payload["value"] == {"lr": 0.01}

    def test_finish_run(self) -> None:
        req = FinishRunWsRequest(run_id="r1")
        msg = _build_ingestion_message(req)
        assert msg.type == "finish_run"
        assert msg.payload == {}

    def test_set_run_property_all_fields(self) -> None:
        req = SetRunPropertyWsRequest(
            run_id="r1",
            name="my_run",
            description="desc",
            archived=True,
            experiment="exp1",
        )
        msg = _build_ingestion_message(req)
        assert msg.type == "set_run_property"
        assert msg.payload == {
            "name": "my_run",
            "description": "desc",
            "archived": True,
            "experiment": "exp1",
        }

    def test_set_run_property_no_fields(self) -> None:
        req = SetRunPropertyWsRequest(run_id="r1")
        msg = _build_ingestion_message(req)
        assert msg.payload == {}

    def test_add_tag(self) -> None:
        req = AddTagWsRequest(run_id="r1", tag_name="best")
        msg = _build_ingestion_message(req)
        assert msg.type == "add_tag"
        assert msg.payload == {"tag_name": "best"}

    def test_remove_tag(self) -> None:
        req = RemoveTagWsRequest(run_id="r1", tag_name="old")
        msg = _build_ingestion_message(req)
        assert msg.type == "remove_tag"
        assert msg.payload == {"tag_name": "old"}

    def test_log_custom_object(self) -> None:
        req = LogCustomObjectWsRequest(
            run_id="r1",
            name="images",
            value={"s3_key": "k"},
            step=0,
            epoch=0,
            context={},
            dtype="image",
        )
        msg = _build_ingestion_message(req)
        assert msg.type == "log_custom_object"
        assert msg.payload["name"] == "images"

    def test_log_terminal_line(self) -> None:
        req = LogTerminalLineWsRequest(run_id="r1", line="hello", step=0)
        msg = _build_ingestion_message(req)
        assert msg.type == "log_terminal_line"
        assert msg.payload == {"line": "hello", "step": 0}

    def test_log_record_minimal(self) -> None:
        req = LogRecordWsRequest(
            run_id="r1",
            message="msg",
            level=20,
            timestamp=1000.0,
        )
        msg = _build_ingestion_message(req)
        assert msg.type == "log_record"
        assert "logger_info" not in msg.payload
        assert "extra_args" not in msg.payload

    def test_log_record_full(self) -> None:
        req = LogRecordWsRequest(
            run_id="r1",
            message="msg",
            level=40,
            timestamp=2000.0,
            logger_info=["mod", "func", 42],
            extra_args={"key": "val"},
        )
        msg = _build_ingestion_message(req)
        assert msg.payload["logger_info"] == ["mod", "func", 42]
        assert msg.payload["extra_args"] == {"key": "val"}

    def test_blob_ref(self) -> None:
        req = BlobRefWsRequest(
            run_id="r1",
            s3_key="run/img.png",
            artifact_path="img.png",
            content_type="image/png",
        )
        msg = _build_ingestion_message(req)
        assert msg.type == "blob_ref"
        assert msg.payload["s3_key"] == "run/img.png"

    def test_unhandled_type_raises(self) -> None:
        class FakeRequest:
            type = "unknown"
            run_id = "r1"

        with pytest.raises(TypeError, match="Unhandled request type"):
            _build_ingestion_message(FakeRequest())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WebSocket endpoint integration tests
# ---------------------------------------------------------------------------


class TestWsHandlerHappyPath:
    def test_create_run(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "create_run",
                        "client_datetime": NOW.isoformat(),
                    },
                ),
            )
            resp = json.loads(ws.receive_text())
            assert resp["status"] == "ok"
        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].type == "create_run"

    def test_log_metric(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "log_metric",
                        "name": "loss",
                        "value": 0.42,
                        "step": 0,
                        "epoch": 0,
                        "context": {"subset": "train"},
                        "dtype": "float",
                        "client_datetime": NOW.isoformat(),
                    },
                ),
            )
            resp = json.loads(ws.receive_text())
            assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "log_metric"

    def test_log_hparams(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(json.dumps({"type": "log_hparams", "value": {"lr": 0.001}}))
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "log_hparams"

    def test_finish_run(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(json.dumps({"type": "finish_run"}))
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "finish_run"

    def test_set_run_property(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "set_run_property",
                        "name": "renamed",
                        "description": "desc",
                        "archived": False,
                        "experiment": "baseline",
                    },
                ),
            )
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "set_run_property"

    def test_add_tag(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(json.dumps({"type": "add_tag", "tag_name": "best"}))
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "add_tag"

    def test_remove_tag(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(json.dumps({"type": "remove_tag", "tag_name": "old"}))
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "remove_tag"

    def test_log_custom_object(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "log_custom_object",
                        "name": "images",
                        "value": {"s3_key": "run/img.png"},
                        "step": 0,
                        "dtype": "image",
                    },
                ),
            )
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "log_custom_object"

    def test_log_terminal_line(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(json.dumps({"type": "log_terminal_line", "line": "epoch 1", "step": 0}))
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "log_terminal_line"

    def test_log_record(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "log_record",
                        "message": "training started",
                        "level": 20,
                        "timestamp": 1000.0,
                        "logger_info": ["mod", "fn", 10],
                        "extra_args": {"k": "v"},
                    },
                ),
            )
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "log_record"

    def test_blob_ref(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "blob_ref",
                        "s3_key": "run/artifact.bin",
                        "artifact_path": "artifact.bin",
                        "content_type": "application/octet-stream",
                    },
                ),
            )
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert mock_producer.published[0].type == "blob_ref"


class TestWsBatchMessages:
    def test_batch_of_two(self, client: TestClient, mock_producer: MockKafkaProducer) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(
                json.dumps(
                    [
                        {"type": "log_hparams", "value": {"lr": 0.1}},
                        {"type": "finish_run"},
                    ],
                ),
            )
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "ok"
        assert len(mock_producer.published) == 2


class TestWsErrorPaths:
    def test_invalid_json(self, client: TestClient) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text("{bad json")
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "error"
        assert resp["error"] is not None

    def test_validation_error(self, client: TestClient) -> None:
        with client.websocket_connect(WS_URL) as ws:
            ws.send_text(json.dumps({"type": "log_metric"}))  # missing required fields
            resp = json.loads(ws.receive_text())
        assert resp["status"] == "error"

    def test_kafka_publish_error(self, mock_producer: MockKafkaProducer) -> None:
        async def _fail(msg: object) -> None:
            msg = "connection refused"
            raise KafkaError(msg)

        mock_producer.publish = _fail  # type: ignore[assignment]
        with (
            patch("matyan_frontier.app.get_producer", return_value=mock_producer),
            patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
            TestClient(app, raise_server_exceptions=False) as c,
            c.websocket_connect(WS_URL) as ws,
        ):
            ws.send_text(
                json.dumps(
                    {
                        "type": "create_run",
                        "client_datetime": NOW.isoformat(),
                    },
                ),
            )
            resp = json.loads(ws.receive_text())

        assert resp["status"] == "error"
        assert "internal publish error" in resp["error"]

    def test_disconnect_handled(self, client: TestClient) -> None:
        with client.websocket_connect(WS_URL):
            pass  # close immediately — triggers WebSocketDisconnect

    def test_generic_exception_closes_socket(self, mock_producer: MockKafkaProducer) -> None:
        async def _explode(msg: object) -> None:
            msg = "boom"
            raise ValueError(msg)

        mock_producer.publish = _explode  # type: ignore[assignment]
        with (
            patch("matyan_frontier.app.get_producer", return_value=mock_producer),
            patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
            TestClient(app, raise_server_exceptions=False) as c,
        ):
            try:
                with c.websocket_connect(WS_URL) as ws:
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "create_run",
                                "client_datetime": NOW.isoformat(),
                            },
                        ),
                    )
                    with contextlib.suppress(Exception):
                        ws.receive_text()
            except Exception:  # noqa: BLE001, S110
                pass  # socket may already be closed
