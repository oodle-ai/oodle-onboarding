.PHONY: help run run-forever smoke verify verify-logs \
	datapilot-template datapilot-incident datapilot-baseline datapilot-oom-once datapilot-cleanup

SANDBOXES ?= 3
PHASE_SECS ?= 90

help:
	@echo "E2B -> Oodle (sandbox metrics and logs via the E2B OTel export)"
	@echo ""
	@echo "Usage:"
	@echo "  make smoke        - Start one sandbox with short load phases"
	@echo "  make run          - Run one round of $(SANDBOXES) sandboxes"
	@echo "  make run-forever  - Run rounds until you stop it (Ctrl+C)"
	@echo "  make verify       - Check that E2B metrics reached Oodle"
	@echo "  make verify-logs  - Check that E2B logs reached Oodle"
	@echo ""
	@echo "DataPilot OOM scenario (see datapilot/README.md):"
	@echo "  make datapilot-template  - Build the datapilot-analyst E2B template (once)"
	@echo "  make datapilot-incident  - 5 min healthy traffic, then the planner v2 rollout"
	@echo "  make datapilot-baseline  - Healthy traffic only (planner v1)"
	@echo "  make datapilot-oom-once  - One globex session on planner v2 (one OOM)"
	@echo "  make datapilot-cleanup   - Kill all DataPilot sandboxes"

check-env:
	@test -f .env || { echo "Error: .env not found. Run: cp .env.example .env"; exit 1; }

smoke: check-env
	uv run workload.py --sandboxes 1 --phase-secs 15

run: check-env
	uv run workload.py --sandboxes $(SANDBOXES) --phase-secs $(PHASE_SECS)

run-forever: check-env
	uv run workload.py --sandboxes $(SANDBOXES) --phase-secs $(PHASE_SECS) --rounds 0

check-oodle:
	@command -v oodle >/dev/null 2>&1 || { echo "Error: oodle CLI not found. Install from https://docs.oodle.ai"; exit 1; }

verify: check-oodle
	@echo "=== E2B metric names in Oodle (last hour) ==="
	@oodle metrics names -o csv 2>/dev/null | grep '^e2b_' | sed 's/^/  /' || echo "  (none yet, start a sandbox first)"
	@echo ""
	@echo "=== Running sandboxes, as E2B counts them ==="
	@oodle metrics query --query 'sum by (team_id) (e2b_team_sandbox_running)' -o table 2>/dev/null || echo "  (no data yet)"
	@echo ""
	@echo "=== CPU usage percent per sandbox (last minute) ==="
	@oodle metrics query --query 'max by (sandbox_id) (last_over_time(e2b_sandbox_cpu_used[1m]))' -o table 2>/dev/null || echo "  (no data yet)"
	@echo ""
	@echo "=== Memory usage percent per sandbox (last minute) ==="
	@oodle metrics query --query 'max by (sandbox_id) (last_over_time(e2b_sandbox_ram_used[1m]) / last_over_time(e2b_sandbox_ram_total[1m])) * 100' -o table 2>/dev/null || echo "  (no data yet)"

verify-logs: check-oodle
	@echo "=== E2B log messages in Oodle (last 30 minutes) ==="
	@index=$$(oodle logs index-patterns -o json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["title"])'); \
	printf '%s\n' "{\"index\":\"$$index\"}" \
		'{"query":{"bool":{"filter":[{"term":{"service":"e2b"}}]}},"size":0,"aggs":{"m":{"terms":{"field":"message","size":15}}}}' \
		> /tmp/e2b-logs-query.ndjson; \
	oodle logs query -f /tmp/e2b-logs-query.ndjson --start -30m -o json 2>/dev/null \
		| python3 -c 'import json,sys; r=json.load(sys.stdin)["responses"][0]; b=r["aggregations"]["m"]["buckets"]; [print("  %5d  %s" % (x["doc_count"], x["key"])) for x in b] or print("  (none yet, start a sandbox first)")'

USERS ?= 4
MINUTES ?= 16
ROLLOUT_AFTER ?= 300

check-oodle-env: check-env
	@grep -q '^OODLE_API_KEY=' .env || { echo "Error: set OODLE_INSTANCE and OODLE_API_KEY in .env"; exit 1; }

datapilot-template: check-env
	cd datapilot && uv run build_template.py

datapilot-incident: check-oodle-env
	cd datapilot && uv run agent.py --users $(USERS) --minutes $(MINUTES) --rollout-after $(ROLLOUT_AFTER)

datapilot-baseline: check-oodle-env
	cd datapilot && uv run agent.py --users $(USERS) --minutes $(MINUTES) --rollout-after -1

datapilot-oom-once: check-oodle-env
	cd datapilot && uv run agent.py --users 1 --minutes 0.1 --planner v2 --rollout-after -1 --tenant globex

datapilot-cleanup: check-env
	cd datapilot && uv run cleanup.py
