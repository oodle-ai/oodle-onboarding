package ai.oodle.demo.proposals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** The roles that run once and exit. Neither runs under the Java agent. */
@Configuration
public class OneShotRoles {

    /**
     * One-time setup: an environment that allows MCP egress. The
     * managed-agents sub-demo's environment blocks it. Agents are not made
     * here: the app makes one per session, as the reference backend does.
     */
    @Bean
    @ConditionalOnProperty(name = "demo.role", havingValue = "provision")
    CommandLineRunner provision(AnthropicApi api, @Value("${MCP_ENVIRONMENT_ID:}") String existing) {
        return args -> {
            if (!existing.isBlank()) {
                System.out.println("Already set up: MCP_ENVIRONMENT_ID=" + existing);
                return;
            }
            JsonNode env = api.createEnvironment(Map.of(
                    "name", "claude-otel-demo-mcp-backend",
                    "config", Map.of("type", "cloud", "networking", Map.of(
                            "type", "limited", "allow_mcp_servers", true, "allow_package_managers", true))));
            System.out.println("Add this to .env:\n\nMCP_ENVIRONMENT_ID=" + env.path("id").asText());
        };
    }

    /**
     * Plays the web UI: starts a go/no-go session, waits for the agent, then
     * asks the in-house chat a question. Untraced, like the browser that
     * calls the reference backend; each step's trace starts at the app.
     */
    @Bean
    @ConditionalOnProperty(name = "demo.role", havingValue = "driver")
    CommandLineRunner driver(ObjectMapper json,
            @Value("${APP_URL:http://mcp-app:8001}") String app,
            @Value("${QUESTION:Which of our past projects are most like a wastewater plant upgrade, and who led them?}")
            String question) {
        return args -> {
            HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
            waitReady(http, app);

            JsonNode created = null;
            // The quick tunnel takes a few seconds to get a hostname.
            for (int i = 0; i < 15; i++) {
                HttpResponse<String> resp = post(http, app + "/api/managedagents/rfpgonogo/create", "{}");
                if (resp.statusCode() != 503) {
                    check(resp);
                    created = json.readTree(resp.body());
                    break;
                }
                Thread.sleep(4000);
            }
            if (created == null) {
                throw new IllegalStateException("the tunnel never got a hostname");
            }
            System.out.println("agent      " + created.path("agentName").asText());
            System.out.println("session    " + created.path("sessionId").asText());
            System.out.println("mcp url    " + created.path("mcpUrl").asText());
            System.out.println("trace_id   " + created.path("traceId").asText() + "  (go/no-go session)");

            String status = "running";
            while ("running".equals(status)) {
                Thread.sleep(10000);
                HttpResponse<String> resp = http.send(HttpRequest.newBuilder(URI.create(
                        app + "/api/managedagents/sessions/read?sessionId=" + created.path("sessionId").asText()))
                        .build(), HttpResponse.BodyHandlers.ofString());
                check(resp);
                JsonNode row = json.readTree(resp.body());
                status = row.path("status").asText();
                System.out.printf("  %s  %s  events=%d%n", row.path("updatedAt").asText(), status,
                        row.path("events").asInt());
            }

            HttpResponse<String> asked = post(http, app + "/api/chatsession/ask",
                    json.writeValueAsString(Map.of("question", question)));
            check(asked);
            JsonNode body = json.readTree(asked.body());
            System.out.println("\n" + body.path("answer").asText() + "\n");
            System.out.println("trace_id   " + body.path("traceId").asText() + "  (in-house chat)");
        };
    }

    private static void waitReady(HttpClient http, String app) throws InterruptedException {
        for (int i = 0; i < 60; i++) {
            try {
                HttpResponse<Void> resp = http.send(
                        HttpRequest.newBuilder(URI.create(app + "/actuator/health")).build(),
                        HttpResponse.BodyHandlers.discarding());
                if (resp.statusCode() == 200) {
                    return;
                }
            } catch (IOException e) {
                // Not up yet.
            }
            Thread.sleep(2000);
        }
        throw new IllegalStateException("mcp-app did not come up");
    }

    private static HttpResponse<String> post(HttpClient http, String url, String body)
            throws IOException, InterruptedException {
        return http.send(HttpRequest.newBuilder(URI.create(url))
                        .timeout(Duration.ofMinutes(2))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private static void check(HttpResponse<String> resp) {
        if (resp.statusCode() >= 400) {
            throw new IllegalStateException(resp.uri() + " -> " + resp.statusCode() + ": " + resp.body());
        }
    }
}
