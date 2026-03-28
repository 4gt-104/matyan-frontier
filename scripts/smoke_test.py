"""Smoke test for the frontier service.

Prerequisites:
  - Kafka running (docker compose up kafka kafka-init)
  - RustFS (S3) running (docker compose up rustfs)
  - Frontier running (matyan-frontier start)

Usage:
  cd matyan-frontier
  python scripts/smoke_test.py
"""  # noqa: INP001

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

import httpx
from aiokafka import AIOKafkaConsumer
from websockets.asyncio.client import connect as ws_connect

# ruff: noqa: T201

FRONTIER_URL = "http://localhost:53801"
FRONTIER_WS = "ws://localhost:53801"
KAFKA_BOOTSTRAP = "localhost:9092"
DATA_INGESTION_TOPIC = "data-ingestion"

RUN_ID = "smoke_test_run_001"


async def run_websocket() -> list[str]:
    """Send create_run, log_metric, log_hparams, finish_run over WS."""
    url = f"{FRONTIER_WS}/api/v1/ws/runs/{RUN_ID}"
    print(f"\n[WS] Connecting to {url}")

    published_types: list[str] = []

    async with ws_connect(url) as ws:
        messages = [
            {"type": "create_run", "client_datetime": datetime.now(UTC).isoformat()},
            {
                "type": "log_metric",
                "name": "loss",
                "value": 0.42,
                "step": 0,
                "epoch": 0,
                "context": {"subset": "train"},
                "dtype": "float",
                "client_datetime": datetime.now(UTC).isoformat(),
            },
            {
                "type": "log_metric",
                "name": "loss",
                "value": 0.35,
                "step": 1,
                "epoch": 0,
                "context": {"subset": "train"},
                "dtype": "float",
                "client_datetime": datetime.now(UTC).isoformat(),
            },
            {"type": "log_hparams", "value": {"lr": 0.001, "batch_size": 32}},
            {"type": "finish_run"},
        ]

        for msg in messages:
            await ws.send(json.dumps(msg))
            resp_raw = await ws.recv()
            resp = json.loads(resp_raw)
            status = resp.get("status")
            label = msg["type"]
            if status == "ok":
                print(f"  [OK] {label}")
                published_types.append(label)  # ty:ignore[invalid-argument-type]
            else:
                print(f"  [FAIL] {label}: {resp}")

    return published_types


async def run_presigned_url() -> bool:
    """Request a presigned blob upload URL."""
    url = f"{FRONTIER_URL}/api/v1/rest/artifacts/presign"
    print(f"\n[REST] POST {url}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={
                "run_id": RUN_ID,
                "artifact_path": "images/test.png",
                "content_type": "image/png",
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  [OK] upload_url={data['upload_url'][:80]}...")
            print(f"       s3_key={data['s3_key']}")
            return True
        print(f"  [FAIL] status={resp.status_code} body={resp.text}")
        return False


async def verify_kafka(expected_count: int) -> int:
    """Consume from data-ingestion and verify messages arrived."""
    print(f"\n[KAFKA] Consuming from {DATA_INGESTION_TOPIC} ...")

    consumer = AIOKafkaConsumer(
        DATA_INGESTION_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        group_id="frontier-smoke-test",
        consumer_timeout_ms=5000,
    )
    await consumer.start()

    received: list[dict] = []
    try:
        async for msg in consumer:
            value = json.loads(msg.value.decode())
            if value.get("run_id") == RUN_ID:
                received.append(value)
                print(f"  [MSG] type={value['type']}  run_id={value['run_id']}")
            if len(received) >= expected_count:
                break
    finally:
        await consumer.stop()

    print(f"  Received {len(received)} / {expected_count} expected messages")
    return len(received)


async def main() -> None:
    print("=" * 60)
    print("Frontier Smoke Test")
    print("=" * 60)

    ws_types = await run_websocket()
    presign_ok = await run_presigned_url()

    expected = len(ws_types) + (1 if presign_ok else 0)
    kafka_count = await verify_kafka(expected)

    print("\n" + "=" * 60)
    ok = kafka_count >= expected and presign_ok
    if ok:
        print("PASS: All checks succeeded")
    else:
        print("FAIL: Some checks did not pass")
    print("=" * 60)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
