.PHONY: up down logs logs-collector logs-workload logs-crdb status clean restart sql console scrape verify import-dashboards help

# Must match CRDB_CLUSTER_NAME in .env. It is the `crdb_cluster` label value
# the collector stamps on every series.
CLUSTER ?= crdb-demo

help:
	@echo "CockroachDB -> Oodle (metrics via OTel Collector)"
	@echo ""
	@echo "Usage:"
	@echo "  make up                - Start the 3-node cluster, workload, and collector"
	@echo "  make down              - Stop all services"
	@echo "  make clean             - Stop and remove volumes (wipes cluster data)"
	@echo "  make restart           - Restart all services"
	@echo "  make status            - Show service status"
	@echo "  make logs              - Tail all logs"
	@echo "  make logs-collector    - Tail OTel Collector logs"
	@echo "  make logs-workload     - Tail movr workload logs"
	@echo "  make logs-crdb         - Tail CockroachDB node logs"
	@echo "  make sql               - Open a SQL shell on roach1"
	@echo "  make console           - Print the DB Console URL"
	@echo "  make scrape            - Show a sample of the raw /_status/vars output"
	@echo "  make verify            - Check that CockroachDB metrics reached Oodle"
	@echo "  make import-dashboards - Import the CockroachDB dashboard into Oodle"

up:
	@test -f .env || { echo "Error: .env not found. Run: cp .env.example .env"; exit 1; }
	docker compose up -d
	@echo ""
	@echo "Cluster starting. DB Console: http://localhost:8080"
	@echo "Give it ~2 minutes, then run: make verify"

down:
	docker compose down

clean:
	docker compose down -v

restart: down up

status:
	docker compose ps

logs:
	docker compose logs -f

logs-collector:
	docker compose logs -f otel-collector

logs-workload:
	docker compose logs -f workload

logs-crdb:
	docker compose logs -f roach1 roach2 roach3

sql:
	docker compose exec roach1 ./cockroach sql --insecure --host=roach1:26257

console:
	@echo "http://localhost:8080"

scrape:
	@echo "=== sample of roach1:8080/_status/vars ==="
	@curl -s http://localhost:8080/_status/vars \
		| grep -E '^(sql_query_count|sql_conns|liveness_livenodes|ranges|replicas|capacity_used)[ {]' || true
	@echo ""
	@printf 'exposition lines from roach1 (histogram buckets counted individually): '
	@curl -s http://localhost:8080/_status/vars | grep -vc '^#'

verify:
	@command -v oodle >/dev/null 2>&1 || { echo "Error: oodle CLI not found. Install from https://docs.oodle.ai"; exit 1; }
	@echo "=== Collector export counters (0 failures expected) ==="
	@curl -s http://localhost:8888/metrics \
		| grep -E '^otelcol_exporter_(sent|send_failed)_metric_points\{exporter="otlphttp/oodle"' \
		| sed 's/{.*}/ /' || echo "  (collector not reachable on :8888)"
	@echo ""
	@echo "=== CockroachDB metric families in Oodle (all crdb_ prefixed) ==="
	@oodle metrics names -o csv 2>/dev/null | tail -n +2 > /tmp/crdb-metric-names.txt || true
	@echo "  crdb_ prefixed names: $$(grep -c '^crdb_' /tmp/crdb-metric-names.txt || echo 0)"
	@grep -E '^crdb_(sql_query_count|sql_conns|sql_service_latency_bucket|liveness_livenodes|ranges|replicas|capacity_used|txn_commits)$$' \
		/tmp/crdb-metric-names.txt | sed 's/^/  found: /' || echo "  (none yet, give the collector a minute)"
	@echo ""
	@echo "=== Unprefixed leftovers (expect none) ==="
	@grep -E '^(sql_|txn_|ranges|replicas|capacity|liveness_|sys_|rocksdb_|livebytes|clock_offset)' \
		/tmp/crdb-metric-names.txt > /tmp/crdb-stale-names.txt 2>/dev/null; \
		if [ -s /tmp/crdb-stale-names.txt ]; then sed 's/^/  STALE: /' /tmp/crdb-stale-names.txt; \
		else echo "  none"; fi
	@echo ""
	@echo "=== Scrape metrics keep their standard names ==="
	@# Query rather than grep the name list: a stale crdb_up from an older
	@# pipeline stays in the name list until it ages out of retention.
	@test "$$(oodle metrics query --query 'count(up{job="cockroachdb",crdb_cluster="$(CLUSTER)"})' -o csv 2>/dev/null | tail -n +2 | wc -l)" -gt 0 \
		&& echo "  ok: up is reporting" || echo "  MISSING: up has no current data"
	@test "$$(oodle metrics query --query 'count(crdb_up{crdb_cluster="$(CLUSTER)"})' -o csv 2>/dev/null | tail -n +2 | wc -l)" -eq 0 \
		&& echo "  ok: crdb_up is not reporting" \
		|| echo "  WARN: crdb_up is live, the prefix is renaming scrape metrics"
	@echo ""
	@echo "=== Live nodes ==="
	@oodle metrics query --query 'max(crdb_liveness_livenodes{crdb_cluster="$(CLUSTER)"})' -o table 2>/dev/null || echo "  (no data yet)"
	@echo ""
	@echo "=== SQL statements/sec per node ==="
	@oodle metrics query --query 'sum by (crdb_node) (rate(crdb_sql_query_count{crdb_cluster="$(CLUSTER)"}[5m]))' -o table 2>/dev/null || echo "  (no data yet)"
	@echo ""
	@echo "=== SQL service latency p99 (nanoseconds) ==="
	@oodle metrics query --query 'histogram_quantile(0.99, sum by (le) (rate(crdb_sql_service_latency_bucket{crdb_cluster="$(CLUSTER)"}[5m])))' -o table 2>/dev/null || echo "  (no data yet)"

import-dashboards:
	@command -v oodle >/dev/null 2>&1 || { echo "Error: oodle CLI not found. Install from https://docs.oodle.ai"; exit 1; }
	oodle dashboards create -f dashboards/cockroachdb.json
