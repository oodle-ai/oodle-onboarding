#!/bin/bash
# Sync this directory to the demo VM and restart the stack.
#
# .env is excluded on purpose: the VM's copy carries the real
# credentials and the local one does not, so syncing it leaves the
# collector with no Oodle endpoint and it crash loops.
set -euo pipefail
cd "$(dirname "$0")"
VM=${VM:-ubuntu@100.71.238.123}
rsync -az --exclude node_modules --exclude __pycache__ --exclude .claude --exclude .env \
  ./ "$VM":~/newrelic-demo/
ssh "$VM" 'cd ~/newrelic-demo && docker compose up -d'
