PYTHON ?= 3.12
UV ?= uv
RUN := .venv/bin/python

.PHONY: help setup deploy status up demo error test destroy
help:
	@echo 'make setup    Install Python dependencies (requires uv and AWS CLI)'
	@echo 'make deploy   Create the managed agent, action group, and IAM role'
	@echo 'make status   Show stack status and agent identifiers'
	@echo 'make demo     Invoke the managed agent and export traces to Oodle'
	@echo 'make error    Demonstrate a traced tool failure'
	@echo 'make test     Verify return-control and OTLP export without AWS calls'
	@echo 'make destroy  Delete this demo stack after confirmation'
setup:
	$(UV) venv --python $(PYTHON) .venv
	$(UV) pip install --python $(RUN) -r requirements.txt
deploy:
	$(RUN) manage.py deploy
status:
	$(RUN) manage.py status
up: deploy
demo:
	$(RUN) app/main.py
error:
	$(RUN) app/main.py --prompt 'Look up order ORD-ERROR. Do not retry if the lookup fails.'
test:
	$(RUN) verify_local.py
	$(RUN) verify_tools.py
destroy:
	$(RUN) manage.py destroy

.PHONY: tools-deploy tools-status tools-destroy tools-check
tools-deploy:
	$(RUN) manage_tools.py deploy
tools-status:
	$(RUN) manage_tools.py status
tools-destroy:
	$(RUN) manage_tools.py destroy
tools-check:
	$(RUN) app/check_tools.py
