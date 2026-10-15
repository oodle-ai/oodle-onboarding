package ai.oodle.demo.proposals;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * One jar, four roles, picked by {@code demo.role} ({@code DEMO_ROLE}):
 * <ul>
 *   <li>{@code web}: the firm's MCP server, under the Java agent.</li>
 *   <li>{@code app}: the backend that drives sessions and the in-house
 *       chat, under the Java agent.</li>
 *   <li>{@code driver}: plays the browser, untraced.</li>
 *   <li>{@code provision}: one-time setup, untraced.</li>
 * </ul>
 */
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
