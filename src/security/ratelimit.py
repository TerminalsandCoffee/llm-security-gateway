"""Rate limiting module using in-memory sliding window counters.

Enforces per-client request limits keyed by client_id. Uses a sliding
window algorithm: timestamps of recent requests are stored in a deque,
and expired entries are pruned on each check.

Returns standard rate limit metadata for response headers:
- X-RateLimit-Limit
- X-RateLimit-Remaining
- X-RateLimit-Reset
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass

# Per-client request timestamp deques
# Key: client_id, Value: deque of request timestamps
_client_windows: dict[str, deque[float]] = defaultdict(deque)

WINDOW_SECONDS = 60.0  # 1-minute sliding window


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: float


async def check_rate_limit(client_id: str, limit: int) -> RateLimitResult:
    """Check if the client has exceeded their rate limit.

    Args:
        client_id: Unique client identifier (not raw API key).
        limit: Max requests per minute for this client.
    """
    now = time.monotonic()
    window_start = now - WINDOW_SECONDS

    window = _client_windows[client_id]

    # Prune expired timestamps from the left
    while window and window[0] < window_start:
        window.popleft()

    if len(window) >= limit:
        # Calculate when the oldest request in the window expires
        reset = window[0] + WINDOW_SECONDS - now
        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            reset_seconds=round(reset, 1),
        )

    # Record this request
    window.append(now)
    remaining = max(0, limit - len(window))

    # Reset = time until the oldest entry in window expires
    reset = window[0] + WINDOW_SECONDS - now if window else WINDOW_SECONDS

    return RateLimitResult(
        allowed=True,
        limit=limit,
        remaining=remaining,
        reset_seconds=round(reset, 1),
    )


def reset_client(client_key: str) -> None:
    """Clear rate limit state for a client. Useful for testing."""
    _client_windows.pop(client_key, None)
