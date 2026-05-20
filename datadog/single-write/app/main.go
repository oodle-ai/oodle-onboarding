package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"time"

	"github.com/DataDog/datadog-go/v5/statsd"
	httptrace "gopkg.in/DataDog/dd-trace-go.v1/contrib/net/http"
	"gopkg.in/DataDog/dd-trace-go.v1/ddtrace/tracer"
)

// traceFields extracts dd.trace_id and dd.span_id from the request context
// so Datadog can correlate logs with APM traces.
func traceFields(r *http.Request) map[string]any {
	span, ok := tracer.SpanFromContext(r.Context())
	if !ok {
		return nil
	}
	return map[string]any{
		"dd.trace_id": span.Context().TraceID(),
		"dd.span_id":  span.Context().SpanID(),
	}
}

func mergeFields(a, b map[string]any) map[string]any {
	m := make(map[string]any, len(a)+len(b))
	for k, v := range a {
		m[k] = v
	}
	for k, v := range b {
		m[k] = v
	}
	return m
}

func logJSON(level, msg string, fields map[string]any) {
	entry := map[string]any{
		"timestamp": time.Now().UTC().Format(time.RFC3339Nano),
		"level":     level,
		"message":   msg,
		"service":   "datadog-demo",
		"env":       "demo",
	}
	for k, v := range fields {
		entry[k] = v
	}
	data, _ := json.Marshal(entry)
	fmt.Fprintln(os.Stdout, string(data))
}

var stats *statsd.Client

func main() {
	// Start the Datadog APM tracer
	tracer.Start(
		tracer.WithService("datadog-demo"),
		tracer.WithEnv("demo"),
		tracer.WithServiceVersion("1.0.0"),
	)
	defer tracer.Stop()

	// Initialize DogStatsD client for custom metrics
	var err error
	stats, err = statsd.New("datadog-agent:8125",
		statsd.WithNamespace("demo."),
		statsd.WithTags([]string{"env:demo", "service:datadog-demo"}),
	)
	if err != nil {
		logJSON("fatal", "Failed to create DogStatsD client", map[string]any{"error": err.Error()})
		os.Exit(1)
	}
	defer stats.Close()

	// Start background goroutine emitting custom metrics
	go emitMetrics()

	// HTTP routes with APM tracing
	mux := httptrace.NewServeMux()
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/api/order", handleOrder)
	mux.HandleFunc("/api/users", handleUsers)

	server := &http.Server{
		Addr:              ":8080",
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	logJSON("info", "datadog-demo listening on :8080", nil)
	if err := server.ListenAndServe(); err != nil {
		logJSON("fatal", "server error", map[string]any{"error": err.Error()})
		os.Exit(1)
	}
}

func handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	fmt.Fprintln(w, "ok")
}

func handleOrder(w http.ResponseWriter, r *http.Request) {
	// Track request count
	stats.Incr("order.requests", []string{"method:" + r.Method}, 1)

	// Simulate processing time
	delay := time.Duration(50+rand.Intn(200)) * time.Millisecond
	time.Sleep(delay)

	// Track processing duration
	stats.Timing("order.duration_ms", delay, nil, 1)

	// Simulate occasional errors
	if rand.Float64() < 0.1 {
		stats.Incr("order.errors", nil, 1)
		logJSON("error", "order processing failed", traceFields(r))
		http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
		return
	}

	stats.Incr("order.success", nil, 1)
	logJSON("info", "order created", mergeFields(traceFields(r), map[string]any{"processing_ms": delay.Milliseconds()}))
	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"status":"created","processing_ms":%d}`, delay.Milliseconds())
}

func handleUsers(w http.ResponseWriter, r *http.Request) {
	stats.Incr("users.requests", []string{"method:" + r.Method}, 1)

	delay := time.Duration(20+rand.Intn(100)) * time.Millisecond
	time.Sleep(delay)

	stats.Timing("users.duration_ms", delay, nil, 1)
	logJSON("info", "users listed", traceFields(r))

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintln(w, `{"users":[{"id":1,"name":"alice"},{"id":2,"name":"bob"}]}`)
}

// emitMetrics sends gauge and count metrics every 10 seconds to simulate
// application-level business metrics alongside the host metrics collected
// by the Datadog Agent.
func emitMetrics() {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		// Simulated business gauges
		stats.Gauge("queue.depth", float64(rand.Intn(100)), nil, 1)
		stats.Gauge("cache.hit_ratio", 0.5+rand.Float64()*0.5, nil, 1)
		stats.Gauge("active_connections", float64(10+rand.Intn(50)), nil, 1)

		logJSON("info", "emitted custom metrics", nil)
	}
}
