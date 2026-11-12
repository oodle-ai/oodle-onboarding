# Amazon Bedrock AgentCore → Oodle

A Python Strands order-support agent served by `BedrockAgentCoreApp`, runnable
locally or deployed to managed AgentCore Runtime. It calls Amazon Bedrock and
exports traces to Oodle following the
[AgentCore observability guide](https://levantar.ai/insights/agentcore-07-observability.html):
ADOT botocore auto-instrumentation, session.id propagated via OTel baggage,
and OTLP/HTTP export to Oodle.

```text
Client → AgentCore Runtime → Strands agent → Bedrock Converse
                                ├─ lookup_order → DynamoDB
                                ├─ get_return_policy → SSM Parameter Store
                                └─ search_aws_docs → AWS Knowledge MCP
                                └─ OpenTelemetry → Oodle
```

## How traces work

The guide's agent (`07-observability/agent/`) is a hand-written
`ThreadingHTTPServer` started under ADOT via `opentelemetry-instrument python
main.py` in the Dockerfile.  ADOT creates the TracerProvider, installs
botocore instrumentation, and provides a BaggageSpanProcessor that copies
baggage onto spans — all before user code runs.  The guide's `main.py` uses a
`traced()` context manager on every request to extract the runtime's trace
context from HTTP headers and set `session.id` as baggage.  The guide's
`trail.py` is a Strands hook that records the tool calls the model makes and
enforces a tool-call budget per turn; it is not telemetry code.

This demo uses `BedrockAgentCoreApp` with direct-code deployment (no
Dockerfile), so the same instrumentors are installed programmatically in
`telemetry.py`.  A Docker deployment would replace the CMD with the guide's
`opentelemetry-instrument` wrapper and set the OTEL_* env vars listed in
`deploy.py`.

**Botocore auto-instrumentation** — ADOT's `BotocoreInstrumentor` adds a span
for every AWS SDK call (DynamoDB, SSM, Bedrock Converse).  The agent's own tool
code does not create manual SDK spans; the instrumentor handles it.

**BaggageSpanProcessor** — the entrypoint sets `session.id` as OTel baggage.
In the guide's Docker path, ADOT provides the processor natively.  This demo
installs it explicitly in `telemetry.py` for the programmatic setup.  The
processor copies session.id onto every child span so queries can filter by
session.

**`traced()` context manager** — extracts the runtime's trace context from HTTP
request headers and sets session baggage.  The guide uses it because its
hand-written HTTP server is not auto-instrumented by ADOT.
`BedrockAgentCoreApp` runs on Starlette, which ADOT instruments automatically,
so trace context flows without this helper.  `traced()` is provided in
`telemetry.py` for the same pattern when using a hand-written server.

## Run locally first

Requires [uv](https://docs.astral.sh/uv/) (which installs Python 3.12), an AWS profile with Bedrock model invocation access,
and an Oodle data-ingestion key.

```bash
cd amazon/bedrock-agentcore
cp .env.example .env
# Set AWS_PROFILE, AWS_REGION, OODLE_INSTANCE, and OODLE_API_KEY.
# Set OODLE_OTLP_ENDPOINT to the base URL from your integration if needed.
make setup
make tools-deploy
make tools-check
make local
```

In another terminal in the same directory:

```bash
curl --fail http://localhost:8080/ping
make demo
make error
```

The SDK serves `/ping` and `/invocations` on port 8080. The default model is
`us.amazon.nova-lite-v1:0` in `us-west-2`; `BEDROCK_MODEL_ID` can select another
tool-capable Bedrock model or inference profile available in your account.
The tool data is fictional: `ORD-1001` was delivered 7 days ago, `ORD-1002`
is in transit, and `ORD-1003` was delivered 45 days ago. Returns are allowed
within 30 days. `ORD-ERROR` intentionally fails the order tool.

## Deploy to AgentCore Runtime

```bash
make deploy
make tools-deploy  # Attach table/parameter read access to the generated Runtime role.
make status
make invoke-tools  # Exercise AWS/MCP tools inside the deployed Runtime without a model.
make invoke
```

`make tools-deploy` discovers the Runtime execution role from the generated
configuration when present. For the first deployment, rerun it after `make deploy`
to attach a CloudFormation-managed policy granting only GetItem/GetParameter on
this demo's resources. Set `TOOL_RUNTIME_ROLE_NAME` to select an existing role
explicitly. The deployer needs IAM policy management for this step. Role policies
do not override organization policy denies. Tool configuration is passed to the
Runtime alongside the existing Oodle settings.

The deploying AWS profile needs AgentCore control-plane permissions, IAM role
creation/policy attachment and `iam:PassRole`, plus S3 deployment-bucket access.
The toolkit creates a demo execution role, uploads Python code and dependencies
to S3, and creates or updates the named Runtime. The Runtime execution role
needs access to the selected Bedrock model/inference profile. There is no
Docker, ECR, or CodeBuild step. Invocations use AWS IAM authentication.

`deploy.py` uses the pinned Python starter toolkit's direct-code deployment API
with Python 3.12. AWS now recommends its newer Node-based AgentCore CLI for new
features; this demo pins the Python toolkit to keep its deployment reproducible
and its dependencies in one Python environment.

Only `app/` is packaged. `.env` stays outside the bundle, and local AWS profile
credentials are never passed to the Runtime. The Oodle ingestion key is passed
as a Runtime environment variable, which is visible to principals who can read
the Runtime configuration. This is a demo setup; use your normal secret store
for a production deployment.

The deployment sets `enable_observability=True` so the Runtime passes trace
context in request headers, following the guide's approach. OTEL_* env vars
in `deploy.py` direct export to Oodle (instead of CloudWatch) for both the
programmatic code path and any ADOT auto-instrumentation the Runtime applies.

The generated configuration is `app/.bedrock_agentcore.yaml` (git-ignored).
Keep it for status, invocation, and cleanup. Change `AGENTCORE_AGENT_NAME` before
the first deployment if you need a separate demo; keep the same profile and
region for subsequent commands. `make deploy` updates that named Runtime.

## Inspect in Oodle

Open **Agent Observability → Traces** (`/genai/traces`), filter by service
`amazon-bedrock-agentcore-demo`, and find the trace ID returned by the invocation.
Both local and hosted runs use this service name. Expect the request span,
native Strands agent/model/tool spans, botocore auto-instrumented AWS SDK spans,
token counts, transcript, and errors.

`session.id` is propagated via OTel baggage and copied to every span by the
`BaggageSpanProcessor`.  Filter or group by `session.id` to see all turns
in a conversation (matching the guide's session-based querying pattern).

Each invocation constructs a fresh agent. Session IDs correlate traces but
do not enable conversation persistence or AgentCore Memory.

`CAPTURE_CONTENT=true` records fictional prompt/answer and tool content on spans.
Set it to `false` to redact those fields through native Strands configuration.
Token counts, timings, names, and tool errors remain. Custom exception messages
are not redacted. After changing `.env`, restart the local process or redeploy.

## Offline verification

```bash
make test
CAPTURE_CONTENT=false make test
```

The test calls the SDK's actual `/ping` and `/invocations` handlers, runs the real
Strands tools with stubbed Bedrock responses, and inspects gzip OTLP protobuf
received by a local HTTP server. It checks trace hierarchy, tokens, transcript,
redaction, tool errors, session.id baggage propagation, and Oodle auth headers
without contacting AWS or Oodle. Use `make invoke` and inspect its trace ID in
Oodle for live verification.

## Cleanup

Stop the local server with Ctrl-C. For the hosted deployment:

```bash
make tools-destroy  # Remove the tool policy before deleting the execution role.
.venv/bin/python manage.py destroy --dry-run
make destroy
```

The toolkit asks for confirmation and removes the Runtime, its deployment
artifacts, and its demo execution role. Inspect the reported warnings and
retained resources; shared deployment buckets or CloudWatch logs may remain.

If invocation is denied, check caller `bedrock-agentcore:InvokeAgentRuntime`
permission and Runtime readiness. If the model is denied, check the Runtime
execution role's Bedrock permissions and the selected model's region/access.
If traces are missing, inspect export errors in local output or Runtime logs,
and check the Oodle endpoint, instance, and ingestion key.

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

Agent runs contain native Strands `execute_tool` spans with child botocore
auto-instrumented SDK spans (DynamoDB, SSM) and native MCP SDK spans (`MCP send
initialize`, `MCP send tools/list`, `MCP send tools/call`). AWS request IDs,
service/operation, latency, and failures are recorded. MCP calls are native child
RPC spans, so they do not double-count the outer tool call. An MCP `isError`
result marks the enclosing tool span ERROR even if the RPC itself succeeded.
`CAPTURE_CONTENT=false` omits tool request/result content, including MCP content.
Exception text is not redacted.

`make test` checks the real AWS request shapes using botocore Stubber with ADOT
auto-instrumented spans and exercises the actual MCP SDK against a local JSON-RPC
HTTP server, including an MCP `isError` result, denied AWS requests, parent links,
and content capture on/off.

### Remove the tool resources

```bash
make tools-destroy
```

This prompts before deleting this demo's tool stack, including its fictional
orders and policy parameter. It does not delete resources supplied through the
existing-resource overrides. Tool resources are independent of agent deployment
and must be cleaned up separately.

## References

- [AgentCore observability guide](https://levantar.ai/insights/agentcore-07-observability.html) — the architecture this demo follows
- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-getting-started.html)
- [AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- [AWS Distro for OpenTelemetry — Python](https://aws-otel.github.io/docs/getting-started/python-sdk)
- [Strands tracing](https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/)
- [Python deployment API](https://github.com/aws/bedrock-agentcore-starter-toolkit/blob/main/src/bedrock_agentcore_starter_toolkit/notebook/runtime/bedrock_agentcore.py)
