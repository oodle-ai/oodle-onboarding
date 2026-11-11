# DataPilot: an OOM in agent sandboxes, debugged with E2B telemetry

DataPilot is a sample AI data analyst. A user uploads order and event data
and asks questions in a chat. The agent writes pandas code and runs it in an
[E2B Code Interpreter](https://e2b.dev/docs/code-interpreting/analyze-data-with-ai)
sandbox. Perplexity uses
[the same pattern](https://e2b.dev/blog/how-perplexity-implemented-advanced-data-analysis-for-pro-users-in-1-week)
for its advanced data analysis. The model writes Python, a sandbox runs it,
and the result goes back into the answer.

The demo makes an incident and then shows how to find its cause in Oodle.
The point of the demo is to show what the E2B OTel export adds to the
telemetry of the application.

## The incident

The agent starts with planner v1. After five minutes it rolls out planner v2.
In the product an LLM writes the analysis code. The demo uses fixed code per
question (`planner.py`), so each run behaves the same way.

Planner v2 asks the model to keep row-level detail. For the question
"average order value by channel", the model then joins the raw orders to the
raw events on `customer_id`. That join is many-to-many. On the two small
tenants it is a few million rows. On `globex`, the largest tenant, it needs
more memory than the 2 GiB sandbox has. The Linux OOM killer in the sandbox
kills the Jupyter kernel.

The sandbox itself keeps running, and the agent never sees an OOM error. It
sees these errors from the E2B SDK:

1. `UnexpectedEndOfExecution: Connection to the execution was closed before
   the execution was finished`. The agent thinks that this is a network
   problem and tries again.
2. On the retry, while the kernel restarts: `TimeoutException: The sandbox is
   running but port is not open ... This error is likely due to sandbox
   timeout`. A retry after the restart gets `NameError`, because the restart
   removed the data that the session loaded.

The agent also has a second bug. When a session fails, it stops counting the
session but does not kill the sandbox. The sandbox runs until its 10-minute
timeout and costs money for that time.

## Three telemetry sources

| Service in Oodle | Sent by | What it has |
|------------------|---------|-------------|
| `datapilot-agent` | The agent, from outside the sandbox (`agent.py`) | Traces, logs, and the metrics `datapilot_analysis_requests`, `datapilot_analysis_duration_*`, `datapilot_sessions_active`. Tenant, question, planner version, error type, `sandbox_id`. |
| `datapilot-kernel` | The Jupyter kernel in the sandbox (`sandbox/datapilot_runtime.py`) | Step logs from the analysis code and the gauge `datapilot_kernel_rss` (exported every 10 seconds). Tenant, session, planner version, `sandbox_id`. |
| `e2b` | E2B, through its OTel export | `e2b_sandbox_*` metrics (sampled every 5 seconds from outside the VM) and logs from the E2B orchestrator, envd, and the process API. `sandbox_id` and `team_id`. |

All three have `sandbox_id`. That is the key that joins them. In the logs
index it is `log.attributes.sandbox_id`. In metrics it is the label
`sandbox_id`.

## Prerequisites

- The setup of the parent demo (`../README.md`): an E2B team with the OTel
  export pointed at your Oodle instance, an E2B API key in `../.env`, and
  `uv`.
- `OODLE_INSTANCE` and `OODLE_API_KEY` in `../.env`. The agent and the
  sandboxes send their own telemetry to
  `https://<instance>-otlp.collector.oodle.ai`. Set `OODLE_OTLP_ENDPOINT` to
  use a different endpoint.

The agent gives the Oodle API key to each sandbox as an environment
variable, because the kernel sends its telemetry directly. Code in the
sandbox can read the key. Use a key that can only ingest data.

## Run

Run these commands from the `e2b-demo` directory:

```bash
make datapilot-template   # once: builds the datapilot-analyst E2B template
make datapilot-incident   # 4 users, 16 minutes, planner v2 after 5 minutes
make datapilot-cleanup    # kills the sandboxes that the agent leaked
```

Other targets:

- `make datapilot-baseline` sends healthy traffic only.
- `make datapilot-oom-once` runs one `globex` session on planner v2. Use it
  to make one OOM during a live demo.
- `USERS`, `MINUTES` and `ROLLOUT_AFTER` change the size and the timing, for
  example `make datapilot-incident USERS=6 ROLLOUT_AFTER=120`.

To import the dashboard "DataPilot on E2B", run
`oodle dashboards create -f datapilot/dashboard.json`. If you changed
`make_dashboard.py`, run `python3 datapilot/make_dashboard.py` first.

A full incident run starts about 100 sandboxes. Each lives for less than a
minute, except the leaked ones, which live for 10 minutes.

## Files

| File | Purpose |
|------|---------|
| `agent.py` | The agent and the simulated users |
| `planner.py` | The code for each question and planner version |
| `sandbox/datapilot_runtime.py` | Telemetry from the Jupyter kernel |
| `sandbox/make_dataset.py` | Makes a tenant's uploaded files in the sandbox |
| `build_template.py` | Builds the E2B template |
| `make_dashboard.py` | Writes `dashboard.json` |
| `cleanup.py` | Kills all DataPilot sandboxes |

## Investigation runbook

Use this runbook to present the demo. Run `make datapilot-incident` and
wait until about 5 minutes after the rollout. Then give an AI agent that has
the Oodle MCP server the symptom only, for example:

> DataPilot users say that analyses fail since a few minutes ago. Find the
> cause. Use Oodle.

The steps below are the path that the investigation takes. They show what
each telemetry source can and cannot tell you. The numbers come from a run
on 2026-11-11 with 4 users and the rollout at 09:33 UTC.

### Step 1: the symptom, from the agent's metrics

```promql
sum by (outcome, error_type, tenant, question, planner_version)
  (increase(datapilot_analysis_requests[25m]))
```

All failures are `globex`, `aov_by_channel`, planner `v2`. Planner v2
succeeds on `acme-retail` and `initech`. Planner v1 succeeds on `globex`.
The error types are `TimeoutException` and `ContextRestarting`.

The agent's telemetry gives the scope of the problem. It does not give the
cause. The agent log for a failed question says:

```
UnexpectedEndOfExecution: Connection to the execution was closed before the execution was finished
TimeoutException: The sandbox is running but port is not open ... This error is likely due to sandbox timeout.
```

This text points at the network or at E2B. A team that sees only this
telemetry opens a ticket with E2B or increases the sandbox timeout. Neither
action helps.

### Step 2: the kernel's telemetry, from inside the sandbox

Filter the logs on `log.attributes.sandbox_id.keyword` for one failed
sandbox, with service `datapilot-kernel`. The last kernel log line is
`step: join orders with events on customer_id (keep row detail)`. After
that line, the kernel sends nothing. The kernel sent no
`datapilot_kernel_rss` sample at all, because it died before its first
10-second export. In other runs the last step log is also lost, because the
kernel dies before its log batch is sent.

A process that the OOM killer stops cannot report that event. The kernel's
telemetry shows where the code was, but it cannot show a hang, a crash or
an OOM. It also cannot show whether E2B lost the sandbox.

### Step 3: the E2B telemetry, for the same sandbox_id

Filter the logs on the same `sandbox_id`, with service `e2b`:

```
09:39:20  Sandbox created                     end_time 09:49:20
09:39:20  Process with pid 1633 started       python /opt/datapilot/make_dataset.py --tenant globex
09:39:37  Out of memory: process was killed   process=python   (level warn, logger orchestrator)
```

E2B logged no `Sandbox stopped`, so the sandbox did not time out. The
"sandbox timeout" in the SDK error is wrong. A process in the sandbox was
killed for memory.

The memory gauge from outside the VM shows the same event:

```promql
max by (sandbox_id) (e2b_sandbox_ram_used{sandbox_id="<id>"}) / 1048576
```

The values were 508, 634 and 1359 MiB, then 211 MiB, then a flat 424 MiB.
The fall to 211 MiB is the kill. The flat line after it is a new kernel
with no data loaded. That explains `ContextRestarting` and the `NameError`
on later questions in the same session.

The gauge is sampled every 5 seconds, so it can miss the peak of a fast
allocation. The OOM log does not miss it. Use the log as the proof and the
gauge as the picture.

### Step 4: scope and cost, from E2B

Count the OOM kills over time:

```
service:e2b AND fingerprint:"Out of memory: process was killed"
```

In the example run, the first OOM kill came in the minute of the rollout.
After that, 13 sandboxes had a kill in 8 minutes, and each killed process
was `python`. Put this next to step 1: the OOM kills start with planner v2
and affect only the largest tenant. The cause is the code that planner v2
writes. Its many-to-many join does not fit in the 2 GiB sandbox.

Then compare the agent's count of sandboxes with E2B's count:

```promql
sum(datapilot_sessions_active)   # the agent: at most 4
sum(e2b_team_sandbox_running)    # E2B: went from 3 to 14
```

The E2B lifecycle logs show how the sandboxes end. Aggregate
`log.attributes.kill_reason` on `Killing sandbox` messages: `request` means
that the agent killed the sandbox, `timeout` means that it expired. Each
failed session leaves a sandbox that runs until its timeout. This is the
second bug, and only E2B's telemetry shows it.

### Step 5: the outage for all tenants

The leaked sandboxes add up. In the example run, E2B counted 20 running
sandboxes at 09:43, while the agent believed that it held 1. 20 is the
concurrent sandbox limit of the E2B team in this run. After that, each new
session for each tenant failed:

```
429: Rate limit exceeded ... you have reached the maximum number of concurrent E2B sandboxes (20).
```

```promql
sum by (tenant, outcome, error_type) (increase(datapilot_sessions[1m]))
```

The 429 error is clear, but it does not say why the team is at its limit.
The agent's own count says that it is not. The E2B telemetry gives the
answer:

1. `e2b_team_sandbox_running` is at the limit.
2. The running sandboxes are the ones with an OOM log and no
   `Killing sandbox` with `kill_reason: request`.
3. As each one expires, E2B logs `Killing sandbox` with
   `kill_reason: timeout`, and capacity comes back.

The OOM on one tenant became an outage for all tenants. To see this part,
the incident must run long enough for the leaked sandboxes to reach your
team's limit. With the default settings, that took about 9 minutes of
planner v2 on a team with a limit of 20.

### What each source contributes

| Question | Agent | Kernel | E2B |
|----------|-------|--------|-----|
| Which tenant, question, and release fail? | Yes | Yes | No |
| Which code step was running? | No | Yes, but the kernel can die before it sends the line | Process command line only |
| Did the process crash, and why? | No, the error says "timeout" | No, it was killed | Yes: `Out of memory: process was killed` |
| Did the sandbox stay up? | No | No | Yes: no `Sandbox stopped` |
| How much memory, up to the kill? | No | No sample before the kill | Yes: `e2b_sandbox_ram_used` |
| Did the kernel lose its data? | Only as later errors | No | Yes: memory falls to the idle level |
| Do failed sessions leak sandboxes? | No, it counts what it believes | No | Yes: `e2b_team_sandbox_running`, `kill_reason` |
| Why is the team at its sandbox limit? | No, it sees only the 429 | No | Yes: leaked sandboxes that expire with `kill_reason: timeout` |

### The fix

1. Change the planner v2 prompt so that the model aggregates events per
   customer before the join, as planner v1 does.
2. Kill the sandbox in a `finally` block, so that a failed session does not
   leak it.
3. Make an Oodle monitor on the E2B log `Out of memory: process was killed`.
   Then the next OOM kill sends an alert with the `sandbox_id`, and nobody
   needs to start from a misleading timeout error.

## Behavior to know

- The E2B OOM log has its text in `fingerprint`, and Oodle can show
  `message` as null for it. Search with
  `fingerprint:"Out of memory: process was killed"`.
- The E2B log attributes are under `log.attributes`. Filter with
  `log.attributes.sandbox_id.keyword` for an exact match.
- E2B logs the command line of each `commands.run` call, and envd logs the
  names of the environment variables that the agent sets, but not their
  values.
- Code that runs through `run_code` goes to the Jupyter kernel, not to the
  E2B process API. E2B does not log its text. The kernel's own logs are the
  only record of which step ran.
