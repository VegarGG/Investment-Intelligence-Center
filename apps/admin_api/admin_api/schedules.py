"""Read/write Settings → Schedules YAML (P3.5).

Pure I/O around ``infra/cron/schedules.yaml``. The orchestrator's
``triggers/cron.py:CRON_JOBS`` table is the canonical job set; this
file just lets ops override the schedule expression per-job and toggle
each on/off without a redeploy.

Shape of ``infra/cron/schedules.yaml``::

    cron:morning_brief:
      enabled: true
      cron: "30 6 * * *"
      timezone: "America/Los_Angeles"
    cron:intel_gdelt_pull:
      enabled: true
      cron: "*/15 * * * *"
    ...
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from featureflags.paths import repo_root

SCHEDULES_REL = "infra/cron/schedules.yaml"


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    job_id: str
    enabled: bool
    cron: str | None
    timezone: str | None


def path() -> Path:
    return repo_root() / SCHEDULES_REL


def load() -> dict[str, ScheduleEntry]:
    p = path()
    if not p.is_file():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    out: dict[str, ScheduleEntry] = {}
    if not isinstance(raw, dict):
        return out
    for job_id, body in raw.items():
        if not isinstance(body, dict):
            continue
        out[job_id] = ScheduleEntry(
            job_id=job_id,
            enabled=bool(body.get("enabled", True)),
            cron=body.get("cron"),
            timezone=body.get("timezone"),
        )
    return out


def dump(entries: dict[str, ScheduleEntry]) -> str:
    doc = {
        e.job_id: {
            "enabled": e.enabled,
            **({"cron": e.cron} if e.cron else {}),
            **({"timezone": e.timezone} if e.timezone else {}),
        }
        for e in entries.values()
    }
    return yaml.safe_dump(doc, sort_keys=True)
