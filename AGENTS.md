# Openflow Agent Guidelines

This file defines repository-wide rules for AI/code agents to keep changes consistent.

## Scope

- Apply to the whole repository unless a user request explicitly overrides a rule.
- Prefer minimal, targeted changes over broad refactors.

## Project Structure

- `src/agents`: provider-agnostic agent system (`codex`, `gemini-cli`)
- `src/interface`: external interface layer (current: Feishu)
- `src/scheduler`: JSON-driven scheduler and job execution
- `examples/`: runnable flows and scheduler config examples

## Python Conventions

- Follow existing style in nearby files; keep type hints where already used.
- Keep modules focused: avoid mixing scheduler logic into agent/interface modules.
- Avoid adding new dependencies unless necessary; use stdlib first.
- Use ASCII by default for code/comments unless file already requires non-ASCII text.

## Agent System Rules (`src/agents`)

- Keep provider interface normalized through `AgentEvent` and `AgentResult`.
- Validate inputs at boundaries (constructor and public methods).
- Do not couple provider adapters to scheduler or interface-specific logic.
- Preserve compatibility of event types: `done`, `token`, `request`, `message`.

## Interface Rules (`src/interface`)

- Normalize inbound payloads before handing to business logic.
- Fail fast on missing credentials/config.
- Keep transport/API details in interface modules, not in scheduler/agent core.

## Scheduler Rules (`src/scheduler`)

- Scheduler decides *when* to run; scripts decide *what* to do.
- Keep path resolution relative to config directory for predictable behavior.
- Job failures must not crash scheduler process.
- Honor per-job failure policy fields (`retry`, `retry_delay_s`, `max_failures`, `disable_on_failure`).
- If `log_to_file=true`, do not print script `stdout/stderr` to terminal.

## Logging and Errors

- Use structured, readable logs with job id and attempt context.
- Do not swallow exceptions silently; log with context.
- Treat non-zero process exit codes as failed job attempts.

## Documentation and Examples

- Update `README.md` for any user-visible behavior/config changes.
- Keep `examples/scheduler_jobs.json` aligned with supported fields and defaults.
- Prefer examples that run from repository root with `uv run python ...`.

## Safety

- Do not modify unrelated files.
- Do not commit secrets or env files.
- Do not introduce destructive git operations.
