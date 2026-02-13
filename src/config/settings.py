"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gateway authentication
    # Comma-separated list of valid API keys for clients
    # TODO: per-client key tracking with usage metrics
    gateway_api_keys: str = "dev-key-1"

    # Upstream LLM provider
    upstream_base_url: str = "https://api.openai.com"
    upstream_api_key: str = ""

    # Security pipeline
    injection_threshold: float = 0.7  # Risk score at which to block (0.0-1.0)
    pii_action: str = "redact"  # redact | block | log_only
    response_pii_action: str = "log_only"  # redact | block | log_only
    rate_limit_rpm: int = 60  # Requests per minute per client

    # Client store
    client_store_backend: str = "json"  # "json" | "dynamodb"
    client_config_path: str = "clients.json"  # path to JSON client config
    dynamodb_table_name: str = "llm-gateway-clients"
    aws_region: str = "us-east-1"

    # Logging
    log_level: str = "INFO"
    audit_log_file: str = ""  # Empty = stdout only

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def api_keys_list(self) -> list[str]:
        """Parse comma-separated API keys into a set for O(1) lookup."""
        return [k.strip() for k in self.gateway_api_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
