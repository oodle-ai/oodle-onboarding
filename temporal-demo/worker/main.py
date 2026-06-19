"""Temporal worker with order processing workflow and full OTel observability.

Exports traces, structured logs, and SDK metrics to Oodle via an OTel Collector.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

# Pass non-deterministic imports through the workflow sandbox
with workflow.unsafe.imports_passed_through():
    import asyncio
    import contextvars
    import json
    import logging
    import os
    import random
    from datetime import datetime, timezone

    from opentelemetry import _logs as otel_logs
    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from temporalio.client import Client
    from temporalio.contrib.opentelemetry import TracingInterceptor
    from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig
    from temporalio.worker import Worker

_current_customer = contextvars.ContextVar("current_customer", default=None)

OTEL_ENDPOINT_GRPC = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
OTEL_ENDPOINT_HTTP = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT_HTTP", "http://otel-collector:4318")
SERVICE_NAME = "temporal-worker"
TASK_QUEUE = "order-processing"


@dataclass
class OrderInput:
    order_id: str
    item: str
    quantity: int
    customer: str


@dataclass
class OrderResult:
    order_id: str
    status: str
    total: float
    tracking_id: str


ITEM_PRICES = {
    "widget": 9.99,
    "gadget": 24.99,
    "doohickey": 14.99,
    "thingamajig": 39.99,
    "whatchamacallit": 19.99,
}


class CustomerSpanProcessor(SpanProcessor):
    """Injects the current customer into every span, including auto-instrumented ones."""

    def on_start(self, span, parent_context=None):
        customer = _current_customer.get()
        if customer:
            span.set_attribute("customer", customer)


def _set_customer(customer: str):
    _current_customer.set(customer)
    otel_trace.get_current_span().set_attribute("customer", customer)


@activity.defn
async def validate_order(order: OrderInput) -> dict:
    _set_customer(order.customer)
    logger = logging.getLogger("activities")
    logger.info("Validating order %s: %dx %s for %s", order.order_id, order.quantity, order.item, order.customer,
                extra={"customer": order.customer})

    await asyncio.sleep(random.uniform(0.05, 0.2))

    if order.quantity <= 0:
        raise ValueError(f"Invalid quantity: {order.quantity}")
    if order.item not in ITEM_PRICES:
        raise ValueError(f"Unknown item: {order.item}")

    price = ITEM_PRICES[order.item]
    total = price * order.quantity
    logger.info("Order %s validated: $%.2f", order.order_id, total,
                extra={"customer": order.customer})
    return {"valid": True, "unit_price": price, "total": total}


@activity.defn
async def process_payment(order_id: str, amount: float, customer: str) -> dict:
    _set_customer(customer)
    logger = logging.getLogger("activities")
    logger.info("Processing payment for order %s: $%.2f from %s", order_id, amount, customer,
                extra={"customer": customer})

    await asyncio.sleep(random.uniform(0.1, 0.5))

    if random.random() < 0.05:
        raise RuntimeError(f"Payment gateway timeout for order {order_id}")

    txn_id = f"txn-{random.randint(100000, 999999)}"
    logger.info("Payment processed for order %s: txn=%s", order_id, txn_id,
                extra={"customer": customer})
    return {"transaction_id": txn_id, "status": "charged"}


@activity.defn
async def ship_order(order_id: str, item: str, quantity: int, customer: str) -> dict:
    _set_customer(customer)
    logger = logging.getLogger("activities")
    logger.info("Shipping order %s: %dx %s", order_id, quantity, item,
                extra={"customer": customer})

    await asyncio.sleep(random.uniform(0.1, 0.3))

    tracking_id = f"TRACK-{random.randint(100000, 999999)}"
    logger.info("Order %s shipped: tracking=%s", order_id, tracking_id,
                extra={"customer": customer})
    return {"tracking_id": tracking_id, "status": "shipped"}


@activity.defn
async def send_notification(order_id: str, customer: str, tracking_id: str) -> dict:
    _set_customer(customer)
    logger = logging.getLogger("activities")
    logger.info("Sending notification for order %s to %s: tracking=%s", order_id, customer, tracking_id,
                extra={"customer": customer})

    await asyncio.sleep(random.uniform(0.02, 0.1))

    logger.info("Notification sent for order %s", order_id,
                extra={"customer": customer})
    return {"notified": True}


@workflow.defn(name="OrderProcessingWorkflow")
class OrderProcessingWorkflow:
    @workflow.run
    async def run(self, order: OrderInput) -> OrderResult:
        workflow.logger.info("Starting order processing: %s", order.order_id)

        validation = await workflow.execute_activity(
            validate_order,
            order,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        payment = await workflow.execute_activity(
            process_payment,
            args=[order.order_id, validation["total"], order.customer],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        shipment = await workflow.execute_activity(
            ship_order,
            args=[order.order_id, order.item, order.quantity, order.customer],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        await workflow.execute_activity(
            send_notification,
            args=[order.order_id, order.customer, shipment["tracking_id"]],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        workflow.logger.info("Order %s completed: tracking=%s", order.order_id, shipment["tracking_id"])
        return OrderResult(
            order_id=order.order_id,
            status="completed",
            total=validation["total"],
            tracking_id=shipment["tracking_id"],
        )


class JsonLogFormatter(logging.Formatter):
    """Emits each log record as a single JSON line with trace context."""

    def format(self, record):
        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "service": SERVICE_NAME,
            "log": record.getMessage(),
        }
        if ctx.is_valid:
            entry["trace_id"] = format(ctx.trace_id, "032x")
            entry["span_id"] = format(ctx.span_id, "016x")
        customer = getattr(record, "customer", None) or _current_customer.get()
        if customer:
            entry["customer"] = customer
        return json.dumps(entry, default=str)


def setup_opentelemetry() -> Runtime:
    resource = Resource.create({"service.name": SERVICE_NAME})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(CustomerSpanProcessor())
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT_GRPC, insecure=True))
    )
    otel_trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{OTEL_ENDPOINT_HTTP}/v1/logs"))
    )
    otel_logs.set_logger_provider(logger_provider)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)

    root.addHandler(LoggingHandler(logger_provider=logger_provider))

    runtime = Runtime(
        telemetry=TelemetryConfig(
            metrics=OpenTelemetryConfig(url=f"{OTEL_ENDPOINT_GRPC}")
        )
    )
    return runtime


async def main():
    runtime = setup_opentelemetry()
    logger = logging.getLogger(__name__)

    temporal_host = os.environ.get("TEMPORAL_HOST", "temporal:7233")
    logger.info("Connecting to Temporal at %s", temporal_host)

    client = await Client.connect(
        temporal_host,
        interceptors=[TracingInterceptor()],
        runtime=runtime,
    )

    logger.info("Starting worker on task queue: %s", TASK_QUEUE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[OrderProcessingWorkflow],
        activities=[validate_order, process_payment, ship_order, send_notification],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
