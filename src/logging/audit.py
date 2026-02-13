"""Structured JSON audit logging for the security gateway.

Logs go to stdout as JSON lines (12-factor/cloud-native pattern).
Optional file output via AUDIT_LOG_FILE env var.

Downstream log aggregators (CloudWatch, Elastic, Splunk) ingest
structured JSON directly — no parsing rules needed.
"""

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar

from src.config.settings import get_settings

# Request-scoped context for correlating log entries
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(""),
        }
        # Merge any extra fields passed via `extra={}` kwarg
        if hasattr(record, "audit_data"):
            log_entry.update(record.audit_data)
        return json.dumps(log_entry, default=str)


def setup_logging() -> None:
    """Configure the audit logger with JSON output."""
    settings = get_settings()

    logger = logging.getLogger("gateway.audit")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.handlers.clear()

    formatter = JSONFormatter()

    # Always log to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # Optional file output
    if settings.audit_log_file:
        file_handler = logging.FileHandler(settings.audit_log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger (avoids duplicate output)
    logger.propagate = False


def get_audit_logger() -> logging.Logger:
    return logging.getLogger("gateway.audit")


def generate_request_id() -> str:
    return uuid.uuid4().hex[:12]


class RequestTimer:
    """Context manager to measure request latency."""

    def __init__(self):
        self.start_time: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
