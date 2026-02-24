## Openflow

### JSON Scheduler

This project includes a basic scheduler that can trigger Python scripts based on a JSON configuration.

#### 1) Install dependencies

```bash
uv sync
```

#### 2) Prepare the config file

See `examples/scheduler_jobs.json`.

Configuration structure:

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
  - `retry`: retry count after a failed run in the same trigger execution (optional, default: `1`)
  - `retry_delay_s`: delay between retries in seconds (optional, default: `30`)
  - `max_failures`: max consecutive failed runs before pause (optional, default: `1`)
  - `disable_on_failure`: auto-pause job after reaching `max_failures` (optional, default: `true`)

#### 3) Start the scheduler

```bash
uv run python -m src.scheduler.runner --config examples/scheduler_jobs.json
```

After startup, the scheduler keeps running and triggers jobs using `cron / interval / once`.

#### 4) Logging and shutdown

- Each run logs start/success/failure, duration, and stdout/stderr.
- Press `Ctrl+C` for graceful shutdown.
- Failure policy notes:
  - `retry` retries immediately within the same trigger execution.
  - Consecutive failure count is tracked per trigger execution (not per retry attempt).
  - Default behavior: retry once, then pause the job immediately if it still fails.
  - If `disable_on_failure=true` and failures reach `max_failures`, the job is automatically paused.
  - Consecutive failure state is in memory only and resets after scheduler restart.

