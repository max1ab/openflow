from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import JobConfig, SchedulerConfigError, load_scheduler_config
from .executor import run_python_script

LOGGER = logging.getLogger("openflow.scheduler")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run JSON-based scheduler for Python scripts.")
    parser.add_argument(
        "--config",
        default="examples/scheduler_jobs.json",
        help="Path to scheduler JSON config file.",
    )
    return parser.parse_args()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def main() -> None:
    setup_logging()
    args = parse_args()

    try:
        config, config_dir = load_scheduler_config(args.config)
    except SchedulerConfigError as exc:
        LOGGER.error("invalid scheduler config: %s", exc)
        raise SystemExit(2) from exc

    scheduler = BlockingScheduler(timezone=config.timezone_info())
    enabled_jobs = [job for job in config.jobs if job.enabled]
    if not enabled_jobs:
        LOGGER.warning("no enabled jobs found in config, scheduler will idle")

    for job in enabled_jobs:
        trigger = build_trigger(job, timezone=scheduler.timezone)
        scheduler.add_job(
            run_job,
            trigger=trigger,
            id=job.id,
            replace_existing=True,
            kwargs={"job": job, "config_dir": config_dir},
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        LOGGER.info("registered job=%s trigger=%s", job.id, job.trigger.type)

    LOGGER.info("scheduler started (jobs=%d)", len(enabled_jobs))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("scheduler stopped")


def build_trigger(job: JobConfig, *, timezone: Any):
    if job.trigger.type == "cron":
        return CronTrigger.from_crontab(job.trigger.cron or "", timezone=timezone)

    if job.trigger.type == "interval":
        return IntervalTrigger(
            seconds=job.trigger.seconds or 0,
            minutes=job.trigger.minutes or 0,
            hours=job.trigger.hours or 0,
            timezone=timezone,
        )

    run_at_raw = job.trigger.run_at or ""
    run_at = datetime.fromisoformat(run_at_raw)
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone)
    return DateTrigger(run_date=run_at, timezone=timezone)


def run_job(*, job: JobConfig, config_dir: Path) -> None:
    LOGGER.info("job started id=%s", job.id)
    try:
        result = run_python_script(job, config_dir=config_dir)
    except Exception:
        LOGGER.exception("job crashed id=%s", job.id)
        return

    if result.ok:
        LOGGER.info("job succeeded id=%s duration=%.2fs", job.id, result.duration_s)
    elif result.timed_out:
        LOGGER.error("job timeout id=%s duration=%.2fs", job.id, result.duration_s)
    else:
        LOGGER.error(
            "job failed id=%s code=%s duration=%.2fs",
            job.id,
            result.return_code,
            result.duration_s,
        )

    if result.stdout.strip():
        LOGGER.info("job stdout id=%s\n%s", job.id, result.stdout.rstrip())
    if result.stderr.strip():
        LOGGER.warning("job stderr id=%s\n%s", job.id, result.stderr.rstrip())


if __name__ == "__main__":
    main()

