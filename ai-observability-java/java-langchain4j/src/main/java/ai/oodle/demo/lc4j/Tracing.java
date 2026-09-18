package ai.oodle.demo.lc4j;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.otel.bridge.OtelCurrentTraceContext;
import io.micrometer.tracing.otel.bridge.OtelTracer;
import io.opentelemetry.sdk.OpenTelemetrySdk;

/**
 * The only observability wiring this application needs.
 *
 * <p>LangChain4j speaks Micrometer's Observation API; Oodle speaks OpenTelemetry.
 * Micrometer's OTel bridge joins the two, and from then on every
 * {@code gen_ai.*} attribute is produced by {@code langchain4j-observation} —
 * this application never names one.
 */
final class Tracing {

    private Tracing() {}

    static ObservationRegistry observationRegistry(OpenTelemetrySdk sdk) {
        OtelTracer bridgedTracer = new OtelTracer(
                sdk.getTracer("ai.oodle.demo.lc4j"),
                new OtelCurrentTraceContext(),
                event -> { /* no event bus in a plain Java app */ });

        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
                .observationHandler(new DefaultTracingObservationHandler(bridgedTracer));
        return registry;
    }

    static MeterRegistry meterRegistry() {
        // langchain4j-observation also records gen_ai token/duration histograms.
        // They are not exported here — Oodle reads the spans — but the listener
        // requires a registry to write them to.
        return new SimpleMeterRegistry();
    }
}
