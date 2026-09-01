import { OTLPHttpProtoTraceExporter } from '@vercel/otel';
import { otelIntegration } from 'eve/instrumentation/otel';

// eve wraps the exporter in its own batching processor and
// names the service after the agent, so there is no tracer
// provider or resource to build here.
export default otelIntegration({
  traceExporter: new OTLPHttpProtoTraceExporter({
    // The path is explicit: this option is the full URL.
    url: `${process.env.OODLE_OTLP_ENDPOINT}/v1/traces`,
  }),
});
