package ai.oodle.demo.raw;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.autoconfigure.AutoConfiguredOpenTelemetrySdk;

/**
 * Plain Java program — no framework — calling Claude over raw HTTP and running a
 * one-tool agent loop.
 *
 * <p>OpenTelemetry is configured from the standard OTEL_* environment variables
 * (OTEL_SERVICE_NAME, OTEL_EXPORTER_OTLP_ENDPOINT), so the wiring here is three
 * lines; all the GenAI-specific work lives in {@link GenAiSpans}.
 */
public final class Main {

    private static final String SYSTEM_PROMPT =
            "You are a concise weather assistant. Use the get_weather tool when asked about "
          + "weather, then answer in one short sentence.";

    private static final String USER_PROMPT =
            "What's the weather in Paris right now, and should I take an umbrella?";

    public static void main(String[] args) throws Exception {
        String apiKey = requireEnv("ANTHROPIC_API_KEY");
        String model = envOrDefault("ANTHROPIC_MODEL", "claude-sonnet-5");
        String baseUrl = envOrDefault("ANTHROPIC_BASE_URL", "https://api.anthropic.com");

        // Reads OTEL_SERVICE_NAME / OTEL_EXPORTER_OTLP_ENDPOINT from the environment.
        OpenTelemetrySdk sdk = AutoConfiguredOpenTelemetrySdk.initialize().getOpenTelemetrySdk();
        Tracer tracer = sdk.getTracer("ai.oodle.demo.raw");

        int iterations = Integer.parseInt(envOrDefault("ITERATIONS", "1"));
        long intervalMs = Long.parseLong(envOrDefault("INTERVAL_MS", "15000"));

        try {
            for (int i = 0; i < iterations || iterations <= 0; i++) {
                try {
                    String answer = runAgent(tracer, new AnthropicRawClient(baseUrl, apiKey, model, tracer));
                    System.out.println("[java-raw] " + answer);
                } catch (Exception e) {
                    System.err.println("[java-raw] run failed: " + e.getMessage());
                }
                if (iterations <= 0 || i < iterations - 1) {
                    Thread.sleep(intervalMs);
                }
            }
        } finally {
            // A short-lived process must flush before it exits, or the last batch of
            // spans dies with it.
            sdk.close();
        }
    }

    /** chat -> tool_use -> tool result -> chat, all under one agent span. */
    private static String runAgent(Tracer tracer, AnthropicRawClient client) throws Exception {
        ObjectMapper json = AnthropicRawClient.json();
        Span agent = GenAiSpans.startAgent(tracer, "weather-agent");

        try (Scope ignored = agent.makeCurrent()) {
            ArrayNode tools = json.createArrayNode();
            tools.add(weatherToolDefinition(json));

            ArrayNode messages = json.createArrayNode();
            messages.add(json.createObjectNode().put("role", "user").put("content", USER_PROMPT));

            JsonNode response = client.createMessage(messages, tools, SYSTEM_PROMPT);

            // Turn 2 only happens if Claude actually asked for the tool.
            if ("tool_use".equals(response.path("stop_reason").asText())) {
                messages.add(json.createObjectNode()
                        .put("role", "assistant")
                        .set("content", response.path("content")));

                ArrayNode toolResults = json.createArrayNode();
                for (JsonNode block : response.path("content")) {
                    if (!"tool_use".equals(block.path("type").asText())) {
                        continue;
                    }
                    String toolName = block.path("name").asText();
                    String location = block.path("input").path("location").asText("unknown");
                    String result = GenAiSpans.tool(tracer, toolName, () -> getWeather(location));

                    toolResults.add(json.createObjectNode()
                            .put("type", "tool_result")
                            .put("tool_use_id", block.path("id").asText())
                            .put("content", result));
                }
                messages.add(json.createObjectNode().put("role", "user").set("content", toolResults));

                response = client.createMessage(messages, tools, SYSTEM_PROMPT);
            }

            return firstText(response);
        } finally {
            agent.end();
        }
    }

    /** Stand-in for a real weather service — the demo is about the telemetry, not the data. */
    private static String getWeather(String location) {
        return "18C, light rain, 80% humidity in " + location;
    }

    private static ObjectNode weatherToolDefinition(ObjectMapper json) {
        ObjectNode location = json.createObjectNode()
                .put("type", "string")
                .put("description", "City name");
        ObjectNode properties = json.createObjectNode();
        properties.set("location", location);

        ObjectNode schema = json.createObjectNode();
        schema.put("type", "object");
        schema.set("properties", properties);
        schema.set("required", json.createArrayNode().add("location"));

        ObjectNode tool = json.createObjectNode();
        tool.put("name", "get_weather");
        tool.put("description", "Get the current weather for a location");
        tool.set("input_schema", schema);
        return tool;
    }

    private static String firstText(JsonNode response) {
        for (JsonNode block : response.path("content")) {
            if ("text".equals(block.path("type").asText())) {
                return block.path("text").asText();
            }
        }
        return "(no text in response)";
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " is not set");
        }
        return value;
    }

    private static String envOrDefault(String name, String fallback) {
        String value = System.getenv(name);
        return (value == null || value.isBlank()) ? fallback : value;
    }
}
