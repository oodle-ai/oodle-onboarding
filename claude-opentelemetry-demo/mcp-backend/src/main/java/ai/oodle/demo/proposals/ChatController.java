package ai.oodle.demo.proposals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.opentelemetry.api.trace.Span;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * The in-house chat (role {@code app}): a tool loop on the firm's own
 * model wrapper that calls the firm's MCP server directly.
 *
 * <p>Deliberate gap, as in the reference backend: the MCP calls go over
 * {@code java.net.http} as raw JSON-RPC, with no tool span around them. The
 * trace shows a bare {@code POST} client span and the server's
 * {@code POST /mcp}, so Oodle counts no tool calls on this path.
 */
@RestController
@ConditionalOnProperty(name = "demo.role", havingValue = "app")
public class ChatController {
    private final GenAi genAi;
    private final ObjectMapper json;

    @Value("${CHAT_MODEL:claude-haiku-4-5}")
    private String chatModel;
    @Value("${MCP_INTERNAL_URL:http://mcp-web:8000/mcp}")
    private String mcpUrl;

    public ChatController(GenAi genAi, ObjectMapper json) {
        this.genAi = genAi;
        this.json = json;
    }

    record AskRequest(Integer orgid, String question) {
    }

    @PostMapping("/api/chatsession/ask")
    public Map<String, Object> ask(@RequestBody AskRequest req) {
        int orgId = req.orgid() != null ? req.orgid() : 54;
        RawMcpClient mcp = new RawMcpClient(mcpUrl, json);
        List<Map<String, Object>> tools = new ArrayList<>();
        for (JsonNode t : mcp.tools()) {
            tools.add(Map.of("name", t.path("name").asText(), "description", t.path("description").asText(),
                    "input_schema", t.path("inputSchema")));
        }
        List<Object> messages = new ArrayList<>();
        messages.add(Map.of("role", "user", "content", "orgid=" + orgId + ". " + req.question()));
        String answer = "";
        for (int i = 0; i < 6; i++) {
            JsonNode resp = genAi.chat(chatModel, 1024, Map.of(
                    "system", ManagedAgentsController.SYSTEM, "tools", tools, "messages", messages));
            messages.add(Map.of("role", "assistant", "content", resp.path("content")));
            List<Map<String, Object>> results = new ArrayList<>();
            for (JsonNode block : resp.path("content")) {
                if ("tool_use".equals(block.path("type").asText())) {
                    results.add(Map.of("type", "tool_result", "tool_use_id", block.path("id").asText(),
                            "content", mcp.call(block.path("name").asText(), block.path("input"))));
                }
            }
            if (results.isEmpty()) {
                answer = GenAi.text(resp);
                break;
            }
            messages.add(Map.of("role", "user", "content", results));
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("answer", answer);
        out.put("traceId", Span.current().getSpanContext().getTraceId());
        return out;
    }

    /** JSON-RPC over plain HTTP, with no span of its own. */
    static final class RawMcpClient {
        private final HttpClient http = HttpClient.newHttpClient();
        private final String url;
        private final ObjectMapper json;
        private String sessionId = "";
        private int nextId;

        RawMcpClient(String url, ObjectMapper json) {
            this.url = url;
            this.json = json;
            HttpResponse<String> init = post(Map.of("jsonrpc", "2.0", "id", ++nextId, "method", "initialize",
                    "params", Map.of("protocolVersion", "2025-06-18", "capabilities", Map.of(),
                            "clientInfo", Map.of("name", "in-house-chat", "version", "1.0.0"))));
            sessionId = init.headers().firstValue("Mcp-Session-Id").orElse("");
            post(Map.of("jsonrpc", "2.0", "method", "notifications/initialized"));
        }

        JsonNode tools() {
            return rpc("tools/list", Map.of()).path("tools");
        }

        String call(String name, JsonNode arguments) {
            StringBuilder sb = new StringBuilder();
            rpc("tools/call", Map.of("name", name, "arguments", arguments))
                    .path("content").forEach(c -> sb.append(c.path("text").asText()));
            return sb.toString();
        }

        private JsonNode rpc(String method, Object params) {
            try {
                return json.readTree(post(Map.of("jsonrpc", "2.0", "id", ++nextId, "method", method,
                        "params", params)).body()).path("result");
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }

        private HttpResponse<String> post(Object body) {
            try {
                HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url))
                        .header("Content-Type", "application/json")
                        .header("Accept", "application/json, text/event-stream")
                        .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(body)));
                if (!sessionId.isEmpty()) {
                    b.header("Mcp-Session-Id", sessionId);
                }
                HttpResponse<String> resp = http.send(b.build(), HttpResponse.BodyHandlers.ofString());
                if (resp.statusCode() >= 400) {
                    throw new IllegalStateException("MCP " + resp.statusCode());
                }
                return resp;
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        }
    }
}
