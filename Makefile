# Run `make help` to list targets.
SHELL := /bin/bash
.DEFAULT_GOAL := help

# The pyenv shim resolves `python` using .python-version.
PYTHON ?= python
VENV   := .venv
UV     := uv

# npm writes this after every install, so it tells us whether node_modules matches the lockfile.
WEB_DEPS := web/node_modules/.package-lock.json

# uv should always target the project .venv, never a VIRTUAL_ENV leaking in from the shell.
unexport VIRTUAL_ENV

# Prefix for web recipes: make sure node matches .nvmrc. Make's shell doesn't load nvm from
# your shell rc, so if the node on PATH is another version, source nvm and switch. CI runners
# also have nvm, but setup-node already puts the right node on PATH, so nvm is skipped there.
NVM_USE := if [ "$$(node --version 2>/dev/null)" != "v$$(cat .nvmrc)" ]; then \
	export NVM_DIR="$${NVM_DIR:-$$HOME/.nvm}"; \
	if [ -s "$$NVM_DIR/nvm.sh" ]; then . "$$NVM_DIR/nvm.sh" && nvm use >/dev/null || exit 1; fi; \
	fi;

.PHONY: help setup up down dev worker voice-smoke chat test test-integration lint fmt eval annotate judge judge-sample judge-calibrate gate baseline compare models dashboard deploy-infra deploy-secrets deploy-images deploy-release deploy-smoke demo-limits demo-phoenix demo-stop demo-start deploy-destroy

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Create .venv with the stdlib venv module, using the pyenv interpreter from .python-version.
$(VENV)/bin/python:
	@want="$$(cat .python-version)"; \
	have="$$($(PYTHON) -c 'import platform; print(platform.python_version())' 2>/dev/null)"; \
	if [ "$$have" != "$$want" ]; then \
	  echo "error: '$(PYTHON)' is Python $${have:-not found}, but .python-version wants $$want"; \
	  echo "       install it with: pyenv install $$want"; \
	  exit 1; \
	fi
	$(PYTHON) -m venv $(VENV)

# Reinstall web deps only when they're missing or the lockfile changed.
$(WEB_DEPS): web/package-lock.json
	@$(NVM_USE) echo "web: npm ci (node $$(node --version))" && cd web && npm ci --no-fund

setup: $(VENV)/bin/python $(WEB_DEPS) ## Create .venv, install locked deps and git hooks
	$(UV) sync --locked
	$(UV) run --locked pre-commit install
	@test -f .env || { cp .env.example .env; echo "created .env from .env.example"; }

up: ## Start postgres, livekit-server, phoenix and wait until healthy
	@test -f .env || { echo "error: no .env (run make setup or cp .env.example .env)"; exit 1; }
	docker compose up -d --wait --wait-timeout 300

down: ## Stop services (data volumes are kept)
	docker compose down

dev: $(VENV)/bin/python $(WEB_DEPS) ## Run backend (:8000), agent worker and web (:5173) together
	@$(NVM_USE) trap 'kill 0' EXIT; \
	$(UV) run --locked uvicorn voice_order.api.app:app --port 8000 & \
	$(UV) run --locked python -m livekit.agents start src/voice_order/agent/worker.py --dev & \
	(cd web && npm run dev) & \
	wait

worker: $(VENV)/bin/python ## Run only the LiveKit agent worker
	$(UV) run --locked python -m livekit.agents start src/voice_order/agent/worker.py --dev

voice-smoke: $(VENV)/bin/python ## Scripted voice call against a running worker (ARGS="line one" "line two")
	$(UV) run --locked python -m evals.caller.voice_smoke $(ARGS)

chat: $(VENV)/bin/python ## Talk to the agent as the caller (ARGS=--memory to skip Postgres)
	$(UV) run --locked python -m voice_order.textmode $(ARGS)

test: $(VENV)/bin/python ## Unit tests (deterministic, no network)
	$(UV) run --locked pytest -m "not integration"

test-integration: $(VENV)/bin/python ## Integration tests: real Postgres, API keys (from .env)
	@$(UV) run --locked $(if $(wildcard .env),--env-file .env) pytest -m integration; status=$$?; \
	if [ $$status -eq 5 ]; then echo "no integration tests collected"; else exit $$status; fi

lint: $(VENV)/bin/python $(WEB_DEPS) ## ruff + mypy + web typecheck + oxlint
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
	$(UV) run --locked mypy
	@$(NVM_USE) echo "web: tsc -b && oxlint (node $$(node --version))" && cd web && npm run -s typecheck && npm run -s lint

fmt: $(VENV)/bin/python ## Auto-format and apply safe lint fixes
	$(UV) run --locked ruff format .
	$(UV) run --locked ruff check --fix .

MODE ?= text
SCENARIOS ?= *

eval: $(VENV)/bin/python ## make eval MODE=text|audio|recorded SCENARIOS=<glob> RUNS=<n> (ARGS=--memory, --yes ...)
	$(UV) run --locked python -m evals.runner --mode $(MODE) --scenarios '$(SCENARIOS)' $(if $(RUNS),--runs $(RUNS)) $(ARGS)

judge: $(VENV)/bin/python ## make judge REPORT=<dir>: run the LLM judges over a finished report
	@test -n "$(REPORT)" || { echo "Usage: make judge REPORT=reports/<run>"; exit 2; }
	$(UV) run --locked python -m evals.judge apply '$(REPORT)'

judge-sample: $(VENV)/bin/python ## make judge-sample REPORT="<dir> ...": 20 error cases to label by hand
	@test -n "$(REPORT)" || { echo "Usage: make judge-sample REPORT=reports/<run>"; exit 2; }
	$(UV) run --locked python -m evals.judge sample $(REPORT) $(ARGS)

