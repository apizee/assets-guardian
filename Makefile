.DEFAULT_GOAL := help
.PHONY: help setup install upgrade uninstall version-show version-bump lint-check lint-format lint-type lint-complexity lint-fix-format test test-coverage security-bandit security-dependency-audit security-gitleaks security-hadolint security-trivy all clean docs-clean docs-build docs-serve pre-commit-update pre-commit-run local-sync local-audit local-check docker-build docker-sync docker-audit docker-check docker-help kevin kevin-security-plumber

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-26s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies (prod + dev + docs)
	@printf "\033[36m▶\033[0m Installing dependencies (prod + dev + docs)...\n"
	@uv sync --all-groups
	@uv run pre-commit install
	@printf "\033[32m✓\033[0m Dependencies installed.\n"

install: ## Build and install the standalone assets-guardian command globally (uv tool)
	@printf "\033[36m▶\033[0m Building and installing the standalone 'assets-guardian' command...\n"
	@uv tool install .
	@printf "\033[32m✓\033[0m 'assets-guardian' installed. Run 'assets-guardian --version' to verify.\n"

upgrade: ## Rebuild and reinstall the standalone assets-guardian command from current source (uv tool)
	@printf "\033[36m▶\033[0m Upgrading the standalone 'assets-guardian' command...\n"
	@uv tool install . --reinstall
	@printf "\033[32m✓\033[0m 'assets-guardian' upgraded to the current source version.\n"

uninstall: ## Remove the standalone assets-guardian command (uv tool)
	@printf "\033[36m▶\033[0m Removing the standalone 'assets-guardian' command...\n"
	@if uv tool list 2>/dev/null | grep -q '^assets-guardian'; then \
		uv tool uninstall assets-guardian; \
		printf "\033[32m✓\033[0m 'assets-guardian' uninstalled.\n"; \
	else \
		printf "\033[33m⚠\033[0m  Not installed as a 'uv tool', nothing to uninstall.\n"; \
	fi
	@if command -v assets-guardian >/dev/null 2>&1; then \
		printf "\033[33m⚠\033[0m  '%s' is still on your PATH (provided by the project venv, not 'uv tool').\n" "$$(command -v assets-guardian)"; \
	fi

version-show: ## Print the project version (single source: pyproject.toml)
	@uv version --short

version-bump: ## Bump version and sync README badge (PART=major|minor|patch, default: patch)
	@printf "\033[36m▶\033[0m Bumping version ($(or $(PART),patch))...\n"
	@uv version --bump $(or $(PART),patch)
	@new=$$(uv version --short); \
		sed -i -E "s|(badge/version-)[^-]+(-blue)|\1$$new\2|" README.md; \
		printf "\033[32m✓\033[0m Bumped to %s (pyproject.toml + README badge synced).\n" "$$new";

lint-check: ## Check code with ruff (lint + format + type)
	@printf "\033[36m▶\033[0m Analysing code with ruff...\n"
	@uv run ruff check src/ tests/
	@printf "\033[32m✓\033[0m Ruff lint: no errors.\n"

lint-format: ## Format check with ruff (does not modify files)
	@printf "\033[36m▶\033[0m Checking formatting with ruff...\n"
	@uv run ruff format --check src/ tests/
	@printf "\033[32m✓\033[0m Formatting is compliant.\n"

lint-type: ## Type check with mypy
	@printf "\033[36m▶\033[0m Checking types with mypy...\n"
	@uv run mypy --config-file=pyproject.toml
	@printf "\033[32m✓\033[0m Mypy type check: no errors.\n"

lint-complexity: ## Cyclomatic complexity analysis with radon (fail if >= C)
	@printf "\033[36m▶\033[0m Analysing cyclomatic complexity with radon...\n"
	@uv run radon cc src/ -a -s
	@if uv run radon cc src/ -n C -s --no-assert | grep -q .; then \
		printf "\033[31m✗\033[0m Code complexity above acceptable threshold (>= C).\n"; \
		exit 1; \
	fi
	@printf "\033[32m✓\033[0m Code complexity below acceptable threshold.\n"

lint-fix-format: ## Fix and format code with ruff (modifies files)
	@printf "\033[36m▶\033[0m Fixing and formatting code with ruff...\n"
	@uv run ruff check --fix src/ tests/
	@uv run ruff format src/ tests/
	@printf "\033[32m✓\033[0m Code fixed and formatted.\n"

