package ai.oodle.demo.proposals;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * Reads and writes the firm's tenant tables. Table names hold the org id,
 * as in the reference backend, so each JDBC span names its tenant's table
 * ({@code SELECT meta_db.org_54_employees}).
 */
@Component
public class FirmDb {
    private final JdbcTemplate jdbc;

    public FirmDb(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Every org's props, one query per org. The MCP server runs this before
     * it reads the method of each request, as the reference backend does.
     */
    public Map<Integer, Map<String, String>> loadAllOrgProps() {
        jdbc.queryForList("SELECT actor_id FROM fed_db.actors_list");
        Map<Integer, Map<String, String>> props = new LinkedHashMap<>();
        for (Integer orgId : jdbc.queryForList("SELECT org_id FROM fed_db.orgs_list", Integer.class)) {
            Map<String, String> p = new LinkedHashMap<>();
            jdbc.query("SELECT k, v FROM meta_db.org_" + orgId + "_props",
                    rs -> { p.put(rs.getString("k"), rs.getString("v")); });
            props.put(orgId, p);
        }
        return props;
    }

    public Map<String, Object> actor(String email) {
        return one(jdbc.queryForList("SELECT * FROM fed_db.actors_list WHERE email = ?", email));
    }

    public Map<String, Object> org(int orgId) {
        return one(jdbc.queryForList("SELECT * FROM fed_db.orgs_list WHERE org_id = ?", orgId));
    }

    public Map<String, Object> corp(int orgId) {
        return one(jdbc.queryForList("SELECT * FROM " + meta(orgId, "corp")));
    }

    public Map<String, Object> bid(int orgId, String bidId) {
        return one(jdbc.queryForList("SELECT * FROM " + meta(orgId, "bids") + " WHERE bid_id = ?", bidId));
    }

    public List<Map<String, Object>> projectList(int orgId) {
        return jdbc.queryForList("SELECT project_id, name, year FROM " + meta(orgId, "projects"));
    }

    public List<Map<String, Object>> projects(int orgId, List<String> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }
        String marks = String.join(",", java.util.Collections.nCopies(ids.size(), "?"));
        return jdbc.queryForList(
                "SELECT * FROM " + meta(orgId, "projects") + " WHERE project_id IN (" + marks + ")", ids.toArray());
    }

    public List<Map<String, Object>> employees(int orgId) {
        return jdbc.queryForList("SELECT name, role, years FROM " + meta(orgId, "employees"));
    }

    public List<Map<String, Object>> searchChunks(int orgId, String word) {
        String like = "%" + word.toLowerCase() + "%";
        return jdbc.queryForList(
                "SELECT snippet_id, project_id, title, text FROM conv_db.c_" + orgId + "_chunk"
                        + " WHERE lower(text) LIKE ? OR lower(title) LIKE ?", like, like);
    }

    /** The progress row of a session, written by the app's poller. */
    public void saveFacet(int orgId, String id, String data) {
        jdbc.update("INSERT INTO conv_db.c_" + orgId + "_facet (id, type, data, update_time_ms) VALUES (?, 'session', ?, ?)"
                + " ON DUPLICATE KEY UPDATE data = VALUES(data), update_time_ms = VALUES(update_time_ms)",
                id, data, System.currentTimeMillis());
    }

    public Map<String, Object> facet(int orgId, String id) {
        return one(jdbc.queryForList("SELECT * FROM conv_db.c_" + orgId + "_facet WHERE id = ?", id));
    }

    private static String meta(int orgId, String table) {
        return "meta_db.org_" + orgId + "_" + table;
    }

    private static Map<String, Object> one(List<Map<String, Object>> rows) {
        return rows.isEmpty() ? null : rows.get(0);
    }
}
