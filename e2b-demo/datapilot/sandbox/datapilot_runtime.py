"""DataPilot runtime for the Jupyter kernel inside an E2B sandbox.

The agent runs `datapilot_runtime.start(...)` as the first cell of each
session. After that, the code that the planner writes logs through
`datapilot_runtime.log` and the kernel reports its own memory. Both go
straight to Oodle over OTLP, so this is the telemetry of the application
that runs inside the sandbox.

The kernel exports on a timer. If the kernel is killed between two
exports, the last samples and log lines never leave the sandbox.
"""

import logging
import os

from opentelemetry import metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

log = logging.getLogger("datapilot.kernel")

_attrs: dict = {}
_started = False


class _AddContext(logging.Filter):
    """Put the session attributes on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for k, v in _attrs.items():
            setattr(record, k, v)
        return True


def _rss_bytes() -> int:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    return 0


def _observe_rss(_options):
    yield metrics.Observation(_rss_bytes(), _attrs)


def start(sandbox_id: str, tenant: str, session_id: str, planner_version: str) -> None:
    global _started
    _attrs.update(
        sandbox_id=sandbox_id,
        tenant=tenant,
        session_id=session_id,
        planner_version=planner_version,
    )
    if _started:
        return
    _started = True

    endpoint = os.environ["OODLE_OTLP_ENDPOINT"].rstrip("/")
    headers = {
        "X-OODLE-INSTANCE": os.environ["OODLE_INSTANCE"],
        "X-API-KEY": os.environ["OODLE_API_KEY"],
    }
    resource = Resource.create({"service.name": "datapilot-kernel", **_attrs})

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers),
        export_interval_millis=10_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    meter_provider.get_meter("datapilot.kernel").create_observable_gauge(
        "datapilot.kernel.rss",
        callbacks=[_observe_rss],
        unit="By",
        description="Resident memory of the Jupyter kernel that runs the analysis code",
    )

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers),
            schedule_delay_millis=2_000,
        )
    )
    set_logger_provider(provider)
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    handler.addFilter(_AddContext())
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    log.info("kernel ready, rss=%d MiB", _rss_bytes() // 2**20)


def rss_mib() -> int:
    return _rss_bytes() // 2**20
