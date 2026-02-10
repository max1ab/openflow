from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .types import AgentEvent, AgentParams


class BaseProviderAdapter(ABC):
    """Abstract provider adapter interface."""

    def __init__(self, params: AgentParams) -> None:
        self.params = params

    @abstractmethod
    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[AgentEvent]:
        """Stream normalized events from provider output."""