judge-calibrate: $(VENV)/bin/python ## Compare the judge with the hand labels
	$(UV) run --locked python -m evals.judge calibrate

gate: $(VENV)/bin/python ## make gate REPORT=<dir>: fail if the report is worse than the baseline
	@test -n "$(REPORT)" || { echo "Usage: make gate REPORT=reports/<run>"; exit 2; }
	$(UV) run --locked python -m evals.gate '$(REPORT)'

baseline: $(VENV)/bin/python ## make baseline REPORT=<dir>: record a reviewed report as the baseline
	@test -n "$(REPORT)" || { echo "Usage: make baseline REPORT=reports/<run>"; exit 2; }
	$(UV) run --locked python -m evals.gate '$(REPORT)' --update-baseline

compare: $(VENV)/bin/python ## make compare BEFORE=<dir> AFTER=<dir> [ONLY=<glob>]: two reports side by side
	@test -n "$(BEFORE)" -a -n "$(AFTER)" || { echo "Usage: make compare BEFORE=reports/<a> AFTER=reports/<b>"; exit 2; }
	$(UV) run --locked python -m evals.compare '$(BEFORE)' '$(AFTER)' $(if $(ONLY),--scenarios '$(ONLY)')

KOKORO_URL := https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
models: $(VENV)/bin/python ## Download the local speech models (Kokoro and Whisper)
	@mkdir -p models/kokoro
	@test -f models/kokoro/kokoro-v1.0.onnx || curl -fL --progress-bar -o models/kokoro/kokoro-v1.0.onnx $(KOKORO_URL)/kokoro-v1.0.onnx
	@test -f models/kokoro/voices-v1.0.bin || curl -fL --progress-bar -o models/kokoro/voices-v1.0.bin $(KOKORO_URL)/voices-v1.0.bin
	$(UV) run --locked python -c "from faster_whisper import WhisperModel; WhisperModel('$(or $(WHISPER_MODEL),base.en)', device='cpu', compute_type='int8')"
	@echo "Local speech models are ready. Set STT_PROVIDER=whisper and TTS_PROVIDER=kokoro to use them."

annotate: $(VENV)/bin/python ## make annotate SESSION=<id>: start the expected order for a real call
	@test -n "$(SESSION)" || { echo "Usage: make annotate SESSION=<session id from recordings/>"; exit 2; }
	$(UV) run --locked python -m evals.annotate '$(SESSION)' $(ARGS)

dashboard: $(VENV)/bin/python ## Build dashboard/index.html: every recorded call, per day, linked to Phoenix
	$(UV) run --locked python -m voice_order.telemetry.dashboard $(ARGS)
	@echo "Open dashboard/index.html in a browser."

# --- the demo on AWS (docs/adr/0009-deployment.md) ---------------------------------------
TF := terraform -chdir=deploy/terraform

deploy-infra: ## Create or update the AWS demo: registry, instance, network, permissions
	$(TF) init -input=false
	$(TF) apply

deploy-secrets: ## Put the demo's secrets in SSM Parameter Store (OpenAI key from .env)
	deploy/secrets.sh

deploy-images: ## Build the arm64 images at this commit and push them to ECR
	deploy/images.sh

deploy-release: ## make deploy-release TAG=<commit>: roll the demo to that image tag
	@test -n "$(TAG)" || { echo "Usage: make deploy-release TAG=<tag printed by make deploy-images>"; exit 2; }
	deploy/release.sh '$(TAG)'

deploy-smoke: $(VENV)/bin/python ## Place a silent test call to the live demo and check the agent answers
	.venv/bin/python deploy/smoke_call.py "$$($(TF) output -raw site_host)"

demo-limits: ## make demo-limits PER_IP=<n> PER_DAY=<n> [TAG=<tag>]: change the call limits and restart
	@test -n "$(PER_IP)" -a -n "$(PER_DAY)" || { echo "Usage: make demo-limits PER_IP=5 PER_DAY=40"; exit 2; }
	aws ssm put-parameter --name /voice-order-agent/calls_per_ip_per_hour --type String --overwrite --value '$(PER_IP)' >/dev/null
	aws ssm put-parameter --name /voice-order-agent/calls_per_day --type String --overwrite --value '$(PER_DAY)' >/dev/null
	for p in calls_per_ip_per_hour calls_per_day; do aws ssm add-tags-to-resource --resource-type Parameter --resource-id /voice-order-agent/$$p --tags Key=project,Value=voice-order-agent Key=repo,Value=observable-voice-agent; done
	deploy/release.sh "$(or $(TAG),$$(aws ssm get-parameter --name /voice-order-agent/image_tag --query Parameter.Value --output text))"

demo-phoenix: ## Open the demo's Phoenix at http://localhost:6007 (needs the AWS Session Manager plugin)
	aws ssm start-session --target "$$($(TF) output -raw instance_id)" \
	  --document-name AWS-StartPortForwardingSession \
	  --parameters '{"portNumber":["6006"],"localPortNumber":["6007"]}'

demo-stop: ## Stop the demo instance (keeps its disk and address; stops the hourly charge)
	aws ec2 stop-instances --instance-ids "$$($(TF) output -raw instance_id)" --output text

demo-start: ## Start the demo instance again; the stack comes up on boot
	aws ec2 start-instances --instance-ids "$$($(TF) output -raw instance_id)" --output text
	@echo "Up in a few minutes at $$($(TF) output -raw url)"

deploy-destroy: ## Delete everything the demo created in AWS, images included
	$(TF) destroy
