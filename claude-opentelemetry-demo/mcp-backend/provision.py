"""One-time setup: create the environment the backend's sessions run in.

The managed-agents sub-demo's environment blocks MCP egress, so this one
sets allow_mcp_servers. Agents are not created here: the backend creates
one per session, as the reference backend does. Paste the printed id into .env.
"""

import os

import anthropic


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


def main() -> None:
    if environment_id := os.environ.get("MCP_ENVIRONMENT_ID"):
        print(f"Already set up: MCP_ENVIRONMENT_ID={environment_id}")
        return
    client = anthropic.Anthropic(default_headers=workspace_headers())
    environment = client.beta.environments.create(
        name="claude-otel-demo-mcp-backend",
        config={
            "type": "cloud",
            "networking": {"type": "limited", "allow_mcp_servers": True, "allow_package_managers": True},
        },
    )
    print("Add this to .env:\n")
    print(f"MCP_ENVIRONMENT_ID={environment.id}")


if __name__ == "__main__":
    main()
