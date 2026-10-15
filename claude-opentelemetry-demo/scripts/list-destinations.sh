#!/usr/bin/env bash
# List API tracing destinations with their delivery health.
# Healthy: state "enabled" and last_success_at later than any last_error_at.
source "$(dirname "$0")/common.sh"
require_admin_login

admin_ant beta:organization:telemetry-destinations list --format jsonl \
  | jq -s 'map({id, display_name, endpoint_url, content_mode: .traces.content_mode,
        state: .state.type, last_success_at: .delivery_health.last_success_at,
        last_error_at: .delivery_health.last_error_at, last_error: .delivery_health.last_error})'
