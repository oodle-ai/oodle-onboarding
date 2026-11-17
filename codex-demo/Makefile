.PHONY: setup collector stop smoke-test clean enable-codex-otel disable-codex-otel

# ── Setup ───────────────────────────────────────────────────
setup: .env
	@echo "✓ .env ready. Run 'make collector' then 'make enable-codex-otel'."

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

# ── Codex native OTel ───────────────────────────────────────
# Enable Codex's built-in OTLP export pointing at the local collector.
# This modifies ~/.codex/config.toml — back it up first if needed.
enable-codex-otel:
	@echo 'Adding [otel] section to ~/.codex/config.toml ...'
	@grep -q '^\[otel\]' ~/.codex/config.toml 2>/dev/null || \
		printf '\n[otel]\nenvironment = "demo"\n\n[otel.exporter.otlp-http]\nprotocol = "binary"\nendpoint = "http://localhost:4318"\n' >> ~/.codex/config.toml
	@echo "✓ Codex native OTel enabled → http://localhost:4318"
	@echo "  Restart any running Codex session for changes to take effect."

disable-codex-otel:
	@echo "To disable: remove the [otel] and [otel.exporter.otlp-http] sections from ~/.codex/config.toml."

# ── Smoke test ──────────────────────────────────────────────
# Runs a one-shot Codex task against the disposable workspace.
smoke-test:
	cd workspace && codex exec \
		--sandbox read-only \
		"Read the file hello.txt and tell me what it says."

# ── Cleanup ─────────────────────────────────────────────────
clean:
	docker compose down -v
