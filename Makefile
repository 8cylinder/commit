SHELL := bash

.DEFAULT_GOAL := help
.PHONY: help sync fmt fmt-check lint lint-check type test check ci build install install-completions uninstall upgrade clean

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync:  ## Install or update dependencies
	uv sync --all-groups

fmt:  ## Format code
	uv run ruff format .

fmt-check:  ## Check formatting without changing files
	uv run ruff format --check .

lint:  ## Lint and apply safe fixes
	uv run ruff check --fix .

lint-check:  ## Lint without changing files
	uv run ruff check .

type:  ## Type-check the project
	uv run ty check

test:  ## Run tests
	uv run pytest

check: fmt-check lint-check type test  ## Run all checks without changing files

ci:  ## Install locked dependencies and run all checks
	uv sync --locked --all-groups
	$(MAKE) check

build:  ## Build the wheel and sdist
	uv build

install:  ## Install the app and bash completions
	uv tool install --editable --force .
	$(MAKE) install-completions

install-completions:  ## Generate and install bash completions
	uv run cm --completions

uninstall:  ## Remove the installed tool
	uv tool uninstall cm

upgrade:  ## Upgrade dependencies and the lockfile
	uv sync --upgrade --all-groups

clean:  ## Remove build and test artifacts
	rm -rf build dist .pytest_cache .ruff_cache .ty_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
