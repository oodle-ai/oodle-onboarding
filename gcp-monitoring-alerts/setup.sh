#!/usr/bin/env bash
set -euo pipefail
PROJECT="${1:-${GOOGLE_CLOUD_PROJECT:-}}"
if [[ -z "$PROJECT" ]]; then echo "Usage: $0 <project-id>" && exit 1; fi
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Creating sample alert policies in project: $PROJECT"
for f in "$DIR"/policies/*.json; do
  name=$(basename "$f" .json)
  echo "  Creating policy: $name"
  gcloud alpha monitoring policies create \
    --project="$PROJECT" \
    --policy-from-file="$f" 2>&1 || echo "  Warning: $name may already exist"
done
echo "Done. Verify at: https://console.cloud.google.com/monitoring/alerting?project=$PROJECT"
