# Configurable variables
AWS_PROFILE    ?= navteca
AWS_REGION     ?= us-east-1
AWS_ACCOUNT_ID ?= 607399646027
REPO_NAME      ?= navteca/images/bbc-earth-pulse
IMAGE_TAG      ?= latest

ECR_REGISTRY   := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
ECR_IMAGE      := $(ECR_REGISTRY)/$(REPO_NAME):$(IMAGE_TAG)
LOCAL_IMAGE    := $(REPO_NAME):$(IMAGE_TAG)
PLATFORMS      := linux/arm64,linux/amd64
BUILDER        := bbc-earth-pulse-builder

.PHONY: help login requirements build push release clean

help:
	@echo "Usage:"
	@echo "  make login          Authenticate Docker to ECR"
	@echo "  make build          Build multi-arch image (arm64 + amd64) and push to ECR"
	@echo "  make push           Tag and push local image to ECR (single-arch fallback)"
	@echo "  make release        login + build (full pipeline)"
	@echo "  make clean          Remove the buildx builder"
	@echo ""
	@echo "Overridable variables:"
	@echo "  AWS_PROFILE=$(AWS_PROFILE)"
	@echo "  AWS_REGION=$(AWS_REGION)"
	@echo "  AWS_ACCOUNT_ID=$(AWS_ACCOUNT_ID)"
	@echo "  REPO_NAME=$(REPO_NAME)"
	@echo "  IMAGE_TAG=$(IMAGE_TAG)"

# Regenerate requirements.txt from uv.lock (run on host where uv is available)
requirements:
	uv export --no-dev --no-hashes -o requirements.txt

login:
	aws ecr get-login-password \
		--region $(AWS_REGION) \
		--profile $(AWS_PROFILE) \
	| docker login \
		--username AWS \
		--password-stdin $(ECR_REGISTRY)

# Multi-arch build using buildx — builds and pushes both arm64 and amd64 in one step
build: requirements login
	docker buildx inspect $(BUILDER) > /dev/null 2>&1 || \
		docker buildx create --name $(BUILDER) --driver docker-container --bootstrap
	docker buildx build \
		--builder $(BUILDER) \
		--platform $(PLATFORMS) \
		--tag $(ECR_IMAGE) \
		--push \
		.

# Single-arch fallback: build locally, tag, and push
push: requirements login
	docker build -t $(LOCAL_IMAGE) .
	docker tag $(LOCAL_IMAGE) $(ECR_IMAGE)
	docker push $(ECR_IMAGE)

release: login build

clean:
	docker buildx rm $(BUILDER) || true
