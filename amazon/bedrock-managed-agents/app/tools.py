"""Read-only fictional order tools, executed only on Bedrock return-control requests."""

ORDERS = {
    "ORD-1001": {"item": "wireless headphones", "status": "delivered", "days_since_delivery": 7},
    "ORD-1002": {"item": "coffee grinder", "status": "in transit", "estimated_delivery": "in 2 days"},
    "ORD-1003": {"item": "desk lamp", "status": "delivered", "days_since_delivery": 45},
}


def execute(function: str, arguments: dict) -> dict:
    if function == "get_return_policy" and not arguments:
        return {"return_window_days": 30, "condition": "Item must be undamaged", "shipping": "Free returns"}
    if function == "lookup_order" and set(arguments) == {"order_id"}:
        order_id = arguments["order_id"]
        if order_id == "ORD-ERROR":
            raise RuntimeError("Simulated order backend outage")
        if order_id not in ORDERS:
            raise ValueError(f"Order {order_id} was not found")
        return {"order_id": order_id, **ORDERS[order_id]}
    raise ValueError("Unsupported function or invalid arguments")
