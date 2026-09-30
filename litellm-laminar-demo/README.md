# LiteLLM + Laminar Demo

Agent tracing that dual-writes to [Laminar](https://lmnr.ai) and Oodle,
set up the way production agent platforms run it: the Laminar SDK is the
primary tracer, model calls go through a LiteLLM Router gateway, and Oodle
receives both LiteLLM's GenAI spans and a mirror of every Laminar span.

The agent emits the span hierarchy, attribute keys and payload shapes of a
production coding agent: route-audit events, per-call usage and cache
metrics, prompt and tool content, structured tool and turn-loop
payloads, and a context-compaction timeline for long sessions.

## Architecture

```
POST /session
     |
     v
FastAPI app (:8102) — small coding agent
     |
     +-- LiteLLM Router gateway ----------------> model provider
     |     model groups: <model>__reasoning-<effort>
     |
     +-- Laminar SDK (own TracerProvider) ---- gRPC ----> Laminar
     |        |
     |        +-- mirror span processor --+
     |                                    |
     +-- LiteLLM otel callback -----------+-- OTLP/HTTP --> Oodle
              (private TracerProvider)
```

## What gets traced

A session is one or more user messages, and each message produces this
tree as its own trace. Every span below reaches both backends, except
`chat <model>`, which only Oodle receives.

```
session_workflow
  agent_session                       session id, account metadata; route_completed
    llm_call                          title generation, first message only; route_started
      chat <model>                    LiteLLM GenAI span
    run_agent_with_messages           run config in, run result out; route_completed
      summarizing_compact [main]      only when the context nears the window; compaction timeline
        compaction_extract_terms_from_text [main]    output: extracted terms ¹
          llm_call
            chat <model>
        summarizing_get_summary       output: the handoff summary ¹
          compaction_call_model_api
            llm_call
              chat <model>
      llm_call_stream                 usage, cache, content, tool definitions; route_started
        chat <model>
      tool_call [bash_execute]        {tool_id, tool_name, args} in, {stdout, stderr, exitCode} out
      llm_call_stream
        chat <model>
      tool_call [add_task]
        subagent [explore]
          run_agent_with_messages     subagent config, its own route scope
            llm_call_stream
              chat <model>
      llm_call_stream
        chat <model>
```

### Attributes

| Group | Spans | Keys |
|---|---|---|
| Session association | every Laminar span | `lmnr.association.properties.session_id`, `...metadata.account_id`, `...metadata.environment` |
| Route audit (27 fields) | LLM spans get `route_started`; the enclosing turn loop or `agent_session` gets `route_completed` | `agent.route.event`, `purpose`, `route`, `provider`, `model`, `reason`, `selection_reason`, `attempt_id`, `logical_call_id`, `parent_attempt_id`, `input_batch_id`, `input_message_ids`, `input_message_count`, `started`, `fallback`, `forced_api`, `quota`, `auth`, ... |
| Usage and cache | `llm_call`, `llm_call_stream` | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `llm.usage.total_tokens`, `llm.usage.visible_output_tokens`, `cache.read_tokens`, `cache.creation_tokens`, `cache.hit_pct`; reasoning and cache token counts when non-zero |
| Resolved model config | `llm_call`, `llm_call_stream` | `gen_ai.system`, `gen_ai.request.model`, `llm.resolved.reasoning_effort`, `llm.model_selection.fast_mode_enabled` |
| Content ¹ | `llm_call`, `llm_call_stream` | `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.tool.definitions` (Laminar shows these as the span's input, output and tools) |
| Tool payloads ¹ | `tool_call [*]` | input `{tool_id, tool_name, args}`, output `{stdout, stderr, exitCode, outputExceededThreshold}` |
| Turn-loop payloads ¹ | `run_agent_with_messages` | input `{config, user_messages, message_ids}`, output `{final_text, interrupted, tool_call_count, ...}` |
| Gateway | `chat <model>` (Oodle) | `litellm.model_group`, `gen_ai.provider.name`, `gen_ai.usage.*`, `gen_ai.cost.*`, `hidden_params` |
| Conversation | `llm_call`, `llm_call_stream` | `gen_ai.conversation.id`; after the agent's first compaction, `gen_ai.conversation.compacted=true` and `agent.compaction.round` |
| Compaction timeline | `summarizing_compact [<agent>]` | `gen_ai.conversation.id`, `gen_ai.agent.name`, `agent.compaction.round`, `trigger`, `strategy`, `context_window_tokens`, `threshold`, `tokens_before`, `tokens_after`, `messages_before`, `messages_after`, `summary_id`, `previous_summary_id`, `seconds_since_previous`, `agent_key` |

¹ Laminar always receives content. Oodle receives it only with
`OODLE_CAPTURE_MESSAGE_CONTENT=true`. It is off by default, so Oodle
gets the span structure, route data, usage and cost, but no prompts,
completions, tool schemas or tool and turn payloads, on the mirrored
spans and the LiteLLM `chat` spans alike.

Set `ROUTE_ATTRIBUTE_PREFIX` to rename the route-audit namespace, for
example to match an existing platform's attribute names.

## How the pieces work

**Route audit** (`app/route_audit.py`). Every model call runs inside a
`RouteAttempt`. It emits `route_selected` before the LLM span opens,
stamps `route_started` inside the LLM span, and emits `route_completed`
(or `route_failed`) after it closes. Each event writes all 27 fields onto
the span that is current at that moment. That is why the LLM span records
how a call started and its parent records how it ended. `input_batch`
ties every call in a turn to the user messages that triggered it, through
a digest of their ids.

**Gateway** (`app/gateway.py`). A `litellm.Router` with one model group
per selection, named `<model>__reasoning-<effort>`. Each deployment
carries `model_info` with the provider name and base model key.
Cooldowns are off when a group has a single deployment, because cooling it
down would leave nothing to route to.

**Compaction** (`app/compaction.py`). Before every model call the agent
estimates its context size. At 80% of `CONTEXT_WINDOW_TOKENS` (soft) or
87.5% (hard) it extracts key terms, summarizes the history, and keeps
only the system prompt, the summary and the last five user requests. The
agent keeps its history and compaction state from one message's trace to
the next, so rounds count up across the whole session.

Each compaction writes one timeline row onto its `summarizing_compact`
span: round, trigger, tokens and messages before and after, the window
and threshold, a digest of the summary, the previous summary's digest,
and the seconds since the previous compaction. Token counts are estimates
of the context the agent holds, not provider usage, so they compare
before and after. Every later inference span of that agent carries
`gen_ai.conversation.compacted=true` and the round it runs in. Nothing
here is message content, so it reaches Oodle with content capture off.

The handoff summary itself is content. It is the output of
`summarizing_get_summary`, in markdown with the sections User Request,
Progress and Next Steps, so a trace viewer can show what the agent kept
at each compaction. Oodle receives it only with content capture on.

This maps to the [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
where they reach:

| Need | Convention | Here |
|---|---|---|
| Group a session's spans across traces | `gen_ai.conversation.id` | set on inference and compaction spans |
| Mark a call that runs on a compacted history | `gen_ai.conversation.compacted` (boolean, set only when `true`) | set on inference spans after round 1 |
| Name the agent | `gen_ai.agent.name` | `main`, or the subagent type |
| A span for the compaction step | none: orchestrator-side compaction was deferred upstream | `summarizing_compact [<agent>]` |
| Round, trigger, tokens before/after, time between compactions | none | `agent.compaction.*` |

**Dual write** (`app/tracing.py`). Laminar attaches its spans to the global
OpenTelemetry context, so each LiteLLM `chat` span is created as a child of
the Laminar LLM span around it. Laminar exports only to Laminar, though.
The mirror span processor re-exports every Laminar span to Oodle, so the
`chat` spans arrive with their parents, and Oodle gets the session, tool,
subagent and route data too. Set `OODLE_MIRROR_LAMINAR_SPANS=false` to see
Oodle receive only orphaned `chat` spans.

Telemetry never breaks the app. Initialization is idempotent, a mirror
or callback failure is logged and dropped, the app still starts with
LiteLLM spans only if Laminar is not initialized, and both Oodle
pipelines are flushed and closed when the app stops.

## Things that fail quietly

| Setting | What happens without it |
|---|---|
| `disabled_instruments={Instruments.LITELLM}` on `Laminar.initialize` | Laminar's LiteLLM streaming handler records no usage, so Laminar shows $0. The app sets usage on its own LLM spans instead. |
| `semconv_stability_opt_in=gen_ai_latest_experimental` on the LiteLLM callback | The span is named `litellm_request` and Agent Observability lists nothing. |
| `skip_set_global=True` on the LiteLLM callback | LiteLLM tries to become the global tracer provider and competes with Laminar. |
| `gen_ai.operation.name` restored in the callback | LiteLLM 1.102 writes it only when message content is captured. With capture off, Oodle drops the span from Agent Observability. |
| Mirror spans rebuilt with the app's resource | Laminar names its resource after `sys.argv[0]`, so mirrored spans would land under a service called `main.py`. |

## Prerequisites

- Docker and Docker Compose
- An [Oodle](https://oodle.ai) instance ID and API key
- A Laminar project API key
- A key for the provider `MODEL` names, or `MOCK_LLM=true`

## Quick start

```bash
cp .env.example .env    # fill in the keys
make up
make test-session
make test-long-session
```

`test-session` returns the session id and trace id. Search for either
in both Laminar and Oodle. `test-long-session` sends nine messages in one
session and returns every trace id and the number of compactions. Search
Oodle for `agent.compaction.round` to see the session's timeline.

## Verify without any accounts

```bash
make verify-local            # all 30 checks pass; Oodle gets no content
make verify-local-capture    # all 32 checks pass; Oodle gets content too
make verify-local-no-mirror  # parent, session and Oodle attribute checks fail
```

This runs one mocked session of six messages inside the container against
a local gRPC receiver standing in for Laminar and a local HTTP receiver
standing in for the Oodle collector. It uses a 320-token context window,
so the agent compacts four times across the six traces. It then checks
both copies of the traces: span parents, the Router group on `chat`
spans, route events on the right spans, usage attributes, where content,
tool and turn-loop payloads should and should not appear, and the
compaction timeline: consecutive rounds across traces, each round linked
to the one before, and every inference span marked with the round it
runs in.

## Verification

In Oodle:
1. Open **Agent Observability** and filter to service `litellm-laminar-demo`.
2. Open the trace from `make test-session`. The `chat` spans sit under
   `llm_call_stream`, inside the session, tool and subagent spans.
3. Open an `llm_call_stream` span and filter on `agent.route.event`.

In Laminar:
1. Open the project's traces and search for the session id.
2. The trace shows the same tree without the `chat` spans. LLM spans show
   input, output and tools, and Laminar adds cost from the token counts.

## Cleanup

```bash
make clean
```
