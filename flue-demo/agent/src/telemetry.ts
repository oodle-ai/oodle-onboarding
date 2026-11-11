/**
 * OpenTelemetry for the Flue agents in this process.
 *
 * Import this module first in app.ts. It configures the OpenTelemetry
 * SDK, then registers Flue's instrumentation, which turns every agent
 * run, model turn, tool call and delegated task into a GenAI span.
 *
 * The exporters read the standard OTEL_EXPORTER_OTLP_* variables, so
 * the same code exports to a local OTel Collector or straight to Oodle.
 *
 * Only traces are exported. Oodle derives the token, cost and latency
 * metrics from the GenAI spans at ingest, so Flue's own GenAI metrics
 * would repeat them. With no meter given, Flue records them on the
 * no-op global meter.
 */
import { createOpenTelemetryInstrumentation } from '@flue/opentelemetry';
import { instrument } from '@flue/runtime';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { BatchSpanProcessor, NodeTracerProvider } from '@opentelemetry/sdk-trace-node';

// NodeTracerProvider does not read OTEL_SERVICE_NAME. Without an
// explicit resource, every trace lands under `unknown_service:node`.
const resource = resourceFromAttributes({
  'service.name': process.env.OTEL_SERVICE_NAME ?? 'flue-agent',
});

const tracerProvider = new NodeTracerProvider({
  resource,
  spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter())],
});
// Flue parents its own spans, so it needs only the tracer passed below.
// register() is for the spans your own code starts: it makes this the
// global provider and installs the async context manager, so a span
// started inside a tool (an HTTP call, a database query) joins the
// agent's trace under that tool. Without it, those spans are not sent.
tracerProvider.register();

// Content (prompts, replies, tool arguments and results) is on by
// default. Set FLUE_TRACE_CONTENT=false to send spans without it.
const content = process.env.FLUE_TRACE_CONTENT === 'false' ? false : undefined;

instrument(
  createOpenTelemetryInstrumentation({
    tracer: tracerProvider.getTracer('@flue/opentelemetry'),
    content,
  }),
);

// The batch processor holds the spans of the latest turns until its
// next export, so flush when the container stops. The Flue server owns
// the process exit: it drains active work and then exits, so this
// listener only flushes and must not call process.exit itself.
for (const signal of ['SIGTERM', 'SIGINT'] as const) {
  process.on(signal, () => {
    void tracerProvider.forceFlush();
  });
}
