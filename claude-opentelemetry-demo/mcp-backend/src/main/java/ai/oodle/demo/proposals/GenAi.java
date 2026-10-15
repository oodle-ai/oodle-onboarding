package ai.oodle.demo.proposals;

import com.fasterxml.jackson.databind.JsonNode;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * The firm's own model wrapper, traced by hand the way the reference
 * backend's wrapper is: an {@code ai.model.request <model>} span around a
 * {@code chat <model>} CLIENT span with the gen_ai.* attributes, under its
 * own instrumentation scope.
 *
 * Deliberate gaps, as in the reference: no prompt or response on the span,
 * and no agent name, conversation id or user id. A tool call that the
 * model asks for is not traced here either; see {@link ChatController}.
 */
@Component
public class GenAi {
    private static final AttributeKey<List<String>> FINISH_REASONS =
            AttributeKey.stringArrayKey("gen_ai.response.finish_reasons");

    private final Tracer tracer = GlobalOpenTelemetry.getTracer("ai.oodle.demo.genai");
    private final AnthropicApi api;

    public GenAi(AnthropicApi api) {
        this.api = api;
    }

    public JsonNode chat(String model, int maxTokens, Map<String, Object> request) {
        Span outer = tracer.spanBuilder("ai.model.request " + model)
                .setAttribute("ai.model.name", model)
                .setAttribute("ai.model.cache.mode", "NO_READ_CACHE")
                .startSpan();
        try (Scope ignored = outer.makeCurrent()) {
            Span chat = tracer.spanBuilder("chat " + model)
                    .setSpanKind(SpanKind.CLIENT)
                    .setAttribute("gen_ai.operation.name", "chat")
                    .setAttribute("gen_ai.provider.name", "anthropic")
                    .setAttribute("gen_ai.system", "anthropic")
                    .setAttribute("gen_ai.request.model", model)
                    .setAttribute("gen_ai.request.max_tokens", (long) maxTokens)
                    .startSpan();
            try (Scope inner = chat.makeCurrent()) {
                Map<String, Object> body = new java.util.HashMap<>(request);
                body.put("model", model);
                body.put("max_tokens", maxTokens);
                JsonNode resp = api.messages(body);
                JsonNode usage = resp.path("usage");
                chat.setAttribute("gen_ai.response.model", resp.path("model").asText(model));
                chat.setAttribute(FINISH_REASONS, List.of(resp.path("stop_reason").asText("")));
                chat.setAttribute("gen_ai.usage.input_tokens", usage.path("input_tokens").asLong());
                chat.setAttribute("gen_ai.usage.output_tokens", usage.path("output_tokens").asLong());
                chat.setAttribute("gen_ai.usage.cache_read.input_tokens",
                        usage.path("cache_read_input_tokens").asLong());
                return resp;
            } catch (RuntimeException e) {
                chat.setStatus(StatusCode.ERROR);
                chat.recordException(e);
                throw e;
            } finally {
                chat.end();
            }
        } finally {
            outer.end();
        }
    }

    /** The text blocks of a Messages response, joined. */
    public static String text(JsonNode resp) {
        StringBuilder sb = new StringBuilder();
        for (JsonNode block : resp.path("content")) {
            if ("text".equals(block.path("type").asText())) {
                sb.append(block.path("text").asText());
            }
        }
        return sb.toString();
    }
}
