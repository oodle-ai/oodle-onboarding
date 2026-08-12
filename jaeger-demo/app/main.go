package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/jaeger"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	tp, err := initTracerProvider(ctx)
	if err != nil {
		log.Fatalf("failed to initialize tracer provider: %v", err)
	}
	defer func() {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		if err := tp.Shutdown(shutdownCtx); err != nil {
			log.Printf("failed to shutdown tracer provider: %v", err)
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", handleHealth)
	mux.HandleFunc("POST /order", handleOrder)

	handler := otelhttp.NewHandler(mux, "jaeger-demo-service")

	server := &http.Server{
		Addr:              ":8080",
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Println("jaeger-demo-service listening on :8080")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	<-sigCh
	log.Println("shutting down server...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("server shutdown error: %v", err)
	}
}

func initTracerProvider(_ context.Context) (*sdktrace.TracerProvider, error) {
	endpoint := os.Getenv("JAEGER_ENDPOINT")
	if endpoint == "" {
		endpoint = "http://otel-collector:14268/api/traces"
	}

	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "jaeger-demo-service"
	}

	exporter, err := jaeger.New(
		jaeger.WithCollectorEndpoint(jaeger.WithEndpoint(endpoint)),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create Jaeger exporter: %w", err)
	}

	res, err := resource.New(context.Background(),
		resource.WithAttributes(
			semconv.ServiceName(serviceName),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)

	otel.SetTracerProvider(tp)
	return tp, nil
}

func handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	resp := map[string]string{"status": "ok", "service": "jaeger-demo-service"}
	json.NewEncoder(w).Encode(resp)
}

func handleOrder(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	tracer := otel.Tracer("jaeger-demo-service")

	var req struct {
		Item     string `json:"item"`
		Quantity int    `json:"quantity"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
		return
	}

	span := trace.SpanFromContext(ctx)
	span.SetAttributes(
		attribute.String("order.item", req.Item),
		attribute.Int("order.quantity", req.Quantity),
	)

	if err := validateOrder(ctx, tracer, req.Item, req.Quantity); err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err.Error()), http.StatusBadRequest)
		return
	}

	price := lookupPrice(ctx, tracer, req.Item)
	total := calculateTotal(ctx, tracer, price, req.Quantity)

	span.SetAttributes(attribute.Float64("order.total", total))

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"item":     req.Item,
		"quantity": req.Quantity,
		"price":    price,
		"total":    total,
		"status":   "confirmed",
	})
}

func validateOrder(ctx context.Context, tracer trace.Tracer, item string, quantity int) error {
	_, span := tracer.Start(ctx, "order.validate")
	defer span.End()

	span.SetAttributes(
		attribute.String("validate.item", item),
		attribute.Int("validate.quantity", quantity),
	)

	if item == "" {
		return fmt.Errorf("item is required")
	}
	if quantity <= 0 {
		return fmt.Errorf("quantity must be positive")
	}
	return nil
}

func lookupPrice(ctx context.Context, tracer trace.Tracer, item string) float64 {
	_, span := tracer.Start(ctx, "order.lookup_price")
	defer span.End()

	span.SetAttributes(attribute.String("pricing.item", item))

	time.Sleep(time.Duration(10+rand.Intn(40)) * time.Millisecond) //nolint:gosec

	prices := map[string]float64{
		"widget":  9.99,
		"gadget":  24.99,
		"gizmo":   14.99,
		"doodad":  4.99,
		"thingam": 19.99,
	}

	if p, ok := prices[item]; ok {
		span.SetAttributes(attribute.Float64("pricing.amount", p))
		return p
	}

	defaultPrice := 12.99
	span.SetAttributes(attribute.Float64("pricing.amount", defaultPrice))
	return defaultPrice
}

func calculateTotal(ctx context.Context, tracer trace.Tracer, price float64, quantity int) float64 {
	_, span := tracer.Start(ctx, "order.calculate_total")
	defer span.End()

	total := price * float64(quantity)
	span.SetAttributes(
		attribute.Float64("billing.unit_price", price),
		attribute.Int("billing.quantity", quantity),
		attribute.Float64("billing.total", total),
	)
	return total
}
