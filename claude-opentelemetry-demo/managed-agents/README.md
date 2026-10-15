# Claude Managed Agents (SDK + API tracing)

A Managed Agents session where the agent writes and runs a Python script in
its Anthropic-hosted sandbox. The trace needs both sources:

- **SDK tracing** (this process): an `anthropic.sessions.*` CLIENT span for
  each Sessions API request.
- **API tracing** (Anthropic's side): the SERVER span of each request, and
  the work the agent does: `anthropic.session.turn`, its
  `anthropic.model_request` spans, and an `anthropic.tool_use <tool>` span for
  each sandbox tool (`bash`, `write`, ...).

The SDK sees only the requests, so without the
[destination](../README.md#api-tracing-destination) you get the CLIENT spans
and nothing about what the agent did.

```
demo.managed_agent_task                           claude-otel-managed-agents
├─ anthropic.sessions.create          [CLIENT]
│  └─ anthropic.sessions.create       [SERVER]    claude-platform
├─ anthropic.sessions.events.stream   [CLIENT]
└─ anthropic.sessions.events.send     [CLIENT]
   └─ anthropic.sessions.events.send  [SERVER]    claude-platform
      └─ anthropic.session.turn                   claude-platform
         ├─ anthropic.model_request
         ├─ anthropic.tool_use write
         ├─ anthropic.tool_use bash
         └─ anthropic.model_request
```

## Run

```bash
make managed-agents-setup   # once: prints MANAGED_AGENT_ID / MANAGED_ENVIRONMENT_ID
# paste both into ../.env
make managed-agents

# your own task:
docker compose run --rm --build managed-agents main.py "Compute the first 20 primes and their sum"
```

`provision.py` creates a cloud environment with limited networking and an
agent (`CLAUDE_MODEL`, the built-in agent toolset, web tools off, `auto`
permission policy). Agents are persistent and versioned, so this runs once,
not on every session. Re-running it with both ids set does nothing.

`main.py`:

1. Opens a span of its own and creates a session inside it.
2. Opens the event stream **before** sending the task, since the stream
   delivers only events that happen after it opens.
3. Sends the task as a `user.message`.
4. Prints the agent's messages and tool calls until the session goes idle.

A tool call that needs approval is denied, because nobody is watching.

The run prints the `trace_id` and the session's Console URL. The Console's
session viewer shows the same session with no setup, which is useful for
comparing against the trace.

## Cleanup

Nothing is deleted automatically. To remove what the demo created:

```bash
ant beta:agents archive --agent-id "$MANAGED_AGENT_ID"
ant beta:environments archive --environment-id "$MANAGED_ENVIRONMENT_ID"
```
