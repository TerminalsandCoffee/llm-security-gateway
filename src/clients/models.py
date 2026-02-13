"""Client configuration model."""

from dataclasses import dataclass, field


@dataclass
class ClientConfig:
    client_id: str
    api_key: str
    provider: str = "openai"  # "openai" | "bedrock"
    rate_limit_rpm: int = 60
    model_allowlist: list[str] = field(default_factory=list)  # empty = all allowed
    upstream_api_key: str = ""  # per-client upstream key (falls back to global)
    bedrock_model_id: str = ""  # e.g. "anthropic.claude-3-sonnet-20240229-v1:0"
    status: str = "active"  # "active" | "suspended"
