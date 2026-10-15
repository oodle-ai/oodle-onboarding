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
import java.security.SecureRandom;
import java.time.Duration;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * Starts and polls go/no-go sessions (role {@code app}), the way the
 * reference backend does.
 *
 * <p>The create request makes a managed agent for this one session, opens
 * the session, mounts the bid's files, sends the task and returns. A poller
 * then reads the session on a fixed interval until the agent is done. The
 * Java agent carries the request's context into the executor, so the
 * poller stays in the request's trace, as in the reference.
 *
 * <p>Deliberate gaps: the agent is new for every session, and its name
 * holds the org, a random id, a timestamp and the user's email. The MCP
 * server name is new for every session too. No span carries user.id.
 */
@RestController
@ConditionalOnProperty(name = "demo.role", havingValue = "app")
public class ManagedAgentsController {
    static final String SYSTEM = """
            Proposal assistant for AEC (Architecture, Engineering and Construction)
            firms. The firm's past projects, people, bids and documents are reachable
            through the MCP tools; always pass the firm's orgid. Files for the current
            bid are mounted under /mnt/session/uploads/workspace. Write deliverables to
            /mnt/session/outputs.""";

    private static final String TASK = """
            <summary_for_user>
            Write an RFP go/no-go plan for this bid.
            </summary_for_user>

            Read the bid with identifier %s for orgid %d.

            A bid is a proposal our firm is working on in response to an RFP. Read the
            RFP, find comparable past projects and the people who could staff it, and
            fill in the go/no-go template. Write the plan to
            /mnt/session/outputs/go_no_go_plan.md and summarize the recommendation.""";

    private static final DateTimeFormatter STAMP = DateTimeFormatter.ofPattern("yyyyMMddHHmm");
    private static final SecureRandom RANDOM = new SecureRandom();

    private final AnthropicApi api;
    private final FirmDb db;
    private final ObjectMapper json;
    private final ExecutorService pollers = Executors.newCachedThreadPool();
    private final HttpClient http = HttpClient.newHttpClient();

    @Value("${CLAUDE_MODEL:claude-opus-5-5}")
    private String model;
    @Value("${MCP_ENVIRONMENT_ID:}")
    private String environmentId;
    @Value("${MCP_PUBLIC_URL:}")
    private String publicMcpUrl;
    @Value("${TUNNEL_METRICS_URL:http://mcp-tunnel:2000}")
    private String tunnelMetricsUrl;
    @Value("${POLL_SECONDS:5}")
    private long pollSeconds;
    @Value("${SESSION_TIMEOUT_SECONDS:900}")
    private long timeoutSeconds;

    public ManagedAgentsController(AnthropicApi api, FirmDb db, ObjectMapper json) {
        this.api = api;
        this.db = db;
        this.json = json;
    }

    record CreateRequest(Integer orgid, String bidId, String userEmail) {
    }

    @PostMapping("/api/managedagents/rfpgonogo/create")
    public Map<String, Object> create(@RequestBody(required = false) CreateRequest req) {
        int orgId = req != null && req.orgid() != null ? req.orgid() : 54;
        String bidId = req != null && req.bidId() != null ? req.bidId() : "wrw50evpgs8z9l";
        String email = req != null && req.userEmail() != null ? req.userEmail() : "estimator@example.com";
        if (environmentId.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Set MCP_ENVIRONMENT_ID in .env (run `make mcp-backend-setup`).");
        }
        if (db.actor(email) == null || db.org(orgId) == null || db.bid(orgId, bidId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "unknown user, org or bid");
        }

        String mcpUrl = publicMcpUrl();
        String stamp = ZonedDateTime.now(ZoneOffset.UTC).format(STAMP);
        String serverName = "mcp-ShortId__" + shortId();
        JsonNode agent = api.createAgent(Map.of(
                "name", orgId + "_" + shortId() + "_" + stamp + "_" + email,
                "model", model,
                "system", SYSTEM,
                "mcp_servers", List.of(Map.of("type", "url", "name", serverName, "url", mcpUrl)),
                "tools", List.of(
                        Map.of("type", "agent_toolset_20260401",
                                "default_config", Map.of("enabled", true, "permission_policy", Map.of("type", "auto")),
                                "configs", List.of(
                                        Map.of("name", "web_fetch", "enabled", false),
                                        Map.of("name", "web_search", "enabled", false))),
                        Map.of("type", "mcp_toolset",
                                "mcp_server_name", serverName,
                                "default_config", Map.of("permission_policy", Map.of("type", "always_allow"))))));
        String agentId = agent.path("id").asText();
        JsonNode session = api.createSession(Map.of(
                "agent", agentId, "environment_id", environmentId, "title", "go/no-go " + bidId));
        String sessionId = session.path("id").asText();

        mount(sessionId, "bid_docs/sample_rfp.md", "/mnt/session/uploads/workspace/rfp_main/sample_rfp.md");
        mount(sessionId, "bid_docs/go_no_go_template.md",
                "/mnt/session/uploads/workspace/template_doc/go_no_go_template.md");
        db.saveFacet(orgId, sessionId, progress("running", 0, agentId));
        api.sendEvents(sessionId, Map.of("events", List.of(Map.of("type", "user.message",
                "content", List.of(Map.of("type", "text", "text", TASK.formatted(bidId, orgId)))))));

        pollers.submit(() -> poll(orgId, sessionId, agentId));

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("sessionId", sessionId);
        out.put("agentId", agentId);
        out.put("agentName", agent.path("name").asText());
        out.put("mcpUrl", mcpUrl);
        out.put("traceId", Span.current().getSpanContext().getTraceId());
        return out;
    }