test: ## Run tests
	@printf "\033[36m▶\033[0m Running tests...\n"
	@uv run pytest
	@printf "\033[32m✓\033[0m Tests passed.\n"

test-coverage: ## Run tests with coverage
	@printf "\033[36m▶\033[0m Running tests with coverage...\n"
	@uv run pytest --cov --cov-report=html --cov-report=term-missing
	@printf "\033[32m✓\033[0m Tests passed. HTML report: htmlcov/index.html\n"

security-bandit: ## SAST code audit with bandit
	@printf "\033[36m▶\033[0m SAST code audit with bandit...\n"
	@uv run bandit -c pyproject.toml -r src/
	@printf "\033[32m✓\033[0m Bandit audit complete.\n"

security-dependency-audit: ## Dependency audit (pip-audit)
	@printf "\033[36m▶\033[0m Dependency audit with pip-audit...\n"
	@uv export --frozen --no-dev --no-emit-project --quiet --format requirements-txt -o requirements-audit.txt
	@uvx pip-audit --vulnerability-service pypi -r requirements-audit.txt --require-hashes --disable-pip; \
		status=$$?; \
		rm -f requirements-audit.txt; \
		exit $$status
	@printf "\033[32m✓\033[0m Dependency audit complete.\n"

security-gitleaks: ## Secret scanning with gitleaks
	@printf "\033[36m▶\033[0m Secret scanning with gitleaks...\n"
	@uv run pre-commit run gitleaks --all-files
	@printf "\033[32m✓\033[0m Gitleaks: no secrets detected.\n"
#docker run --rm -v "$(pwd)":/repo -w /repo --entrypoint "" zricethezav/gitleaks:v8.30.1 gitleaks detect --source=/repo --config=/repo/.gitleaks.toml --report-path=/repo/gitleaks-report.json --report-format=json --verbose --redact
#docker run --rm -v "$(pwd)":/repo -w /repo --entrypoint "" zricethezav/gitleaks:v8.30.1 gitleaks detect --source=/repo --config=/repo/.gitleaks.toml --report-path=/repo/gitleaks-report.json --report-format=json --verbose --redact --log-opts="-5"

security-hadolint: ## Dockerfile linting with hadolint
	@printf "\033[36m▶\033[0m Linting Dockerfile with hadolint...\n"
	@docker run --rm -v $(shell pwd)/Dockerfile:/Dockerfile:ro hadolint/hadolint:v2.14.0-debian hadolint /Dockerfile
	@printf "\033[32m✓\033[0m Hadolint: no issues found.\n"

security-trivy: docker-build ## Build then scan the 'assets-guardian' Docker image with trivy (same gate as CI)
	@printf "\033[36m▶\033[0m Scanning Docker image 'assets-guardian' with trivy...\n"
	@docker run --rm \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v trivy-cache:/root/.cache/trivy \
		-v $(shell pwd)/.trivyignore.yml:/.trivyignore.yml:ro \
		aquasec/trivy:0.72.0 image \
		--exit-code 1 \
		--scanners vuln \
		--severity HIGH,CRITICAL \
		--ignorefile /.trivyignore.yml \
		--show-suppressed \
		assets-guardian
	@printf "\033[32m✓\033[0m Trivy: no HIGH/CRITICAL vulnerabilities found.\n"

all: lint-check lint-format lint-type lint-complexity test-coverage security-bandit security-dependency-audit security-gitleaks security-hadolint security-trivy ## Run all checks
	@printf "\033[32m✓\033[0m All code checks completed successfully.\n"

clean: ## Clean all tool-generated artifacts (caches, builds, docs, coverage...)
	@printf "\033[36m▶\033[0m Removing generated artifacts...\n"
	@rm -rf \
		.venv/ \
		*.egg-info/ \
		dist/ \
		build/ \
		.mypy_cache/ \
		.ruff_cache/ \
		.pytest_cache/ \
		.coverage \
		htmlcov/ \
		benchmarks/fixtures/ \
		benchmarks/results/ \
		MagicMock/ \
		.assets-guardian_cache/ \
		docs/_build/ \
		docs/src/stubs/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name '*Zone.Identifier' -delete 2>/dev/null || true
	@find outputs/ -mindepth 1 -not -name '.gitkeep' -delete 2>/dev/null || true
	@find logs/ -mindepth 1 -not -name '.gitkeep' -delete 2>/dev/null || true
	@printf "\033[32m✓\033[0m Clean complete: generated artifacts (caches, builds, docs, coverage, output, logs) removed.\n"

