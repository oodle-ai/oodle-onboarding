#!/usr/bin/env bash
# List API tracing destinations with their delivery health.
# Healthy: state "enabled" and last_success_at later than any last_error_at.
source "$(dirname "$0")/common.sh"
require_admin_login

if ! out="$(admin_ant beta:organization:telemetry-destinations list --format jsonl)"; then
  echo "Listing failed for $(grep -m1 'Logged in to' <<<"$AUTH_STATUS" | sed 's/^ *//')." >&2
  echo "A 403 means this login can't manage destinations in that organization: check it is the" >&2
  echo "organization that owns ANTHROPIC_API_KEY and that you are an admin there." >&2
  exit 1
fi
jq -s 'map({id, display_name, endpoint_url, content_mode: .traces.content_mode,
      state: .state.type, last_success_at: .delivery_health.last_success_at,
      last_error_at: .delivery_health.last_error_at, last_error: .delivery_health.last_error})' <<<"$out"
