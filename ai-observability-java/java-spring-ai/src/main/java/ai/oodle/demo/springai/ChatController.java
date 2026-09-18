package ai.oodle.demo.springai;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * HTTP entry point. The incoming server span parents the agent and LLM spans,
 * which is the shape a real service produces.
 */
@RestController
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @PostMapping("/chat")
    public String chat(@RequestParam("q") String question) {
        return chatService.ask(question);
    }

    @GetMapping("/healthz")
    public String healthz() {
        return "ok";
    }
}
