"""Structured logging.

Two modes: human-readable for local development, single-line JSON for anything that ships
logs to a collector. Correlation IDs are attached per request by the API middleware so a
single analysis run can be traced end to end.

Deliberate omission: connection names, employers, and URLs are never logged. Only counts,
durations, and error classes. Log files should never become a shadow copy of the export.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Single-line JSON records, collector-friendly."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if correlation_id := getattr(record, "correlation_id", None):
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
            datefmt="%H:%M:%S",
        )


def configure(level: str = "INFO", json_output: bool = False) -> None:
    """Idempotent root logger configuration. Safe to call from tests and from uvicorn."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
    # stderr, never stdout: `netlab analyze --json` must emit parseable JSON on stdout.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    root.addHandler(handler)

    # uvicorn installs its own noisy access logger; align it with ours.
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.error").handlers = [handler]
