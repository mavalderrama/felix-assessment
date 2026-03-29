.DEFAULT_GOAL := help

PYTHON  := uv run python
MANAGE  := $(PYTHON) backend/manage.py

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\nTargets:\n"} \
	     /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ── Environment ───────────────────────────────────────────────────────────────

.PHONY: env
env: ## Copy .env.example → .env (no-clobber; fill in your API key after)
	@cp -n .env.example .env && echo ".env created — add your LLM API key before running" \
	  || echo ".env already exists, skipping"

# ── Dependencies ──────────────────────────────────────────────────────────────

.PHONY: install
install: ## Install Python dependencies via uv
	uv sync

# ── Infrastructure ────────────────────────────────────────────────────────────

.PHONY: infra-up
infra-up: ## Start PostgreSQL + Langfuse stack (docker compose)
	docker compose up -d

.PHONY: infra-down
infra-down: ## Stop infrastructure stack (keeps data volumes)
	docker compose down

.PHONY: infra-reset
infra-reset: ## Stop infrastructure and wipe all data volumes
	docker compose down -v

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Apply Django migrations (creates all tables)
	$(MANAGE) migrate

.PHONY: seed
seed: ## Seed corridors, exchange rates, and demo transfers
	$(MANAGE) migrate
	$(MANAGE) seed_corridors
	$(MANAGE) seed_exchange_rates
	$(MANAGE) seed_transfers

.PHONY: seed-clear
seed-clear: ## Wipe and re-seed demo transfers (corridors + rates untouched)
	$(MANAGE) seed_transfers --clear

# ── First-time setup ──────────────────────────────────────────────────────────

.PHONY: setup
setup: env install infra-up _wait-postgres migrate seed ## Full first-time setup (deps + infra + DB + seed)

.PHONY: _wait-postgres
_wait-postgres:
	@echo "Waiting for PostgreSQL to be ready..."
	@for i in $$(seq 1 20); do \
	  docker compose exec postgres pg_isready -U send_money -d send_money -q 2>/dev/null && break; \
	  echo "  ...retrying ($$i/20)"; sleep 3; \
	done

# ── Running ───────────────────────────────────────────────────────────────────

.PHONY: run
run: ## Start the interactive CLI agent (auth + conversation loop)
	$(PYTHON) backend/main.py

.PHONY: web
web: ## Start the ADK web UI (browser chat + tool-call inspector)
	uv run adk web backend

# ── Testing & linting ─────────────────────────────────────────────────────────

.PHONY: test
test: ## Run the full test suite (110 tests, no DB or API key required)
	uv run pytest backend/tests/ -q

.PHONY: lint
lint: ## Lint the codebase with ruff
	uv run ruff check backend/
