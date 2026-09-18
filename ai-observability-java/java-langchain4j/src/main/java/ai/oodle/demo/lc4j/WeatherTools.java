package ai.oodle.demo.lc4j;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

/**
 * The agent's one tool.
 *
 * <p>langchain4j-observation hooks ChatModelListener, which fires on LLM calls only —
 * tool executions are invisible to it. The span opened here is what gives Oodle the
 * "LLM -> tool -> LLM" shape instead of two unrelated chat calls. Note that it sets
 * only structural attributes; nothing about the model, prompt, or token usage is
 * written by hand anywhere in this application.
 */
public class WeatherTools {

    private final Tracer tracer;

    public WeatherTools(Tracer tracer) {
        this.tracer = tracer;
    }

    @Tool("Get the current weather for a location")
    public String getWeather(@P("City name") String location) {
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
