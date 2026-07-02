# OTel Collector contrib — has the syslog receiver + awscloudwatchlogs exporter.
FROM otel/opentelemetry-collector-contrib:0.155.0

COPY otel-collector-config.yaml /etc/otel/config.yaml

# Base image ENTRYPOINT is the collector binary; these are its args.
CMD ["--config", "/etc/otel/config.yaml"]
