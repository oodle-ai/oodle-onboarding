"""One-time setup: create the environment and the agent the demo runs.

Agents and environments are persistent and versioned, so they are created
once here, not on every run. Paste the printed ids into .env.
Re-running with both ids already set in .env does nothing.
"""

import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

SYSTEM = """You are a data analyst working in a sandbox with Python available.
When asked a question about data, write a short Python script to a file,
run it, and report the result in two or three sentences."""


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


def main() -> None:
    agent_id = os.environ.get("MANAGED_AGENT_ID")
    environment_id = os.environ.get("MANAGED_ENVIRONMENT_ID")
    if agent_id and environment_id:
        print(f"Already set up: MANAGED_AGENT_ID={agent_id} MANAGED_ENVIRONMENT_ID={environment_id}")
        return

    # These setup calls are traced only if a tracer provider is registered;
    # this script registers none, so only main.py's runs show up in Oodle.
    client = anthropic.Anthropic(default_headers=workspace_headers())

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
            tools=[
                {
                    "type": "agent_toolset_20260401",
                    "default_config": {"enabled": True, "permission_policy": {"type": "auto"}},
                    "configs": [
                        {"name": "web_fetch", "enabled": False},
                        {"name": "web_search", "enabled": False},
                    ],
                }
            ],
        )
        agent_id = agent.id

    print("Add these to .env:\n")
    print(f"MANAGED_AGENT_ID={agent_id}")
    print(f"MANAGED_ENVIRONMENT_ID={environment_id}")


if __name__ == "__main__":
    main()
