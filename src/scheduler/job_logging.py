from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import JobConfig

_FILE_LOGGERS: dict[str, logging.Logger] = {}


def write_attempt_log(
    *,
    job: JobConfig,
    config_dir: Path,
    attempt: int,
    attempts: int,
    status: str,
    duration_s: float | None,
    return_code: int | None,
    stdout_text: str | None = None,
    stderr_text: str | None = None,
    error_text: str | None = None,
) -> None:
    if not job.log_to_file:
        return

    logger = _get_or_create_job_file_logger(job=job, config_dir=config_dir)
    timestamp = datetime.now().isoformat(timespec="seconds")
    duration_label = f"{duration_s:.2f}s" if duration_s is not None else "n/a"
    code_label = str(return_code) if return_code is not None else "n/a"

    lines = [
        f"[{timestamp}] job={job.id} attempt={attempt}/{attempts} status={status} duration={duration_label} code={code_label}",
        "[stdout]",
        (stdout_text or "").rstrip() or "<empty>",
        "[stderr]",
        (stderr_text or "").rstrip() or "<empty>",
    ]
    if error_text:
        lines.extend(["[error]", error_text.strip()])
    lines.append("-" * 80)
    logger.info("\n".join(lines))


def _get_or_create_job_file_logger(*, job: JobConfig, config_dir: Path) -> logging.Logger:
    log_path = _resolve_log_path(job=job, config_dir=config_dir)
    cache_key = str(log_path)
    existing = _FILE_LOGGERS.get(cache_key)
    if existing is not None:
        return existing

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"openflow.scheduler.job.{job.id}.{len(_FILE_LOGGERS)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        filename=log_path,
        mode="a" if job.log_append else "w",
        maxBytes=job.log_max_bytes,
        backupCount=job.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    _FILE_LOGGERS[cache_key] = logger
    return logger


def _resolve_log_path(*, job: JobConfig, config_dir: Path) -> Path:
    log_dir_raw = job.log_dir or "logs/scheduler"
    log_dir = Path(log_dir_raw).expanduser()
    if not log_dir.is_absolute():
        log_dir = (config_dir / log_dir).resolve()

    filename = (job.log_file or f"{job.id}.log").strip() or f"{job.id}.log"
    return (log_dir / filename).resolve()

