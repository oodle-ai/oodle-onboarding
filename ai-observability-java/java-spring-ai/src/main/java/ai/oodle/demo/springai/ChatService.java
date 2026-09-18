package ai.oodle.demo.springai;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

/**
 * The agent itself. Spring AI runs the tool-calling loop — chat, tool, chat —
 * and records a Micrometer observation for each LLM call, which Boot's OTel
 * bridge turns into a gen_ai span. No instrumentation code lives here.
 */
@Service
public class ChatService {

    private static final String SYSTEM_PROMPT =
            "You are a concise weather assistant. Use the getWeather tool when asked about "
          + "weather, then answer in one short sentence.";

    private final ChatClient chatClient;
    private final Tracer tracer;

    public ChatService(ChatClient.Builder builder, WeatherTools weatherTools, Tracer tracer) {
        this.chatClient = builder
                .defaultSystem(SYSTEM_PROMPT)
                .defaultTools(weatherTools)
                .build();
        this.tracer = tracer;
    }

    public String ask(String question) {
        Span agent = tracer.spanBuilder("invoke_agent weather-agent")
                .setSpanKind(SpanKind.INTERNAL)
                .setAttribute("gen_ai.operation.name", "invoke_agent")
                .setAttribute("gen_ai.agent.name", "weather-agent")
                .startSpan();
        try (Scope ignored = agent.makeCurrent()) {
            return chatClient.prompt().user(question).call().content();
        } finally {
            agent.end();
        }
    }
}
