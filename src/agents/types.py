from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


ProviderName = Literal["codex", "gemini-cli"]
AgentResultStatus = Literal["success", "failure", "error"]
AgentEventType = Literal["done", "token", "request", "item"]
OutputSchema = dict[str, Any]


@dataclass(slots=True)
class AgentParams:
    provider: ProviderName
    workdir: str | None = None
    role: str | None = None
    output_schema: OutputSchema | None = None
    mcp: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    model: str | None = None
    timeout_s: int | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentResult:
    status: AgentResultStatus
    output: OutputSchema | None = None
    error_message: str | None = None


class DoneEvent(TypedDict):
    event_type: Literal["done"]
    provider: ProviderName
    result: AgentResult


class TokenEvent(TypedDict):
    event_type: Literal["token"]
    provider: ProviderName
    usage: dict[str, Any]


class RequestEvent(TypedDict):
    event_type: Literal["request"]
    provider: ProviderName
    request: dict[str, Any]


class ItemEvent(TypedDict):
    event_type: Literal["item"]
    provider: ProviderName
    item: dict[str, Any]


AgentEvent = DoneEvent | TokenEvent | RequestEvent | ItemEvent
