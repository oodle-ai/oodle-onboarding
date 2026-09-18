package ai.oodle.demo.raw;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Anthropic Messages API over the JDK's built-in HttpClient — no vendor SDK, no
 * framework. This is the "before" state most teams are actually in; the only thing
 * added is the {@link GenAiSpans} wrapper around the call.
 */
final class AnthropicRawClient {

    private static final String ANTHROPIC_VERSION = "2023-06-01";
    private static final ObjectMapper JSON = new ObjectMapper();

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final String baseUrl;
    private final String apiKey;
    private final String model;
    private final Tracer tracer;

    AnthropicRawClient(String baseUrl, String apiKey, String model, Tracer tracer) {
        this.baseUrl = baseUrl;
        this.apiKey = apiKey;
        this.model = model;
        this.tracer = tracer;
    }

    /**
     * One turn of the conversation. {@code messages} is the running history and
     * {@code tools} the tool definitions, both in Anthropic wire format.
     *
     * <p>The span is opened before the request and closed after the response is
     * parsed, so its duration is the real latency of the call and its attributes
     * carry the token usage the response reports.
     */
    JsonNode createMessage(ArrayNode messages, ArrayNode tools, String systemPrompt) throws Exception {
        ObjectNode body = JSON.createObjectNode();
        body.put("model", model);
        body.put("max_tokens", 1024);
        body.put("system", systemPrompt);
        body.set("messages", messages);
        body.set("tools", tools);

        Span span = GenAiSpans.startChat(tracer, model, systemPrompt, messages.toString());
        try (Scope ignored = span.makeCurrent()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/v1/messages"))
                    .timeout(Duration.ofSeconds(120))
                    .header("content-type", "application/json")
                    .header("x-api-key", apiKey)
                    .header("anthropic-version", ANTHROPIC_VERSION)
                    .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
                    .build();

            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                // Ending the span is left to the catch block below, so it happens
                // exactly once on every path out of this method.
                throw new IllegalStateException(
                        "Anthropic API returned HTTP " + response.statusCode() + ": " + response.body());
            }

            JsonNode parsed = JSON.readTree(response.body());
            JsonNode usage = parsed.path("usage");
            GenAiSpans.endChat(
                    span,
                    parsed.path("model").asText(null),
                    usage.path("input_tokens").asLong(0),
                    usage.path("output_tokens").asLong(0),
                    parsed.path("stop_reason").asText(null),
                    parsed.path("content").toString());
            return parsed;
        } catch (Exception e) {
            span.recordException(e);
            span.setStatus(StatusCode.ERROR, e.getMessage());
            span.end();
            throw e;
        }
    }

    static ObjectMapper json() {
        return JSON;
    }
}
