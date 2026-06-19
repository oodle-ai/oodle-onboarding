"""Load generator that continuously starts order processing workflows.

Generates random orders at a configurable interval to produce a steady stream
of metrics, traces, and logs for observability.
"""

import asyncio
import logging
import os
import random
import uuid

from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from temporalio.client import Client
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig

OTEL_ENDPOINT_GRPC = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
SERVICE_NAME = "temporal-starter"
TASK_QUEUE = "order-processing"

ITEMS = ["widget", "gadget", "doohickey", "thingamajig", "whatchamacallit"]
CUSTOMERS = ["alice", "bob", "charlie", "diana", "eve"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def setup_opentelemetry() -> Runtime:
    resource = Resource.create({"service.name": SERVICE_NAME})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT_GRPC, insecure=True))
    )
    otel_trace.set_tracer_provider(tracer_provider)

    runtime = Runtime(
        telemetry=TelemetryConfig(
            metrics=OpenTelemetryConfig(url=f"{OTEL_ENDPOINT_GRPC}")
        )
    )
    return runtime


async def main():
    runtime = setup_opentelemetry()

    temporal_host = os.environ.get("TEMPORAL_HOST", "temporal:7233")
    interval = float(os.environ.get("WORKFLOW_INTERVAL_SECONDS", "5"))

    logger.info("Connecting to Temporal at %s", temporal_host)
    client = await Client.connect(
        temporal_host,
        interceptors=[TracingInterceptor()],
        runtime=runtime,
    )

    logger.info("Starting load generator (interval=%.1fs)", interval)
    while True:
        order_id = f"order-{uuid.uuid4().hex[:8]}"
        item = random.choice(ITEMS)
        quantity = random.randint(1, 10)
        customer = random.choice(CUSTOMERS)

        order = {
            "order_id": order_id,
            "item": item,
            "quantity": quantity,
            "customer": customer,
        }

        try:
            result = await client.execute_workflow(
                "OrderProcessingWorkflow",
                order,
                id=order_id,
                task_queue=TASK_QUEUE,
            )
            logger.info("Workflow %s completed: status=%s total=%.2f tracking=%s",
                         order_id, result["status"], result["total"], result["tracking_id"])
        except Exception as e:
            logger.error("Workflow %s failed: %s", order_id, e)

        await asyncio.sleep(interval + random.uniform(-1, 1))


if __name__ == "__main__":
    asyncio.run(main())
