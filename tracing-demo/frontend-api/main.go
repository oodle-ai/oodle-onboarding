package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
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
	mux.HandleFunc("POST /order", orderHandler(httpClient))
	mux.HandleFunc("GET /trace-demo", traceDemoHandler(httpClient))

	handler := otelhttp.NewHandler(mux, "frontend-api")

	server := &http.Server{
		Addr:              ":8080",
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Println("frontend-api listening on :8080")
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
		serviceName = "frontend-api"
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
		"service": "frontend-api",
	}
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("failed to encode health response: %v", err)
	}
}

type orderRequest struct {
	Item     string `json:"item"`
	Quantity int    `json:"quantity"`
}

type serviceResponse struct {
	Service string `json:"service"`
	Data    json.RawMessage
	Err     error
}

func orderHandler(client *http.Client) http.HandlerFunc {
	javaServiceURL := os.Getenv("JAVA_SERVICE_URL")
	if javaServiceURL == "" {
		javaServiceURL = "http://java-service:8081"
	}

	goServiceURL := os.Getenv("GO_SERVICE_URL")
	if goServiceURL == "" {
		goServiceURL = "http://go-service:8083"
	}

	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		tracer := otel.Tracer("frontend-api")

		var order orderRequest
		if err := json.NewDecoder(r.Body).Decode(&order); err != nil {
			http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
			return
		}

		orderBytes, err := json.Marshal(order)
		if err != nil {
			http.Error(w, `{"error":"failed to serialize order"}`, http.StatusInternalServerError)
			return
		}

		span := trace.SpanFromContext(ctx)
		span.SetAttributes(
			attribute.String("order.item", order.Item),
			attribute.Int("order.quantity", order.Quantity),
		)

		var wg sync.WaitGroup
		results := make([]serviceResponse, 2)

		wg.Add(2)

		go func() {
			defer wg.Done()
			results[0] = callService(ctx, tracer, client, "process-order",
				javaServiceURL+"/process-order", orderBytes)
		}()

		go func() {
			defer wg.Done()
			results[1] = callService(ctx, tracer, client, "calculate-billing",
				goServiceURL+"/calculate-billing", orderBytes)
		}()

		wg.Wait()

		response := map[string]interface{}{
			"status": "completed",
			"order":  order,
		}

		for _, res := range results {
			if res.Err != nil {
				response[res.Service] = map[string]string{"error": res.Err.Error()}
			} else {
				var data interface{}
				if err := json.Unmarshal(res.Data, &data); err != nil {
					response[res.Service] = string(res.Data)
				} else {
					response[res.Service] = data
				}
			}
		}

		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(response); err != nil {
			log.Printf("failed to encode order response: %v", err)
		}
	}
}

func callService(ctx context.Context, tracer trace.Tracer, client *http.Client, name, url string, body []byte) serviceResponse {
	ctx, span := tracer.Start(ctx, fmt.Sprintf("call-%s", name))
	defer span.End()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		span.RecordError(err)
		return serviceResponse{Service: name, Err: fmt.Errorf("failed to create request: %w", err)}
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		span.RecordError(err)
		return serviceResponse{Service: name, Err: fmt.Errorf("request failed: %w", err)}
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Printf("failed to close response body: %v", err)
		}
	}()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		span.RecordError(err)
		return serviceResponse{Service: name, Err: fmt.Errorf("failed to read response: %w", err)}
	}

	if resp.StatusCode >= http.StatusBadRequest {
		span.RecordError(fmt.Errorf("service returned status %d", resp.StatusCode))
		return serviceResponse{Service: name, Err: fmt.Errorf("service returned status %d: %s", resp.StatusCode, string(respBody))}
	}

	return serviceResponse{Service: name, Data: respBody}
}

func traceDemoHandler(client *http.Client) http.HandlerFunc {
	javaServiceURL := os.Getenv("JAVA_SERVICE_URL")
	if javaServiceURL == "" {
		javaServiceURL = "http://java-service:8081"
	}

	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		tracer := otel.Tracer("frontend-api")

		ctx, span := tracer.Start(ctx, "trace-demo")
		defer span.End()

		span.SetAttributes(attribute.String("demo.type", "quick-test"))

		req, err := http.NewRequestWithContext(ctx, http.MethodGet, javaServiceURL+"/health", nil)
		if err != nil {
			http.Error(w, `{"error":"failed to create request"}`, http.StatusInternalServerError)
			return
		}

		resp, err := client.Do(req)
		if err != nil {
			span.RecordError(err)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadGateway)
			response := map[string]string{
				"status": "error",
				"error":  fmt.Sprintf("backend service unavailable: %v", err),
			}
			if encErr := json.NewEncoder(w).Encode(response); encErr != nil {
				log.Printf("failed to encode error response: %v", encErr)
			}
			return
		}
		defer func() {
			if err := resp.Body.Close(); err != nil {
				log.Printf("failed to close response body: %v", err)
			}
		}()

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			span.RecordError(err)
			http.Error(w, `{"error":"failed to read backend response"}`, http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		response := map[string]interface{}{
			"status":           "ok",
			"trace_propagated": true,
		}

		var backendData interface{}
		if err := json.Unmarshal(body, &backendData); err != nil {
			response["backend_response"] = string(body)
		} else {
			response["backend_response"] = backendData
		}

		if encErr := json.NewEncoder(w).Encode(response); encErr != nil {
			log.Printf("failed to encode trace-demo response: %v", encErr)
		}
	}
}
