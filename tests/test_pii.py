"""Tests for src/security/pii.py — PII detection and redaction."""

import pytest

from src.security.pii import _luhn_check, scan_for_pii


class TestLuhnCheck:

    def test_valid_visa(self):
        assert _luhn_check("4111111111111111") is True

    def test_valid_mastercard(self):
        assert _luhn_check("5500000000000004") is True

    def test_invalid_number(self):
        assert _luhn_check("4111111111111112") is False

    def test_too_short(self):
        assert _luhn_check("123456") is False

    def test_too_long(self):
        assert _luhn_check("4111111111111111111111") is False


class TestSSNDetection:

    async def test_ssn_dash_format(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("My SSN is 123-45-6789")
        assert "SSN" in result.detections
        assert "[REDACTED_SSN]" in result.redacted_content

    async def test_ssn_space_format(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("My SSN is 123 45 6789")
        assert "SSN" in result.detections


class TestCreditCardDetection:

    async def test_valid_cc_plain(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Card: 4111111111111111")
        assert "CREDIT_CARD" in result.detections
        assert "[REDACTED_CC]" in result.redacted_content

    async def test_valid_cc_dashes(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Card: 4111-1111-1111-1111")
        assert "CREDIT_CARD" in result.detections

    async def test_valid_cc_spaces(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Card: 4111 1111 1111 1111")
        assert "CREDIT_CARD" in result.detections

    async def test_invalid_cc_fails_luhn(self, override_settings):
        """Number that matches CC regex but fails Luhn should NOT be detected."""
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Number: 4111111111111112")
        assert "CREDIT_CARD" not in result.detections


class TestEmailDetection:

    async def test_simple_email(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Contact me at user@example.com")
        assert "EMAIL" in result.detections
        assert "[REDACTED_EMAIL]" in result.redacted_content

    async def test_email_with_plus(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("user+tag@example.com")
        assert "EMAIL" in result.detections


class TestPhoneDetection:

    async def test_phone_dashes(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Call me at 123-456-7890")
        assert "PHONE" in result.detections
        assert "[REDACTED_PHONE]" in result.redacted_content

    async def test_phone_dots(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Call me at 123.456.7890")
        assert "PHONE" in result.detections

    async def test_phone_parens(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Call me at (123) 456-7890")
        assert "PHONE" in result.detections

    async def test_bare_digits_not_phone(self, override_settings):
        """10 consecutive digits without separators should not match phone."""
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Order ID: 1234567890")
        assert "PHONE" not in result.detections


class TestIPDetection:

    async def test_ipv4(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Server at 192.168.1.100")
        assert "IP_ADDRESS" in result.detections
        assert "[REDACTED_IP]" in result.redacted_content

    async def test_boundary_ip(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("IP: 255.255.255.255")
        assert "IP_ADDRESS" in result.detections


class TestPIIActions:

    async def test_redact_mode(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("Email: test@example.com")
        assert result.clean is False
        assert result.redacted_content is not None
        assert "test@example.com" not in result.redacted_content

    async def test_block_mode(self, override_settings):
        override_settings(PII_ACTION="block")
        result = await scan_for_pii("Email: test@example.com")
        assert result.clean is False
        assert result.redacted_content is None
        assert result.detection_count == 1

    async def test_log_only_mode(self, override_settings):
        override_settings(PII_ACTION="log_only")
        result = await scan_for_pii("Email: test@example.com")
        assert result.clean is True
        assert result.detection_count == 1
        assert "EMAIL" in result.detections

    async def test_empty_input(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("")
        assert result.clean is True
        assert result.detection_count == 0

    async def test_no_pii(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii("This is a clean message with no PII.")
        assert result.clean is True

    async def test_multiple_pii_types(self, override_settings):
        override_settings(PII_ACTION="redact")
        result = await scan_for_pii(
            "My email is user@test.com and my SSN is 123-45-6789"
        )
        assert "EMAIL" in result.detections
        assert "SSN" in result.detections
        assert result.detection_count == 2
