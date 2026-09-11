# netlab — development tasks
# Every target is idempotent and safe to re-run.

PYTHON  ?= python
VENV    ?= .venv
BIN     := $(VENV)/bin
SAMPLE  := data/sample/Connections.csv

.DEFAULT_GOAL := help
.PHONY: help install sample dev serve test test-fast coverage lint format typecheck report clean build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install with dev extras
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"
	@echo "\n  Activate with: source $(BIN)/activate\n"

sample: ## Regenerate the synthetic export (git-ignored)
	$(BIN)/netlab sample --out $(SAMPLE) --count 800

dev: ## Serve with auto-reload
	$(BIN)/netlab serve --reload

serve: ## Serve without reload
	$(BIN)/netlab serve

test: ## Run the suite with coverage
	$(BIN)/pytest --cov=netlab --cov-report=term-missing --cov-report=xml

test-fast: ## Run the suite without coverage
	$(BIN)/pytest -q

lint: ## Lint and type-check
	$(BIN)/ruff check src tests
	$(BIN)/mypy src/netlab

format: ## Auto-fix lint findings and formatting
	$(BIN)/ruff check --fix src tests
	$(BIN)/ruff format src tests

typecheck: ## Type-check only
	$(BIN)/mypy src/netlab

report: sample ## Render a Markdown report from the synthetic sample
	$(BIN)/netlab analyze $(SAMPLE) --markdown --redact --out network-report.md
	@echo "  → network-report.md"

build: ## Build the wheel and sdist
	$(BIN)/pip install --quiet build
	$(BIN)/python -m build

clean: ## Remove build, cache, and coverage artifacts
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
