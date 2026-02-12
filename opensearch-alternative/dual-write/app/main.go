package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net"
	"os"
	"time"

	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/log"
	"go.opentelemetry.io/otel/log/global"
	sdklog "go.opentelemetry.io/otel/sdk/log"
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

	// Check if OTEL_ENDPOINT is set for OTel SDK mode
	otelEndpoint := os.Getenv("OTEL_ENDPOINT")
	useOTelSDK := otelEndpoint != "" && os.Getenv("USE_OTEL_SDK") == "true"

	if useOTelSDK {
		// Use OpenTelemetry SDK
		ctx := context.Background()

		// Initialize OTel logger
		loggerProvider, err := initOTelLogger(ctx, otelEndpoint)
		if err != nil {
			panic(fmt.Sprintf("failed to initialize OTel logger: %v", err))
		}
		defer func() {
			if err := loggerProvider.Shutdown(ctx); err != nil {
				fmt.Printf("failed to shutdown logger provider: %v\n", err)
			}
		}()

		logger := loggerProvider.Logger("demo-app")

		// Emit logs using OTel SDK
		for {
			level := levels[rand.Intn(len(levels))]
			message := messages[rand.Intn(len(messages))]

			logRecord := log.Record{}
			logRecord.SetBody(log.StringValue(message))
			logRecord.SetSeverityText(level)
			logRecord.SetTimestamp(time.Now())
			logRecord.AddAttributes(
				log.String("service", "demo-app"),
				log.String("request_id", generateRequestID()),
				log.Int("duration_ms", rand.Intn(1000)),
				log.Int("user_id", rand.Intn(100)),
			)

			logger.Emit(ctx, logRecord)

			time.Sleep(time.Duration(2+rand.Intn(3)) * time.Second)
		}
	} else {
		// Fallback to stdout or TCP mode for other agents
		var writer io.Writer = os.Stdout

		if otelEndpoint != "" {
			// Connect to OTel collector via TCP (legacy mode for tcplog receiver)
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

			time.Sleep(time.Duration(2+rand.Intn(3)) * time.Second)
		}
	}
}

func initOTelLogger(ctx context.Context, endpoint string) (*sdklog.LoggerProvider, error) {
	// Create OTLP HTTP exporter
	exporter, err := otlploghttp.New(ctx,
		otlploghttp.WithEndpoint(endpoint),
		otlploghttp.WithInsecure(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create OTLP exporter: %w", err)
	}

	// Create logger provider
	loggerProvider := sdklog.NewLoggerProvider(
		sdklog.WithProcessor(sdklog.NewBatchProcessor(exporter)),
	)

	// Set as global logger provider
	global.SetLoggerProvider(loggerProvider)

	return loggerProvider, nil
}

func generateRequestID() string {
	const charset = "abcdefghijklmnopqrstuvwxyz0123456789"
	b := make([]byte, 8)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}
