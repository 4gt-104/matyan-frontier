"""Centralized loguru configuration."""

import sys

from loguru import logger

from .log_context import log_context_filter

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "{extra[ctx]}"
    "{message}"
)


def _format_with_separator(record: dict) -> str:
    """Return format string, inserting `` | `` separator when ctx is non-empty."""
    ctx = record["extra"].get("ctx", "")
    sep = " | " if ctx else ""
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
        f"{sep}{{extra[ctx]}}"
        " - {message}\n{exception}"
    )


def configure_logging(level: str = "INFO") -> None:
    """Remove the default loguru handler and re-add one at *level*."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        filter=log_context_filter,
        format=_format_with_separator,
    )
