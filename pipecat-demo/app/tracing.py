"""Pick the tracing path. Both write to Langfuse and to Oodle.

``TRACING_BACKEND=otel`` uses plain OpenTelemetry exporters,
``langfuse-sdk`` goes through the Langfuse Python SDK, and ``none``
disables tracing. The two paths are mutually exclusive by construction:
each registers the process-wide tracer provider.
"""

import logging
import os

import tracing_langfuse
import tracing_otel

logger = logging.getLogger(__name__)

BACKENDS = {
    tracing_otel.BACKEND: tracing_otel,
    tracing_langfuse.BACKEND: tracing_langfuse,
}


def _selected() -> str:
    return os.environ.get("TRACING_BACKEND", tracing_otel.BACKEND).strip().lower()


def enabled() -> bool:
    """Whether Pipecat should record spans at all."""
    return _selected() in BACKENDS


def init(service_name: str) -> bool:
    """Set up the selected path. False when tracing is off."""
    backend = _selected()
    module = BACKENDS.get(backend)
    if module is None:
        if backend not in ("none", ""):
            raise SystemExit(
                f"TRACING_BACKEND={backend!r} is not one of "
                f"{', '.join([*BACKENDS, 'none'])}"
            )
        logger.info("Tracing is disabled (TRACING_BACKEND=none)")
        return False

    module.init(
        service_name,
        console_export=os.environ.get("OTEL_CONSOLE_EXPORT", "").strip().lower()
        in ("1", "true"),
    )
    return True


def flush() -> None:
    """Deliver everything recorded so far, on whichever path was set up."""
    module = BACKENDS.get(_selected())
    if module is not None:
        module.flush()


def shutdown() -> None:
    """Flush and close whichever path was set up."""
    module = BACKENDS.get(_selected())
    if module is not None:
        module.shutdown()
