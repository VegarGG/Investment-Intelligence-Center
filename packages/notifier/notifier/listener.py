"""Bus subscription glue (workflow 20 §11.3).

Lives in `apps/agent_secretary` at runtime — kept here so the wiring is
co-located with the router. Maps `secretary.notify.v1` to a
`Notification` and dispatches via `router.notify`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from schema import SecretaryNotifyV1

from .router import Router
from .types import ChannelHint, Notification, NotifyResult, Severity

log = logging.getLogger(__name__)

OnDoneFn = Callable[[NotifyResult], Awaitable[None]] | None


def from_event(event: SecretaryNotifyV1, *, target_user: str | None = None) -> Notification:
    """Translate `secretary.notify.v1` into the notifier's `Notification`."""
    return Notification(
        severity=Severity(event.severity),
        channel_hint=ChannelHint(event.channel_hint),
        markdown=event.markdown,
        language=event.language,
        mentioned_list=event.mentioned_list,
        target_user=target_user,
    )


async def handle(
    raw_event: dict[str, Any] | SecretaryNotifyV1,
    *,
    router: Router,
    on_done: OnDoneFn = None,
) -> NotifyResult:
    """Validate, dispatch, optionally notify caller via `on_done`."""
    event = (
        raw_event
        if isinstance(raw_event, SecretaryNotifyV1)
        else SecretaryNotifyV1.model_validate(raw_event)
    )
    notification = from_event(event)
    result = await router.notify(notification)
    if on_done is not None:
        await on_done(result)
    log.info(
        "notifier dispatched: severity=%s adapters=%s",
        event.severity,
        ",".join(a.name for a in result.attempts if a.succeeded),
    )
    return result
