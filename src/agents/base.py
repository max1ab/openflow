from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .types import AgentEvent, AgentParams, OutputSchema


class BaseProviderAdapter(ABC):
    """Abstract provider adapter interface."""

    def __init__(self, params: AgentParams) -> None:
        self.params = params

    @abstractmethod
    async def start(self, prompt: str, output_schema: OutputSchema | None = None) -> AsyncIterator[AgentEvent]:
        """Start a new conversation and stream events."""

    @abstractmethod
    async def replay(self, prompt: str, output_schema: OutputSchema | None = None) -> AsyncIterator[AgentEvent]:
        """Continue an existing conversation and stream events."""
