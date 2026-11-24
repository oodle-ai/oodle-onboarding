"""Read-only AWS tools; botocore auto-instrumentation adds the SDK spans."""

import json
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_STACK = "oodle-bedrock-agentcore-tools"
ORDERS = {
    "ORD-1001": {"item": "wireless headphones", "status": "delivered", "days_since_delivery": 7},
    "ORD-1002": {"item": "coffee grinder", "status": "in transit", "estimated_delivery": "in 2 days"},
    "ORD-1003": {"item": "desk lamp", "status": "delivered", "days_since_delivery": 45},
}
POLICY = {"return_window_days": 30, "condition": "Item must be undamaged", "shipping": "Free returns"}


def aws_call(service, operation, **kwargs):
    """Execute an AWS API call.  ADOT botocore instrumentor adds the span."""
    try:
        client = boto3.client(service, region_name=os.environ.get("AWS_REGION", "us-west-2"),
                              config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}))
        return getattr(client, operation)(**kwargs)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"AWS {service}.{operation} failed: {exc}") from exc


def fixture_mode():
    mode = os.environ.get("TOOL_DATA_SOURCE", "aws")
    if mode not in {"aws", "fixture"}:
        raise ValueError("TOOL_DATA_SOURCE must be aws or fixture")
    return mode == "fixture"


def lookup_order(order_id):
    if order_id == "ORD-ERROR":
        raise RuntimeError("Simulated order backend outage")
    if fixture_mode():
        item = ORDERS.get(order_id)
    else:
        table = os.environ.get("ORDERS_TABLE_NAME") or os.environ.get("TOOLS_STACK_NAME", DEFAULT_STACK) + "-orders"
        response = aws_call("dynamodb", "get_item", TableName=table,
                            Key={"order_id": {"S": order_id}}, ConsistentRead=True)
        item = json.loads(response["Item"]["payload"]["S"]) if response.get("Item") else None
    if item is None:
        raise ValueError(f"Order {order_id} was not found")
    return {"order_id": order_id, **item}


def get_return_policy():
    if fixture_mode():
        return POLICY.copy()
    name = os.environ.get("RETURN_POLICY_PARAMETER") or "/" + os.environ.get("TOOLS_STACK_NAME", DEFAULT_STACK) + "/return-policy"
    response = aws_call("ssm", "get_parameter", Name=name, WithDecryption=False)
    return json.loads(response["Parameter"]["Value"])
