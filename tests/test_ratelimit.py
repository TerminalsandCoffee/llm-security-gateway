"""Tests for src/security/ratelimit.py — sliding window rate limiter."""

from unittest.mock import patch

import pytest

from src.security.ratelimit import check_rate_limit, reset_client, _client_windows


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Clear all rate limit state between tests."""
    _client_windows.clear()
    yield
    _client_windows.clear()


class TestCheckRateLimit:

    async def test_first_request_allowed(self):
        result = await check_rate_limit("client-1", limit=5)
        assert result.allowed is True
        assert result.remaining == 4
        assert result.limit == 5

    async def test_remaining_decrements(self):
        for i in range(3):
            result = await check_rate_limit("client-1", limit=5)
        assert result.allowed is True
        assert result.remaining == 2

    async def test_limit_exceeded(self):
        for _ in range(5):
            await check_rate_limit("client-1", limit=5)
        result = await check_rate_limit("client-1", limit=5)
        assert result.allowed is False
        assert result.remaining == 0
        assert result.reset_seconds > 0

    async def test_different_clients_independent(self):
        for _ in range(5):
            await check_rate_limit("client-a", limit=5)
        # client-a is exhausted
        result_a = await check_rate_limit("client-a", limit=5)
        assert result_a.allowed is False
        # client-b should be fine
        result_b = await check_rate_limit("client-b", limit=5)
        assert result_b.allowed is True

    async def test_window_expiry(self):
        """After window expires, requests should be allowed again."""
        # Fill up the limit
        with patch("src.security.ratelimit.time.monotonic", return_value=1000.0):
            for _ in range(5):
                await check_rate_limit("client-1", limit=5)
            result = await check_rate_limit("client-1", limit=5)
            assert result.allowed is False

        # Jump forward past the 60s window
        with patch("src.security.ratelimit.time.monotonic", return_value=1061.0):
            result = await check_rate_limit("client-1", limit=5)
            assert result.allowed is True
            assert result.remaining == 4


class TestResetClient:

    async def test_reset_clears_state(self):
        for _ in range(3):
            await check_rate_limit("client-1", limit=5)
        reset_client("client-1")
        result = await check_rate_limit("client-1", limit=5)
        assert result.allowed is True
        assert result.remaining == 4

    async def test_reset_nonexistent_client(self):
        """Resetting unknown client should not raise."""
        reset_client("nonexistent")
