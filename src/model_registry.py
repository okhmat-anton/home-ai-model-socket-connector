"""Registry of connected models (via Socket.IO)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class ConnectedModel:
    name: str
    sid: str  # Socket.IO session id
    connected_at: float = 0.0


class ModelRegistry:
    """Thread-safe registry that maps model names to Socket.IO sessions."""

    def __init__(self) -> None:
        self._models: dict[str, ConnectedModel] = {}
        self._lock = asyncio.Lock()

    async def register(self, name: str, sid: str, connected_at: float) -> None:
        async with self._lock:
            self._models[name] = ConnectedModel(name=name, sid=sid, connected_at=connected_at)

    async def unregister_by_sid(self, sid: str) -> str | None:
        """Remove model by sid. Returns model name or None."""
        async with self._lock:
            for name, m in list(self._models.items()):
                if m.sid == sid:
                    del self._models[name]
                    return name
        return None

    async def get(self, name: str) -> ConnectedModel | None:
        async with self._lock:
            return self._models.get(name)

    async def get_sid(self, name: str) -> str | None:
        m = await self.get(name)
        return m.sid if m else None

    async def list_names(self) -> list[str]:
        async with self._lock:
            return list(self._models.keys())

    async def is_connected(self, name: str) -> bool:
        async with self._lock:
            return name in self._models


registry = ModelRegistry()
