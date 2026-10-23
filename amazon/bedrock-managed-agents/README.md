# Managed Agents for Amazon Bedrock → Oodle

A real **Agents for Amazon Bedrock** agent owns the model calls and orchestration
inside AWS. A Python client invokes it with `enableTrace=True`, handles a small
return-control action group, and exports the resulting spans to Oodle.

```text
Python client → InvokeAgent → AWS-managed agent → Bedrock model
      ↑                         │
      └── returnControl ────────┘
      ├─ lookup_order / get_return_policy (local read-only tools)
      ├─ return tool results to the same managed-agent session
      └─ service trace events + tool spans → OTLP/HTTP → Oodle
```

AWS manages planning, prompt construction, and subsequent model calls. The
client executes only the fictional tools selected by the service. No Strands
agent, AgentCore Runtime, Lambda, collector, or local model is involved.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) and AWS CLI; `make setup` installs Python 3.12.
- AWS credentials with CloudFormation, IAM role creation/PassRole, and managed
  Bedrock agent creation/preparation permissions. Invocation needs
  `bedrock:InvokeAgent`; the agent's service role needs `bedrock:InvokeModel`.
- Access to an Agents-compatible model/inference profile in the chosen region.
- An Oodle instance, ingestion key, and OTLP endpoint.

AWS now calls this service **Bedrock Agents Classic** and limits it to existing
customers. Check [AWS's service availability](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-supported.html)
for your account. This demo deliberately exercises that managed-agent API.

## Run

```bash
cd amazon/bedrock-managed-agents
cp .env.example .env
# Set AWS_PROFILE, AWS_REGION, BEDROCK_MODEL_ID, and the Oodle settings.
make setup
make deploy
make status
make demo
make error
```

CloudFormation creates an IAM service role and an agent with the `OrderSupport`
action group. `AutoPrepare` prepares its DRAFT version. The demo invokes the
special `TSTALIASID` test alias, so rerunning deployment uses the updated draft
without leaving an alias pointing to an older version. For production, publish
an agent version and use a versioned alias.

`make demo` reads the agent ID from this stack's outputs. To invoke an existing
compatible agent instead, set `BEDROCK_AGENT_ID` and `BEDROCK_AGENT_ALIAS_ID` in
`.env` and skip deployment. Its return-control action group must use the same
`OrderSupport`, `lookup_order(order_id)`, and `get_return_policy()` definitions.

The Oodle key stays in the local client; it is never passed to CloudFormation.
The service role permits model invocation across foundation models and account
inference profiles so `BEDROCK_MODEL_ID` can change; narrow those resources for
a production deployment. Existing AWS organization policies still apply.

The tools use fictional data: `ORD-1001` was delivered 7 days ago, `ORD-1002` is
in transit, and `ORD-1003` was delivered 45 days ago. Returns are allowed within
30 days. `ORD-ERROR` simulates a tool outage. Tools cannot change orders.

```bash
.venv/bin/python app/main.py --prompt 'Can I return order ORD-1003?'
```

Each invocation prints its answer, session ID, and Oodle trace ID. For follow-up
questions, reuse `--session-id`; the managed service retains session context
for the configured 600-second idle timeout. The client caps return-control
round trips at eight and closes event streams on success or failure.

## What arrives in Oodle

Open **Agent Observability → Traces** and filter for
`amazon-bedrock-managed-agents-demo`:

| Span | Source | Content |
|---|---|---|
| `invoke_agent managed-order-support` | Client | Agent/alias/session IDs, user prompt, final answer, request errors |
| `chat <model>` | Bedrock `modelInvocationInput` + `modelInvocationOutput` events | Model, phase, service timestamps, reported input/output tokens |
| `execute_tool <function>` | Local return-control handler | Tool arguments/results, duration, errors |

The client translates the AWS trace stream into OTel; these are not spans
exported directly by AWS. Model events correlate by service `traceId` within
each InvokeAgent call. Duplicate output events are ignored. Missing output
events produce an incomplete/error model span, without invented token counts.
When AWS omits model timestamps, `aws.bedrock.trace.timing=client_observed`
marks the fallback timing. The parent trace covers all return-control rounds.

`CAPTURE_CONTENT=true` includes the user-facing transcript and tool content.
Raw service model payloads are stored separately as `aws.bedrock.model.input`
and `aws.bedrock.model.output`; their format depends on the model. Dedicated
rationale, guardrail, and observation events are not copied. This is not a
complete archive of every AWS trace event.

Set `CAPTURE_CONTENT=false` to omit transcript, model payload, and tool-content
attributes. Names, counts, timings, and errors remain. Exception text is not
redacted by this switch. The provider flushes on exit, including failed calls.

## Verify without AWS or Oodle

```bash
make test
CAPTURE_CONTENT=false make test
```

The test validates scripted stream events and client requests against botocore's
actual API schemas. It runs the tools and exports real gzip OTLP protobuf to a
localhost receiver. Checks cover invocation/session IDs, continuation payloads,
token deduplication, UTF-8 chunks, service timing, tool failures, stream denial,
incomplete model events, round-trip limits, closed streams, and content omission.
Scripted responses are confined to the test; `make demo` always calls AWS.

## Troubleshooting and cleanup

If deployment fails, inspect its actual CloudFormation resource errors:

```bash
# Use the profile, region, and stack name from .env.
aws cloudformation describe-stack-events --profile demoacc --region us-west-2 \
  --stack-name oodle-bedrock-managed-agents-demo
```

An explicit service-control-policy deny requires an approved model/region or
AWS organization administrator action. `AccessDenied` while creating the
agent can also indicate missing provisioning permissions or service eligibility.
If deployment rolls back to `ROLLBACK_COMPLETE`, remove that failed stack
before redeploying. If Oodle export fails, check the ingestion key and the OTLP
base URL (the client adds `/v1/traces`).

```bash
make destroy
```

Cleanup asks for confirmation and deletes only this CloudFormation stack,
including its managed agent and IAM role. An existing agent supplied through
`BEDROCK_AGENT_ID` is not part of the stack and is not deleted.

References: [return control](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-returncontrol.html),
[service trace events](https://docs.aws.amazon.com/bedrock/latest/userguide/trace-events.html),
[CloudFormation agent resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html).
