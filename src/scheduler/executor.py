from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import JobConfig


@dataclass(slots=True)
class JobExecutionResult:
    return_code: int
    duration_s: float
    timed_out: bool
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.return_code == 0 and not self.timed_out


def run_python_script(job: JobConfig, *, config_dir: Path) -> JobExecutionResult:
    script_path = _resolve_with_base(job.script, base_dir=config_dir)
    if not script_path.exists():
        raise FileNotFoundError(f"script not found for job={job.id}: {script_path}")

    cwd_path = _resolve_with_base(job.cwd, base_dir=config_dir) if job.cwd else config_dir
    env = os.environ.copy()
    env.update(job.env)
    command = [sys.executable, str(script_path), *job.args]

    started_at = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd_path),
            env=env,
            text=True,
            capture_output=True,
            timeout=job.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started_at
        return JobExecutionResult(
            return_code=-1,
            duration_s=duration,
            timed_out=True,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )

    duration = time.monotonic() - started_at
    return JobExecutionResult(
        return_code=completed.returncode,
        duration_s=duration,
        timed_out=False,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _resolve_with_base(path_value: str | None, *, base_dir: Path) -> Path:
    if path_value is None:
        return base_dir.resolve()
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()

