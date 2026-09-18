package ai.oodle.demo.springai;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Drives the agent on a timer so the demo produces traces without anyone
 * curling it. Disable with DEMO_LOADGEN=false and use POST /chat?q=... instead.
 */
@Component
@EnableScheduling
@ConditionalOnProperty(name = "demo.loadgen.enabled", havingValue = "true", matchIfMissing = true)
public class LoadGenerator {

    private static final String QUESTION =
            "What's the weather in Paris right now, and should I take an umbrella?";

    private final ChatService chatService;

    public LoadGenerator(ChatService chatService) {
        this.chatService = chatService;
    }

    @Scheduled(initialDelayString = "${demo.loadgen.initial-delay-ms:5000}",
               fixedDelayString = "${demo.loadgen.interval-ms:15000}")
    public void tick() {
        try {
            System.out.println("[java-spring-ai] " + chatService.ask(QUESTION));
        } catch (Exception e) {
            System.err.println("[java-spring-ai] run failed: " + e.getMessage());
        }
    }
}
