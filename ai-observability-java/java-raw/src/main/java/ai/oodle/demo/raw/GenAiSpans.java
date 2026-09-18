package ai.oodle.demo.raw;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

import java.util.List;

/**
 * The whole point of this example: a thin wrapper that turns a raw HTTP call to an
 * LLM into a span Oodle can read.
 *
 * <p>Nothing here is specific to Anthropic or to java.net.http — if you call an LLM
 * over raw HTTP today, this is the shape of the change you need. The OpenTelemetry
 * GenAI semantic conventions are just attribute names on an ordinary span; the
 * expensive part is knowing <em>which</em> names, which is what this file records.
 *
 * <p>Attribute keys are plain strings rather than the semconv artifact's generated
 * constants so this compiles against any recent OpenTelemetry version — the GenAI
 * conventions are still experimental and the constants move between releases.
 */
final class GenAiSpans {

    // --- OpenTelemetry GenAI semantic conventions -------------------------------
    static final AttributeKey<String> OPERATION_NAME  = AttributeKey.stringKey("gen_ai.operation.name");
    static final AttributeKey<String> PROVIDER_NAME   = AttributeKey.stringKey("gen_ai.provider.name");
    static final AttributeKey<String> SYSTEM          = AttributeKey.stringKey("gen_ai.system");
    static final AttributeKey<String> REQUEST_MODEL   = AttributeKey.stringKey("gen_ai.request.model");
    static final AttributeKey<String> RESPONSE_MODEL  = AttributeKey.stringKey("gen_ai.response.model");
    static final AttributeKey<Long>   INPUT_TOKENS    = AttributeKey.longKey("gen_ai.usage.input_tokens");
    static final AttributeKey<Long>   OUTPUT_TOKENS   = AttributeKey.longKey("gen_ai.usage.output_tokens");
    static final AttributeKey<List<String>> FINISH_REASONS = AttributeKey.stringArrayKey("gen_ai.response.finish_reasons");
    static final AttributeKey<String> INPUT_MESSAGES  = AttributeKey.stringKey("gen_ai.input.messages");
    static final AttributeKey<String> OUTPUT_MESSAGES = AttributeKey.stringKey("gen_ai.output.messages");
    static final AttributeKey<String> SYSTEM_INSTRUCTIONS = AttributeKey.stringKey("gen_ai.system_instructions");
    static final AttributeKey<String> AGENT_NAME      = AttributeKey.stringKey("gen_ai.agent.name");
    static final AttributeKey<String> TOOL_NAME       = AttributeKey.stringKey("gen_ai.tool.name");

    private GenAiSpans() {}

    /**
     * Root span of an agent run. Everything the agent does — every LLM call, every
     * tool execution — hangs off this, which is what lets Oodle draw an agent graph
     * instead of a flat list of HTTP calls.
     */
    static Span startAgent(Tracer tracer, String agentName) {
        return tracer.spanBuilder("invoke_agent " + agentName)
                .setSpanKind(SpanKind.INTERNAL)
                .setAttribute(OPERATION_NAME, "invoke_agent")
                .setAttribute(AGENT_NAME, agentName)
                .setAttribute(PROVIDER_NAME, "anthropic")
                .setAttribute(SYSTEM, "anthropic")
                .startSpan();
    }

    /** One LLM call. Response attributes are filled in by {@link #endChat}. */
    static Span startChat(Tracer tracer, String model, String systemPrompt, String inputMessagesJson) {
        Span span = tracer.spanBuilder("chat " + model)
                .setSpanKind(SpanKind.CLIENT)
                .setAttribute(OPERATION_NAME, "chat")
                // gen_ai.provider.name is the current convention (semconv >= 1.36);
                // gen_ai.system is its older name. Setting both keeps the spans
                // readable by backends that have only adopted one of them.
                .setAttribute(PROVIDER_NAME, "anthropic")
                .setAttribute(SYSTEM, "anthropic")
                .setAttribute(REQUEST_MODEL, model)
                .startSpan();
        if (systemPrompt != null) {
            span.setAttribute(SYSTEM_INSTRUCTIONS, systemPrompt);
        }
        if (inputMessagesJson != null) {
            span.setAttribute(INPUT_MESSAGES, inputMessagesJson);
        }
        return span;
    }

    static void endChat(Span span, String responseModel, long inputTokens, long outputTokens,
                        String stopReason, String outputMessagesJson) {
        if (responseModel != null) {
            span.setAttribute(RESPONSE_MODEL, responseModel);
        }
        span.setAttribute(INPUT_TOKENS, inputTokens);
        span.setAttribute(OUTPUT_TOKENS, outputTokens);
        if (stopReason != null) {
            span.setAttribute(FINISH_REASONS, List.of(stopReason));
        }
        if (outputMessagesJson != null) {
            span.setAttribute(OUTPUT_MESSAGES, outputMessagesJson);
        }
        span.end();
    }

    /** One tool execution, as a child of the agent span. */
    static <T> T tool(Tracer tracer, String toolName, java.util.function.Supplier<T> body) {
        Span span = tracer.spanBuilder("execute_tool " + toolName)
                .setSpanKind(SpanKind.INTERNAL)
                .setAttribute(OPERATION_NAME, "execute_tool")
                .setAttribute(TOOL_NAME, toolName)
                .startSpan();
        try (Scope ignored = span.makeCurrent()) {
            return body.get();
        } catch (RuntimeException e) {
            span.recordException(e);
            throw e;
        } finally {
            span.end();
        }
    }
}
