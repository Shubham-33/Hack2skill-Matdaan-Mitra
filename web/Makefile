.PHONY: help install sync run test lint check deploy clean

VENV := ../.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python deps into ../.venv (run once)
	$(PIP) install -r requirements.txt -r requirements-dev.txt

sync: ## Refresh OpenCity data (candidates + manifestos)
	$(PYTHON) ../execution/sync_candidates.py
	$(PYTHON) ../execution/sync_manifestos.py

run: ## Start the Flask dev server on port 5050
	PORT=5050 $(PYTHON) app.py

test: ## Run pytest with the 100% coverage gate
	$(PYTHON) -m pytest -q

lint: ## Run ruff
	$(VENV)/bin/ruff check app.py tests/

check: lint test ## Run lint + tests (= what CI runs)

deploy: ## Deploy to Cloud Run (requires PROJECT_ID and GEMINI_API_KEY env vars)
	@test -n "$(PROJECT_ID)" || (echo "Set PROJECT_ID, e.g.: make deploy PROJECT_ID=foo GEMINI_API_KEY=AIza..."; exit 1)
	@test -n "$(GEMINI_API_KEY)" || (echo "Set GEMINI_API_KEY"; exit 1)
	./deploy.sh $(PROJECT_ID) $(GEMINI_API_KEY)

clean: ## Remove caches
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} +
	rm -f .coverage
