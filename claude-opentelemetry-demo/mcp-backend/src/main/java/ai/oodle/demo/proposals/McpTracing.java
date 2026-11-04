package ai.oodle.demo.proposals;

import com.fasterxml.jackson.databind.JsonNode;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanBuilder;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapGetter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

/**
 * Joins an MCP request to the agent's trace. Off unless MCP_TRACE_CONTEXT is
 * true, because this sub-demo's default is to keep the reference backend's
 * gaps.
 *
 * <p>Anthropic's MCP connector sends the agent's trace context in the
 * JSON-RPC body, as {@code params._meta.traceparent}, and not as an HTTP
 * header. The Java agent reads headers only, and it starts the
 * {@code POST /mcp} span before the body is parsed, so that span can't join
 * the trace. This class starts a second server span from {@code _meta}, with
 * a link back to {@code POST /mcp}. The handler runs inside it, so its SQL and
 * model calls are in the agent's trace.
 *
 * <p>The span has no {@code gen_ai.operation.name}: the agent's
 * {@code anthropic.mcp_tool_use} span is already the {@code execute_tool}
 * span for this call, and a second one would count the call twice.
 */
@Component
public class McpTracing {
    private static final TextMapGetter<JsonNode> META = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(JsonNode meta) {
            List<String> keys = new ArrayList<>();
            meta.fieldNames().forEachRemaining(keys::add);
            return keys;
        }

        @Override
        public String get(JsonNode meta, String key) {
            JsonNode value = meta == null ? null : meta.get(key);
            return value == null ? null : value.asText();
        }
    };

    private final Tracer tracer = GlobalOpenTelemetry.getTracer("ai.oodle.demo.mcp");
    private final boolean enabled;

    public McpTracing(@Value("${MCP_TRACE_CONTEXT:false}") boolean enabled) {
        this.enabled = enabled;
    }

    /** Runs the handler in the caller's trace, when the request names one. */
    public <T> T inCallerTrace(JsonNode payload, HttpHeaders headers, Callable<T> handler) throws Exception {
        JsonNode params = payload.path("params");
        JsonNode meta = params.path("_meta");
        if (!enabled || !meta.has("traceparent")) {
            return handler.call();
        }
        Span span = span(payload, params, headers, GlobalOpenTelemetry.getPropagators()
                .getTextMapPropagator().extract(Context.current(), meta, META));
        try (Scope ignored = span.makeCurrent()) {
            return handler.call();
        } catch (Exception e) {
            span.setStatus(StatusCode.ERROR, e.getMessage());
            span.recordException(e);
            throw e;
        } finally {
            span.end();
        }
    }

    private Span span(JsonNode payload, JsonNode params, HttpHeaders headers, Context caller) {
        String method = payload.path("method").asText();
        String tool = params.path("name").asText();
        SpanBuilder span = tracer.spanBuilder(tool.isEmpty() ? method : method + " " + tool)
                .setParent(caller)
                .setSpanKind(SpanKind.SERVER)
                .addLink(Span.current().getSpanContext())
                .setAttribute("mcp.method.name", method)
                .setAttribute("jsonrpc.request.id", payload.path("id").asText());
        if (!tool.isEmpty()) {
            span.setAttribute("gen_ai.tool.name", tool);
        }
        String mcpSession = headers.getFirst("Mcp-Session-Id");
        if (mcpSession != null) {
            span.setAttribute("mcp.session.id", mcpSession);
        }
        String agentSession = headers.getFirst("X-Anthropic-Cma-Session-Id");
        if (agentSession != null) {
            span.setAttribute("anthropic.session.id", agentSession);
        }
        return span.startSpan();
    }
}