docs-clean: ## Clean documentation artifacts
	@printf "\033[36m▶\033[0m Cleaning documentation artifacts...\n"
	@rm -rf docs/src/stubs docs/_build
	@printf "\033[32m✓\033[0m Documentation artifacts removed.\n"

docs-build: docs-clean ## Generate Sphinx documentation (HTML)
	@printf "\033[36m▶\033[0m Generating Sphinx documentation (HTML)...\n"
	@uv run --group docs sphinx-build -b html docs/ docs/_build/html
	@printf "\033[32m✓\033[0m Documentation generated: docs/_build/html/index.html\n"

docs-serve: docs-build ## Serve docs on http://localhost:8000
	@printf "\033[36m▶\033[0m Serving documentation at http://localhost:8000 (Ctrl+C to stop)\n"
	@uv run python -m http.server 8000 -d docs/_build/html

pre-commit-update: ## Update pre-commit hooks
	@printf "\033[36m▶\033[0m Updating pre-commit hooks...\n"
	@uv run pre-commit clean
	@uv run pre-commit install
	@printf "\033[32m✓\033[0m Pre-commit hooks updated.\n"

pre-commit-run: ## Run pre-commit hooks on all files
	@printf "\033[36m▶\033[0m Running pre-commit hooks on all files...\n"
	@uv run pre-commit run --all-files
	@printf "\033[32m✓\033[0m Pre-commit hooks executed.\n"

local-sync: ## Run local sync
	@printf "\033[36m▶\033[0m Running local sync...\n"
	@uv run assets-guardian --verbose sync
	@printf "\033[32m✓\033[0m Sync complete.\n"

local-audit: ## Run local audit (PDF generation)
	@printf "\033[36m▶\033[0m Running local audit (PDF generation)...\n"
	@uv run assets-guardian --verbose audit
	@printf "\033[32m✓\033[0m Audit complete.\n"

local-check: ## Run local diagnostic check of the configuration
	@printf "\033[36m▶\033[0m Running configuration diagnostic...\n"
	@uv run assets-guardian --verbose check
	@printf "\033[32m✓\033[0m Diagnostic complete.\n"

docker-build: ## Build the production Docker image
	@printf "\033[36m▶\033[0m Building production Docker image...\n"
	@docker build -t assets-guardian .
	@printf "\033[32m✓\033[0m Docker image 'assets-guardian' built.\n"

docker-sync: ## Run sync via Docker
	@printf "\033[36m▶\033[0m Running sync via Docker...\n"
	@docker run --rm \
		-v $(shell pwd)/logs:/app/logs \
		-v $(shell pwd)/outputs:/app/outputs \
		-v $(shell pwd)/config:/app/config:ro \
		-v $(shell pwd)/.assets-guardian_cache:/app/.assets-guardian_cache \
		--env-file .env \
		assets-guardian --verbose sync
	@printf "\033[32m✓\033[0m Docker sync complete.\n"

docker-audit: ## Run audit via Docker
	@printf "\033[36m▶\033[0m Running audit via Docker...\n"
	@docker run --rm \
		-v $(shell pwd)/logs:/app/logs \
		-v $(shell pwd)/outputs:/app/outputs \
		-v $(shell pwd)/config:/app/config:ro \
		-v $(shell pwd)/.assets-guardian_cache:/app/.assets-guardian_cache \
		--env-file .env \
		assets-guardian --verbose audit
	@printf "\033[32m✓\033[0m Docker audit complete.\n"

docker-check: ## Run diagnostic check via Docker
	@printf "\033[36m▶\033[0m Running diagnostic via Docker...\n"
	@docker run --rm \
		-v $(shell pwd)/logs:/app/logs \
		-v $(shell pwd)/outputs:/app/outputs \
		-v $(shell pwd)/config:/app/config:ro \
		-v $(shell pwd)/.assets-guardian_cache:/app/.assets-guardian_cache \
		--env-file .env \
		assets-guardian --verbose check
	@printf "\033[32m✓\033[0m Docker diagnostic complete.\n"

docker-help: ## Show helper via Docker
	@printf "\033[36m▶\033[0m Show helper via Docker...\n"
	@docker run --rm \
		-v $(shell pwd)/logs:/app/logs \
		-v $(shell pwd)/outputs:/app/outputs \
		-v $(shell pwd)/config:/app/config:ro \
		-v $(shell pwd)/.assets-guardian_cache:/app/.assets-guardian_cache \
		assets-guardian --help
	@printf "\033[32m✓\033[0m Docker show helper.\n"
