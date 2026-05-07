"""Cron triggers — APScheduler in-process with the §2.1 schedule.

Persistent jobstore in Redis so a container restart doesn't re-run jobs
that already fired (workflow 06 §9 risk #1). `coalesce=True` so missed
runs fire at most once at recovery.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .types import Trigger

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger(__name__)

DEFAULT_TZ = "America/Los_Angeles"

# Workflow 06 §2.1 cron schedule.
CRON_JOBS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("cron:morning_brief", {"hour": 6, "minute": 30}),
    ("cron:midday_check", {"hour": 12, "minute": 0}),
    ("cron:evening_recap", {"hour": 16, "minute": 30}),
    ("cron:hourly_intel", {"hour": "6-22", "minute": 0}),
    ("cron:weekly_eval", {"day_of_week": "mon", "hour": 9, "minute": 0}),
)


def build_scheduler(
    on_trigger: Callable[[Trigger], Awaitable[None]],
    *,
    timezone: str = DEFAULT_TZ,
    redis_url: str | None = None,
) -> AsyncIOScheduler:
    """Build (but don't start) the cron scheduler.

    Caller `await scheduler.start()` and `await scheduler.shutdown()` —
    keeps lifecycle visible at the FastAPI startup/shutdown event hooks.
    """
    from apscheduler.jobstores.redis import RedisJobStore
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    resolved_url: str = redis_url or os.environ.get("REDIS_URL") or "redis://redis:6379/0"
    jobstores = {
        "default": RedisJobStore(
            jobs_key="orch.cron.jobs",
            run_times_key="orch.cron.runs",
            host=_redis_host(resolved_url),
            port=_redis_port(resolved_url),
            db=_redis_db(resolved_url),
        )
    }
    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone=timezone,
        job_defaults={"coalesce": True, "misfire_grace_time": 300},
    )

    for name, cron_kwargs in CRON_JOBS:
        scheduler.add_job(
            _emit_trigger,
            CronTrigger(timezone=timezone, **cron_kwargs),
            args=[on_trigger, name],
            id=name,
            replace_existing=True,
        )
    return scheduler


async def _emit_trigger(on_trigger: Callable[[Trigger], Awaitable[None]], name: str) -> None:
    trigger = Trigger(kind="cron", name=name, fired_at=datetime.now())
    log.info("cron fire: %s", name)
    await on_trigger(trigger)


def _redis_host(url: str) -> str:
    # naive parse: redis://host:port/db
    return url.split("://", 1)[-1].split(":", 1)[0]


def _redis_port(url: str) -> int:
    after_host = url.split("://", 1)[-1]
    if ":" not in after_host:
        return 6379
    return int(after_host.split(":", 1)[1].split("/", 1)[0])


def _redis_db(url: str) -> int:
    after_host = url.split("://", 1)[-1]
    if "/" not in after_host:
        return 0
    return int(after_host.split("/", 1)[1])
