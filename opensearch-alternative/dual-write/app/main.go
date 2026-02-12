package main

import (
	"context"
	"fmt"
	"math/rand"
	"os"
	"time"

	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/log"
	"go.opentelemetry.io/otel/log/global"
	sdklog "go.opentelemetry.io/otel/sdk/log"
)

func main() {
	ctx := context.Background()

	// Initialize OTel logger
	loggerProvider, err := initOTelLogger(ctx)
	if err != nil {
		panic(fmt.Sprintf("failed to initialize OTel logger: %v", err))
	}
	defer func() {
		if err := loggerProvider.Shutdown(ctx); err != nil {
			fmt.Printf("failed to shutdown logger provider: %v\n", err)
		}
	}()

	logger := loggerProvider.Logger("demo-app")

	// Emit logs
	levels := []string{"INFO", "WARN", "ERROR", "DEBUG"}
	messages := []string{
		"Processing user request",
		"Database query executed",
		"Cache miss occurred",
		"API endpoint called",
		"Background job completed",
	}

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
}

func initOTelLogger(ctx context.Context) (*sdklog.LoggerProvider, error) {
	endpoint := os.Getenv("OTEL_ENDPOINT")
	if endpoint == "" {
		return nil, fmt.Errorf("OTEL_ENDPOINT environment variable is required")
	}

	exporter, err := otlploghttp.New(ctx,
		otlploghttp.WithEndpoint(endpoint),
		otlploghttp.WithInsecure(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create OTLP exporter: %w", err)
	}

	loggerProvider := sdklog.NewLoggerProvider(
		sdklog.WithProcessor(sdklog.NewBatchProcessor(exporter)),
	)

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
