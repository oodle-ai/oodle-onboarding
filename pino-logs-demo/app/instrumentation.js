'use strict';

// Optional: correlate logs with traces. The HTTP instrumentation
// opens a span per request, and the Pino instrumentation writes
// that span's trace_id and span_id on every log line inside it.
// The OTLP transport then carries them as the record's trace
// context, so Oodle links each log to its trace.
//
// Loaded with `node --require ./instrumentation.js` so the
// modules are patched before server.js requires them.
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-proto');
const { registerInstrumentations } = require('@opentelemetry/instrumentation');
const { HttpInstrumentation } = require('@opentelemetry/instrumentation-http');
const { PinoInstrumentation } = require('@opentelemetry/instrumentation-pino');
const { resourceFromAttributes } = require('@opentelemetry/resources');
const { BatchSpanProcessor } = require('@opentelemetry/sdk-trace-base');
const { NodeTracerProvider } = require('@opentelemetry/sdk-trace-node');
const { ATTR_SERVICE_NAME } = require('@opentelemetry/semantic-conventions');

const provider = new NodeTracerProvider({
  // NodeTracerProvider does not read OTEL_SERVICE_NAME; without a
  // resource every trace lands under unknown_service:node.
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'pino-logs-demo',
  }),
  spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter())],
});
provider.register();

registerInstrumentations({
  instrumentations: [
    new HttpInstrumentation(),
    // Only the log-correlation half is wanted: the transport already
    // exports the records, so a second log sender would double them.
    new PinoInstrumentation({ disableLogSending: true }),
  ],
});

process.on('SIGTERM', () => provider.shutdown());
