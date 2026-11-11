# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "e2b-code-interpreter>=2.0",
#   "python-dotenv",
#   "opentelemetry-sdk==1.38.0",
#   "opentelemetry-exporter-otlp-proto-http==1.38.0",
# ]
# ///
"""DataPilot: an AI data analyst that runs its code in E2B sandboxes.

A user uploads order and event data and asks questions in a chat. For each
chat session the agent starts one E2B Code Interpreter sandbox, loads the
uploads into the Jupyter kernel, and runs the code that the planner writes
for each question. Follow-up questions reuse the variables in the kernel.

This script is the agent and the users. Simulated users from three
tenants open sessions and ask questions. After --rollout-after seconds the
agent switches from planner v1 to planner v2, the release that causes the
incident (see planner.py).

The agent sends traces, logs and metrics to Oodle as service
datapilot-agent. The kernel in each sandbox sends its own logs and
memory as service datapilot-kernel. E2B sends the sandbox metrics and
logs through its OTel export.
"""

import argparse
import logging
import os
import random
import signal
import threading
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from e2b_code_interpreter import Sandbox
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

from planner import LOAD, code_for

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TEMPLATE = "datapilot-analyst"
SANDBOX_TIMEOUT_SECS = 600
TENANTS = {"acme-retail": 0.4, "initech": 0.35, "globex": 0.25}
QUESTIONS = ["revenue_by_month", "top_customers", "aov_by_channel"]

OODLE_INSTANCE = os.environ["OODLE_INSTANCE"]
OODLE_API_KEY = os.environ["OODLE_API_KEY"]
OTLP_ENDPOINT = os.environ.get(
    "OODLE_OTLP_ENDPOINT", f"https://{OODLE_INSTANCE}-otlp.collector.oodle.ai"
).rstrip("/")

log = logging.getLogger("datapilot.agent")
planner_version = "v1"
forced_tenant = ""
stop = threading.Event()


def setup_telemetry() -> tuple:
    headers = {"X-OODLE-INSTANCE": OODLE_INSTANCE, "X-API-KEY": OODLE_API_KEY}
    resource = Resource.create({"service.name": "datapilot-agent", "deployment.environment": "demo"})

    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTLP_ENDPOINT}/v1/traces", headers=headers)))
    trace.set_tracer_provider(tp)

    mp = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{OTLP_ENDPOINT}/v1/metrics", headers=headers),
                export_interval_millis=10_000,
            )
        ],
    )
    metrics.set_meter_provider(mp)

    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{OTLP_ENDPOINT}/v1/logs", headers=headers)))
    set_logger_provider(lp)
    log.addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    log.addHandler(console)
    log.setLevel(logging.INFO)
    return tp, mp, lp


tracer = trace.get_tracer("datapilot.agent")
meter = metrics.get_meter("datapilot.agent")
requests_total = meter.create_counter("datapilot.analysis.requests", description="Questions answered or failed")
duration = meter.create_histogram("datapilot.analysis.duration", unit="s", description="Time to run the code for one question")
sessions_total = meter.create_counter("datapilot.sessions", description="Chat sessions, by how they ended")
sessions_active = meter.create_up_down_counter("datapilot.sessions.active", description="Chat sessions that hold a sandbox, as the agent counts them")


class AnalysisFailed(Exception):
    pass


def run_cell(sbx: Sandbox, code: str, attrs: dict) -> None:
    """Run one cell. Retry once on a connection error, as the agent treats it as a network blip."""
    for attempt in (1, 2):
        try:
            ex = sbx.run_code(code, timeout=180)
        except Exception as exc:  # The SDK raises transport errors while the kernel restarts.
            err_type, err_msg = type(exc).__name__, str(exc)
        else:
            if ex.error is None:
                return
            err_type, err_msg = ex.error.name, ex.error.value
        log.warning(
            "sandbox execution error %s: %s",
            err_type,
            err_msg[:200],
            extra={**attrs, "error_type": err_type, "attempt": attempt},
        )
        if attempt == 1 and err_type in ("UnexpectedEndOfExecution", "RemoteProtocolError", "ReadError"):
            time.sleep(3)
            continue
        raise AnalysisFailed(err_type)


def ask(sbx: Sandbox, question: str, attrs: dict) -> None:
    attrs = {**attrs, "question": question, "planner_version": planner_version}
    start = time.monotonic()
    outcome, error_type = "ok", ""
    with tracer.start_as_current_span("datapilot.analysis", attributes=attrs) as span:
        try:
            run_cell(sbx, code_for(question, planner_version), attrs)
        except AnalysisFailed as exc:
            outcome, error_type = "error", str(exc)
            span.set_status(Status(StatusCode.ERROR, error_type))
            raise
        finally:
            secs = time.monotonic() - start
            labels = {
                "tenant": attrs["tenant"],
                "question": question,
                "planner_version": planner_version,
                "outcome": outcome,
                "error_type": error_type,
            }
            requests_total.add(1, labels)
            duration.record(secs, labels)
            log.info(
                "analysis %s question=%s tenant=%s in %.1fs",
                outcome,
                question,
                attrs["tenant"],
                secs,
                extra={**attrs, "outcome": outcome, "error_type": error_type, "duration_s": round(secs, 2)},
            )


