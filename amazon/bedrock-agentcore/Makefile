PYTHON ?= 3.12
UV ?= uv
VENV := .venv
RUN := $(VENV)/bin/python

.PHONY: help setup up local demo error test deploy invoke status destroy
help:
	@echo 'make setup    Install dependencies'
	@echo 'make local    Serve the AgentCore app locally on port 8080'
	@echo 'make demo     Call the local app (run make local in another terminal)'
	@echo 'make error    Send a tool-failure request to the local app'
	@echo 'make test     Verify the agent, runtime handler, and OTLP export offline'
	@echo 'make deploy   Deploy to AWS AgentCore Runtime'
	@echo 'make invoke   Call the deployed Runtime'
	@echo 'make status   Show deployment status'
	@echo 'make destroy  Remove the deployment using the toolkit confirmation prompt'

setup:
	$(UV) venv --python $(PYTHON) $(VENV)
	$(UV) pip install --python $(RUN) -r requirements.txt

up: local

local:
	$(RUN) app/main.py

demo:
	curl --fail-with-body -sS http://localhost:8080/invocations \
		-H 'Content-Type: application/json' \
		-d '{"prompt":"Where is order ORD-1001, and can I return it? Check the order and return policy."}'

error:
	curl --fail-with-body -sS http://localhost:8080/invocations \
		-H 'Content-Type: application/json' \
		-d '{"prompt":"Look up order ORD-ERROR. Do not retry if the lookup fails."}'

test:
	$(RUN) verify_local.py

deploy:
	$(RUN) deploy.py

invoke:
	$(RUN) manage.py invoke '{"prompt":"Where is order ORD-1001, and can I return it? Check the order and return policy."}'

status:
	$(RUN) manage.py status

destroy:
	$(RUN) manage.py destroy
