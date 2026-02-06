from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
from typing import Any, Dict, Optional


class Codex:
    """Thin stdio wrapper for the Codex MCP server tool calls."""

    def __init__(
        self,
        cmd: str | list[str] | None = None,
        *,
        cwd: str | None = None,
        protocol_version: str = "2024-11-05",
        codex_params: Optional[Dict[str, Any]] = None,
        env: Optional[Dict[str, str]] = None,
        approval_policy: Optional[str] = None,
        base_instructions: Optional[str] = None,
        compact_prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        tool_cwd: Optional[str] = None,
        developer_instructions: Optional[str] = None,
        model: Optional[str] = None,
        profile: Optional[str] = None,
        sandbox: Optional[str] = None,
    ) -> None:
        """
        Args:
            cmd: Server command for stdio (string or argv list). Defaults to
                CODEX_MCP_CMD or "codex mcp-server".
            cwd: Working directory for the server process.
            protocol_version: MCP protocol version string.
            codex_params: Default parameters to pass to the initial codex tool call.
            env: Extra environment variables for the server process.
            approval_policy: Codex tool approval policy (e.g. on-request).
            base_instructions: Replace default system/base instructions.
            compact_prompt: Prompt used for conversation compaction.
            config: Overrides for CODEX_HOME/config.toml.
            tool_cwd: Working directory passed to the codex tool (not process cwd).
            developer_instructions: Developer-role instructions injected into the run.
            model: Override model name (e.g. gpt-5.2-codex).
            profile: Config profile name from config.toml.
            sandbox: Sandbox mode for the Codex session.
        """
        # Merge custom env on top of the current process environment.
        proc_env = None
        if env is not None:
            proc_env = os.environ.copy()
            proc_env.update(env)
        self._cmd = self._normalize_cmd(cmd)
        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=proc_env,
        )
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("Failed to open stdio pipes for codex mcp-server")

        self._lock = threading.Lock()
        self._next_id = 1
        self.thread_id: Optional[str] = None
        # Base parameters for the initial codex tool call; can be overridden at runtime.
        params: Dict[str, Any] = dict(codex_params or {})
        explicit = {
            "approval-policy": approval_policy,
            "base-instructions": base_instructions,
            "compact-prompt": compact_prompt,
            "config": config,
            "cwd": tool_cwd,
            "developer-instructions": developer_instructions,
            "model": model,
            "profile": profile,
            "sandbox": sandbox,
        }
        for key, value in explicit.items():
            if value is not None:
                params[key] = value
        self._codex_params = self._normalize_tool_args(params)

        self._initialize(protocol_version)

    def _normalize_cmd(self, cmd: str | list[str] | None) -> list[str]:
        if cmd is None:
            env_cmd = os.environ.get("CODEX_MCP_CMD")
            cmd = env_cmd or "codex mcp-server"
        if isinstance(cmd, str):
            return shlex.split(cmd)
        return cmd

    def _send(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
            if params is not None:
                msg["params"] = params
            self._send(msg)

            # Read until we get the matching response id.
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("codex mcp-server closed the stream")
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if resp.get("id") != req_id:
                    continue
                if "error" in resp:
                    raise RuntimeError(resp["error"])
                return resp.get("result")

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _initialize(self, protocol_version: str) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "clientInfo": {"name": "codex-wrapper", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )
        self._notify("initialized", {})

    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def _call_codex(self, **kwargs: Any) -> Any:
        return self._call_tool("codex", kwargs)

    def _call_codex_reply(self, **kwargs: Any) -> Any:
        return self._call_tool("codex-reply", kwargs)

    def start(self, prompt: str, **kwargs: Any) -> Any:
        # Merge instance defaults with per-call overrides.
        runtime = self._normalize_tool_args(kwargs)
        merged = {**self._codex_params, **runtime, "prompt": prompt}
        result = self._call_codex(**merged)
        self.thread_id = self._extract_thread_id(result) or self.thread_id
        return result

    def reply(self, prompt: str, thread_id: Optional[str] = None, **kwargs: Any) -> Any:
        tid = thread_id or self.thread_id
        if not tid:
            raise ValueError("thread_id is required for codex-reply")
        # codex-reply only needs the thread id and new prompt.
        result = self._call_codex_reply(threadId=tid, prompt=prompt, **kwargs)
        self.thread_id = self._extract_thread_id(result) or tid
        return result

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()

    def __enter__(self) -> "Codex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _extract_thread_id(result: Any) -> Optional[str]:
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                for key in ("threadId", "thread_id", "conversationId", "conversation_id"):
                    value = structured.get(key)
                    if isinstance(value, str):
                        return value
            for key in ("threadId", "thread_id", "conversationId", "conversation_id"):
                if key in result and isinstance(result[key], str):
                    return result[key]
            nested = result.get("result") if isinstance(result, dict) else None
            if isinstance(nested, dict):
                for key in ("threadId", "thread_id", "conversationId", "conversation_id"):
                    if key in nested and isinstance(nested[key], str):
                        return nested[key]
        return None

    @staticmethod
    def _normalize_tool_args(params: Dict[str, Any]) -> Dict[str, Any]:
        if not params:
            return {}
        mapping = {
            "approval_policy": "approval-policy",
            "base_instructions": "base-instructions",
            "compact_prompt": "compact-prompt",
            "developer_instructions": "developer-instructions",
        }
        normalized: Dict[str, Any] = {}
        for key, value in params.items():
            if "-" in key:
                normalized[key] = value
                continue
            normalized[mapping.get(key, key)] = value
        return normalized
