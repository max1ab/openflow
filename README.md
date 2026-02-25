## Openflow

Openflow currently contains three parts:

- `Agent System`: unified wrapper for provider CLIs (`codex`, `gemini-cli`)
- `Interface`: external messaging integration (current implementation: Feishu)
- `JSON Scheduler`: time-based task runner that executes Python scripts

## Install

```bash
uv sync
```

## 1) Agent System

Core module: `src/agents`.

### What it provides

- Unified `Agent` API for different providers
- Async `stream()` and `run()` execution modes
- Structured output support via JSON schema (`default_output_schema` or per-run `output_schema`)
- Event callback hook (`on_event`) for token/message/request events

### Key types

- Provider: `codex` / `gemini-cli`
- Event types: `done` / `token` / `request` / `message`
- Result status: `success` / `failure` / `error`

### Minimal example

```python
import asyncio
from src.agents.agent import Agent

async def main():
    agent = Agent(provider="codex", role="assistant")
    result = await agent.run("Give me a short summary.")
    print(result.status, result.message, result.data)

asyncio.run(main())
```

## 2) Interface

Core module: `src/interface`.

Current interface implementation is Feishu:

- `FeishuConfig`: loads credentials from env
- `FeishuInterface`: receive messages from websocket events and send/reply text messages
- `InboundMessage`: normalized inbound message structure

### Required env vars (Feishu)

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

Optional:

- `FEISHU_VERIFICATION_TOKEN`
- `FEISHU_ENCRYPT_KEY`

## 3) JSON Scheduler

Core module: `src/scheduler`.

The scheduler reads a JSON config and triggers Python scripts by time rules.

### Config file

Default example: `examples/scheduler_jobs.json`.

- `timezone`: scheduler timezone (for example, `Asia/Shanghai`)
- `jobs`: list of jobs
  - `id`: unique job ID
  - `enabled`: whether the job is enabled (default: `true`)
  - `trigger`: trigger definition
    - `{"type":"cron","cron":"0 9 * * *"}`
    - `{"type":"interval","seconds":300}` (also supports `minutes` / `hours`)
    - `{"type":"once","run_at":"2026-02-25T09:00:00+08:00"}`
  - `script`: Python script path to execute (relative to config directory or absolute path)
  - `args`: argument list passed to the script (optional)
  - `cwd`: working directory for the script (optional, relative to config directory)
  - `env`: per-job environment variables (optional)
  - `timeout_s`: timeout in seconds (optional)
  - `retry`: retry count after a failed run in the same trigger execution (default: `1`)
  - `retry_delay_s`: delay between retries in seconds (default: `30`)
  - `max_failures`: max consecutive failed runs before pause (default: `1`)
  - `disable_on_failure`: auto-pause job after reaching `max_failures` (default: `true`)
  - `log_to_file`: write each attempt output to file (default: `true`)
  - `log_dir`: log directory (default: `logs/scheduler`, relative to config directory)
  - `log_file`: log file name (default: `<job_id>.log`)
  - `log_append`: append mode for log file (default: `true`)
  - `log_max_bytes`: max size before rotation (default: `10485760`)
  - `log_backup_count`: number of rotated backups to keep (default: `5`)

### Start scheduler

```bash
uv run python -m src.scheduler.runner --config examples/scheduler_jobs.json
```

### Runtime behavior

- Supports `cron / interval / once` triggers
- Default failure policy: retry once; if still failed, pause job immediately
- `log_to_file=true`: script `stdout/stderr` only goes to file
- `log_to_file=false`: script `stdout/stderr` is printed to terminal

