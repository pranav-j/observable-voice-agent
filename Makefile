# Run `make help` to list targets.
SHELL := /bin/bash
.DEFAULT_GOAL := help

# The pyenv shim resolves `python` using .python-version.
PYTHON ?= python
VENV   := .venv
UV     := uv

# uv should always target the project .venv, never a VIRTUAL_ENV leaking in from the shell.
unexport VIRTUAL_ENV

.PHONY: help setup up down dev test test-integration lint fmt eval

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

setup: $(VENV)/bin/python ## Create .venv and install locked Python deps
	$(UV) sync --locked
	@test -f .env || { cp .env.example .env; echo "created .env from .env.example"; }

up: ## Start postgres, livekit-server, phoenix and wait until healthy
	@test -f .env || { echo "error: no .env (run make setup or cp .env.example .env)"; exit 1; }
	docker compose up -d --wait --wait-timeout 300

down: ## Stop services (data volumes are kept)
	docker compose down

dev: ## Run backend + agent worker + web (not implemented yet)
	@echo "make dev: not implemented yet"; exit 1

test: $(VENV)/bin/python ## Unit tests (deterministic, no network)
	$(UV) run --locked pytest -m "not integration"

test-integration: $(VENV)/bin/python ## Integration tests (skip when API keys are missing)
	@$(UV) run --locked pytest -m integration; status=$$?; \
	if [ $$status -eq 5 ]; then echo "no integration tests collected"; else exit $$status; fi

lint: $(VENV)/bin/python ## ruff + mypy
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
	$(UV) run --locked mypy

fmt: $(VENV)/bin/python ## Auto-format and apply safe lint fixes
	$(UV) run --locked ruff format .
	$(UV) run --locked ruff check --fix .

eval: ## make eval MODE=text|audio|recorded SCENARIOS=<glob> RUNS=<n> (not implemented yet)
	@echo "make eval: not implemented yet"; exit 1
