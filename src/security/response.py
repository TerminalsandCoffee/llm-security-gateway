"""Response scanning — scans LLM output for PII and injection indicators."""

from dataclasses import dataclass

from src.config.settings import get_settings
from src.security.injection import ScanResult, scan_prompt
from src.security.pii import PIIResult, scan_for_pii


@dataclass
class ResponseScanResult:
    injection: ScanResult
    pii: PIIResult
    blocked: bool = False


async def scan_response(content: str) -> ResponseScanResult:
    """Scan LLM response content for PII and injection patterns.

    Injection in responses is always advisory (log-only).
    PII blocking depends on response_pii_action setting.
    """
    injection_result = await scan_prompt(content)
    pii_result = await scan_for_pii(content)

    settings = get_settings()
    blocked = (
        settings.response_pii_action == "block"
        and not pii_result.clean
        and pii_result.detection_count > 0
    )

    return ResponseScanResult(
        injection=injection_result,
        pii=pii_result,
        blocked=blocked,
    )
