# GCP Monitoring Alert Policies — Oodle Migration Test Fixtures

Sample GCP Cloud Monitoring alert policies for testing the Oodle alert migration wizard. These policies cover all four GCP condition types the wizard must handle, allowing end-to-end testing of policy import, translation, and monitor creation in Oodle.

## Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Cloud Monitoring API enabled in the target project (`gcloud services enable monitoring.googleapis.com`)
- `roles/monitoring.editor` IAM role on the project

## Usage

### Create sample policies

```bash
./setup.sh <project-id>
```

Or with the env var set:

```bash
export GOOGLE_CLOUD_PROJECT=my-gcp-project
./setup.sh
```

This creates four alert policies in the specified project. All policy `displayName` values are prefixed with `oodle-test-` for easy identification.

### Remove sample policies

```bash
./cleanup.sh <project-id>
```

The cleanup script lists all policies in the project and deletes any whose `displayName` starts with `oodle-test-`.

## Policy files

| File | Condition type | What it tests |
|------|---------------|---------------|
| `policies/metric-threshold.json` | `ConditionThreshold` | CPU utilization > 80% on GCE instances for 5 minutes |
| `policies/metric-absent.json` | `ConditionAbsent` | CPU utilization metric absent for 10 minutes |
| `policies/promql-alert.json` | `ConditionPrometheusQueryLanguage` | PromQL-based average CPU rate > 70% |
| `policies/log-based-alert.json` | `ConditionMatchedLog` | Log entries with `severity >= ERROR` |

### Condition type coverage

- **ConditionThreshold** — the most common GCP alert type; maps to a standard threshold monitor in Oodle using the same metric filter and aggregation settings.
- **ConditionAbsent** — fires when a metric stops reporting; maps to a "no data" / absent-metric monitor in Oodle.
- **ConditionPrometheusQueryLanguage** — native PromQL conditions introduced in GCP; maps directly to a PromQL monitor in Oodle (no translation needed beyond the duration/evaluation fields).
- **ConditionMatchedLog** — log-based alerting using Cloud Logging filter syntax; maps to a log-count monitor in Oodle.

## Notes

- All policy names are prefixed with `oodle-test-` to prevent collisions with real production policies and to make bulk cleanup reliable.
- `setup.sh` uses `gcloud alpha monitoring policies create`; the `alpha` group is required for PromQL and log-based condition types.
- Running `setup.sh` a second time will print warnings for already-existing policies but will not fail.
