# Managed Agents for Amazon Bedrock → Oodle

A real **Agents for Amazon Bedrock** agent owns the model calls and orchestration
inside AWS. A Python client invokes it with `enableTrace=True`, handles a small
return-control action group, and exports the resulting spans to Oodle.

```text
Python client → InvokeAgent → AWS-managed agent → Bedrock model
      ↑                         │
      └── returnControl ────────┘
      ├─ lookup_order → DynamoDB / get_return_policy → SSM
      ├─ search_aws_docs → AWS Knowledge MCP
      ├─ return tool results to the same managed-agent session
      └─ service trace events + tool spans → OTLP/HTTP → Oodle
```

AWS manages planning, prompt construction, and subsequent model calls. The
client executes the AWS/MCP tool wrappers selected by the service. No Strands
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
make tools-deploy
make tools-check
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
`OrderSupport`, `lookup_order(order_id)`, `get_return_policy()`, and
`search_aws_docs(search_phrase)` definitions.

The local client needs DynamoDB/SSM read permissions; the managed-agent service
role only calls the model and returns tool requests. MCP runs in the client, not
inside the Bedrock managed service. The tools stack is deployable even when
managed-agent creation is denied.

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
make tools-destroy
```

Cleanup asks for confirmation and deletes only this CloudFormation stack,
including its managed agent and IAM role. An existing agent supplied through
`BEDROCK_AGENT_ID` is not part of the stack and is not deleted.

## AWS service tools and managed MCP

| Tool | Implementation | Agent permissions |
|---|---|---|
| `lookup_order(order_id)` | DynamoDB `GetItem` from this demo's orders table | `dynamodb:GetItem` on that table |
| `get_return_policy()` | SSM `GetParameter` containing the return policy JSON | `ssm:GetParameter` on that parameter |
| `search_aws_docs(search_phrase)` | AWS-managed Knowledge MCP over Streamable HTTP | Public HTTPS; no AWS credentials |

`make tools-deploy` creates a separate CloudFormation stack containing a DynamoDB
on-demand table and an SSM String parameter, then inserts three fictional orders.
Existing order items are preserved. Provisioning needs CloudFormation, DynamoDB
create/describe/PutItem, and SSM parameter management permissions. Agent execution
only reads these resources. `make tools-status` displays the stack outputs.

`TOOL_DATA_SOURCE=aws` is the default. `ORDERS_TABLE_NAME` and
`RETURN_POLICY_PARAMETER` can select existing resources; otherwise names derive
from `TOOLS_STACK_NAME`. The table uses a String `order_id` key and a String
`payload` containing JSON. The SSM value is JSON with the return policy fields.
Set `TOOL_DATA_SOURCE=fixture` explicitly to use the original in-memory order data.
AWS errors never silently fall back to fixture data. The MCP tool always calls
the remote server; `make test` substitutes local boundaries for offline checks.

The [AWS Knowledge MCP server](https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server)
is hosted by AWS at `https://knowledge-mcp.global.api.aws`. The client initializes
an MCP session, checks `tools/list`, and calls only `aws___search_documentation`.
No local MCP server, Gateway deployment, or MCP credential is needed. The wrapper
passes a technical search phrase and bounds results and timeouts. It exposes no
arbitrary AWS command or code-execution tools. Search text goes to the public AWS
endpoint; the agent is instructed to exclude order/customer data and treat results
as reference text. The agent-visible wrapper name is `search_aws_docs`.

The default prompt asks for order status, the return policy, and AWS documentation
on DynamoDB point-in-time recovery, exercising all three tools when model access
is available. `ORD-ERROR` remains an intentional local failure before an AWS call.

### Emit real tool traces without a model

```bash
make tools-check
```

This calls DynamoDB, SSM, and the managed MCP directly and emits a `tools.smoke`
trace under the demo's normal service name. It prints the trace ID and each tool's
status, attempts all three tools even if one fails, and exits nonzero on failure.
The trace has `demo.run.type=tool-check`; it is a direct diagnostic, with no model
generations or invented tokens. It works even if Bedrock invocation is denied.

Agent runs contain native/return-control `execute_tool` spans with child AWS SDK
spans (`dynamodb.get_item`, `ssm.get_parameter`) and native MCP SDK spans (`MCP send initialize`,
`MCP send tools/list`, `MCP send tools/call aws___search_documentation`). AWS request IDs,
service/operation, latency, and failures are recorded. MCP calls are native child RPC
spans, so they do not double-count the outer tool call. An MCP `isError` result
marks the enclosing tool span ERROR even if the RPC itself succeeded.
`CAPTURE_CONTENT=false` omits tool request/result content, including MCP content. Exception text is not redacted.

`make test` checks the real AWS request shapes using botocore Stubber and exercises
the actual MCP SDK against a local JSON-RPC HTTP server, including an MCP
`isError` result, denied AWS requests, parent links, and content capture on/off.

### Remove the tool resources

```bash
make tools-destroy
```

This prompts before deleting this demo's tool stack, including its fictional
orders and policy parameter. It does not delete resources supplied through the
existing-resource overrides. Tool resources are independent of agent deployment
and must be cleaned up separately.

References: [return control](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-returncontrol.html),
[service trace events](https://docs.aws.amazon.com/bedrock/latest/userguide/trace-events.html),
[CloudFormation agent resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html).
