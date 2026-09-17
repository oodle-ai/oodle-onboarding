.PHONY: help up down logs clean restart status shell \
       ask heartbeat tools test-all \
       native-up native-down native-ask native-spans native-logs

MESSAGE ?= Reply with exactly HEARTBEAT_OK and nothing else.
OPENCODE_MODEL ?= google/gemini-2.5-pro
# CONTINUE=1 sends the message into the last session instead of a
# new one, so the turns land in one Oodle session.
CONTINUE ?=
RUN_FLAGS = --model $(OPENCODE_MODEL) $(if $(CONTINUE),--continue,)

help:
	@echo "OpenCode Demo (real OpenCode + Langfuse OpenCode plugin -> Oodle)"
	@echo ""
	@echo "Usage:"
	@echo "  make up               - Build and start OpenCode"
	@echo "  make down             - Stop"
	@echo "  make logs             - OpenCode's own log (plugin messages included)"
	@echo "  make clean            - Stop and remove volumes"
	@echo "  make status           - Show service status"
	@echo "  make shell            - Shell into the OpenCode container"
	@echo ""
	@echo "Agent turns (each one is a trace in Oodle):"
	@echo "  make heartbeat        - A one-line turn, no tools"
	@echo "  make tools            - A turn that makes the agent read a file"
	@echo "  make ask MESSAGE=...  - A turn with your own message"
	@echo "  make ask MESSAGE=... CONTINUE=1  - Same, into the last session"
	@echo "  make test-all         - Run both canned turns"
	@echo ""
	@echo "The repro (OpenCode's own OTLP export, through a collector):"
	@echo "  make native-up        - Start OpenCode + a collector printing every span"
	@echo "  make native-ask MESSAGE=...  - A turn through the native export"
	@echo "  make native-spans     - Span-name histogram of what the collector received"
	@echo "  make native-down      - Stop the repro"
	@echo ""
	@echo "Variables: MESSAGE, OPENCODE_MODEL, CONTINUE"

up:
	docker compose up --build -d opencode
	@echo ""
	@echo "Run a turn with: make heartbeat"

down:
	docker compose down

logs:
	docker compose exec opencode sh -c \
		'tail -n 100 "$$(ls -t /root/.local/share/opencode/log/*.log | head -1)"'

clean:
	docker compose --profile native down -v

restart: down up

status:
	docker compose --profile native ps

shell:
	docker compose exec opencode bash

# Each turn is a one-shot `opencode run`: the plugin records the
# observations and flushes them on session.idle, before the process
# exits.
ask:
	docker compose exec opencode opencode run $(RUN_FLAGS) "$(MESSAGE)"

heartbeat:
	@$(MAKE) ask MESSAGE="Reply with exactly HEARTBEAT_OK and nothing else."

tools:
	@$(MAKE) ask MESSAGE="Use the read tool to read /workspace/hello.txt, then reply with the secret word in uppercase."

test-all: heartbeat tools

# --- The repro -------------------------------------------------------

native-up:
	docker compose --profile native up --build -d otel-collector opencode-native
	@echo ""
	@echo "Run a turn with: make native-ask, then: make native-spans"

native-down:
	docker compose --profile native down

native-logs:
	docker compose --profile native logs -f otel-collector

# Attached to a long-lived server on purpose: a one-shot
# `opencode run` exits before the batch processor flushes, and the
# model-call spans are the ones left in the queue.
native-ask:
	docker compose exec opencode-native sh -c \
		'pgrep -f "opencode serve" >/dev/null || (nohup opencode serve --port 4096 --hostname 127.0.0.1 >/tmp/serve.log 2>&1 &) ; sleep 3'
	docker compose exec opencode-native opencode run \
		--attach http://127.0.0.1:4096 $(RUN_FLAGS) "$(MESSAGE)"
	@echo "Waiting for the batch processor..."; sleep 8

native-spans:
	@docker compose --profile native logs --no-log-prefix otel-collector 2>/dev/null \
		| grep -E '^ +Name +: ' | sed -E 's/^ +Name +: //' \
		| sort | uniq -c | sort -rn | head -40
	@echo ""
	@echo "Spans total: $$(docker compose --profile native logs --no-log-prefix otel-collector 2>/dev/null | grep -c '^Span #')"
	@echo "AI SDK spans: $$(docker compose --profile native logs --no-log-prefix otel-collector 2>/dev/null | grep -c 'ai.operationId')"
