"""The agent's two tools, and the contract they actually enforce.

The tool *declarations* the model sees live in Oodle, in the prompt's config
(see seed.py). Version 1 of that prompt describes these parameters vaguely, so
the model guesses wrong and has to be corrected by the error message. That drift
is the whole point: it is what Oodle's insights are meant to name.

Errors are returned, not raised, so the model gets to see them and retry.
"""

import re

ORDER_ID = re.compile(r"ORD-\d{5}")

REASON_CODES = ["damaged_in_transit", "never_arrived", "wrong_item"]

ORDERS = {
    "ORD-78432": {"item": "Ceramic pour-over kettle", "total": "$24.99", "status": "delivered"},
    "ORD-51907": {"item": "Merino wool socks (3-pack)", "total": "$32.50", "status": "delivered"},
    "ORD-66120": {"item": "Desk lamp, walnut", "total": "$89.00", "status": "in_transit"},
    "ORD-40388": {"item": "Cold brew carafe", "total": "$18.75", "status": "delivered"},
}


def _invalid(message: str) -> dict:
    return {"error": "invalid_args", "message": message}


def _order(order_id):
    if not isinstance(order_id, str) or not ORDER_ID.fullmatch(order_id):
        return None, _invalid(
            f"order_id must be a ShopWorld order number matching ^ORD-\\d{{5}}$, "
            f"for example ORD-78432; got {order_id!r}"
        )
    order = ORDERS.get(order_id)
    if order is None:
        return None, {"error": "not_found", "message": f"no order {order_id}"}
    return order, None


def lookup_order(order_id=None, **extra):
    if extra:
        return _invalid(f"unknown argument(s) {sorted(extra)}; lookup_order takes only order_id")
    order, err = _order(order_id)
    return err or {"order_id": order_id, **order}


def issue_refund(order_id=None, amount_cents=None, reason_code=None, **extra):
    if extra:
        return _invalid(
            f"unknown argument(s) {sorted(extra)}; issue_refund takes "
            f"order_id, amount_cents and reason_code"
        )
    order, err = _order(order_id)
    if err:
        return err

    expected = round(float(order["total"].lstrip("$")) * 100)
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        return _invalid(
            f"amount_cents is an integer number of CENTS, not dollars "
            f"({expected} for an order totalling {order['total']}); got {amount_cents!r}"
        )
    if amount_cents != expected:
        return _invalid(
            f"amount_cents must equal the order total, which is {expected} cents "
            f"({order['total']}); got {amount_cents}"
        )
    if reason_code not in REASON_CODES:
        return _invalid(f"reason_code must be one of {REASON_CODES}; got {reason_code!r}")

    return {
        "refund_id": f"RF-{order_id[4:]}",
        "order_id": order_id,
        "amount_cents": amount_cents,
        "reason_code": reason_code,
        "status": "refunded",
    }


TOOLS = {"lookup_order": lookup_order, "issue_refund": issue_refund}


TICKETS = [
    {"id": "T-1001", "text": "Hi - my order 78432 turned up with the spout cracked clean off. "
                             "Can I get my $24.99 back please?"},
    {"id": "T-1002", "text": "Order 51907 never arrived, tracking has said 'label created' for "
                             "nine days. I paid $32.50 and would like a refund."},
    {"id": "T-1003", "text": "You sent me the wrong thing. I ordered a walnut desk lamp, order "
                             "66120, and received a phone stand. Refund the $89.00."},
    {"id": "T-1004", "text": "The carafe from order 40388 arrived in pieces. $18.75 refund please."},
]
