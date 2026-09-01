import { OpenTelemetry } from '@ai-sdk/otel';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions';
import { registerTelemetry } from 'ai';

// NodeTracerProvider does not read OTEL_SERVICE_NAME, so name the
// service here or every trace lands under unknown_service:node.
export const provider = new NodeTracerProvider({
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: 'vercel-ai-sdk-demo',
  }),
  spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter())],
});

provider.register();

// AI SDK 7 moved OpenTelemetry out of the `ai` package into
// @ai-sdk/otel. Registering the integration turns telemetry on for
// every call: there is no per-call experimental_telemetry flag any
// more, and passing one traces nothing.
registerTelemetry(new OpenTelemetry());
