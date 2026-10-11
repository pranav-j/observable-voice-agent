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

.PHONY: help setup up down dev worker voice-smoke chat test test-integration lint fmt eval annotate judge judge-sample judge-calibrate gate baseline compare

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

annotate: $(VENV)/bin/python ## make annotate SESSION=<id>: start the expected order for a real call
	@test -n "$(SESSION)" || { echo "Usage: make annotate SESSION=<session id from recordings/>"; exit 2; }
	$(UV) run --locked python -m evals.annotate '$(SESSION)' $(ARGS)
