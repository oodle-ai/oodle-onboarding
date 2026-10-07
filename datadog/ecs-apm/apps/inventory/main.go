// inventory is the leaf service. It answers stock lookups and wraps a
// simulated database call in its own span so Datadog shows a db node.
package main

import (
	"encoding/json"
	"log"
	"math/rand"
	"net/http"
	"time"

	httptrace "github.com/DataDog/dd-trace-go/contrib/net/http/v2"
	"github.com/DataDog/dd-trace-go/v2/ddtrace/tracer"
)

var skus = []string{"sku-100", "sku-200", "sku-300", "sku-400"}

func main() {
	// Service, env and version come from DD_SERVICE, DD_ENV and DD_VERSION.
	// The agent is on localhost:8126 because Fargate tasks share a network namespace.
	if err := tracer.Start(); err != nil {
		log.Fatalf("start tracer: %v", err)
	}
	defer tracer.Stop()

	mux := httptrace.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/inventory/{sku}", stock)

	log.Println("inventory listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}

func stock(w http.ResponseWriter, r *http.Request) {
	sku := r.PathValue("sku")

	span, _ := tracer.StartSpanFromContext(r.Context(), "postgres.query",
		tracer.ServiceName("inventory-db"),
		tracer.SpanType("sql"),
		tracer.ResourceName("SELECT qty FROM stock WHERE sku = $1"),
		tracer.Tag("db.system", "postgresql"),
	)
	time.Sleep(time.Duration(5+rand.Intn(40)) * time.Millisecond)
	span.Finish()

	known := false
	for _, s := range skus {
		if s == sku {
			known = true
		}
	}
	if !known {
		http.Error(w, `{"error":"unknown sku"}`, http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"sku": sku, "qty": rand.Intn(50)})
}
