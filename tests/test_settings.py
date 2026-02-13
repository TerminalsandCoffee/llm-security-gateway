"""Tests for src/config/settings.py — Settings and api_keys_list."""

from src.config.settings import Settings, get_settings


class TestSettings:

    def test_defaults(self, override_settings):
        override_settings()
        s = get_settings()
        assert s.injection_threshold == 0.7
        assert s.pii_action == "redact"
        assert s.rate_limit_rpm == 60
        assert s.client_store_backend == "json"
        assert s.log_level == "INFO"

    def test_api_keys_list_single(self, override_settings):
        override_settings(GATEWAY_API_KEYS="my-key")
        s = get_settings()
        assert s.api_keys_list == ["my-key"]

    def test_api_keys_list_multiple(self, override_settings):
        override_settings(GATEWAY_API_KEYS="key1, key2 , key3")
        s = get_settings()
        assert s.api_keys_list == ["key1", "key2", "key3"]

    def test_api_keys_list_strips_empty(self, override_settings):
        override_settings(GATEWAY_API_KEYS="k1,,k2,")
        s = get_settings()
        assert s.api_keys_list == ["k1", "k2"]

    def test_env_override(self, override_settings):
        override_settings(
            INJECTION_THRESHOLD="0.5",
            PII_ACTION="block",
            RATE_LIMIT_RPM="120",
        )
        s = get_settings()
        assert s.injection_threshold == 0.5
        assert s.pii_action == "block"
        assert s.rate_limit_rpm == 120
