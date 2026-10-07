#!/usr/bin/env bash
# Prints `export TF_VAR_...` lines for Terraform.
#   Datadog: DD_API_KEY and DD_SITE from DD_ENV_FILE (default ../single-write/.env).
#   Oodle:   instance, collector domain and ingestion key from the configured oodle CLI.
# Any value that is already set in the environment wins.
set -euo pipefail

DD_ENV_FILE="${DD_ENV_FILE:-$(dirname "$0")/../../single-write/.env}"
if [[ -z "${DD_API_KEY:-}" && -f "$DD_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$DD_ENV_FILE"; set +a
fi
: "${DD_API_KEY:?set DD_API_KEY or DD_ENV_FILE}"
echo "export TF_VAR_dd_api_key='${DD_API_KEY}'"
echo "export TF_VAR_dd_site='${DD_SITE:-us5.datadoghq.com}'"

[[ "${WITH_OODLE:-0}" == "1" ]] || exit 0

OODLE_INSTANCE="${OODLE_INSTANCE:-$(awk '/^instance:/ {print $2}' ~/.oodle/config.yaml)}"
OODLE_COLLECTOR_DOMAIN="${OODLE_COLLECTOR_DOMAIN:-$(oodle integrations list -o json |
  python3 -c 'import json,sys; print(next(i["collectorDomain"] for i in json.load(sys.stdin) if i["type"] == "DATADOG"))')}"
OODLE_API_KEY="${OODLE_API_KEY:-$(oodle api-keys list -o json |
  python3 -c 'import json,sys; print(next(k["token"] for k in json.load(sys.stdin) if k["name"] == "Ingestion API Key"))')}"

echo "export TF_VAR_oodle_instance_id='${OODLE_INSTANCE}'"
echo "export TF_VAR_oodle_collector_domain='${OODLE_COLLECTOR_DOMAIN}'"
echo "export TF_VAR_oodle_api_key='${OODLE_API_KEY}'"
