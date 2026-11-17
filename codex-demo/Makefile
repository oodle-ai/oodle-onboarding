.PHONY: setup collector stop smoke-test clean enable-codex-otel disable-codex-otel install-client client-test

# ── Setup ───────────────────────────────────────────────────
setup: .env
	@echo "✓ .env ready. Run 'make collector' then 'make install-client'."

.env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — fill in your Oodle credentials."; \
	fi

# ── Collector ───────────────────────────────────────────────
collector:
	docker compose up -d
	@echo "✓ OTel collector running on :4318 (HTTP) and :4317 (gRPC)"

stop:
	docker compose down

# ── Instrumented app-server client ──────────────────────────
install-client:
	cd client && npm install
	@echo "✓ Client dependencies installed."

client-test:
	cd client && CODEX_CWD=$(CURDIR)/workspace \
		node index.mjs "Read hello.txt and tell me what it says"

# ── Codex native OTel (optional) ────────────────────────────
# Enable Codex's built-in OTLP export pointing at the local collector.
# This modifies ~/.codex/config.toml — back it up first if needed.
enable-codex-otel:
	@echo 'Adding [otel] section to ~/.codex/config.toml ...'
	@grep -q '^\[otel\]' ~/.codex/config.toml 2>/dev/null || \
		printf '\n[otel]\nenvironment = "demo"\n\n[otel.trace_exporter.otlp-http]\nprotocol = "binary"\nendpoint = "http://localhost:4318"\n\n[otel.metrics_exporter.otlp-http]\nprotocol = "binary"\nendpoint = "http://localhost:4318"\n' >> ~/.codex/config.toml
	@echo "✓ Codex native OTel enabled → http://localhost:4318"
	@echo "  Restart the Codex desktop app for changes to take effect."

disable-codex-otel:
	@echo "To disable: remove the [otel], [otel.trace_exporter.otlp-http], and [otel.metrics_exporter.otlp-http] sections from ~/.codex/config.toml."

# ── Smoke test (codex exec, no instrumentation) ─────────────
smoke-test:
	cd workspace && codex exec \
		--sandbox read-only \
		"Read the file hello.txt and tell me what it says."

# ── Cleanup ─────────────────────────────────────────────────
clean:
	docker compose down -v
