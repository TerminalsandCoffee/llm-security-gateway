"""PII detection and redaction module.

Scans request content for personally identifiable information using
regex patterns. Supports configurable actions per detection:
- redact: replace PII with type-labeled placeholders
- block: reject the entire request
- log_only: allow through but log detections

Detected PII types:
- SSN (Social Security Number)
- Credit card numbers (with Luhn validation)
- Email addresses
- US phone numbers
- IPv4 addresses
"""

import re
from dataclasses import dataclass, field

from src.config.settings import get_settings

# Pattern definitions: (compiled regex, PII type label, redaction placeholder)
_PII_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # SSN: 123-45-6789 or 123 45 6789
    (re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"), "SSN", "[REDACTED_SSN]"),

    # Credit card: 13-19 digits, optionally separated by spaces or dashes
    # Common formats: 4111-1111-1111-1111, 4111 1111 1111 1111, 4111111111111111
    (re.compile(r"\b(?:\d[-\s]?){12,18}\d\b"), "CREDIT_CARD", "[REDACTED_CC]"),

    # Email
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "EMAIL", "[REDACTED_EMAIL]"),

    # US phone: requires separators to avoid matching bare digit strings
    # Matches: (123) 456-7890, 123-456-7890, 123.456.7890, +1-123-456-7890
    (re.compile(r"(?:\+1[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), "PHONE", "[REDACTED_PHONE]"),

    # IPv4 address (avoid matching version numbers like 1.2.3)
    (re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"), "IP_ADDRESS", "[REDACTED_IP]"),
]


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False

    checksum = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


@dataclass
class PIIResult:
    clean: bool
    detections: list[str] = field(default_factory=list)
    redacted_content: str | None = None
    detection_count: int = 0


async def scan_for_pii(content: str) -> PIIResult:
    """Scan content for PII and optionally redact.

    Returns detection results based on configured PII_ACTION:
    - redact: redacted_content is set with PII replaced by placeholders
    - block: clean=False, caller should reject the request
    - log_only: clean=True, detections logged but content unchanged
    """
    if not content.strip():
        return PIIResult(clean=True)

    settings = get_settings()
    detections: list[str] = []
    redacted = content
    total_detections = 0

    for pattern, pii_type, placeholder in _PII_PATTERNS:
        matches = pattern.finditer(content)
        for match in matches:
            matched_text = match.group()

            # Credit cards need Luhn validation to reduce false positives
            if pii_type == "CREDIT_CARD":
                if not _luhn_check(matched_text):
                    continue

            total_detections += 1
            if pii_type not in detections:
                detections.append(pii_type)
            redacted = redacted.replace(matched_text, placeholder, 1)

    if not detections:
        return PIIResult(clean=True)

    action = settings.pii_action.lower()

    if action == "block":
        return PIIResult(
            clean=False,
            detections=detections,
            detection_count=total_detections,
        )
    elif action == "redact":
        return PIIResult(
            clean=False,
            detections=detections,
            redacted_content=redacted,
            detection_count=total_detections,
        )
    else:  # log_only
        return PIIResult(
            clean=True,
            detections=detections,
            detection_count=total_detections,
        )
