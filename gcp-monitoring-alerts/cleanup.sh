#!/usr/bin/env bash
set -euo pipefail
PROJECT="${1:-${GOOGLE_CLOUD_PROJECT:-}}"
if [[ -z "$PROJECT" ]]; then echo "Usage: $0 <project-id>" && exit 1; fi

echo "Deleting alert policies with 'oodle-test-' prefix in project: $PROJECT"
gcloud alpha monitoring policies list --project="$PROJECT" --format="value(name,displayName)" | \
  while IFS=$'\t' read -r name display; do
    if [[ "$display" == oodle-test-* ]]; then
      echo "  Deleting: $display ($name)"
      gcloud alpha monitoring policies delete "$name" --project="$PROJECT" --quiet
    fi
  done
echo "Done."
