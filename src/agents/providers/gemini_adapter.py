from __future__ import annotations

from collections.abc import AsyncIterator

from ..base import BaseProviderAdapter
from ..types import AgentEvent, OutputSchema


class GeminiCliAdapter(BaseProviderAdapter):
    async def start(self, prompt: str, output_schema: OutputSchema | None = None) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError("GeminiCliAdapter start is not implemented yet.")
        yield  # pragma: no cover

    async def replay(self, prompt: str, output_schema: OutputSchema | None = None) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError("GeminiCliAdapter replay is not implemented yet.")
        yield  # pragma: no cover
