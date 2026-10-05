"""Create version 1 of the prompt in Oodle: the drifted one.

The prompt never states the order-number format, never says the refund amount is
in cents, and never lists the reason codes. The tool declarations shipped in the
prompt's config are just as vague. Everything the model needs is missing, so it
learns the contract the expensive way - from tool errors, several turns in.

That is the failure Oodle is left to spot on its own.
"""

import os
import sys

import oodle
from tools import ORDERS, TICKETS

PROMPT_NAME = os.environ.get("PROMPT_NAME", "order-support-agent")
DATASET_NAME = os.environ.get("DATASET_NAME", "order-support-eval")
EXPECTED_REASON = {"T-1001": "damaged_in_transit", "T-1002": "never_arrived",
                   "T-1003": "wrong_item", "T-1004": "damaged_in_transit"}

DRIFTED_PROMPT = """\
You are a support agent for ShopWorld.

Read the customer's ticket, look up their order, and if the complaint is valid,
refund them. Use the tools available to you. Then reply to the customer in two
short sentences.
"""

DRIFTED_TOOLS = [
    {
        "name": "lookup_order",
        "description": "Look up an order.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "the order"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund an order.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "the order"},
                "amount_cents": {"type": "integer", "description": "the refund amount"},
                "reason_code": {"type": "string", "description": "why the refund is being issued"},
            },
            "required": ["order_id", "amount_cents", "reason_code"],
        },
    },
]


def seed_dataset():
    """The tickets the improver's Oodle experiment replays through the agent."""
    try:
        oodle.dataset(DATASET_NAME)
        print(f"Dataset {DATASET_NAME} already exists")
        return
    except RuntimeError:
        pass
    oodle._api("POST", "datasets", json={
        "name": DATASET_NAME, "description": "Tickets the agent got wrong in production"})
    for ticket in TICKETS:
        order_id = "ORD-" + next(w for w in ticket["text"].replace(",", " ").split() if w.isdigit() and len(w) == 5)
        cents = round(float(ORDERS[order_id]["total"].lstrip("$")) * 100)
        oodle._api("POST", "dataset-items", json={
            "datasetName": DATASET_NAME, "input": ticket["text"],
            "expectedOutput": f"Refund of {cents} cents issued for order {order_id}, "
                              f"reason_code {EXPECTED_REASON[ticket['id']]}."})
    print(f"Created dataset {DATASET_NAME} with {len(TICKETS)} tickets")


def main():
    seed_dataset()
    if "--force" not in sys.argv:
        try:
            live = oodle.get_prompt(PROMPT_NAME)
            print(f"{PROMPT_NAME} already exists at version {live['version']} "
                  f"(labels {live['labels']}). Pass --force to add another drifted version.")
            return
        except Exception:
            pass

    created = oodle.create_prompt(
        PROMPT_NAME,
        DRIFTED_PROMPT,
        DRIFTED_TOOLS,
        labels=["production"],
        commit_message="initial - contract left implicit",
    )
    print(f"Created {PROMPT_NAME} version {created['version']}, labels {created['labels']}")


if __name__ == "__main__":
    main()
