"""Tests for src/logging/audit.py — JSON audit logging."""

import json
import logging

import pytest

from src.logging.audit import (
    JSONFormatter,
    RequestTimer,
    generate_request_id,
    get_audit_logger,
    request_id_var,
    setup_logging,
)


class TestJSONFormatter:

    def test_output_is_valid_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

    def test_includes_request_id(self):
        token = request_id_var.set("req-abc123")
        try:
            formatter = JSONFormatter()
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="",
                lineno=0, msg="test", args=(), exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["request_id"] == "req-abc123"
        finally:
            request_id_var.reset(token)

    def test_includes_audit_data(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="test", args=(), exc_info=None,
        )
        record.audit_data = {"client_id": "c1", "model": "gpt-4o"}
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["client_id"] == "c1"
        assert parsed["model"] == "gpt-4o"

    def test_empty_request_id_default(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["request_id"] == ""


class TestGenerateRequestId:

    def test_length(self):
        rid = generate_request_id()
        assert len(rid) == 12

    def test_uniqueness(self):
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100

    def test_hex_chars_only(self):
        rid = generate_request_id()
        assert all(c in "0123456789abcdef" for c in rid)


class TestRequestTimer:

    def test_measures_elapsed(self):
        with RequestTimer() as timer:
            # Do a tiny computation
            _ = sum(range(1000))
        assert timer.elapsed_ms > 0
        assert isinstance(timer.elapsed_ms, float)


class TestSetupLogging:

    def test_creates_stdout_handler(self, override_settings):
        override_settings(AUDIT_LOG_FILE="")
        setup_logging()
        logger = get_audit_logger()
        assert len(logger.handlers) >= 1
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
