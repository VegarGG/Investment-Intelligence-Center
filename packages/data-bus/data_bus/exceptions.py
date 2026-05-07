"""Typed exceptions for the data_bus package (workflow 05 §6, §10)."""

from __future__ import annotations


class DataBusError(Exception):
    """Base for every typed error raised by data_bus."""


class InvalidSubject(DataBusError):
    """Subject doesn't match the GROUND-TRUTH `<word>(.<word>)+\\.v\\d+` pattern.
    Workflow 05 §2 / §10 acceptance criterion."""


class StreamNotFound(DataBusError):
    """Asked to publish/subscribe to a subject that doesn't fall under any
    provisioned stream — usually a typo or a missing init."""


class HandlerError(DataBusError):
    """A user handler raised; the wrapper wraps + naks + retries up to
    max_deliver before letting it die."""
