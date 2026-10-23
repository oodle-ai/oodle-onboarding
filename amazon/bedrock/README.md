# Amazon Bedrock → Oodle

A Python Strands agent uses Amazon Bedrock Converse to answer order-support
questions. Its real model and tool spans go directly to Oodle over OTLP/HTTP.
No collector is required. A small tool stack stores the fictional order data in AWS.

```text
CLI → Strands agent → Bedrock Converse (Amazon Nova Lite)
          ├─ lookup_order → DynamoDB
          ├─ get_return_policy → SSM Parameter Store
          └─ search_aws_docs → AWS Knowledge MCP
          └─ OpenTelemetry → Oodle
```

## Run

Requires [uv](https://docs.astral.sh/uv/) (which installs Python 3.12) and an AWS profile with `bedrock:InvokeModel` permission
for the selected model/inference profile and its destination models. The default
is `us.amazon.nova-lite-v1:0` in `us-west-2`; change `BEDROCK_MODEL_ID` to another
tool-capable Bedrock model or inference profile available in your account.

```bash
cd amazon/bedrock
cp .env.example .env
# Set AWS_PROFILE, AWS_REGION, OODLE_INSTANCE, and OODLE_API_KEY.
# Set OODLE_OTLP_ENDPOINT to the base URL from your integration if needed.
make setup
make tools-deploy
make tools-check
make demo
make error
```

The Oodle key needs data-ingestion access. AWS credentials come from the normal
boto3 credential chain; no AWS keys are stored in this demo. An exported shell
variable takes precedence over `.env`.

Try a custom question:

```bash
.venv/bin/python app/main.py --prompt 'Can I return order ORD-1003?'
```

`ORD-1001` was delivered 7 days ago, `ORD-1002` is in transit, and `ORD-1003`
was delivered 45 days ago. Returns are allowed within 30 days. `ORD-ERROR`
raises a simulated backend error; the agent explains the failure without retrying.
An unknown order also raises a tool error. Tools never change an order.

Each command prints the answer, session ID, and trace ID. Requests start fresh;
`--session-id` groups traces, but does not persist conversation history.

## Inspect in Oodle

Open **Agent Observability → Traces** (`/genai/traces`) and filter for service
`amazon-bedrock-demo`, or search for the printed trace ID. Expect a tree like:

```text
support.request
└─ invoke_agent order-support-agent
   ├─ model call: tool selection
   ├─ execute_tool lookup_order → dynamodb.get_item
   ├─ execute_tool get_return_policy → ssm.get_parameter
   ├─ execute_tool search_aws_docs → MCP session/list/call
   └─ model call: final answer
```

Strands also emits event-loop spans; exact model/tool ordering can vary.
Model spans include model ID, input/output tokens, and transcript content.
The `make error` trace includes an ERROR tool span even when the agent handles
the error and returns a successful answer. Model access or authentication errors
also appear as failed requests.

`app/telemetry.py` configures one HTTP/protobuf exporter with Oodle's
`X-OODLE-INSTANCE` and `X-API-KEY` headers and gzip compression. It enables
`gen_ai_latest_experimental,gen_ai_span_attributes_only` before creating the
agent, so native Strands transcript fields are attached to spans. The CLI shuts
down the provider before exiting to drain the export queue.

`CAPTURE_CONTENT=true` includes the fictional prompts, replies, system prompt,
and tool inputs/results. Set it to `false` to use Strands' native redaction of
those fields while retaining timings, model names, token counts, and tool names.
Custom tool exception messages are not redacted by that option.

## Verify without credentials

```bash
make test
CAPTURE_CONTENT=false make test
```

The check uses botocore's Stubber for Bedrock responses, executes the actual
Strands agent and three tool wrappers, and captures real gzip-compressed OTLP protobuf
requests on localhost. It checks parent links, token usage, transcript/redaction,
error spans, exporter headers, and duplicate exports. It makes no AWS or Oodle
calls. A passing check is not proof of live ingestion; verify the printed trace
ID in Oodle after `make demo`.

For `AccessDeniedException`, check the AWS profile, model access, inference-profile
permissions, and any cross-region restrictions. For OTLP HTTP 401/403, check the
Oodle instance and ingestion key; for connection errors, check the endpoint.
Use `make tools-destroy` to remove the tool resources.

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

References: [Strands tracing](https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/),
[Bedrock client-side tool use](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html).
