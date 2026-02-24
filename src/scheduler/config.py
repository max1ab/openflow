from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TriggerType = Literal["cron", "interval", "once"]


class SchedulerConfigError(ValueError):
    """Raised when scheduler JSON config is invalid."""


@dataclass(slots=True)
class TriggerConfig:
    type: TriggerType
    cron: str | None = None
    seconds: int | None = None
    minutes: int | None = None
    hours: int | None = None
    run_at: str | None = None


@dataclass(slots=True)
class JobConfig:
    id: str
    enabled: bool = True
    trigger: TriggerConfig = field(default_factory=lambda: TriggerConfig(type="interval", seconds=60))
    script: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_s: int | None = None


@dataclass(slots=True)
class SchedulerConfig:
    timezone: str = "Asia/Shanghai"
    jobs: list[JobConfig] = field(default_factory=list)

    def timezone_info(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise SchedulerConfigError(f"invalid timezone: {self.timezone}") from exc


def load_scheduler_config(config_path: str | Path) -> tuple[SchedulerConfig, Path]:
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise SchedulerConfigError(f"config file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchedulerConfigError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SchedulerConfigError("config root must be an object")

    timezone = payload.get("timezone", "Asia/Shanghai")
    if not isinstance(timezone, str) or not timezone.strip():
        raise SchedulerConfigError("timezone must be a non-empty string")

    jobs_raw = payload.get("jobs", [])
    if not isinstance(jobs_raw, list):
        raise SchedulerConfigError("jobs must be an array")

    jobs = [_parse_job(job) for job in jobs_raw]
    _assert_unique_job_ids(jobs)

    config = SchedulerConfig(timezone=timezone.strip(), jobs=jobs)
    config.timezone_info()
    return config, path.parent


def _assert_unique_job_ids(jobs: list[JobConfig]) -> None:
    seen: set[str] = set()
    for job in jobs:
        if job.id in seen:
            raise SchedulerConfigError(f"duplicate job id: {job.id}")
        seen.add(job.id)


def _parse_job(value: Any) -> JobConfig:
    if not isinstance(value, dict):
        raise SchedulerConfigError("each job must be an object")

    job_id = value.get("id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise SchedulerConfigError("job.id must be a non-empty string")

    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise SchedulerConfigError(f"job.enabled must be bool (job={job_id})")

    script = value.get("script")
    if not isinstance(script, str) or not script.strip():
        raise SchedulerConfigError(f"job.script must be a non-empty string (job={job_id})")

    args = value.get("args", [])
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise SchedulerConfigError(f"job.args must be string array (job={job_id})")

    cwd = value.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise SchedulerConfigError(f"job.cwd must be string when provided (job={job_id})")

    timeout_s = value.get("timeout_s")
    if timeout_s is not None and (not isinstance(timeout_s, int) or timeout_s <= 0):
        raise SchedulerConfigError(f"job.timeout_s must be positive int when provided (job={job_id})")

    env = value.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise SchedulerConfigError(f"job.env must be a string map (job={job_id})")

    trigger = _parse_trigger(value.get("trigger"), job_id=job_id)
    return JobConfig(
        id=job_id.strip(),
        enabled=enabled,
        trigger=trigger,
        script=script.strip(),
        args=args,
        cwd=cwd.strip() if isinstance(cwd, str) else None,
        env=env,
        timeout_s=timeout_s,
    )


def _parse_trigger(value: Any, *, job_id: str) -> TriggerConfig:
    if not isinstance(value, dict):
        raise SchedulerConfigError(f"job.trigger must be an object (job={job_id})")

    trigger_type = value.get("type")
    if trigger_type not in {"cron", "interval", "once"}:
        raise SchedulerConfigError(f"job.trigger.type must be cron|interval|once (job={job_id})")

    if trigger_type == "cron":
        cron = value.get("cron")
        if not isinstance(cron, str) or not cron.strip():
            raise SchedulerConfigError(f"job.trigger.cron must be a non-empty string (job={job_id})")
        return TriggerConfig(type="cron", cron=cron.strip())

    if trigger_type == "interval":
        seconds = _parse_positive_int_or_none(value.get("seconds"), key="seconds", job_id=job_id)
        minutes = _parse_positive_int_or_none(value.get("minutes"), key="minutes", job_id=job_id)
        hours = _parse_positive_int_or_none(value.get("hours"), key="hours", job_id=job_id)
        if seconds is None and minutes is None and hours is None:
            raise SchedulerConfigError(
                f"interval trigger requires at least one of seconds/minutes/hours (job={job_id})"
            )
        return TriggerConfig(type="interval", seconds=seconds, minutes=minutes, hours=hours)

    run_at = value.get("run_at")
    if not isinstance(run_at, str) or not run_at.strip():
        raise SchedulerConfigError(f"job.trigger.run_at must be a non-empty datetime string (job={job_id})")
    _validate_datetime(run_at.strip(), job_id=job_id)
    return TriggerConfig(type="once", run_at=run_at.strip())


def _parse_positive_int_or_none(value: Any, *, key: str, job_id: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise SchedulerConfigError(f"job.trigger.{key} must be a positive int (job={job_id})")
    return value


def _validate_datetime(value: str, *, job_id: str) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise SchedulerConfigError(f"job.trigger.run_at must be ISO datetime (job={job_id})") from exc

