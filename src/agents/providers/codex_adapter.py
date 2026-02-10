from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ..base import BaseProviderAdapter
from ..types import AgentEvent, AgentParams, AgentResult


class CodexAdapter(BaseProviderAdapter):
    def __init__(self, params: AgentParams) -> None:
        super().__init__(params)
        self._session_id: str | None = None

    async def start(self, prompt: str) -> AsyncIterator[AgentEvent]:
        self._session_id = None
        first_event = True
        async for event in self._run_exec(
            command=self._build_start_command(prompt=prompt),
            allow_output_schema=True,
        ):
            if first_event:
                first_event = False
                thread_id = self._extract_thread_id(event)
                if thread_id is not None:
                    self._session_id = thread_id
            yield event

    async def replay(self, prompt: str) -> AsyncIterator[AgentEvent]:
        if not self._session_id:
            result = AgentResult(
                status="error",
                error_message="replay called before start: missing codex session id",
            )
            yield {"event_type": "done", "provider": "codex", "result": result}
            return

        async for event in self._run_exec(
            command=self._build_replay_command(prompt=prompt, session_id=self._session_id),
            allow_output_schema=False,
        ):
            yield event

    async def _run_exec(
        self,
        *,
        command: list[str],
        allow_output_schema: bool,
    ) -> AsyncIterator[AgentEvent]:
        schema_path: str | None = None
        output_path: str | None = None
        final_text: str | None = None
        final_error: str | None = None
        saw_done = False

        with tempfile.TemporaryDirectory(prefix="openflow-codex-") as tmp_dir:
            if allow_output_schema and self.params.output_schema is not None:
                schema_path = str(Path(tmp_dir) / "output_schema.json")
                Path(schema_path).write_text(
                    json.dumps(self.params.output_schema, ensure_ascii=True, indent=2),
                    encoding="utf-8",
                )
                output_path = str(Path(tmp_dir) / "final_output.json")
                # Prompt is the last positional arg, so insert flags before it.
                command[-1:-1] = ["--output-schema", schema_path, "--output-last-message", output_path]
            env = self._build_env()

            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=self.params.workdir,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except Exception as exc:
                result = AgentResult(status="error", error_message=f"failed to start codex: {exc}")
                yield {"event_type": "done", "provider": "codex", "result": result}
                return

            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            stdout_task = asyncio.create_task(self._pump_stdout(process, queue))
            stderr_task = asyncio.create_task(self._pump_stderr(process, queue))
            started_at = time.monotonic()
            timed_out = False

            while not (stdout_task.done() and stderr_task.done() and queue.empty()):
                if (
                    self.params.timeout_s is not None
                    and process.returncode is None
                    and time.monotonic() - started_at > self.params.timeout_s
                ):
                    process.kill()
                    timed_out = True
                    final_error = f"codex execution timed out after {self.params.timeout_s}s"

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                if event["event_type"] == "done":
                    saw_done = True
                if event["event_type"] == "message":
                    message = event.get("message", {})
                    if isinstance(message, dict):
                        maybe_text = message.get("text")
                        if isinstance(maybe_text, str):
                            final_text = maybe_text
                yield event

            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            return_code = await process.wait()
            if timed_out and return_code == 0:
                return_code = 124

            if output_path is not None and Path(output_path).exists():
                raw_output = Path(output_path).read_text(encoding="utf-8").strip()
                if raw_output:
                    final_text = raw_output

            if not saw_done:
                if return_code == 0:
                    parsed_output = self._parse_final_output(final_text)
                    result = AgentResult(status="success", output=parsed_output)
                elif final_error:
                    result = AgentResult(status="error", error_message=final_error)
                else:
                    result = AgentResult(status="failure", error_message=f"codex exited with code {return_code}")
                yield {"event_type": "done", "provider": "codex", "result": result}

    def _build_start_command(self, *, prompt: str) -> list[str]:
        command: list[str] = ["codex", "exec", "--json"]
        if self.params.model:
            command.extend(["--model", self.params.model])

        command.extend(self.params.extra_args)
        command.append(self._build_prompt(prompt=prompt))
        return command

    def _build_replay_command(self, *, prompt: str, session_id: str) -> list[str]:
        command: list[str] = ["codex", "exec", "--json", "resume", session_id]
        if self.params.model:
            command.extend(["--model", self.params.model])

        command.extend(self.params.extra_args)
        command.append(self._build_prompt(prompt=prompt))
        return command

    def _build_prompt(self, *, prompt: str) -> str:
        parts: list[str] = []
        if self.params.role:
            parts.append(f"Role:\n{self.params.role}")
        if self.params.system:
            parts.append(f"System:\n{self.params.system}")
        parts.append(prompt)
        return "\n\n".join(parts)

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(self.params.env)
        return env

    async def _pump_stdout(
        self,
        process: asyncio.subprocess.Process,
        queue: asyncio.Queue[AgentEvent],
    ) -> None:
        if process.stdout is None:
            return
        while True:
            line = await process.stdout.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            for event in self._parse_stdout_line(text=text):
                await queue.put(event)

    async def _pump_stderr(
        self,
        process: asyncio.subprocess.Process,
        queue: asyncio.Queue[AgentEvent],
    ) -> None:
        if process.stderr is None:
            return
        while True:
            line = await process.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            await queue.put(
                {"event_type": "message", "provider": "codex", "message": {"stream": "stderr", "text": text}}
            )

    def _parse_stdout_line(self, *, text: str) -> list[AgentEvent]:
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return [{"event_type": "message", "provider": "codex", "message": {"stream": "stdout", "text": text}}]

        events: list[AgentEvent] = []
        event_type = payload.get("type")

        if event_type == "turn.completed":
            usage = payload.get("usage")
            if isinstance(usage, dict):
                events.append({"event_type": "token", "provider": "codex", "usage": usage})
            return events

        if event_type == "turn.failed":
            message = payload.get("error") or payload.get("message") or "codex turn failed"
            result = AgentResult(status="failure", error_message=str(message))
            events.append({"event_type": "done", "provider": "codex", "result": result})
            return events

        if event_type == "error":
            message = payload.get("message") or "codex error"
            result = AgentResult(status="error", error_message=str(message))
            events.append({"event_type": "done", "provider": "codex", "result": result})
            return events

        if event_type in {"item.started", "item.completed", "item.failed"}:
            item = payload.get("item")
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "approval_request":
                    events.append({"event_type": "request", "provider": "codex", "request": item})
                else:
                    events.append({"event_type": "message", "provider": "codex", "message": item})
                return events

        events.append({"event_type": "message", "provider": "codex", "message": payload})
        return events

    def _parse_final_output(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            return {"text": value}

    def _extract_thread_id(self, event: AgentEvent) -> str | None:
        if event["event_type"] != "message":
            return None
        message = event.get("message")
        if not isinstance(message, dict):
            return None
        if message.get("type") != "thread.started":
            return None
        thread_id = message.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            return thread_id
        return None
