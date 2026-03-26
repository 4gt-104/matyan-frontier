"""Tests for logging.py: configure_logging with log context filter."""

from __future__ import annotations

import sys
from typing import Any, cast
from unittest.mock import MagicMock, patch

from matyan_frontier.log_context import log_context_filter
from matyan_frontier.logging import _format_with_separator, configure_logging


class TestConfigureLogging:
    @patch("matyan_frontier.logging.logger")
    def test_removes_default_and_adds_at_level(self, mock_logger: object) -> None:
        configure_logging("DEBUG")

        assert isinstance(mock_logger, MagicMock)
        mock_logger.remove.assert_called_once()
        mock_logger.add.assert_called_once_with(
            sys.stderr,
            level="DEBUG",
            filter=log_context_filter,
            format=_format_with_separator,
        )

    @patch("matyan_frontier.logging.logger")
    def test_uppercases_level(self, mock_logger: object) -> None:
        configure_logging("warning")

        assert isinstance(mock_logger, MagicMock)
        mock_logger.add.assert_called_once_with(
            sys.stderr,
            level="WARNING",
            filter=log_context_filter,
            format=_format_with_separator,
        )

    @patch("matyan_frontier.logging.logger")
    def test_default_level(self, mock_logger: object) -> None:
        configure_logging()

        assert isinstance(mock_logger, MagicMock)
        mock_logger.add.assert_called_once_with(
            sys.stderr,
            level="INFO",
            filter=log_context_filter,
            format=_format_with_separator,
        )


class TestFormatWithSeparator:
    def test_no_ctx_no_separator(self) -> None:
        record = {"extra": {"ctx": ""}}
        fmt = _format_with_separator(cast("Any", record))
        assert " | {extra[ctx]}" not in fmt
        assert "{extra[ctx]}" in fmt

    def test_with_ctx_has_separator(self) -> None:
        record = {"extra": {"ctx": "request_id=abc"}}
        fmt = _format_with_separator(cast("Any", record))
        assert " | {extra[ctx]}" in fmt