def session(tenant: str) -> None:
    session_id = uuid.uuid4().hex[:12]
    attrs = {"tenant": tenant, "session_id": session_id}
    with tracer.start_as_current_span("datapilot.session", attributes=attrs) as span:
        sbx = Sandbox.create(
            template=TEMPLATE,
            timeout=SANDBOX_TIMEOUT_SECS,
            metadata={"app": "datapilot", "tenant": tenant, "session_id": session_id},
            envs={
                "OODLE_INSTANCE": OODLE_INSTANCE,
                "OODLE_API_KEY": OODLE_API_KEY,
                "OODLE_OTLP_ENDPOINT": OTLP_ENDPOINT,
            },
        )
        attrs["sandbox_id"] = sbx.sandbox_id
        span.set_attribute("sandbox_id", sbx.sandbox_id)
        sessions_active.add(1, {"tenant": tenant})
        log.info("session started tenant=%s sandbox=%s", tenant, sbx.sandbox_id, extra=attrs)
        try:
            sbx.commands.run(f"python /opt/datapilot/make_dataset.py --tenant {tenant}", timeout=120)
            run_cell(
                sbx,
                "import sys; sys.path.insert(0, '/opt/datapilot')\n"
                "import datapilot_runtime as dp\n"
                f"dp.start({sbx.sandbox_id!r}, {tenant!r}, {session_id!r}, {planner_version!r})",
                attrs,
            )
            run_cell(sbx, LOAD, attrs)
            questions = random.sample(QUESTIONS, k=random.randint(2, 3))
            if forced_tenant:
                questions = QUESTIONS
            for question in questions:
                if stop.is_set():
                    break
                time.sleep(random.uniform(2, 6))
                ask(sbx, question, attrs)
            # The sandbox is released only when the whole session succeeds.
            # A failed session leaves its sandbox to run until
            # SANDBOX_TIMEOUT_SECS. This is the leak that the incident shows.
            sbx.kill()
            sessions_total.add(1, {"tenant": tenant, "outcome": "finished", "error_type": ""})
            log.info("session finished tenant=%s sandbox=%s", tenant, sbx.sandbox_id, extra=attrs)
        except AnalysisFailed as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            sessions_total.add(1, {"tenant": tenant, "outcome": "aborted", "error_type": str(exc)})
            log.error(
                "session aborted tenant=%s sandbox=%s: %s",
                tenant,
                sbx.sandbox_id,
                exc,
                extra={**attrs, "error_type": str(exc)},
            )
        finally:
            sessions_active.add(-1, {"tenant": tenant})


def worker(i: int, deadline: float) -> None:
    while not stop.is_set() and time.time() < deadline:
        tenant = forced_tenant or random.choices(list(TENANTS), weights=list(TENANTS.values()))[0]
        try:
            session(tenant)
        except Exception as exc:
            sessions_total.add(1, {"tenant": tenant, "outcome": "failed", "error_type": type(exc).__name__})
            log.error(
                "session failed tenant=%s: %s",
                tenant,
                exc,
                extra={"tenant": tenant, "error_type": type(exc).__name__},
            )
        stop.wait(random.uniform(3, 10))


def main() -> None:
    global planner_version, forced_tenant
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--users", type=int, default=3, help="concurrent chat sessions")
    p.add_argument("--minutes", type=float, default=15, help="how long to send traffic")
    p.add_argument("--rollout-after", type=float, default=300, help="seconds of planner v1 before v2, -1 never")
    p.add_argument("--planner", default="v1", choices=["v1", "v2"], help="planner version at start")
    p.add_argument("--tenant", default="", choices=["", *TENANTS], help="send every session for this tenant")
    a = p.parse_args()
    forced_tenant = a.tenant

    tp, mp, lp = setup_telemetry()
    planner_version = a.planner
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    deadline = time.time() + a.minutes * 60
    log.info("traffic start: users=%d planner=%s", a.users, planner_version, extra={"planner_version": planner_version})

    threads = [threading.Thread(target=worker, args=(i, deadline), daemon=True) for i in range(a.users)]
    for t in threads:
        t.start()
        time.sleep(2)

    rollout_at = time.time() + a.rollout_after if a.rollout_after >= 0 else None
    while any(t.is_alive() for t in threads):
        if rollout_at and planner_version == "v1" and time.time() >= rollout_at:
            planner_version = "v2"
            log.info("planner rollout: v1 -> v2", extra={"planner_version": "v2", "event": "deploy"})
        time.sleep(1)

    log.info("traffic stop")
    for provider in (tp, mp, lp):
        provider.shutdown()


if __name__ == "__main__":
    main()
