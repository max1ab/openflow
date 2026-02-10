from __future__ import annotations

from collections.abc import AsyncIterator

from .base import BaseProviderAdapter
from .errors import AgentConfigError
from .providers.codex_adapter import CodexAdapter
from .providers.gemini_cli_adapter import GeminiCliAdapter
from .types import AgentEvent, AgentParams, OutputSchema, ProviderName


class Agent:
    """Unified wrapper for different provider CLIs."""

    def __init__(
        self,
        provider: ProviderName,
        *,
        workdir: str | None = None,
        role: str | None = None,
        system: str | None = None,
        output_schema: OutputSchema | None = None,
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
            output_schema=output_schema,
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
        if self.params.output_schema is not None and not isinstance(self.params.output_schema, dict):
            raise AgentConfigError("output_schema must be a dict when provided.")

    def _build_adapter(self) -> BaseProviderAdapter:
        if self.params.provider == "codex":
            return CodexAdapter(self.params)
        if self.params.provider == "gemini-cli":
            return GeminiCliAdapter(self.params)
        raise AgentConfigError(f"Unsupported provider: {self.params.provider}")

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Stream normalized events from underlying provider adapter."""
        if not prompt.strip():
            raise AgentConfigError("prompt must not be empty.")
        method = self._adapter.start if not self._started else self._adapter.replay
        self._started = True
        async for event in method(prompt):
            yield event

    def reset(self) -> None:
        self._started = False


