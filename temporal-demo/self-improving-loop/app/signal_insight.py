"""Hand the improver a finding now, instead of waiting for one.

The demo does not need this: the improver watches Oodle and acts on what it
reports. But Oodle reports periodically, so on a fresh instance there is a wait
between the first bad tool calls and the first finding. This sends an equivalent
payload straight to the workflow so you can rehearse the rest of the loop.

The evidence below is copied out of real traces from this demo: it is what the
agent actually sent and actually got back.

    python signal_insight.py
"""

import asyncio
import os

from temporalio.client import Client

INSIGHT = {
    "title": "Wrong tool arguments: lookup_order and issue_refund in support-agent",
    "category": "wrong_tool_arguments",
    "severity": "high",
    "service_name": os.environ.get("SERVICE_NAME", "support-agent"),
    "description": (
        "The agent's first call to lookup_order and to issue_refund is rejected as "
        "invalid_args on roughly half of all calls, then succeeds once the tool error "
        "tells it the format. Two wasted model turns per ticket."
    ),
    "details": [
        "lookup_order: 13 of 26 calls rejected as invalid_args",
        "issue_refund: 10 of 21 calls rejected as invalid_args",
    ],
    "evidence": [
        {
            "span_name": "execute_tool lookup_order",
            "span_input": '{"order_id": "40388"}',
            "span_output": '{"error": "invalid_args", "message": "order_id must be a '
                           "ShopWorld order number matching ^ORD-\\\\d{5}$, for example "
                           "ORD-78432; got '40388'\"}",
        },
        {
            "span_name": "execute_tool issue_refund",
            "span_input": '{"amount_cents": 1875, "order_id": "ORD-40388", "reason_code": "damaged"}',
            "span_output": '{"error": "invalid_args", "message": "reason_code must be one of '
                           "['damaged_in_transit', 'never_arrived', 'wrong_item']; got 'damaged'\"}",
        },
        {
            "span_name": "execute_tool issue_refund",
            "span_input": '{"amount_cents": 24.99, "order_id": "ORD-78432", "reason_code": "damaged"}',
            "span_output": '{"error": "invalid_args", "message": "amount_cents is an integer '
                           'number of CENTS, not dollars (2499 for an order totalling $24.99); '
                           'got 24.99"}',
        },
    ],
}


async def main():
    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "temporal:7233"))
    await client.get_workflow_handle("prompt-improver").signal("insight", INSIGHT)
    print("Signalled the improver. Watch `make logs`, then `make status`.")


if __name__ == "__main__":
    asyncio.run(main())
