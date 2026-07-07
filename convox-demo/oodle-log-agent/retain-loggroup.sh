#!/usr/bin/env bash
#
# LOGICAL history preservation (no copy). Sets DeletionPolicy: Retain on a Convox app's
# managed CloudWatch LogGroup, so switching the app to the Syslog driver ORPHANS the group
# (keeps it in place, same name, all history, retention) instead of deleting it.
# CloudFormation reports `DELETE_SKIPPED LogGroup` on the switch. No log data is moved.
#
# Run this ONCE, BEFORE `make enable-syslog`. The original group is then kept in place with all
# its history (orphaned, same name, same retention); the Fluent Bit agent writes NEW logs to its
# own per-app group /convox/<app>. So after migration: original group = historical archive,
# /convox/<app> = new logs. No log data is ever copied.
#
#   ./retain-loggroup.sh <cfn-stack-name> [region]
#   e.g. ./retain-loggroup.sh gm-test-rails-demo us-east-1
#
# The Convox app stack is named "<rack>-<app>" (e.g. gm-test-rails-demo). Find it with:
#   aws cloudformation list-stacks --query "StackSummaries[?contains(StackName,'<app>')].StackName"
#
# NOTE: this is a one-time direct CloudFormation update to the app's stack (drift from Convox's
# generated template — just the DeletionPolicy attribute). After the switch the LogGroup is
# removed from Convox's template anyway, so there is no ongoing conflict.
set -euo pipefail

STACK="${1:?cfn stack name required, e.g. gm-test-rails-demo}"
REGION="${2:-us-east-1}"

aws cloudformation get-template --stack-name "$STACK" --region "$REGION" \
  --query TemplateBody --output json > /tmp/_rlg_tmpl.json

python3 - "$STACK" "$REGION" <<'PY'
import json, subprocess, sys
stack, region = sys.argv[1], sys.argv[2]
t = json.load(open('/tmp/_rlg_tmpl.json'))
lg = t.get('Resources', {}).get('LogGroup')
if not lg or lg.get('Type') != 'AWS::Logs::LogGroup':
    sys.exit(f"No managed LogGroup resource in stack {stack} (is the app on the CloudWatch driver?)")
if lg.get('DeletionPolicy') == 'Retain':
    print("DeletionPolicy is already Retain — nothing to do.")
    sys.exit(0)
lg['DeletionPolicy'] = 'Retain'
json.dump(t, open('/tmp/_rlg_out.json', 'w'))

def q(path):
    return json.loads(subprocess.check_output(
        ['aws','cloudformation','describe-stacks','--stack-name',stack,'--region',region,
         '--query',path,'--output','json']) or 'null')

params = q('Stacks[0].Parameters') or []
json.dump([{'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True} for p in params],
          open('/tmp/_rlg_params.json', 'w'))
caps = q('Stacks[0].Capabilities') or []

cmd = ['aws','cloudformation','update-stack','--stack-name',stack,'--region',region,
       '--template-body','file:///tmp/_rlg_out.json','--parameters','file:///tmp/_rlg_params.json']
if caps:
    cmd += ['--capabilities'] + caps
subprocess.check_call(cmd)
print("update-stack submitted; waiting for completion...")
subprocess.check_call(['aws','cloudformation','wait','stack-update-complete',
                       '--stack-name',stack,'--region',region])
print("Done. DeletionPolicy=Retain applied — the LogGroup will be RETAINED (orphaned, kept in")
print("place with all history) when you switch the app to the Syslog driver.")
PY
