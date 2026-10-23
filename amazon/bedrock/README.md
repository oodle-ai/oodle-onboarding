# Amazon Bedrock → Oodle

A Python Strands agent uses Amazon Bedrock Converse to answer order-support
questions. Its real model and tool spans go directly to Oodle over OTLP/HTTP.
No collector or AWS infrastructure deployment is required.

```text
CLI → Strands agent → Bedrock Converse (Amazon Nova Lite)
          ├─ lookup_order
          └─ get_return_policy
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
   ├─ execute_tool lookup_order
   ├─ execute_tool get_return_policy
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
Strands agent and both tools, and captures real gzip-compressed OTLP protobuf
requests on localhost. It checks parent links, token usage, transcript/redaction,
error spans, exporter headers, and duplicate exports. It makes no AWS or Oodle
calls. A passing check is not proof of live ingestion; verify the printed trace
ID in Oodle after `make demo`.

For `AccessDeniedException`, check the AWS profile, model access, inference-profile
permissions, and any cross-region restrictions. For OTLP HTTP 401/403, check the
Oodle instance and ingestion key; for connection errors, check the endpoint.
There are no persistent services to stop or cloud resources to delete.

References: [Strands tracing](https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/),
[Bedrock client-side tool use](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html).
