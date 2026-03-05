package main

import (
	"fmt"
	"math/rand"
	"os"
	"time"

	"github.com/DataDog/datadog-go/v5/statsd"
)

func main() {
	dogstatsdAddr := os.Getenv("DOGSTATSD_ADDR")
	if dogstatsdAddr == "" {
		dogstatsdAddr = "datadog-agent:8125"
	}

	client, err := statsd.New(dogstatsdAddr,
		statsd.WithNamespace("demo."),
		statsd.WithTags([]string{"service:demo-app", "env:dev"}),
	)
	if err != nil {
		panic(fmt.Sprintf("failed to create DogStatsD client: %v", err))
	}
	defer func() {
		if err := client.Close(); err != nil {
			fmt.Printf("error closing DogStatsD client: %v\n", err)
		}
	}()

	fmt.Printf("DogStatsD client connected to %s\n", dogstatsdAddr)
	fmt.Println("Emitting metrics every 2-5 seconds...")

	endpoints := []string{"/api/users", "/api/orders", "/api/products", "/api/health", "/api/search"}
	methods := []string{"GET", "POST", "PUT", "DELETE"}
	statusCodes := []string{"200", "201", "400", "404", "500"}

	for {
		endpoint := endpoints[rand.Intn(len(endpoints))]
		method := methods[rand.Intn(len(methods))]
		statusCode := statusCodes[rand.Intn(len(statusCodes))]
		durationMs := rand.Float64() * 500

		tags := []string{
			fmt.Sprintf("endpoint:%s", endpoint),
			fmt.Sprintf("method:%s", method),
			fmt.Sprintf("status_code:%s", statusCode),
		}

		// Count: track number of HTTP requests
		if err := client.Incr("http.requests.total", tags, 1); err != nil {
			fmt.Printf("error sending counter: %v\n", err)
		}

		// Histogram: track request duration distribution
		if err := client.Histogram("http.request.duration_ms", durationMs, tags, 1); err != nil {
			fmt.Printf("error sending histogram: %v\n", err)
		}

		// Gauge: simulate active connections (random value 10-100)
		activeConns := float64(10 + rand.Intn(91))
		if err := client.Gauge("http.active_connections", activeConns, nil, 1); err != nil {
			fmt.Printf("error sending gauge: %v\n", err)
		}

		// Gauge: simulate CPU usage percentage
		cpuUsage := 20.0 + rand.Float64()*60.0
		if err := client.Gauge("system.cpu_usage_percent", cpuUsage, nil, 1); err != nil {
			fmt.Printf("error sending gauge: %v\n", err)
		}

		// Gauge: simulate memory usage in MB
		memUsage := 256.0 + rand.Float64()*512.0
		if err := client.Gauge("system.memory_usage_mb", memUsage, nil, 1); err != nil {
			fmt.Printf("error sending gauge: %v\n", err)
		}

		// Distribution: track request payload sizes
		payloadSize := float64(rand.Intn(10000))
		if err := client.Distribution("http.request.payload_bytes", payloadSize, tags, 1); err != nil {
			fmt.Printf("error sending distribution: %v\n", err)
		}

		fmt.Printf("Sent metrics: %s %s -> %s (%.1fms)\n", method, endpoint, statusCode, durationMs)

		time.Sleep(time.Duration(2+rand.Intn(3)) * time.Second)
	}
}
