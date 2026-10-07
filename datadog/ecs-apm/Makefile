# ECS Fargate APM demo: Datadog first, then dual-write to Oodle.
#
#   make datadog      phase 1: build, push and deploy, Agents ship to Datadog only
#   make dual-write   phase 2: Agents ship to Datadog and Oodle
#   make destroy      delete everything
#
# Datadog credentials come from ../single-write/.env (override with DD_ENV_FILE).
# Oodle credentials come from the configured oodle CLI (`oodle configure`).

TF      := terraform -chdir=terraform
REGION  ?= us-east-1
TAG     ?= v1
SERVICES := storefront orders inventory

.PHONY: init datadog dual-write push status logs destroy

init:
	$(TF) init -input=false

# ECR repositories must exist before the images can be pushed.
datadog: init
	eval "$$(scripts/tf-env.sh)" && $(TF) apply -auto-approve -target=aws_ecr_repository.app
	$(MAKE) push
	eval "$$(scripts/tf-env.sh)" && $(TF) apply -auto-approve -var image_tag=$(TAG) -var oodle_dual_write=false

dual-write: init
	eval "$$(WITH_OODLE=1 scripts/tf-env.sh)" && $(TF) apply -auto-approve -var image_tag=$(TAG) -var oodle_dual_write=true

push:
	@registry=$$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(REGION).amazonaws.com; \
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $$registry; \
	for s in $(SERVICES); do \
		docker build --platform linux/arm64 -t $$registry/ecs-apm/$${s}:$(TAG) apps/$${s} && \
		docker push $$registry/ecs-apm/$${s}:$(TAG) || exit 1; \
	done

status:
	aws ecs describe-services --region $(REGION) --cluster ecs-apm --services $(SERVICES) \
		--query 'services[].{service:serviceName,running:runningCount,desired:desiredCount,taskDef:taskDefinition}' --output table

logs:
	aws logs tail /ecs/ecs-apm --region $(REGION) --since 10m --follow

destroy: init
	eval "$$(scripts/tf-env.sh)" && $(TF) destroy -auto-approve
