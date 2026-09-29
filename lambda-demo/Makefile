-include .env
export

STACK ?= oodle-lambda-demo
FUNCTION ?= oodle-lambda-demo-checkout
AWS_REGION ?= us-west-2
# Set SCHEDULE=false to stop the every-minute invocations.
SCHEDULE ?= true

.PHONY: build deploy invoke tail pause destroy check-env

check-env:
	@test -n "$(OODLE_INSTANCE)" || (echo "Set OODLE_INSTANCE in .env" && exit 1)
	@test -n "$(OODLE_API_KEY)" || (echo "Set OODLE_API_KEY in .env" && exit 1)
	@test -n "$(OODLE_OTLP_ENDPOINT)" || (echo "Set OODLE_OTLP_ENDPOINT in .env" && exit 1)

build:
	sam build

deploy: check-env build
	sam deploy \
		--stack-name $(STACK) \
		--region $(AWS_REGION) \
		--resolve-s3 \
		--capabilities CAPABILITY_IAM \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--parameter-overrides \
			OodleInstance=$(OODLE_INSTANCE) \
			OodleApiKey=$(OODLE_API_KEY) \
			OodleOtlpEndpoint=$(OODLE_OTLP_ENDPOINT) \
			ScheduleEnabled=$(SCHEDULE)

# Invoke the function 10 times.
invoke:
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		aws lambda invoke --region $(AWS_REGION) --function-name $(FUNCTION) \
			--cli-binary-format raw-in-base64-out --payload '{}' /dev/null >/dev/null; \
	done; echo "Invoked $(FUNCTION) 10 times"

# Show the function and extension logs in CloudWatch.
tail:
	aws logs tail /aws/lambda/$(FUNCTION) --region $(AWS_REGION) --since 10m --follow

pause:
	$(MAKE) deploy SCHEDULE=false

destroy:
	sam delete --stack-name $(STACK) --region $(AWS_REGION) --no-prompts
