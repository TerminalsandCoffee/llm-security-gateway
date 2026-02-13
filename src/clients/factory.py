"""Factory for client store backends."""

from src.clients.store import ClientStore, JSONClientStore
from src.config.settings import get_settings

_store: ClientStore | None = None


def get_client_store() -> ClientStore | None:
    """Get the client store singleton. Returns None if no store configured."""
    global _store
    if _store is not None:
        return _store

    settings = get_settings()
    backend = settings.client_store_backend

    if backend == "json":
        path = settings.client_config_path
        if path and _file_exists(path):
            _store = JSONClientStore(path)
            return _store
        return None  # no config file = legacy mode

    if backend == "dynamodb":
        # Lazy import to avoid boto3 dependency when not needed
        from src.clients.dynamodb_store import DynamoDBClientStore
        _store = DynamoDBClientStore(
            table_name=settings.dynamodb_table_name,
            region=settings.aws_region,
        )
        return _store

    return None


def _file_exists(path: str) -> bool:
    """Check if a file exists (avoids import os at module level for testability)."""
    import os
    return os.path.isfile(path)
