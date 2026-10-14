.PHONY: help agent webhook chat voice replay forwarder logs down teardown clean

DEMO := agent/demo.py

help: ## Show this help
	@echo "ElevenLabs Agents -> Oodle Agent Observability"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s - %s\n", $$1, $$2}'

agent: ## Create the demo agent in your ElevenLabs workspace
	$(DEMO) setup

webhook: ## Send the agent's post-call traces straight to Oodle (the tile's snippet)
	@set -a; . ./.env; set +a; \
	ELEVENLABS_AGENT_ID=$$(python3 -c 'import json; print(json.load(open("state/agent.json"))["agent_id"])') \
		./setup_webhook.py
	@echo "The agent's post-call webhook now goes straight to Oodle."

chat: ## A short text-only conversation (lowest cost)
	$(DEMO) chat

voice: ## A real voice call with a synthetic caller
	$(DEMO) voice

replay: ## Send the sample trace again (no ElevenLabs account needed)
	$(DEMO) replay sample-trace.json

forwarder: ## Instead of `make webhook`: go through a forwarder on this machine
	docker compose up --build -d
	@url=""; for i in $$(seq 1 30); do \
		url=$$(docker compose logs tunnel 2>/dev/null \
			| grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1); \
		[ -n "$$url" ] && break; sleep 1; done; \
	if [ -z "$$url" ]; then echo "The tunnel has no URL yet. Run make forwarder again."; exit 1; fi; \
	$(DEMO) webhook "$$url"

logs: ## Tail the forwarder's logs
	docker compose logs -f forwarder

down: ## Stop the forwarder and the tunnel
	docker compose down

teardown: ## Delete the demo agent, knowledge base and webhook in ElevenLabs
	$(DEMO) teardown

clean: ## Stop everything and remove the forwarder image
	docker compose down --rmi local --remove-orphans
