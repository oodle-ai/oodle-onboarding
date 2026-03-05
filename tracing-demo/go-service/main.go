package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
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

	httpClient := &http.Client{
		Transport: otelhttp.NewTransport(http.DefaultTransport),
		Timeout:   10 * time.Second,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", handleHealth)
	mux.HandleFunc("POST /calculate-billing", calculateBillingHandler(httpClient))

	handler := otelhttp.NewHandler(mux, "go-service")

	server := &http.Server{
		Addr:              ":8083",
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Println("go-service listening on :8083")
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

func initTracerProvider(ctx context.Context) (*sdktrace.TracerProvider, error) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "otel-collector:4317"
	}

	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "go-service"
	}

	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create OTLP exporter: %w", err)
	}

	res, err := resource.New(ctx,
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
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	return tp, nil
}

func handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	resp := map[string]string{
		"status":  "ok",
		"service": "go-service",
	}
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("failed to encode health response: %v", err)
	}
}

type billingRequest struct {
	Item     string `json:"item"`
	Quantity int    `json:"quantity"`
}

type pricingResponse struct {
	Item     string  `json:"item"`
	Price    float64 `json:"price"`
	Currency string  `json:"currency"`
}

func calculateBillingHandler(client *http.Client) http.HandlerFunc {
	pythonServiceURL := os.Getenv("PYTHON_SERVICE_URL")
	if pythonServiceURL == "" {
		pythonServiceURL = "http://python-service:8082"
	}

	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		tracer := otel.Tracer("go-service")

		var billing billingRequest
		if err := json.NewDecoder(r.Body).Decode(&billing); err != nil {
			http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
			return
		}

		span := trace.SpanFromContext(ctx)
		span.SetAttributes(
			attribute.String("order.item", billing.Item),
			attribute.Int("order.item_count", billing.Quantity),
		)

		// Validate the billing request
		if err := validateBilling(ctx, tracer, &billing); err != nil {
			http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err.Error()), http.StatusBadRequest)
			return
		}

		// Fetch pricing from python-service
		pricing, err := fetchPricing(ctx, client, pythonServiceURL, billing.Item)
		if err != nil {
			span.RecordError(err)
			http.Error(w, fmt.Sprintf(`{"error":"failed to fetch pricing: %s"}`, err.Error()), http.StatusBadGateway)
			return
		}

		// Calculate total
		total := calculateTotal(ctx, tracer, pricing.Price, billing.Quantity)

		// Apply discount
		finalAmount, discountPct := applyDiscount(ctx, tracer, total)

		span.SetAttributes(
			attribute.Float64("billing.amount", finalAmount),
			attribute.String("billing.currency", pricing.Currency),
		)

		w.Header().Set("Content-Type", "application/json")
		response := map[string]interface{}{
			"item":         billing.Item,
			"quantity":     billing.Quantity,
			"unit_price":   pricing.Price,
			"subtotal":     total,
			"discount_pct": discountPct,
			"total":        finalAmount,
			"currency":     pricing.Currency,
			"service":      "go-service",
		}
		if err := json.NewEncoder(w).Encode(response); err != nil {
			log.Printf("failed to encode billing response: %v", err)
		}
	}
}

func validateBilling(ctx context.Context, tracer trace.Tracer, billing *billingRequest) error {
	_, span := tracer.Start(ctx, "billing.validate")
	defer span.End()

	span.SetAttributes(
		attribute.String("billing.validate.item", billing.Item),
		attribute.Int("billing.validate.quantity", billing.Quantity),
	)

	if billing.Item == "" {
		err := fmt.Errorf("item is required")
		span.RecordError(err)
		return err
	}
	if billing.Quantity <= 0 {
		err := fmt.Errorf("quantity must be greater than zero")
		span.RecordError(err)
		return err
	}

	return nil
}

func fetchPricing(ctx context.Context, client *http.Client, baseURL string, item string) (*pricingResponse, error) {
	pricingURL := fmt.Sprintf("%s/get-pricing?item=%s", baseURL, url.QueryEscape(item))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pricingURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create pricing request: %w", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("pricing request failed: %w", err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Printf("failed to close pricing response body: %v", err)
		}
	}()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read pricing response: %w", err)
	}

	if resp.StatusCode >= http.StatusBadRequest {
		return nil, fmt.Errorf("pricing service returned status %d: %s", resp.StatusCode, string(body))
	}

	var pricing pricingResponse
	if err := json.Unmarshal(body, &pricing); err != nil {
		return nil, fmt.Errorf("failed to parse pricing response: %w", err)
	}

	return &pricing, nil
}

func calculateTotal(ctx context.Context, tracer trace.Tracer, unitPrice float64, quantity int) float64 {
	_, span := tracer.Start(ctx, "billing.calculate_total")
	defer span.End()

	total := unitPrice * float64(quantity)

	span.SetAttributes(
		attribute.Float64("billing.unit_price", unitPrice),
		attribute.Int("billing.quantity", quantity),
		attribute.Float64("billing.subtotal", total),
	)

	return total
}

func applyDiscount(ctx context.Context, tracer trace.Tracer, total float64) (float64, float64) {
	_, span := tracer.Start(ctx, "billing.apply_discount")
	defer span.End()

	// Random discount between 0% and 20%
	discountPct := float64(rand.Intn(21)) //nolint:gosec // not security-sensitive
	discountAmount := total * (discountPct / 100.0)
	finalAmount := total - discountAmount

	span.SetAttributes(
		attribute.Float64("billing.discount_pct", discountPct),
		attribute.Float64("billing.discount_amount", discountAmount),
		attribute.Float64("billing.final_amount", finalAmount),
	)

	return finalAmount, discountPct
}
