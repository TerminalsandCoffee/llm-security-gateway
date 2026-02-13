"""Prompt injection detection module.

Uses pattern-based scoring to detect injection attempts in LLM prompts.
Each matched pattern contributes to a cumulative risk score. If the
score exceeds the configured threshold, the request is blocked.

Detection categories:
- Instruction override: "ignore previous instructions", "disregard above"
- Role manipulation: "you are now DAN", "act as an unrestricted AI"
- Delimiter injection: attempts to close/reopen system prompts
- Context manipulation: "respond without restrictions"
"""

import re
from dataclasses import dataclass

from src.config.settings import get_settings

# Each pattern: (compiled regex, weight, category label)
# Weights reflect severity — higher = more suspicious
_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    # --- Instruction override ---
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)", re.I), 0.5, "instruction_override"),
    (re.compile(r"disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions|prompts|rules|programming)", re.I), 0.5, "instruction_override"),
    (re.compile(r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions|rules|context|programming)", re.I), 0.5, "instruction_override"),
    (re.compile(r"do\s+not\s+follow\s+(your|any|the)\s+(previous|prior|original)\s+(instructions|rules)", re.I), 0.5, "instruction_override"),
    (re.compile(r"override\s+(your|all|the)\s+(instructions|rules|guidelines|programming)", re.I), 0.4, "instruction_override"),
    (re.compile(r"new\s+instructions?\s*:", re.I), 0.3, "instruction_override"),

    # --- Role manipulation ---
    (re.compile(r"you\s+are\s+now\s+", re.I), 0.4, "role_manipulation"),
    (re.compile(r"act\s+as\s+(an?\s+)?(unrestricted|unfiltered|uncensored|evil)", re.I), 0.5, "role_manipulation"),
    (re.compile(r"pretend\s+(you'?re?|to\s+be)\s+(an?\s+)?(unrestricted|unfiltered|different\s+ai)", re.I), 0.5, "role_manipulation"),
    (re.compile(r"\bDAN\s*(mode)?\b", re.I), 0.6, "role_manipulation"),
    (re.compile(r"jailbreak", re.I), 0.7, "role_manipulation"),
    (re.compile(r"developer\s+mode\s+(enabled|on|activated)", re.I), 0.5, "role_manipulation"),

    # --- Delimiter injection ---
    (re.compile(r"<\|?(system|im_start|im_end|endoftext)\|?>", re.I), 0.6, "delimiter_injection"),
    (re.compile(r"\[SYSTEM\]", re.I), 0.4, "delimiter_injection"),
    (re.compile(r"#{3,}\s*(system|instruction|prompt)", re.I), 0.3, "delimiter_injection"),
    (re.compile(r"```\s*(system|instruction)", re.I), 0.3, "delimiter_injection"),

    # --- Context manipulation ---
    (re.compile(r"(respond|answer|reply)\s+(without|with\s+no)\s+(restrictions|limits|filters|guidelines)", re.I), 0.5, "context_manipulation"),
    (re.compile(r"no\s+(ethical|moral|safety)\s+(guidelines|restrictions|filters|limits)", re.I), 0.5, "context_manipulation"),
    (re.compile(r"bypass\s+(your|all|the|any)\s+(restrictions|filters|safety|guidelines)", re.I), 0.6, "context_manipulation"),
    (re.compile(r"enable\s+(unrestricted|unfiltered|uncensored)\s+mode", re.I), 0.5, "context_manipulation"),
]


@dataclass
class ScanResult:
    allowed: bool
    risk_score: float  # 0.0 (safe) to 1.0+ (blocked)
    reason: str
    matched_categories: list[str]


async def scan_prompt(content: str) -> ScanResult:
    """Scan prompt content for injection attempts.

    Runs all patterns against the content and accumulates a risk score.
    Blocks if score >= configured threshold.
    """
    if not content.strip():
        return ScanResult(allowed=True, risk_score=0.0, reason="empty", matched_categories=[])

    settings = get_settings()
    total_score = 0.0
    matched = []

    for pattern, weight, category in _PATTERNS:
        hits = pattern.findall(content)
        if hits:
            total_score += weight * len(hits)
            if category not in matched:
                matched.append(category)

    # Cap at 1.0 for clean reporting, but actual can exceed
    display_score = round(min(total_score, 1.0), 2)

    if total_score >= settings.injection_threshold:
        return ScanResult(
            allowed=False,
            risk_score=display_score,
            reason=f"Injection detected: {', '.join(matched)}",
            matched_categories=matched,
        )

    return ScanResult(
        allowed=True,
        risk_score=display_score,
        reason="pass" if not matched else f"Low-risk patterns: {', '.join(matched)}",
        matched_categories=matched,
    )
