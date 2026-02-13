"""Client store abstraction + JSON file implementation."""

import hmac
import json
import os
from abc import ABC, abstractmethod

from src.clients.models import ClientConfig


class ClientStore(ABC):
    """Abstract base for client config lookups."""

    @abstractmethod
    async def get_by_api_key(self, api_key: str) -> ClientConfig | None:
        """Look up a client by API key. Returns None if not found."""
        ...


class JSONClientStore(ClientStore):
    """File-backed client store. Reloads on mtime change."""

    def __init__(self, path: str):
        self._path = path
        self._clients: list[ClientConfig] = []
        self._last_mtime: float = 0.0
        self._load()

    def _load(self) -> None:
        """Load clients from JSON file."""
        try:
            mtime = os.path.getmtime(self._path)
        except OSError:
            self._clients = []
            return

        if mtime == self._last_mtime and self._clients:
            return

        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)

        self._clients = [
            ClientConfig(**entry) for entry in data.get("clients", [])
        ]
        self._last_mtime = mtime

    async def get_by_api_key(self, api_key: str) -> ClientConfig | None:
        """Constant-time key lookup across all clients."""
        self._load()  # reload if file changed

        match: ClientConfig | None = None
        for client in self._clients:
            # Always iterate all keys to maintain constant-time behavior
            if hmac.compare_digest(api_key, client.api_key):
                match = client

        return match
