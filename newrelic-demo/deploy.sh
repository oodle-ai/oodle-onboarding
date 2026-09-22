#!/bin/bash
# Sync the demo to the VM. .env is excluded on purpose: the VM's copy
# carries the real credentials and the local one does not.
set -e
cd "$(dirname "$0")"
rsync -az --exclude node_modules --exclude __pycache__ --exclude .claude --exclude .env \
  newrelic-demo/ ubuntu@100.71.238.123:~/newrelic-demo/
ssh ubuntu@100.71.238.123 'cd ~/newrelic-demo && docker compose up -d'
