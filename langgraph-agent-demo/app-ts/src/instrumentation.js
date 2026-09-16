'use strict';

// Loaded with `node --require`, so @langchain/core and http are
// patched before server.js requires them.
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-proto');
const { registerInstrumentations } = require('@opentelemetry/instrumentation');
const { HttpInstrumentation } = require('@opentelemetry/instrumentation-http');
const { resourceFromAttributes } = require('@opentelemetry/resources');
const { BatchSpanProcessor } = require('@opentelemetry/sdk-trace-base');
const { NodeTracerProvider } = require('@opentelemetry/sdk-trace-node');
const { ATTR_SERVICE_NAME } = require('@opentelemetry/semantic-conventions');
const { LangChainInstrumentation } = require('@traceloop/instrumentation-langchain');

const provider = new NodeTracerProvider({
  // NodeTracerProvider does not read OTEL_SERVICE_NAME; without a
  // resource every trace lands under unknown_service:node.
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'langgraph-agent-demo-ts',
  }),
  spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter())],
});
provider.register();

registerInstrumentations({
  instrumentations: [
    // The LangChain instrumentation starts every span under the span
    // that is active at the time. The request span from the HTTP
    // instrumentation is that span here, so one request is one trace
    // with no manual span in the handler.
    new HttpInstrumentation(),
    new LangChainInstrumentation(),
  ],
});

process.on('SIGTERM', () => provider.shutdown());
