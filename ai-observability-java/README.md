# Java — LLM & agent telemetry to Oodle

Three Java applications calling Claude, each instrumented a different way, all
emitting [OpenTelemetry GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
(`gen_ai.*`) spans to Oodle. They run the same one-tool agent against the same
prompt, so the three traces are directly comparable in the UI.

| Service | Framework | Who writes the `gen_ai.*` attributes | Use when |
|---|---|---|---|
| [java-raw](java-raw) | none — JDK `HttpClient` | your own wrapper (~110 lines, [`GenAiSpans.java`](java-raw/src/main/java/ai/oodle/demo/raw/GenAiSpans.java)) | you call the LLM API directly and can't adopt a framework yet |
| [java-langchain4j](java-langchain4j) | LangChain4j | `langchain4j-observation` | plain Java, Quarkus, Micronaut — anything not Spring |
| [java-spring-ai](java-spring-ai) | Spring Boot 3.5 + Spring AI 1.0 | Spring Boot autoconfiguration | you're on Spring |

All three additionally open two **structural** spans by hand — an `invoke_agent`
root and an `execute_tool` child. See [The agent graph](#the-agent-graph) for why.

## Quick start

```bash
cp .env.example .env     # then fill in your Oodle + Anthropic credentials
make up
make logs
```

Traces appear in Oodle under **AI Observability**, one service per app.
`make chat` sends an ad-hoc request to the Spring app on `:8094`.

## Which one should I copy?

**If you're on Spring, use Spring AI.** It's the Spring-portfolio option, it's on
start.spring.io, and instrumentation is three dependencies and zero lines of code.
Note the version constraint: Spring AI 2.x requires Spring Boot 4, so this demo
pins Boot 3.5 + Spring AI 1.0 — the combination most Spring shops can actually run
today.

**If you're not on Spring, use LangChain4j.** It's the only mature option off
Spring, and `langchain4j-observation` gives you the same attributes through
Micrometer.

**Use the raw wrapper only as a stepping stone.** It exists because rewriting onto
a framework is a bigger change than most teams want to make first. It works, and
it's honest about what it costs: you own those attribute names forever, and the
GenAI conventions are still experimental.

## What each app actually does

### java-raw

`java.net.http.HttpClient` POSTing to `/v1/messages`, exactly as before, with
[`GenAiSpans`](java-raw/src/main/java/ai/oodle/demo/raw/GenAiSpans.java) wrapped
around the call. The wrapper is the deliverable — it's the minimum change that
makes an existing raw-HTTP integration visible to Oodle.

Without it you get a span named `POST` carrying `http.request.method` and
`url.full` and nothing else. Oodle's AI tiles read `gen_ai.*`, so an
uninstrumented call is invisible to them no matter how much HTTP telemetry the
agent collects.

OpenTelemetry is configured from the standard `OTEL_*` environment variables via
`AutoConfiguredOpenTelemetrySdk`, so the SDK wiring is one line.

### java-langchain4j

```java
AnthropicChatModel.builder()
    .apiKey(apiKey)
    .modelName(model)
    .listeners(new ObservationChatModelListener(observationRegistry, meterRegistry))
    .build();
```

That listener is the entire LLM instrumentation. It implements LangChain4j's
`ChatModelListener` over Micrometer's Observation API and sets
`gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.system`,
`gen_ai.request.model`, `gen_ai.response.model` and token usage itself.

The only wiring this app owns is
[`Tracing.java`](java-langchain4j/src/main/java/ai/oodle/demo/lc4j/Tracing.java) —
15 lines bridging Micrometer Observations onto the OpenTelemetry tracer, which
Spring Boot would have done for you.

`langchain4j-observation` is marked `@Experimental` and is published as a beta
artifact (`1.20.0-beta30` against LangChain4j `1.20.0`). Pin it.

### java-spring-ai

Three dependencies — `spring-ai-starter-model-anthropic`,
`spring-boot-starter-actuator`, `micrometer-tracing-bridge-otel` — plus an
endpoint in `application.yaml`. No instrumentation code at all. Spring AI records
a Micrometer observation for every `ChatClient` call and Boot's OTel bridge turns
it into a span.

Prompt and completion capture is off by default (they can be large and
sensitive); this demo turns it on:

```yaml
spring.ai.chat.observations:
  log-prompt: true
  log-completion: true
```

The app exposes `POST /chat?q=...` and also drives itself on a timer so the demo
produces traces unattended.

## The agent graph

Every instrumentation option above covers **LLM calls only**. LangChain4j's
listener hooks `ChatModelListener`; Spring AI observes `ChatClient`. Neither sees
your tool bodies, and neither opens a root span for the agent run as a whole.

Without those, a two-turn agent produces two sibling chat spans with no visible
relationship. So all three apps open two spans by hand:

| Span | Attributes |
|---|---|
| `invoke_agent weather-agent` | `gen_ai.operation.name=invoke_agent`, `gen_ai.agent.name` |
| `execute_tool get_weather` | `gen_ai.operation.name=execute_tool`, `gen_ai.tool.name` |

That's four attribute names total, and they're structural — nothing about the
model, the prompt, or token usage is hand-written in the two framework apps.

Quarkus LangChain4j is the exception: it ships its own AiService-level
instrumentation and produces the root and tool spans for you.

## Note on Langfuse

Langfuse has no Java tracing SDK. [`langfuse-java`](https://github.com/langfuse/langfuse-java)
is an auto-generated client for the REST API and cannot record traces, spans, or
generations — there is no Java equivalent of `@langfuse/tracing`'s
`setLangfuseTracerProvider`. Langfuse's own guidance for Java is to use
OpenTelemetry and point OTLP at an endpoint, which is exactly what these three
apps do.

If you want the spans in Langfuse as well as Oodle, that's a collector change,
not an application change — add a second `otlphttp` exporter pointed at
Langfuse's OTLP endpoint and list it alongside `otlphttp/oodle` in the traces
pipeline.

## Other options considered

| Option | Why not |
|---|---|
| OpenLLMetry / Traceloop | No Java SDK — Python, TypeScript and Go only |
| OpenInference Java | Published only as `0.1.0-SNAPSHOT`, and emits `llm.*`, not `gen_ai.*` |
| OTel Java agent | Has an `openai` instrumentation module, but nothing for Anthropic |
| `langchain4j-otel` | A single-maintainer community Spring Boot starter |
| openai-java against Anthropic's OpenAI-compatible endpoint | Zero-code, but recommending a compatibility shim to reach Claude is bad architecture |

## Configuration

| Variable | Purpose |
|---|---|
| `OODLE_INSTANCE`, `OODLE_API_KEY` | Collector → Oodle export |
| `ANTHROPIC_API_KEY` | Claude API |
| `ANTHROPIC_MODEL` | Defaults to `claude-sonnet-5` |
| `ITERATIONS` | `0` runs forever (the two plain-Java apps) |
| `INTERVAL_MS` | Delay between runs |

The collector exports with `compression: gzip` — GenAI spans carry whole prompts
and a batch is bounded by span count rather than bytes, so an uncompressed export
can exceed the ingress body limit and be refused.
