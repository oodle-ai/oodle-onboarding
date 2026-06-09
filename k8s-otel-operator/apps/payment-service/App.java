import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpExchange;
import java.io.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.logging.Logger;

public class App {
    private static final Logger logger = Logger.getLogger(App.class.getName());
    private static final Random random = new Random();

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);

        server.createContext("/health", exchange -> {
            sendJson(exchange, 200, "{\"status\":\"ok\",\"service\":\"payment-service\"}");
        });

        server.createContext("/charge", exchange -> {
            if (!"POST".equals(exchange.getRequestMethod())) {
                sendJson(exchange, 405, "{\"error\":\"method not allowed\"}");
                return;
            }
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

            try { Thread.sleep(random.nextInt(30) + 10); } catch (InterruptedException ignored) {}

            boolean approved = random.nextInt(10) > 0;
            String txId = "txn-" + System.currentTimeMillis();

            if (approved) {
                logger.info("Payment approved: " + txId);
            } else {
                logger.warning("Payment declined: " + txId);
            }

            String response = String.format(
                "{\"service\":\"payment-service\",\"transaction_id\":\"%s\",\"approved\":%s}",
                txId, approved
            );
            sendJson(exchange, 200, response);
        });

        server.setExecutor(null);
        server.start();
        logger.info("Payment service listening on port " + port);
    }

    private static void sendJson(HttpExchange exchange, int code, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}
