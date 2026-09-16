'use strict';

// One Pino logger for the whole app. The OpenTelemetry transport
// turns every line into an OTLP log record and exports it to the
// endpoint in OTEL_EXPORTER_OTLP_ENDPOINT (the collector here).
const pino = require('pino');

const transport = pino.transport({
  targets: [
    {
      target: 'pino-opentelemetry-transport',
      options: {
        // The transport runs in a worker thread and builds its own
        // resource, so the service name is set here, not on the
        // tracer provider.
        resourceAttributes: {
          'service.name': process.env.OTEL_SERVICE_NAME || 'pino-logs-demo',
        },
      },
    },
    // Keep a copy on stdout so `docker compose logs` shows them too.
    { target: 'pino/file', options: { destination: 1 } },
  ],
});

module.exports = pino(
  { level: process.env.LOG_LEVEL || 'info' },
  transport
);