    @GetMapping("/api/managedagents/sessions/read")
    public JsonNode read(@RequestParam String sessionId, @RequestParam(defaultValue = "54") int orgid)
            throws IOException {
        Map<String, Object> row = db.facet(orgid, sessionId);
        if (row == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "unknown session");
        }
        return json.readTree(String.valueOf(row.get("data")));
    }

    private void mount(String sessionId, String resource, String mountPath) {
        try {
            ClassPathResource doc = new ClassPathResource(resource);
            JsonNode file = api.uploadFile(doc.getFilename(), doc.getContentAsByteArray(), "text/markdown");
            api.addResource(sessionId, Map.of("type", "file", "file_id", file.path("id").asText(), "mount_path", mountPath));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /**
     * Polls until the agent is done, as the reference backend does: retrieve
     * the session, read the newest user message, read every event, and save
     * the progress, on a fixed interval.
     */
    private void poll(int orgId, String sessionId, String agentId) {
        long deadline = System.nanoTime() + Duration.ofSeconds(timeoutSeconds).toNanos();
        String status = "timeout";
        int events = 0;
        try {
            while (System.nanoTime() < deadline) {
                Thread.sleep(Duration.ofSeconds(pollSeconds));
                api.retrieveSession(sessionId);
                api.listEvents(sessionId, "desc", List.of("user.message"), 1);
                JsonNode all = api.listEvents(sessionId, "asc", List.of(), null);
                events = all.size();
                db.saveFacet(orgId, sessionId, progress("running", events, agentId));
                String stop = stopReason(all);
                if (stop != null) {
                    status = stop;
                    break;
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            status = "interrupted";
        } catch (RuntimeException e) {
            status = "error: " + e.getClass().getSimpleName();
        } finally {
            db.saveFacet(orgId, sessionId, progress(status, events, agentId));
            // The agent belongs to this one session. Archive it so runs do
            // not pile up agents in the org; archiving does not change the trace.
            try {
                api.archiveAgent(agentId);
            } catch (RuntimeException ignored) {
                // Best effort.
            }
        }
    }

    /** The stop reason once the agent has finished the task, else null. */
    static String stopReason(JsonNode events) {
        for (int i = events.size() - 1; i >= 0; i--) {
            String type = events.get(i).path("type").asText();
            switch (type) {
                case "session.status_terminated":
                    return "terminated";
                case "session.status_idle": {
                    String reason = events.get(i).path("stop_reason").path("type").asText("end_turn");
                    return "requires_action".equals(reason) ? null : reason;
                }
                case "session.status_running", "user.message":
                    return null;
                default:
                    break;
            }
        }
        return null;
    }

    private String progress(String status, int events, String agentId) {
        try {
            return json.writeValueAsString(Map.of(
                    "status", status, "events", events, "agentId", agentId,
                    "updatedAt", ZonedDateTime.now(ZoneOffset.UTC).toString()));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /**
     * The MCP URL Anthropic can reach: MCP_PUBLIC_URL when set, otherwise
     * the hostname of cloudflared's quick tunnel.
     */
    private String publicMcpUrl() {
        if (!publicMcpUrl.isBlank()) {
            return publicMcpUrl;
        }
        try {
            HttpResponse<String> resp = http.send(
                    HttpRequest.newBuilder(URI.create(tunnelMetricsUrl + "/quicktunnel")).build(),
                    HttpResponse.BodyHandlers.ofString());
            String host = json.readTree(resp.body()).path("hostname").asText("");
            if (host.isBlank()) {
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                        "the tunnel has no hostname yet; retry in a few seconds");
            }
            return "https://" + host + "/mcp";
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "tunnel not reachable", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    private static String shortId() {
        String alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 14; i++) {
            sb.append(alphabet.charAt(RANDOM.nextInt(alphabet.length())));
        }
        return sb.toString();
    }
}
