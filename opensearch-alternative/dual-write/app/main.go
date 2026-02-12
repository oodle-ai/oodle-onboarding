package main

import (
	"encoding/json"
	"io"
	"math/rand"
	"net"
	"os"
	"time"
)

type LogEntry struct {
	Timestamp string                 `json:"timestamp"`
	Level     string                 `json:"level"`
	Message   string                 `json:"message"`
	Service   string                 `json:"service"`
	Log       map[string]interface{} `json:"log,omitempty"`
}

func main() {
	levels := []string{"INFO", "WARN", "ERROR", "DEBUG"}
	messages := []string{
		"Processing user request",
		"Database query executed",
		"Cache miss occurred",
		"API endpoint called",
		"Background job completed",
	}

	// Check if OTEL_ENDPOINT is set
	otelEndpoint := os.Getenv("OTEL_ENDPOINT")
	var writer io.Writer = os.Stdout

	if otelEndpoint != "" {
		// Connect to OTel collector via TCP
		conn, err := net.Dial("tcp", otelEndpoint)
		if err != nil {
			panic(err)
		}
		defer func() {
			if err := conn.Close(); err != nil {
				panic(err)
			}
		}()
		writer = conn
	}

	encoder := json.NewEncoder(writer)

	for {
		level := levels[rand.Intn(len(levels))]
		message := messages[rand.Intn(len(messages))]

		logEntry := LogEntry{
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Level:     level,
			Message:   message,
			Service:   "demo-app",
			Log: map[string]interface{}{
				"request_id":  generateRequestID(),
				"duration_ms": rand.Intn(1000),
				"user_id":     rand.Intn(100),
			},
		}

		if err := encoder.Encode(logEntry); err != nil {
			panic(err)
		}

		// Sleep for 2-5 seconds between logs
		time.Sleep(time.Duration(2+rand.Intn(3)) * time.Second)
	}
}

func generateRequestID() string {
	const charset = "abcdefghijklmnopqrstuvwxyz0123456789"
	b := make([]byte, 8)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}
