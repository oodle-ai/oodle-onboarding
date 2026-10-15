# Sourced by the destination scripts: load ../.env and check the admin login.
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$DEMO_DIR/.env" ]]; then
  echo "Missing $DEMO_DIR/.env (cp .env.example .env)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source "$DEMO_DIR/.env"
set +a

for tool in ant jq; do
  if ! command -v "$tool" >/dev/null; then
    echo "'$tool' is required. ant: https://docs.claude.com/en/api/sdks/cli" >&2
    exit 1
  fi
done

# Every ant call below goes through this: the first two variables would win
# over --profile, and ANTHROPIC_BASE_URL would send the admin login elsewhere.
admin_ant() {
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL \
    ant --profile admin "$@"
}

require_admin_login() {
  if ! AUTH_STATUS="$(admin_ant auth status 2>&1)" || ! grep -q "org:admin" <<<"$AUTH_STATUS"; then
    echo "No admin login with the org:admin scope. Run this, approve in the browser, then retry:" >&2
    echo "  ant auth login --profile admin --scope \"org:admin\"" >&2
    echo "(It makes 'admin' the active profile; switch back with 'ant profile activate <profile>'.)" >&2
    exit 1
  fi
}
