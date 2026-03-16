"""Prometheus metrics definitions for the frontier service."""

from __future__ import annotations

import re

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "matyan_http_requests_total",
    "Total HTTP requests",
    ["method", "path_template", "status_class"],
)

HTTP_REQUEST_DURATION = Histogram(
    "matyan_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path_template", "status_class"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

WS_CONNECTIONS_ACTIVE = Gauge(
    "matyan_ws_connections_active",
    "Number of currently open WebSocket connections",
)

WS_MESSAGES_TOTAL = Counter(
    "matyan_ws_messages_total",
    "Total WebSocket messages processed",
    ["message_type"],
)

WS_CONNECTION_DURATION = Histogram(
    "matyan_ws_connection_duration_seconds",
    "Duration of WebSocket connections in seconds",
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0),
)

_HEX_ID_RE = re.compile(r"(?<=/)[0-9a-f]{8,40}(?=/|$)")
_UUID_RE = re.compile(
    r"(?<=/)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=/|$)",
    re.IGNORECASE,
)


def normalize_path(path: str) -> str:
    """Replace dynamic IDs in a URL path with ``{id}`` to limit label cardinality."""
    path = _UUID_RE.sub("{id}", path)
    return _HEX_ID_RE.sub("{id}", path)
