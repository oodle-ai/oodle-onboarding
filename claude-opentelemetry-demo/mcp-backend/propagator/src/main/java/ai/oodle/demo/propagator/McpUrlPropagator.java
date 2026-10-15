package ai.oodle.demo.propagator;

import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.List;

/**
 * Reads a W3C traceparent from the {@code tp} query parameter of an
 * incoming HTTP request.
 *
 * <p>Anthropic's MCP connector sends a traceparent from its own connection
 * trace, so the MCP server's spans land in a trace that no session span is
 * part of. The app that creates the agent puts the session's traceparent
 * in the MCP URL instead. This propagator runs after the W3C one
 * ({@code OTEL_PROPAGATORS=tracecontext,baggage,mcpurl}), so a {@code tp}
 * parameter replaces the connector's parent and the server span joins the
 * session's trace. A request without {@code tp} keeps the header's parent.
 *
 * <p>The agent's server instrumentation passes its own request object as
 * the carrier and a getter that reads headers only, so the query string is
 * read from the carrier by reflection: {@code queryString()} on Tomcat's
 * coyote request, {@code getQueryString()} on a servlet request.
 */
public final class McpUrlPropagator implements TextMapPropagator {
    static final String PARAM = "tp";
    private static final String TRACEPARENT = "traceparent";

    private static final TextMapGetter<String> VALUE_AS_TRACEPARENT = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(String carrier) {
            return List.of(TRACEPARENT);
        }

        @Override
        public String get(String carrier, String key) {
            return TRACEPARENT.equals(key) ? carrier : null;
        }
    };

    @Override
    public Collection<String> fields() {
        // Extract only: the app writes the parameter into the URL itself.
        return List.of();
    }

    @Override
    public <C> void inject(Context context, C carrier, io.opentelemetry.context.propagation.TextMapSetter<C> setter) {
        // Extract only.
    }

    @Override
    public <C> Context extract(Context context, C carrier, TextMapGetter<C> getter) {
        if (carrier == null) {
            return context;
        }
        String traceparent = param(queryString(carrier), PARAM);
        if (traceparent == null) {
            return context;
        }
        return W3CTraceContextPropagator.getInstance().extract(context, traceparent, VALUE_AS_TRACEPARENT);
    }

    static String queryString(Object carrier) {
        for (String method : new String[] {"queryString", "getQueryString"}) {
            try {
                Object value = carrier.getClass().getMethod(method).invoke(carrier);
                if (value != null) {
                    String s = value.toString();
                    return s.isEmpty() ? null : s;
                }
            } catch (ReflectiveOperationException | RuntimeException ignored) {
                // Not this carrier type; try the next accessor.
            }
        }
        return null;
    }

    static String param(String query, String name) {
        if (query == null) {
            return null;
        }
        for (String pair : query.split("&")) {
            int eq = pair.indexOf('=');
            if (eq > 0 && pair.substring(0, eq).equals(name)) {
                return URLDecoder.decode(pair.substring(eq + 1), StandardCharsets.UTF_8);
            }
        }
        return null;
    }
}
