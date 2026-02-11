from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
import asyncio
from typing import Awaitable, Callable

from .base import BaseProviderAdapter
from .errors import AgentConfigError
from .providers.codex_adapter import CodexAdapter
from .providers.gemini_adapter import GeminiCliAdapter
from .types import AgentEvent, AgentParams, AgentResult, OutputSchema, ProviderName

EventCallback = Callable[[AgentEvent], None | Awaitable[None]]


class Agent:
    """Unified wrapper for different provider CLIs."""

    def __init__(
        self,
        provider: ProviderName,
        *,
        workdir: str | None = None,
        role: str | None = None,
        system: str | None = None,
        default_output_schema: OutputSchema | None = None,
        mcp: list[str] | None = None,
        env: dict[str, str] | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        self.params = AgentParams(
            provider=provider,
            workdir=workdir,
            role=role,
            system=system,
            default_output_schema=default_output_schema,
            mcp=mcp or [],
            env=env or {},
            model=model,
            timeout_s=timeout_s,
            extra_args=extra_args or [],
        )
        self._validate_params()
        self._adapter: BaseProviderAdapter = self._build_adapter()
        self._started = False

    def _validate_params(self) -> None:
        """Validate constructor parameters for the current MVP skeleton."""
        if self.params.provider not in ("codex", "gemini-cli"):
            raise AgentConfigError(f"Unsupported provider: {self.params.provider}")
        if self.params.default_output_schema is not None and not isinstance(self.params.default_output_schema, dict):
            raise AgentConfigError("default_output_schema must be a dict when provided.")

    def _build_adapter(self) -> BaseProviderAdapter:
        if self.params.provider == "codex":
            return CodexAdapter(self.params)
        if self.params.provider == "gemini-cli":
            return GeminiCliAdapter(self.params)
        raise AgentConfigError(f"Unsupported provider: {self.params.provider}")

    async def stream(self, prompt: str, *, output_schema: OutputSchema | None = None) -> AsyncIterator[AgentEvent]:
        """Stream normalized events from underlying provider adapter."""
        if not prompt.strip():
            raise AgentConfigError("prompt must not be empty.")
        if output_schema is not None and not isinstance(output_schema, dict):
            raise AgentConfigError("output_schema must be a dict when provided.")
        method = self._adapter.start if not self._started else self._adapter.replay
        self._started = True
        async for event in method(prompt, output_schema=output_schema):
            yield event

    async def run(
        self,
        prompt: str,
        *,
        on_event: EventCallback | None = None,
        output_schema: OutputSchema | None = None,
    ) -> AgentResult:
        final_result: AgentResult | None = None
        async for event in self.stream(prompt, output_schema=output_schema):
            if event["event_type"] == "done":
                final_result = event["result"]
                break

            if on_event is not None:
                maybe_awaitable = on_event(event)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

        if final_result is None:
            return AgentResult(status="error", error="missing done event")
        return final_result

    def reset(self) -> None:
        self._started = False

async def main():
    agent = Agent(provider="codex")
    result = await agent.run("记住a=1928")
    print(result.data if result.data is not None else result.message)
    result = await agent.run("那么a+73等于多少")
    print(result.data if result.data is not None else result.message)
    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
