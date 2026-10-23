PYTHON ?= 3.12
UV ?= uv
VENV := .venv
RUN := $(VENV)/bin/python

.PHONY: help setup up demo error test
help:
	@echo 'make setup  Install dependencies'
	@echo 'make demo   Run a Bedrock agent and export its trace to Oodle'
	@echo 'make error  Demonstrate a traced tool failure'
	@echo 'make test   Verify the agent and OTLP export without AWS or Oodle'

setup:
	$(UV) venv --python $(PYTHON) $(VENV)
	$(UV) pip install --python $(RUN) -r requirements.txt

up: demo

demo:
	$(RUN) app/main.py

error:
	$(RUN) app/main.py --prompt 'Look up order ORD-ERROR. Do not retry if the lookup fails.'

test:
	$(RUN) verify_local.py
	$(RUN) verify_tools.py

.PHONY: tools-deploy tools-status tools-destroy tools-check
tools-deploy:
	$(RUN) manage_tools.py deploy
tools-status:
	$(RUN) manage_tools.py status
tools-destroy:
	$(RUN) manage_tools.py destroy
tools-check:
	$(RUN) app/check_tools.py
