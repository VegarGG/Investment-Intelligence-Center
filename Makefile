## IIC v2.5 — friendly shortcuts for prototype operators.
##
## Run from the repo root. All commands are safe to re-run.
##
## Examples:
##   make help                   # this help
##   make setup                  # one-shot install (Ubuntu 26.04 LTS)
##   make up                     # start substrate + agents + dashboard
##   make down                   # stop everything (data preserved)
##   make logs                   # tail all container logs
##   make logs SVC=orchestrator  # tail one service
##   make health                 # smoke-check every /health endpoint
##   make ps                     # docker compose ps
##   make migrate                # re-run alembic upgrade head
##   make test                   # run the Python test suite locally
##   make reset                  # wipe ALL data + .env and start over

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml

# Optional service filter: `make logs SVC=orchestrator`
SVC ?=

.PHONY: help
help: ## Show this help
	@awk 'BEGIN { FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n" } \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "Examples:"
	@grep -E '^##   ' Makefile | sed 's/^##   /  /'

.PHONY: setup
setup: ## Run the one-shot installer (Ubuntu 26.04). Idempotent.
	bash deploy/setup.sh

.PHONY: dry-run
dry-run: ## Print what setup.sh would do, without doing it
	bash deploy/setup.sh --dry-run

.PHONY: up
up: ## Bring up the full stack (substrate + agents + dashboard)
	$(COMPOSE) up -d
	@echo ""
	@echo "Dashboard:    http://localhost:4173"
	@echo "Orchestrator: http://localhost:8080/health"

.PHONY: down
down: ## Stop everything (data under /srv/iic preserved)
	$(COMPOSE) down --remove-orphans

.PHONY: restart
restart: ## Restart all services
	$(COMPOSE) restart

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs (all, or SVC=<name>)
ifeq ($(SVC),)
	$(COMPOSE) logs -f --tail=100
else
	$(COMPOSE) logs -f --tail=200 $(SVC)
endif

.PHONY: build
build: ## Rebuild Docker images
	$(COMPOSE) build --pull

.PHONY: migrate
migrate: ## Apply database migrations
	bash deploy/run-migrations.sh

.PHONY: health
health: ## Smoke-check every service's /health
	bash deploy/smoke-check.sh

.PHONY: secrets
secrets: ## Generate a fresh .env from .env.example (if missing)
	bash deploy/bootstrap-secrets.sh

.PHONY: secrets-force
secrets-force: ## Overwrite .env with new random passwords (DANGER — invalidates DB)
	bash deploy/bootstrap-secrets.sh --force

.PHONY: test
test: ## Run the Python test suite locally (no Docker)
	@PYTHONPATH=packages/featureflags:packages/schema:packages/llm-client:packages/data-bus:packages/prompts:packages/notifier:packages/data-lake:apps/orchestrator:apps/agent_persona:apps/agent_quant:apps/agent_fundamental:apps/agent_futu:apps/agent_secretary:apps/agent_backtest:apps/agent_intelligence:apps/agent_board \
		pytest -q --ignore=apps/dashboard

.PHONY: shell-pg
shell-pg: ## Open a psql shell against the running Postgres
	@source .deploy/postgres.env && \
		$(COMPOSE) exec -e PGPASSWORD=$$POSTGRES_PASSWORD postgres \
			psql -U $${POSTGRES_USER:-iic} -d $${POSTGRES_DB:-iic}

.PHONY: shell-redis
shell-redis: ## Open a redis-cli against the running Redis
	$(COMPOSE) exec redis redis-cli

.PHONY: observability
observability: ## Start the Grafana/Loki/Prometheus stack (off by default)
	$(COMPOSE) --profile observability up -d grafana loki prometheus cadvisor
	@echo "Grafana: http://localhost:3000 (admin/admin)"

.PHONY: open
open: ## Open the dashboard in the default browser
	@xdg-open http://localhost:4173 2>/dev/null || \
	  open http://localhost:4173 2>/dev/null || \
	  echo "Open http://localhost:4173 in your browser."

.PHONY: stop
stop: down  ## Alias for `down`

.PHONY: uninstall
uninstall: ## Stop containers, keep data
	bash deploy/setup.sh --uninstall

.PHONY: reset
reset: ## DESTRUCTIVE — wipe /srv/iic data + .env, force a clean reinstall
	bash deploy/setup.sh --reset
