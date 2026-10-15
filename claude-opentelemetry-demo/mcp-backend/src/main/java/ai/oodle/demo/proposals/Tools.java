package ai.oodle.demo.proposals;

import java.util.List;
import java.util.Map;

/** The MCP server's tool list and the firm's content guidelines. */
final class Tools {
    static final String GUIDELINES = """
            ## Firm-Wide Content Guidelines
            - Lead with the client's outcome, not with our history.
            - Name the project manager and two comparable projects in every pursuit.
            - Do not promise schedule dates that the RFP does not give.""";

    private static final Map<String, Object> ORG_ONLY = schema(Map.of("orgid", Map.of("type", "integer")), "orgid");

    static final List<Map<String, Object>> LIST = List.of(
            tool("readBid",
                    "Read a bid (a proposal in progress): its client, team, due date and the firm's content guidelines.",
                    schema(Map.of("orgid", Map.of("type", "integer"), "bidId", Map.of("type", "string")),
                            "orgid", "bidId")),
            tool("getOrgEntryDetails", "Read the firm's name and profile.", ORG_ONLY),
            tool("getProjectList", "List the firm's past projects with their ids.", ORG_ONLY),
            tool("readProjects", "Read the details of past projects by id.",
                    schema(Map.of("orgid", Map.of("type", "integer"),
                            "projectIds", Map.of("type", "array", "items", Map.of("type", "string"))),
                            "orgid", "projectIds")),
            tool("getEmployeeList", "List the firm's people with their roles.", ORG_ONLY),
            tool("searchDocuments", "Search the firm's document snippets (reports, letters, memos).",
                    schema(Map.of("orgid", Map.of("type", "integer"), "searchTerms", Map.of("type", "string")),
                            "orgid", "searchTerms")));

    private Tools() {
    }

    private static Map<String, Object> tool(String name, String description, Map<String, Object> schema) {
        return Map.of("name", name, "description", description, "inputSchema", schema);
    }

    private static Map<String, Object> schema(Map<String, Object> properties, String... required) {
        return Map.of("type", "object", "properties", properties, "required", List.of(required));
    }
}
