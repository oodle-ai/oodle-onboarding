#!/usr/bin/env bash
# Add an API tracing destination that sends Anthropic's server-side spans to Oodle.
# Needs an organization admin login (ant auth login --profile admin --scope "org:admin").
source "$(dirname "$0")/common.sh"
require_admin_login

: "${OODLE_INSTANCE:?set OODLE_INSTANCE in .env}"
: "${OODLE_API_KEY:?set OODLE_API_KEY in .env}"
ENDPOINT="https://${OODLE_INSTANCE}-otlp.collector.oodle.ai"
CONTENT_MODE="${DESTINATION_CONTENT_MODE:-metadata_only}"
WORKSPACES_SPEC="${DESTINATION_WORKSPACES:-all}"

if [[ "$WORKSPACES_SPEC" == "all" ]]; then
  WORKSPACES='{"type":"all"}'
else
  WORKSPACES="$(jq -cn --arg ids "$WORKSPACES_SPEC" \
    '{type: "include", workspace_ids: ($ids | split(",") | map(gsub("\\s"; "")))}')"
fi

cat <<INFO
This makes Anthropic send traces of the organization's Claude Platform activity
(Messages API requests and Managed Agents sessions) to Oodle. Oodle then holds
that data under its own retention and access controls.

  Organization / login:
$(sed 's/^/    /' <<<"$AUTH_STATUS")
  endpoint_url:        $ENDPOINT
  traces.content_mode: $CONTENT_MODE
  max_content_bytes:   750000
  headers:             X-OODLE-INSTANCE=$OODLE_INSTANCE, X-API-KEY=<OODLE_API_KEY from .env>
  workspaces:          $WORKSPACES
INFO
if [[ "$CONTENT_MODE" == "content" ]]; then
  echo "  Content mode exports prompts and responses, not only metadata."
fi
read -r -p "Create this destination? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 1; }

# The headers go in the request body on stdin, read from the environment by
# jq, so the API key never appears on a command line. sub() escapes a
# leading @, which ant would otherwise read as a file name.
body="$(jq -n '{headers: {
  "X-OODLE-INSTANCE": env.OODLE_INSTANCE,
  "X-API-KEY": (env.OODLE_API_KEY | sub("^@"; "\\@"))
}}')"

response="$(admin_ant beta:organization:telemetry-destinations create \
  --display-name "Oodle ($OODLE_INSTANCE)" \
  --endpoint-url "$ENDPOINT" \
  --traces "{\"content_mode\": \"$CONTENT_MODE\", \"max_content_bytes\": 750000}" \
  --workspaces "$WORKSPACES" \
  --format json <<<"$body")"

jq '{id, display_name, endpoint_url, header_names, traces, workspaces, state}' <<<"$response"
if ! jq -e '.header_names | index("X-API-KEY")' <<<"$response" >/dev/null; then
  echo "Warning: X-API-KEY is not in header_names; deliveries will fail with 401." >&2
fi
echo
echo "Spans start arriving within about a minute. Check delivery with: make destination-list"
echo "When done with admin work: ant auth logout --profile admin"
