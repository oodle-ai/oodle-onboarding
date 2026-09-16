.PHONY: help seed up down logs ticket all improver stopimprover status approve reject nudge insights prompt models rollback reset

COMPOSE := docker compose
RUN     := $(COMPOSE) run --rm --no-deps worker

# Only ticket, all, and whatever the improver does once it has a finding to act
# on will spend model calls. Everything else is free.

help:
	@echo "setup"
	@echo "  make seed      - create the vague prompt v1 in Oodle"
	@echo "  make up        - Temporal, collector, idle worker. No model calls."
	@echo "  make logs      - follow the worker"
	@echo ""
	@echo "drive the agent  (these spend model calls)"
	@echo "  make ticket    - one agent run           (~5 calls on v1)"
	@echo "  make ticket T=T-1003"
	@echo "  make all       - all four tickets once   (~20 calls on v1)"
	@echo ""
	@echo "the loop"
	@echo "  make improver  - start the improver watching Oodle"
	@echo "  make stopimprover - terminate it, so nothing drafts unattended"
	@echo "  make nudge     - hand it a finding now, instead of waiting"
	@echo "  make status    - what the improver is waiting on"
	@echo "  make approve   - promote the candidate (the one human step)"
	@echo "  make reject    - discard the candidate"
	@echo ""
	@echo "inspect"
	@echo "  make insights  - what Oodle has reported so far"
	@echo "  make prompt    - which prompt version is live"
	@echo "  make models    - which Gemini models this key can call right now"
	@echo "  make rollback  - move production back to v1"
	@echo "  make down      - stop everything"
	@echo "  make reset     - stop everything and delete the prompt from Oodle"

seed:
	$(RUN) python seed.py

up:
	$(COMPOSE) up -d --build
	@echo "Temporal UI: http://localhost:8083 - worker is idle, run 'make ticket'"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f worker

T ?= T-1001
ticket:
	$(RUN) python starter.py ticket $(T)

all:
	$(RUN) python starter.py all

improver:
	$(RUN) python starter.py improver

stopimprover:
	$(RUN) python approve.py stop

status:
	$(RUN) python approve.py status

approve:
	$(RUN) python approve.py approve

reject:
	$(RUN) python approve.py reject

nudge:
	$(RUN) python signal_insight.py

models:
	$(RUN) python models.py

insights:
	$(RUN) python -c "import oodle; [print(r['severity'], '|', r['category'], '|', r['title']) for r in oodle.recommendations()] or print('none yet')"

prompt:
	$(RUN) python -c "import os,oodle; p=oodle.get_prompt(os.environ['PROMPT_NAME']); print('v%d %s' % (p['version'], p['labels'])); print(p['prompt'])"

rollback:
	$(RUN) python -c "import os,oodle; oodle.move_label(os.environ['PROMPT_NAME'], 1); print('production -> v1')"

reset: down
	$(RUN) python -c "import os,httpx,oodle; print(httpx.delete(oodle._PROMPTS + '/prompts/' + os.environ['PROMPT_NAME'], auth=oodle._AUTH, timeout=30).status_code)"
