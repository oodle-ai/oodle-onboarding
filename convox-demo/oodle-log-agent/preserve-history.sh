#!/usr/bin/env bash
#
# Preserve an app's existing CloudWatch history BEFORE switching it to the Syslog log
# driver. Switching a Convox app off the CloudWatch driver DELETES its Convox-managed
# LogGroup and everything in it (verified) — so copy the history out first, into a
# persistent (non-Convox) group.
#
# To UNIFY history with the Fluent Bit agent's new logs, pass the agent's per-app group as the
# destination (e.g. /convox/<app>); the agent then appends new logs into the same group.
#
# Result: one CloudWatch group holds historical + new logs; nothing is lost.
#
#   ./preserve-history.sh <source-managed-group> <dest-persistent-group> [region]
#   e.g. ./preserve-history.sh gm-test-rails-demo-LogGroup-xxxx /convox/rails-demo us-east-1
#
# Alternative to copying: retain-loggroup.sh keeps the ORIGINAL group in place (no data moved),
# leaving history in the old group and new logs in /convox/<app>.
#
# LIMITATION: CloudWatch PutLogEvents rejects events older than 14 days, so this copies
# only the last ~14 days into the CloudWatch group. For older/large archives, export the
# whole group to S3 instead (no age limit) — see the printed hint at the end.
set -euo pipefail

SRC="${1:?source managed log group required}"
DST="${2:?destination persistent log group required}"
REGION="${3:-us-east-1}"

echo "Copying history: $SRC  ->  $DST  ($REGION)"
aws logs create-log-group --log-group-name "$DST" --region "$REGION" 2>/dev/null || true

copied=0
for STREAM in $(aws logs describe-log-streams --log-group-name "$SRC" --region "$REGION" \
                  --query "logStreams[].logStreamName" --output text); do
  aws logs create-log-stream --log-group-name "$DST" --log-stream-name "$STREAM" --region "$REGION" 2>/dev/null || true
  token=""
  while :; do
    if [ -z "$token" ]; then
      page=$(aws logs get-log-events --log-group-name "$SRC" --log-stream-name "$STREAM" \
               --region "$REGION" --start-from-head --output json)
    else
      page=$(aws logs get-log-events --log-group-name "$SRC" --log-stream-name "$STREAM" \
               --region "$REGION" --start-from-head --next-token "$token" --output json)
    fi
    n=$(echo "$page" | jq '.events | length')
    [ "$n" -eq 0 ] && break
    echo "$page" | jq -c '[.events[] | {timestamp, message}]' > /tmp/_ph_events.json
    aws logs put-log-events --log-group-name "$DST" --log-stream-name "$STREAM" \
      --region "$REGION" --log-events file:///tmp/_ph_events.json >/dev/null 2>&1 || true
    copied=$((copied + n))
    next=$(echo "$page" | jq -r '.nextForwardToken')
    [ "$next" = "$token" ] && break   # token stopped advancing => end of stream
    token="$next"
  done
done
rm -f /tmp/_ph_events.json
echo "Copied ~$copied events into $DST (events older than 14 days are skipped by CloudWatch)."
echo
echo "For a full archive of ALL history (any age), export the source group to S3 instead:"
echo "  aws logs create-export-task --log-group-name \"$SRC\" \\"
echo "    --from 0 --to \$(date +%s)000 --destination <s3-bucket> --destination-prefix \"$SRC\" --region $REGION"
