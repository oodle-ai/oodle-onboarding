package ai.oodle.demo.lc4j;

import dev.langchain4j.model.anthropic.AnthropicChatModel;
import dev.langchain4j.observation.listener.ObservationChatModelListener;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.service.SystemMessage;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.autoconfigure.AutoConfiguredOpenTelemetrySdk;

/**
 * Plain Java program — no Spring, no Quarkus — using LangChain4j.
 *
 * <p>Contrast with java-raw: there is no GenAiSpans class here. The
 * {@code gen_ai.*} attributes on the LLM spans come from
 * {@code langchain4j-observation}, which implements ChatModelListener over
 * Micrometer's Observation API. This application only supplies the structural
 * spans the listener cannot see: the agent root and the tool execution.
 */
public final class Main {

    interface WeatherAssistant {
        @SystemMessage("You are a concise weather assistant. Use the get_weather tool when asked "
                     + "about weather, then answer in one short sentence.")
        String ask(String question);
    }

    private static final String USER_PROMPT =
            "What's the weather in Paris right now, and should I take an umbrella?";

    public static void main(String[] args) throws Exception {
        String apiKey = requireEnv("ANTHROPIC_API_KEY");
        String model = envOrDefault("ANTHROPIC_MODEL", "claude-sonnet-5");

        OpenTelemetrySdk sdk = AutoConfiguredOpenTelemetrySdk.initialize().getOpenTelemetrySdk();
        Tracer tracer = sdk.getTracer("ai.oodle.demo.lc4j");

        AnthropicChatModel chatModel = AnthropicChatModel.builder()
                .apiKey(apiKey)
                .modelName(model)
                .maxTokens(1024)
                // This one line is the entire LLM instrumentation.
                .listeners(new ObservationChatModelListener(
                        Tracing.observationRegistry(sdk), Tracing.meterRegistry()))
                .build();

        WeatherAssistant assistant = AiServices.builder(WeatherAssistant.class)
                .chatModel(chatModel)
                .tools(new WeatherTools(tracer))
                .build();

        int iterations = Integer.parseInt(envOrDefault("ITERATIONS", "1"));
        long intervalMs = Long.parseLong(envOrDefault("INTERVAL_MS", "15000"));

        try {
            for (int i = 0; i < iterations || iterations <= 0; i++) {
                try {
                    System.out.println("[java-langchain4j] " + runAgent(tracer, assistant));
                } catch (Exception e) {
                    System.err.println("[java-langchain4j] run failed: " + e.getMessage());
                }
                if (iterations <= 0 || i < iterations - 1) {
                    Thread.sleep(intervalMs);
                }
            }
        } finally {
            sdk.close();
        }
    }

    private static String runAgent(Tracer tracer, WeatherAssistant assistant) {
        Span agent = tracer.spanBuilder("invoke_agent weather-agent")
                .setSpanKind(SpanKind.INTERNAL)
                .setAttribute("gen_ai.operation.name", "invoke_agent")
                .setAttribute("gen_ai.agent.name", "weather-agent")
                .startSpan();
        try (Scope ignored = agent.makeCurrent()) {
            return assistant.ask(USER_PROMPT);
        } finally {
            agent.end();
        }
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
