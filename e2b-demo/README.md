# E2B Demo

A workload that starts [E2B](https://e2b.dev/) sandboxes and puts CPU, memory
and disk load on them. Use it to see the E2B OTel telemetry export arrive in
Oodle.

E2B sends the telemetry, not this demo. The demo only makes sandboxes run,
because E2B exports metrics and logs only while sandboxes run.

For a realistic application, see [`datapilot/`](datapilot/README.md). It is
an AI data analyst that runs its code in E2B sandboxes. It makes an
out-of-memory (OOM) incident and shows how the E2B telemetry finds its cause.

## Prerequisites

- An E2B team with the
  [OTel telemetry export](https://docs.e2b.dev/sandbox/otel-telemetry-export)
  turned on and pointed at your Oodle instance. E2B offers the export on
  Enterprise and BYOC plans, and the E2B team turns it on. The E2B tile in
  Oodle (Integrations, search "E2B") shows the endpoint and headers to send to
  E2B.
- An E2B API key. Create one in the E2B console: Project, API keys,
  Create a key.
- [uv](https://docs.astral.sh/uv/). The script declares its own dependencies.
- The [oodle CLI](https://docs.oodle.ai), logged in to the instance that gets
  the export, for `make verify`.

## Run

```bash
cp .env.example .env    # then put your E2B API key in .env
make smoke              # one sandbox, short phases
make run                # one round of 3 sandboxes, 90 seconds per phase
make run-forever        # rounds until you stop it with Ctrl+C
```

Each sandbox goes through three phases:

| Phase | What it does | What to look for |
|-------|--------------|------------------|
| cpu | Keeps every vCPU busy | `e2b_sandbox_cpu_used` at 100, `CPU usage threshold exceeded` logs |
| memory | Holds 256 MiB of memory | `e2b_sandbox_ram_used` goes up |
| disk | Writes 512 MiB to `/tmp` | `e2b_sandbox_disk_used` and `e2b_sandbox_ram_cache` go up |

Worker 0 pauses its sandbox after the CPU phase and resumes it 20 seconds
later. This adds the `Pausing sandbox` and `Started resuming sandbox` log
events. The sandboxes are killed at the end of each round.

Set `SANDBOXES` and `PHASE_SECS` to change the size of a round, for example
`make run SANDBOXES=5 PHASE_SECS=120`. Sandboxes use E2B credits while they
run.

## Verify

Allow a minute or two after the first sandbox starts, then run:

```bash
make verify        # metric names, running count, CPU and memory per sandbox
make verify-logs   # E2B log messages of the last 30 minutes
```

Then open the E2B tile in Oodle and provision the dashboard and monitors.

## What arrives in Oodle

Metrics, with `sandbox_id`, `team_id`, `build_id` and `sandbox_type` on the
sandbox metrics and `team_id` on the team metrics:

- `e2b_sandbox_cpu_used`, `e2b_sandbox_cpu_total`
- `e2b_sandbox_ram_used`, `e2b_sandbox_ram_cache`, `e2b_sandbox_ram_total`
- `e2b_sandbox_disk_used`, `e2b_sandbox_disk_total`
- `e2b_team_sandbox_running`, `e2b_team_sandbox_created`

E2B also sends `e2b_sandbox_cpu_possible`, `e2b_sandbox_cpu_target`,
`e2b_sandbox_cpu_target_attempts` and `e2b_sandbox_cpu_write_pending`. The E2B
docs do not describe them, and the tile does not use them.

Logs have `service: e2b`. The sandbox ID, team ID, template ID and the E2B
component (`logger`) are in the log attributes.

## Behavior to know

- E2B samples the sandbox gauges every 5 seconds. When a sandbox stops, E2B
  stops its samples too. A plain PromQL selector keeps the last value for 5 minutes, so a
  stopped sandbox still shows for a while. Use `last_over_time(...[30s])` or
  `e2b_team_sandbox_running` for current counts.
- A resumed sandbox can start a second series with new labels. Group by
  `sandbox_id` to count each sandbox once.
- E2B counts a resume as a sandbox start in `e2b_team_sandbox_created`.
