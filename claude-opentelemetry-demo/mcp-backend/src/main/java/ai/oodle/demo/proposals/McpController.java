package ai.oodle.demo.proposals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.opentelemetry.api.trace.Span;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

/**
 * The firm's MCP server (role {@code web}), served the way the reference
 * backend serves it: a hand-written JSON-RPC handler on POST /mcp
 * (Streamable HTTP, JSON responses only), traced by the Java agent alone.
 *
 * <p>That keeps the reference's blind spots, on purpose:
 * <ul>
 *   <li>The server span is a bare {@code POST /mcp}. It names no JSON-RPC
 *       method, tool, MCP session id or request id, so nothing joins it to
 *       the agent's {@code anthropic.mcp_tool_use} span.</li>
 *   <li>A failed request answers 500 from a caught exception, so the span
 *       has status 500 and no exception event that says why.</li>
 *   <li>Every request first reads each org's props table, one query per
 *       org, before it looks at the method.</li>
 *   <li>GET /mcp answers 405: there is no server-to-client stream.</li>
 * </ul>
 */
@RestController
@ConditionalOnProperty(name = "demo.role", havingValue = "web")
public class McpController {
    private final FirmDb db;
    private final GenAi genAi;
    private final ObjectMapper json;
    private final String searchModel;
    @Value("${MCP_SERVER_SPAN_ATTRIBUTES:false}")
    private boolean spanAttributes;

    public McpController(FirmDb db, GenAi genAi, ObjectMapper json,
            @Value("${SEARCH_MODEL:claude-haiku-4-5}") String searchModel) {
        this.db = db;
        this.genAi = genAi;
        this.json = json;
        this.searchModel = searchModel;
    }

    @PostMapping(value = "/mcp", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> mcp(@RequestBody JsonNode payload,
            @RequestHeader(value = "Mcp-Session-Id", required = false) String mcpSessionId) {
        try {
            Map<Integer, Map<String, String>> props = db.loadAllOrgProps();
            JsonNode id = payload.get("id");
            String method = payload.path("method").asText();
            if (spanAttributes) {
                nameCall(payload, method, mcpSessionId);
            }
            if (id == null || id.isNull()) {
                // A notification (notifications/initialized and the like).
                return ResponseEntity.accepted().build();
            }
            JsonNode params = payload.path("params");
            return switch (method) {
                case "initialize" -> ResponseEntity.ok()
                        .header("Mcp-Session-Id", UUID.randomUUID().toString().replace("-", ""))
                        .body(result(id, Map.of(
                                "protocolVersion", params.path("protocolVersion").asText("2025-06-18"),
                                "capabilities", Map.of("tools", Map.of("listChanged", false)),
                                "serverInfo", Map.of("name", "firm-mcp", "version", "1.0.0"))));
                case "ping" -> ResponseEntity.ok(result(id, Map.of()));
                case "tools/list" -> ResponseEntity.ok(result(id, Map.of("tools", Tools.LIST)));
                case "tools/call" -> {
                    Object out = callTool(props, params.path("name").asText(), params.path("arguments"));
                    yield ResponseEntity.ok(result(id, Map.of(
                            "content", List.of(Map.of("type", "text", "text", json.writeValueAsString(out))),
                            "isError", false)));
                }
                default -> ResponseEntity.ok(Map.of("jsonrpc", "2.0", "id", id,
                        "error", Map.of("code", -32601, "message", "no method " + method)));
            };
        } catch (Exception e) {
            // Deliberate: answer 500 without letting the exception reach the
            // instrumentation, as the reference backend does. The span then
            // says 500 and nothing about the cause.
            return ResponseEntity.status(500).build();
        }
    }

    /**
     * Names the JSON-RPC call on the server span, with the MCP semantic
     * conventions. Off by default: the bare {@code POST /mcp} is one of the
     * gaps this demo keeps. Without these attributes, nothing tells a
     * handshake request from a tool call, or one tool call from another.
     */
    private static void nameCall(JsonNode payload, String method, String mcpSessionId) {
        Span server = Span.current();
        server.setAttribute("mcp.method.name", method);
        if (payload.hasNonNull("id")) {
            server.setAttribute("jsonrpc.request.id", payload.get("id").asText());
        }
        if (mcpSessionId != null) {
            server.setAttribute("mcp.session.id", mcpSessionId);
        }
        if ("tools/call".equals(method)) {
            server.setAttribute("gen_ai.tool.name", payload.path("params").path("name").asText());
        }
    }

    private Object callTool(Map<Integer, Map<String, String>> props, String name, JsonNode args) {
        int orgId = args.path("orgid").asInt(-1);
        if (!props.containsKey(orgId)) {
            throw new IllegalArgumentException("org " + orgId + " not found");
        }
        return switch (name) {
            case "readBid" -> readBid(orgId, args.path("bidId").asText());
            case "getOrgEntryDetails" -> {
                Map<String, Object> corp = new LinkedHashMap<>(db.corp(orgId));
                corp.put("props", props.get(orgId));
                yield corp;
            }
            case "getProjectList" -> db.projectList(orgId);
            case "readProjects" -> {
                List<String> ids = new ArrayList<>();
                args.path("projectIds").forEach(n -> ids.add(n.asText()));
                yield db.projects(orgId, ids);
            }
            case "getEmployeeList" -> db.employees(orgId);
            case "searchDocuments" -> searchDocuments(orgId, args.path("searchTerms").asText());
            default -> throw new IllegalArgumentException("unknown tool " + name);
        };
    }

    private Object readBid(int orgId, String bidId) {
        Map<String, Object> bid = db.bid(orgId, bidId);
        if (bid == null) {
            return Map.of("error", "bid not found");
        }
        // A small model call in the read path, as the reference backend makes
        // one: here it labels the bid's sector.
        JsonNode resp = genAi.chat(searchModel, 16, Map.of("messages", List.of(Map.of("role", "user",
                "content", "One word, the AEC sector of this bid: " + bid.get("title")))));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("bidMetadata", bid);
        out.put("sector", GenAi.text(resp).trim());
        out.put("contentGuidelines", Tools.GUIDELINES);
        out.put("rfpFiles", List.of("/mnt/session/uploads/workspace/rfp_main/sample_rfp.md"));
        out.put("templateFiles", List.of("/mnt/session/uploads/workspace/template_doc/go_no_go_template.md"));
        return out;
    }

    /**
     * Turns the agent's search terms into keywords with a small model call,
     * standing in for the embedding call the reference backend's search
     * makes, then matches them against the document snippets.
     */
    private Object searchDocuments(int orgId, String terms) {
        JsonNode resp = genAi.chat(searchModel, 100, Map.of("messages", List.of(Map.of("role", "user",
                "content", "Give up to five single-word search keywords, comma separated, no other text, for: "
                        + terms))));
        Map<String, Map<String, Object>> hits = new LinkedHashMap<>();
        for (String word : GenAi.text(resp).split(",")) {
            if (!word.isBlank()) {
                for (Map<String, Object> row : db.searchChunks(orgId, word.trim())) {
                    hits.put(String.valueOf(row.get("snippet_id")), row);
                }
            }
        }
        return new ArrayList<>(hits.values());
    }

    private static Map<String, Object> result(JsonNode id, Object result) {
        return Map.of("jsonrpc", "2.0", "id", id, "result", result);
    }
}
