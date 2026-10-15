package ai.oodle.demo.propagator;

import io.opentelemetry.context.propagation.TextMapPropagator;
import io.opentelemetry.sdk.autoconfigure.spi.ConfigProperties;
import io.opentelemetry.sdk.autoconfigure.spi.ConfigurablePropagatorProvider;

/** Registers {@link McpUrlPropagator} under the name {@code mcpurl} for OTEL_PROPAGATORS. */
public final class McpUrlPropagatorProvider implements ConfigurablePropagatorProvider {
    @Override
    public TextMapPropagator getPropagator(ConfigProperties config) {
        return new McpUrlPropagator();
    }

    @Override
    public String getName() {
        return "mcpurl";
    }
}
