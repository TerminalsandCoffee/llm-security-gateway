"""Tests for src/clients/models.py — ClientConfig dataclass."""

from src.clients.models import ClientConfig


class TestClientConfig:

    def test_defaults(self):
        c = ClientConfig(client_id="c1", api_key="k1")
        assert c.provider == "openai"
        assert c.rate_limit_rpm == 60
        assert c.model_allowlist == []
        assert c.upstream_api_key == ""
        assert c.bedrock_model_id == ""
        assert c.status == "active"

    def test_custom_fields(self):
        c = ClientConfig(
            client_id="c2",
            api_key="k2",
            provider="bedrock",
            rate_limit_rpm=100,
            model_allowlist=["gpt-4o"],
            upstream_api_key="sk-up",
            bedrock_model_id="anthropic.claude-3",
            status="suspended",
        )
        assert c.provider == "bedrock"
        assert c.rate_limit_rpm == 100
        assert c.model_allowlist == ["gpt-4o"]
        assert c.status == "suspended"

    def test_independent_allowlist_instances(self):
        """Each instance gets its own list (field default_factory)."""
        a = ClientConfig(client_id="a", api_key="a")
        b = ClientConfig(client_id="b", api_key="b")
        a.model_allowlist.append("gpt-4o")
        assert b.model_allowlist == []

    def test_equality(self):
        """Dataclass equality is field-by-field."""
        a = ClientConfig(client_id="x", api_key="y")
        b = ClientConfig(client_id="x", api_key="y")
        assert a == b
