package ai.oodle.demo.proposals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import okhttp3.HttpUrl;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * The Claude API over plain OkHttp, the way the reference backend calls it.
 *
 * No Claude SDK and no SDK tracing: the only spans on this side are the
 * agent's generic okhttp {@code GET}/{@code POST} client spans. The
 * {@code anthropic.*} spans come from Anthropic's API tracing alone.
 */
@Component
public class AnthropicApi {
    private static final MediaType JSON = MediaType.get("application/json");
    private static final String AGENTS_BETA = "managed-agents-2026-04-01";
    private static final String FILES_BETA = "files-api-2025-04-14";

    private final OkHttpClient http = new OkHttpClient.Builder()
            .connectTimeout(Duration.ofSeconds(30))
            .readTimeout(Duration.ofMinutes(5))
            .build();
    private final ObjectMapper json;
    private final String apiKey;
    private final String workspaceId;
    private final HttpUrl base;

    public AnthropicApi(
            ObjectMapper json,
            @Value("${ANTHROPIC_API_KEY:}") String apiKey,
            @Value("${ANTHROPIC_WORKSPACE_ID:}") String workspaceId,
            @Value("${ANTHROPIC_BASE_URL:https://api.anthropic.com}") String baseUrl) {
        this.json = json;
        this.apiKey = apiKey;
        this.workspaceId = workspaceId;
        this.base = HttpUrl.get(baseUrl);
    }

    public JsonNode createEnvironment(Object body) {
        return post("v1/environments", body, AGENTS_BETA);
    }

    public JsonNode createAgent(Object body) {
        return post("v1/agents", body, AGENTS_BETA);
    }

    public void archiveAgent(String agentId) {
        post("v1/agents/" + agentId + "/archive", java.util.Map.of(), AGENTS_BETA);
    }

    public JsonNode createSession(Object body) {
        return post("v1/sessions", body, AGENTS_BETA);
    }

    public JsonNode retrieveSession(String sessionId) {
        return get(url("v1/sessions/" + sessionId).build(), AGENTS_BETA);
    }

    public JsonNode addResource(String sessionId, Object body) {
        return post("v1/sessions/" + sessionId + "/resources", body, AGENTS_BETA);
    }

    public JsonNode sendEvents(String sessionId, Object body) {
        return post("v1/sessions/" + sessionId + "/events", body, AGENTS_BETA);
    }

    /** Every event of a session, one request per page. */
    public ArrayNode listEvents(String sessionId, String order, List<String> types, Integer limit) {
        ArrayNode all = json.createArrayNode();
        String page = null;
        do {
            HttpUrl.Builder u = url("v1/sessions/" + sessionId + "/events").addQueryParameter("order", order);
            for (String t : types) {
                u.addQueryParameter("types[]", t);
            }
            if (limit != null) {
                u.addQueryParameter("limit", limit.toString());
            }
            if (page != null) {
                u.addQueryParameter("page", page);
            }
            JsonNode resp = get(u.build(), AGENTS_BETA);
            resp.path("data").forEach(all::add);
            page = resp.path("next_page").isTextual() ? resp.path("next_page").asText() : null;
            // One page is all a "newest event" read needs.
            if (limit != null) {
                break;
            }
        } while (page != null);
        return all;
    }

    public JsonNode uploadFile(String name, byte[] content, String mime) {
        RequestBody body = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", name, RequestBody.create(content, MediaType.get(mime)))
                .build();
        return call(request(url("v1/files").build(), FILES_BETA).post(body).build());
    }

    public JsonNode messages(Object body) {
        return call(request(base.newBuilder().addPathSegments("v1/messages").build(), null)
                .post(RequestBody.create(write(body), JSON))
                .build());
    }

    private JsonNode get(HttpUrl u, String beta) {
        return call(request(u, beta).get().build());
    }

    private JsonNode post(String path, Object body, String beta) {
        return call(request(url(path).build(), beta).post(RequestBody.create(write(body), JSON)).build());
    }

    private HttpUrl.Builder url(String path) {
        return base.newBuilder().addPathSegments(path).addQueryParameter("beta", "true");
    }

    private Request.Builder request(HttpUrl u, String beta) {
        Request.Builder b = new Request.Builder()
                .url(u)
                .header("x-api-key", apiKey)
                .header("anthropic-version", "2023-06-01");
        if (beta != null) {
            b.header("anthropic-beta", beta);
        }
        // An API key not scoped to a workspace must name one on every request.
        if (!workspaceId.isBlank()) {
            b.header("anthropic-workspace-id", workspaceId);
        }
        return b;
    }

    private JsonNode call(Request req) {
        try (Response resp = http.newCall(req).execute()) {
            String text = resp.body() == null ? "" : resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IllegalStateException(
                        req.method() + " " + req.url().encodedPath() + " -> " + resp.code() + ": " + text);
            }
            return text.isBlank() ? json.createObjectNode() : json.readTree(text);
        } catch (IOException e) {
            throw new IllegalStateException(req.method() + " " + req.url().encodedPath() + " failed", e);
        }
    }

    private byte[] write(Object body) {
        try {
            return json.writeValueAsBytes(body);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
