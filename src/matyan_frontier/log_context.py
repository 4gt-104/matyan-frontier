"""Request-scoped structured log context using contextvars.

Each async task (HTTP request, WebSocket connection) gets its own copy of
these variables.  A loguru filter injects them into ``record["extra"]`` so
the format string can include them without any per-call-site changes.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loguru import Record

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
_connection_id_var: ContextVar[str | None] = ContextVar("connection_id", default=None)


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


def set_run_id(value: str) -> None:
    _run_id_var.set(value)


def set_connection_id(value: str) -> None:
    _connection_id_var.set(value)


def log_context_filter(record: Record) -> bool:
    """Loguru filter that populates ``record["extra"]`` from contextvars.

    Builds a compact ``ctx`` string containing only the non-empty IDs so the
    format string can use a single ``{extra[ctx]}`` placeholder.
    """
    rid = _request_id_var.get()
    run = _run_id_var.get()
    cid = _connection_id_var.get()

    record["extra"]["request_id"] = rid or ""
    record["extra"]["run_id"] = run or ""
    record["extra"]["connection_id"] = cid or ""

    parts: list[str] = []
    if rid:
        parts.append(f"request_id={rid}")
    if run:
        parts.append(f"run_id={run}")
    if cid:
        parts.append(f"conn_id={cid}")
    record["extra"]["ctx"] = " ".join(parts)

    return True
