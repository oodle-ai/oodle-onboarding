#!/bin/sh
set -e

CONFIG_DIR="${OPENCLAW_STATE_DIR:-/state}"
CONFIG="$CONFIG_DIR/openclaw.json"

mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG" ]; then
  sed -e "s|__OTEL_ENDPOINT__|${OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4318}|g" \
      -e "s|__MODEL__|${OPENCLAW_MODEL:-google/gemini-2.5-flash}|g" \
      /seed/openclaw.json > "$CONFIG"
fi

# Link the plugin rather than copy it, so the Langfuse and OTel packages in
# /plugin/node_modules stay resolvable. Linking is idempotent, and --force is
# rejected for links, so a repeat install is allowed to fail.
openclaw plugins install --link /plugin >/dev/null 2>&1 || true

exec "$@"
