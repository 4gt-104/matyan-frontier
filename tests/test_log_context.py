"""Tests for log_context.py: contextvars, filter, and integration with logging."""

from __future__ import annotations

from typing import TYPE_CHECKING

from matyan_frontier.log_context import (
    _connection_id_var,
    _request_id_var,
    _run_id_var,
    log_context_filter,
    set_connection_id,
    set_request_id,
    set_run_id,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


def _make_record() -> MagicMock:
    """Build a minimal loguru-style record dict wrapped in a MagicMock."""
    record: dict[str, object] = {"extra": {}}
    return record  # type: ignore[return-value]


class TestSetters:
    def test_set_request_id(self) -> None:
        token = _request_id_var.set(None)
        try:
            set_request_id("req-123")
            assert _request_id_var.get() == "req-123"
        finally:
            _request_id_var.reset(token)

    def test_set_run_id(self) -> None:
        token = _run_id_var.set(None)
        try:
            set_run_id("run-abc")
            assert _run_id_var.get() == "run-abc"
        finally:
            _run_id_var.reset(token)

    def test_set_connection_id(self) -> None:
        token = _connection_id_var.set(None)
        try:
            set_connection_id("conn-xyz")
            assert _connection_id_var.get() == "conn-xyz"
        finally:
            _connection_id_var.reset(token)


class TestLogContextFilter:
    def test_returns_true(self) -> None:
        record = _make_record()
        assert log_context_filter(record) is True

    def test_empty_context_produces_empty_strings(self) -> None:
        t1 = _request_id_var.set(None)
        t2 = _run_id_var.set(None)
        t3 = _connection_id_var.set(None)
        try:
            record = _make_record()
            log_context_filter(record)
            assert record["extra"]["request_id"] == ""
            assert record["extra"]["run_id"] == ""
            assert record["extra"]["connection_id"] == ""
            assert record["extra"]["ctx"] == ""
        finally:
            _request_id_var.reset(t1)
            _run_id_var.reset(t2)
            _connection_id_var.reset(t3)

    def test_request_id_only(self) -> None:
        t1 = _request_id_var.set("req-1")
        t2 = _run_id_var.set(None)
        t3 = _connection_id_var.set(None)
        try:
            record = _make_record()
            log_context_filter(record)
            assert record["extra"]["request_id"] == "req-1"
            assert record["extra"]["ctx"] == "request_id=req-1"
        finally:
            _request_id_var.reset(t1)
            _run_id_var.reset(t2)
            _connection_id_var.reset(t3)

    def test_run_and_connection_id(self) -> None:
        t1 = _request_id_var.set(None)
        t2 = _run_id_var.set("run-42")
        t3 = _connection_id_var.set("conn-99")
        try:
            record = _make_record()
            log_context_filter(record)
            assert record["extra"]["run_id"] == "run-42"
            assert record["extra"]["connection_id"] == "conn-99"
            assert "run_id=run-42" in record["extra"]["ctx"]
            assert "conn_id=conn-99" in record["extra"]["ctx"]
        finally:
            _request_id_var.reset(t1)
            _run_id_var.reset(t2)
            _connection_id_var.reset(t3)

    def test_all_three_set(self) -> None:
        t1 = _request_id_var.set("r1")
        t2 = _run_id_var.set("run-7")
        t3 = _connection_id_var.set("c-8")
        try:
            record = _make_record()
            log_context_filter(record)
            ctx = record["extra"]["ctx"]
            assert "request_id=r1" in ctx
            assert "run_id=run-7" in ctx
            assert "conn_id=c-8" in ctx
        finally:
            _request_id_var.reset(t1)
            _run_id_var.reset(t2)
            _connection_id_var.reset(t3)
