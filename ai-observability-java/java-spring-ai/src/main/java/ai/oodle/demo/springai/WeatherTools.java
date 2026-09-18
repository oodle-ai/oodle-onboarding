package ai.oodle.demo.springai;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

/**
 * The agent's one tool.
 *
 * <p>Spring AI's observations cover the ChatClient call, not the tool body, so
 * the span here is what completes the agent graph. As in the LangChain4j example,
 * it carries only structural attributes — model, prompt, and token usage are all
 * written by Spring AI.
 */
@Component
public class WeatherTools {

    private final Tracer tracer;

    public WeatherTools(Tracer tracer) {
        this.tracer = tracer;
    }

    @Tool(description = "Get the current weather for a location")
    public String getWeather(@ToolParam(description = "City name") String location) {
        Span span = tracer.spanBuilder("execute_tool get_weather")
                .setSpanKind(SpanKind.INTERNAL)
                .setAttribute("gen_ai.operation.name", "execute_tool")
                .setAttribute("gen_ai.tool.name", "get_weather")
                .startSpan();
        try (Scope ignored = span.makeCurrent()) {
            // Stand-in for a real weather service.
            return "18C, light rain, 80% humidity in " + location;
        } finally {
            span.end();
        }
    }
}
