package com.oodle.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

@RestController
public class OrderController {

    private final RestTemplate restTemplate;

    @Value("${PYTHON_SERVICE_URL:http://python-service:8082}")
    private String pythonServiceUrl;

    public OrderController(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        Map<String, String> response = new HashMap<>();
        response.put("status", "ok");
        response.put("service", "java-service");
        return response;
    }

    @SuppressWarnings("unchecked")
    @PostMapping("/process-order")
    public Map<String, Object> processOrder(@RequestBody Map<String, Object> orderRequest) {
        String item = (String) orderRequest.get("item");
        int quantity = orderRequest.get("quantity") instanceof Number
                ? ((Number) orderRequest.get("quantity")).intValue()
                : Integer.parseInt(orderRequest.get("quantity").toString());

        // Call python-service to check inventory
        String inventoryUrl = pythonServiceUrl + "/check-inventory?item=" + item;
        Map<String, Object> inventoryResponse;
        try {
            inventoryResponse = restTemplate.getForObject(inventoryUrl, Map.class);
        } catch (Exception e) {
            inventoryResponse = new HashMap<>();
            inventoryResponse.put("error", "Failed to check inventory: " + e.getMessage());
        }

        // Simulate processing delay (50-200ms)
        try {
            Thread.sleep(ThreadLocalRandom.current().nextLong(50, 201));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        // Build order result
        Map<String, Object> result = new HashMap<>();
        result.put("order_item", item);
        result.put("order_quantity", quantity);
        result.put("inventory_status", inventoryResponse);
        result.put("order_status", "processed");
        return result;
    }
}
