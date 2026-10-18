"""One-time setup: create the environment and the agent the demo runs.

Agents and environments are persistent and versioned, so they are created
once here, not on every run. Paste the printed ids into .env.
Re-running with both ids already set in .env brings the agent's system
prompt and tools up to date (a new agent version only if they changed).
"""

import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

SYSTEM = """You are a data analyst working in a sandbox with Python available.
The company's sales data is in the warehouse: read it with the
query_warehouse tool, never by guessing. When asked a question about data,
pull what you need with SQL, write a short Python script to a file for any
analysis beyond a query, run it, and report the result in two or three
sentences."""

# A custom tool runs in the client, not the sandbox: the agent emits an
# agent.custom_tool_use event and waits for main.py to send the result,
# which main.py gets from the warehouse service.
QUERY_WAREHOUSE = {
    "type": "custom",
    "name": "query_warehouse",
    "description": (
        "Run one read-only SQLite SELECT against the sales warehouse and get the rows back as JSON "
        "(at most 200 rows; aggregate in SQL rather than fetching raw orders). Tables:\n"
        "products(product_id INTEGER, name TEXT, category TEXT, list_price REAL)\n"
        "orders(order_id INTEGER, order_date TEXT 'YYYY-MM-DD', region TEXT, channel TEXT, "
        "product_id INTEGER, quantity INTEGER, unit_price REAL)\n"
        "Revenue is quantity * unit_price. The data covers 2025."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "A single SQLite SELECT statement."}},
        "required": ["sql"],
    },
}

TOOLS = [
    {
        "type": "agent_toolset_20260401",
        "default_config": {"enabled": True, "permission_policy": {"type": "auto"}},
        "configs": [
            {"name": "web_fetch", "enabled": False},
            {"name": "web_search", "enabled": False},
        ],
    },
    QUERY_WAREHOUSE,
]


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


def update_agent(client: anthropic.Anthropic, agent_id: str) -> None:
    """Give an agent made before the custom tool existed the current prompt and tools."""
    agent = client.beta.agents.retrieve(agent_id)
    has_tool = any(getattr(t, "name", None) == QUERY_WAREHOUSE["name"] for t in agent.tools)
    if agent.system == SYSTEM and has_tool:
        return
    agent = client.beta.agents.update(agent_id, version=agent.version, system=SYSTEM, tools=TOOLS)
    print(f"Updated {agent_id} to version {agent.version}: added {QUERY_WAREHOUSE['name']}")


def main() -> None:
    agent_id = os.environ.get("MANAGED_AGENT_ID")
    environment_id = os.environ.get("MANAGED_ENVIRONMENT_ID")

    # These setup calls are traced only if a tracer provider is registered;
    # this script registers none, so only main.py's runs show up in Oodle.
    client = anthropic.Anthropic(default_headers=workspace_headers())

    if agent_id:
        update_agent(client, agent_id)
    if agent_id and environment_id:
        print(f"Already set up: MANAGED_AGENT_ID={agent_id} MANAGED_ENVIRONMENT_ID={environment_id}")
        return

    if not environment_id:
        environment = client.beta.environments.create(
            name="claude-otel-demo",
            config={"type": "cloud", "networking": {"type": "limited", "allow_package_managers": True}},
        )
        environment_id = environment.id

    if not agent_id:
        agent = client.beta.agents.create(
            name="claude-otel-demo-analyst",
            model=MODEL,
            system=SYSTEM,
            tools=TOOLS,
        )
        agent_id = agent.id

    print("Add these to .env:\n")
    print(f"MANAGED_AGENT_ID={agent_id}")
    print(f"MANAGED_ENVIRONMENT_ID={environment_id}")


if __name__ == "__main__":
    main()
