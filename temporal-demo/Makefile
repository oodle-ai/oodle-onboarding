.PHONY: up down logs logs-collector logs-worker logs-starter logs-temporal clean restart test status import-dashboards verify help

help:
	@echo "Temporal Demo (Order Processing Workflow with Full Observability)"
	@echo ""
	@echo "Usage:"
	@echo "  make up                - Build and start all services"
	@echo "  make down              - Stop all services"
	@echo "  make logs              - View all logs"
	@echo "  make logs-collector    - View OTel Collector logs"
	@echo "  make logs-worker       - View worker logs"
	@echo "  make logs-starter      - View starter/load-gen logs"
	@echo "  make logs-temporal     - View Temporal server logs"
	@echo "  make clean             - Stop and remove volumes"
	@echo "  make restart           - Restart all services"
	@echo "  make test              - Start a single test workflow"
	@echo "  make status            - Show service status"
	@echo "  make import-dashboards - Import Temporal dashboards to Oodle"
	@echo "  make verify            - Verify signals are flowing to Oodle"

up:
	@echo "Starting all services..."
	docker-compose up --build -d

down:
	@echo "Stopping all services..."
	docker-compose down

logs:
	docker-compose logs -f

logs-collector:
	docker-compose logs -f otel-collector

logs-worker:
	docker-compose logs -f worker

logs-starter:
	docker-compose logs -f starter

logs-temporal:
	docker-compose logs -f temporal

clean:
	@echo "Cleaning up..."
	docker-compose down -v

restart: down up

test:
	@echo "Starting a single test workflow..."
	docker-compose run --rm starter python -c "\
		import asyncio; \
		from temporalio.client import Client; \
		async def run(): \
		    c = await Client.connect('temporal:7233'); \
		    r = await c.execute_workflow('OrderProcessingWorkflow', \
		        {'order_id':'test-001','item':'widget','quantity':2,'customer':'alice'}, \
		        id='test-order-001', task_queue='order-processing'); \
		    print(f'Result: {r}'); \
		asyncio.run(run())"

status:
	docker-compose ps

verify:
	@command -v oodle >/dev/null 2>&1 || { echo "Error: oodle CLI not found."; exit 1; }
	@echo "=== Checking Metrics ==="
	@echo "Server metrics:"
	@oodle metrics names --start -30m --end now 2>/dev/null | grep -E 'service_requests|persistence' || echo "  (none found yet)"
	@echo "SDK metrics:"
	@oodle metrics names --start -30m --end now 2>/dev/null | grep temporal_ || echo "  (none found yet)"
	@echo ""
	@echo "=== Checking Traces ==="
	@oodle traces list --service temporal-worker --start -30m --end now --limit 3 -o json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Found {d[\"total\"]} traces')" || echo "  (error querying traces)"
	@echo ""
	@echo "=== Checking Logs ==="
	@oodle logs index-patterns 2>/dev/null | head -5 || echo "  (error querying logs)"

import-dashboards:
	@command -v oodle >/dev/null 2>&1 || { echo "Error: oodle CLI not found. Install from https://docs.oodle.ai"; exit 1; }
	@echo "Importing Temporal dashboards to Oodle..."
	oodle dashboards create -f dashboards/temporal-server.json
	oodle dashboards create -f dashboards/temporal-sdk.json
	@echo "Dashboards imported successfully."
