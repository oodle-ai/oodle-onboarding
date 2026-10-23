# Amazon Bedrock AgentCore → Oodle

A Python Strands order-support agent served by `BedrockAgentCoreApp`, runnable
locally or deployed to managed AgentCore Runtime. It calls Amazon Bedrock and
exports its native agent/model/tool traces directly to Oodle.

```text
Client → AgentCore Runtime → Strands agent → Bedrock Converse
                                ├─ lookup_order
                                └─ get_return_policy
                                └─ OpenTelemetry → Oodle
```

## Run locally first

Requires [uv](https://docs.astral.sh/uv/) (which installs Python 3.12), an AWS profile with Bedrock model invocation access,
and an Oodle data-ingestion key.

```bash
cd amazon/bedrock-agentcore
cp .env.example .env
# Set AWS_PROFILE, AWS_REGION, OODLE_INSTANCE, and OODLE_API_KEY.
# Set OODLE_OTLP_ENDPOINT to the base URL from your integration if needed.
make setup
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
make status
make invoke
```

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

The generated configuration is `app/.bedrock_agentcore.yaml` (git-ignored).
Keep it for status, invocation, and cleanup. Change `AGENTCORE_AGENT_NAME` before
the first deployment if you need a separate demo; keep the same profile and
region for subsequent commands. `make deploy` updates that named Runtime.

## Inspect in Oodle

Open **Agent Observability → Traces** (`/genai/traces`), filter by service
`amazon-bedrock-agentcore-demo`, and find the trace ID returned by the invocation.
Both local and hosted runs use this service name. Expect the request span,
native Strands agent/model/tool spans, token counts, transcript, and errors.
`session.id` and `gen_ai.conversation.id` use the Runtime's session ID.

Each invocation constructs a fresh agent. Session IDs correlate traces but
do not enable conversation persistence or AgentCore Memory.

The deployment sets `enable_observability=False` in the starter toolkit to prevent its
ADOT auto-instrumentation from installing a second tracer provider. The app
installs its own Oodle OTLP/HTTP exporter and keeps Strands' native spans.
It flushes before returning because Runtime may suspend after the response.
This exports application traces; it does not enable CloudWatch ingestion,
AgentCore infrastructure metrics, or other managed AgentCore features.

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
redaction, tool errors, and Oodle auth headers without contacting AWS or Oodle.
Use `make invoke` and inspect its trace ID in Oodle for live verification.

## Cleanup

Stop the local server with Ctrl-C. For the hosted deployment:

```bash
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

References: [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-getting-started.html),
[Strands tracing](https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/),
[Python deployment API](https://github.com/aws/bedrock-agentcore-starter-toolkit/blob/main/src/bedrock_agentcore_starter_toolkit/notebook/runtime/bedrock_agentcore.py).
