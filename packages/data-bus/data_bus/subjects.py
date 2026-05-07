"""Subject + stream registry — workflow 05 §2 GROUND TRUTH (verbatim).

Adding a new subject elsewhere without registering here is a typo waiting
to happen — keep this file the single source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from data_bus.exceptions import InvalidSubject

# Subject pattern: dotted lowercase, ends with `.v<n>`. Matches the
# §2 routing-matrix convention from workflow 00 §4.
SUBJECT_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*\.v\d+$")


# ---- subject constants (workflow 05 §2) ------------------------------------
INTEL_DIGEST = "intel.digest.v1"
INTEL_DASHBOARD = "intel.dashboard.v1"
INTEL_BRIEF = "intel.brief.v1"

ADVICE_FUNDAMENTAL = "advice.fundamental.v1"
ADVICE_QUANT = "advice.quant.v1"


def advice_persona(slug: str) -> str:
    """Persona advice subject is dynamic — slug is one of the eight personas
    in workflow 13."""
    if not slug or not slug.replace("_", "").isalnum():
        raise InvalidSubject(f"persona slug must be alnum/underscore; got {slug!r}")
    return f"advice.persona.{slug}.v1"


BACKTEST_FILL = "backtest.fill.v1"
BACKTEST_DAILY = "backtest.daily.v1"
BACKTEST_LEADERBOARD = "backtest.leaderboard.v1"

SECRETARY_NOTIFY = "secretary.notify.v1"

OPS_HEARTBEAT = "ops.heartbeat.v1"
OPS_ALERT = "ops.alert.v1"


# ---- streams (workflow 05 §2 table) ---------------------------------------
@dataclass(frozen=True, slots=True)
class StreamSpec:
    name: str
    subject_prefix: str  # everything matching this prefix lands in the stream
    retention_seconds: int | None  # None == forever
    replicas: int = 1


# Retention values per workflow 05 §2 table.
SECONDS_PER_DAY = 24 * 3600

STREAMS: tuple[StreamSpec, ...] = (
    StreamSpec("INTEL", "intel.>", retention_seconds=30 * SECONDS_PER_DAY),
    StreamSpec("ADVICE", "advice.>", retention_seconds=None),  # forever
    StreamSpec("BACKTEST", "backtest.>", retention_seconds=365 * SECONDS_PER_DAY),
    StreamSpec("SECRETARY", "secretary.>", retention_seconds=7 * SECONDS_PER_DAY),
    StreamSpec("OPS", "ops.>", retention_seconds=14 * SECONDS_PER_DAY),
)

# ---- KV buckets (workflow 05 §2) ------------------------------------------
KV_BUCKETS: tuple[str, ...] = ("iic_state", "iic_locks", "iic_versions")


def assert_valid_subject(subject: str) -> None:
    """Workflow 05 §2 + §8.3 — the .v\\d+ guard."""
    if not SUBJECT_RE.match(subject):
        raise InvalidSubject(
            f"subject {subject!r} doesn't match the required pattern "
            f"(lowercase dotted, ends with .v<n>)"
        )


def stream_for(subject: str) -> str:
    """Map a subject to its enclosing stream name. Raises if no match."""
    for spec in STREAMS:
        prefix = spec.subject_prefix.rstrip(">")
        if subject.startswith(prefix):
            return spec.name
    raise InvalidSubject(f"subject {subject!r} doesn't fall under any provisioned stream")
