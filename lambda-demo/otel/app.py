"""Checkout handler that emits metrics, logs, and traces to Oodle.

The OpenTelemetry Python layer wraps this handler
(AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument). The wrapper makes the
invocation span, instruments boto3, and flushes the SDK before the
invocation ends. The handler only adds its own spans and metrics through
the OpenTelemetry API.

The SDK's log handler sends the log records
(OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED). Every field given in
`extra` becomes a log attribute in Oodle.
"""

import logging
import random
import time
import uuid

import boto3
from opentelemetry import metrics, trace

logger = logging.getLogger()
logger.setLevel(logging.INFO)

tracer = trace.get_tracer("lambda-demo.checkout")
meter = metrics.get_meter("lambda-demo.checkout")

orders_counter = meter.create_counter(
    "demo.orders",
    unit="{order}",
    description="Orders that the checkout handler processed, by outcome.",
)
order_amount = meter.create_histogram(
    "demo.order.amount",
    unit="USD",
    description="Order amount.",
)

sts = boto3.client("sts")

PAYMENT_METHODS = ["card", "wallet", "bank_transfer"]
FAILURE_RATE = 0.15


def _log(level, message, **fields):
    """Writes one JSON log line that carries the active trace context."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        fields["trace_id"] = format(ctx.trace_id, "032x")
        fields["span_id"] = format(ctx.span_id, "016x")
    logger.log(level, message, extra=fields)


def _reserve_inventory(order_id, items):
    with tracer.start_as_current_span("reserve_inventory") as span:
        span.set_attribute("order.items", items)
        time.sleep(random.uniform(0.01, 0.05))
        _log(logging.INFO, "Inventory reserved", order_id=order_id, items=items)


def _charge_payment(order_id, amount, method):
    with tracer.start_as_current_span("charge_payment") as span:
        span.set_attribute("payment.method", method)
        span.set_attribute("order.amount", amount)
        time.sleep(random.uniform(0.02, 0.08))
        if random.random() < FAILURE_RATE:
            raise RuntimeError(f"Card declined for order {order_id}")
        _log(
            logging.INFO,
            "Payment captured",
            order_id=order_id,
            amount=amount,
            payment_method=method,
        )


def handler(event, context):
    order_id = str(uuid.uuid4())
    items = random.randint(1, 5)
    amount = round(random.uniform(5, 250), 2)
    method = random.choice(PAYMENT_METHODS)

    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.id", order_id)
        _log(logging.INFO, "Order received", order_id=order_id, items=items)

        # A real AWS call, so the trace also shows a span that the
        # boto3 auto-instrumentation makes.
        sts.get_caller_identity()

        try:
            _reserve_inventory(order_id, items)
            _charge_payment(order_id, amount, method)
        except RuntimeError as err:
            span.record_exception(err)
            span.set_status(trace.StatusCode.ERROR, str(err))
            orders_counter.add(1, {"outcome": "failed", "payment.method": method})
            _log(logging.ERROR, "Order failed", order_id=order_id, error=str(err))
            return {"statusCode": 402, "orderId": order_id}

        orders_counter.add(1, {"outcome": "completed", "payment.method": method})
        order_amount.record(amount, {"payment.method": method})
        _log(logging.INFO, "Order completed", order_id=order_id, amount=amount)
        return {"statusCode": 200, "orderId": order_id}
