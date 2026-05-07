"""Light wrapper around OpenTelemetry — no-op when no tracer is configured.

Workflow 05 §7 says every publish/consume call emits a span and trace IDs
propagate via `Nats-Trace-Id`. The actual exporter wiring is workflow 30's
problem; here we just emit spans + provide header injection/extraction so
traces stitch together once an exporter is plugged in.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import extract, inject

TRACE_HEADER = "Nats-Trace-Id"

_tracer = trace.get_tracer("iic.data_bus", "0.1.0")


@contextmanager
def span(name: str, **attributes: Any) -> Any:
    """Start a span; tag it with the supplied attributes."""
    with _tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, v)
        yield s


def inject_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Add W3C / Nats-Trace-Id headers from the active span context."""
    out = dict(headers or {})
    inject(out)  # inject the W3C traceparent into the dict
    span_ctx = trace.get_current_span().get_span_context()
    if span_ctx.is_valid:
        out[TRACE_HEADER] = format(span_ctx.trace_id, "032x")
    return out


def extract_context(headers: Mapping[str, str]) -> Any:
    """Restore the trace context from headers received over NATS."""
    return extract(dict(headers))


@contextmanager
def attach_context(ctx: Any) -> Any:
    """Bind an extracted context as the current OTel context for the body."""
    token = otel_context.attach(ctx)
    try:
        yield
    finally:
        otel_context.detach(token)
