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

PROMPT_NAME = os.environ.get("PROMPT_NAME", "order-support-agent")

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


def main():
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
