"""Tests for cli.py: main group and start command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from matyan_frontier.cli import main


class TestCli:
    def test_main_help(self) -> None:
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Matyan Frontier CLI" in result.output

    def test_start_help(self) -> None:
        result = CliRunner().invoke(main, ["start", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output

    def test_start_default(self) -> None:
        mock_run = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": MagicMock(run=mock_run)}):
            result = CliRunner().invoke(main, ["start"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            "matyan_frontier.app:app",
            host="0.0.0.0",
            port=53801,
            workers=1,
            log_level="info",
        )

    def test_start_custom_host_port(self) -> None:
        mock_run = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": MagicMock(run=mock_run)}):
            result = CliRunner().invoke(main, ["start", "--host", "127.0.0.1", "--port", "9999"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            "matyan_frontier.app:app",
            host="127.0.0.1",
            port=9999,
            workers=1,
            log_level="info",
        )
