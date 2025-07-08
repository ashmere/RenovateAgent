.PHONY: help install install-dev test test-cov lint format type-check security-check clean run docker-build docker-run docker-stop pre-commit setup-dev

# Default target
.DEFAULT_GOAL := help

# Colors for output
BOLD := \033[1m
RESET := \033[0m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m

help: ## Show this help message
	@echo "$(BOLD)Renovate PR Assistant$(RESET)"
	@echo "Available commands:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

install: ## Install production dependencies
	@echo "$(YELLOW)Installing production dependencies...$(RESET)"
	pip install -r requirements.txt
	pip install -e .

install-dev: ## Install development dependencies
	@echo "$(YELLOW)Installing development dependencies...$(RESET)"
	pip install -r requirements.txt
	pip install -e .[dev]

setup-dev: install-dev ## Complete development setup
	@echo "$(YELLOW)Setting up development environment...$(RESET)"
	pre-commit install
	@echo "$(GREEN)Development environment ready!$(RESET)"

test: ## Run tests
	@echo "$(YELLOW)Running tests...$(RESET)"
	pytest tests/ -v

test-cov: ## Run tests with coverage
	@echo "$(YELLOW)Running tests with coverage...$(RESET)"
	pytest tests/ -v --cov=renovate_agent --cov-report=html --cov-report=term-missing

test-integration: ## Run integration tests
	@echo "$(YELLOW)Running integration tests...$(RESET)"
	pytest tests/integration/ -v -m integration

lint: ## Run linting
	@echo "$(YELLOW)Running linting...$(RESET)"
	ruff check src/ tests/
	black --check src/ tests/

format: ## Format code
	@echo "$(YELLOW)Formatting code...$(RESET)"
	black src/ tests/
	isort src/ tests/
	ruff check --fix src/ tests/

type-check: ## Run type checking
	@echo "$(YELLOW)Running type checking...$(RESET)"
	mypy src/

security-check: ## Run security checks
	@echo "$(YELLOW)Running security checks...$(RESET)"
	bandit -r src/ -f json -o bandit-report.json
	@echo "$(GREEN)Security check complete. Report: bandit-report.json$(RESET)"

pre-commit: ## Run pre-commit hooks
	@echo "$(YELLOW)Running pre-commit hooks...$(RESET)"
	pre-commit run --all-files

clean: ## Clean build artifacts
	@echo "$(YELLOW)Cleaning build artifacts...$(RESET)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf bandit-report.json
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: ## Run the application
	@echo "$(YELLOW)Starting Renovate PR Assistant...$(RESET)"
	uvicorn renovate_agent.main:app --reload --log-level debug

run-prod: ## Run the application in production mode
	@echo "$(YELLOW)Starting Renovate PR Assistant (production)...$(RESET)"
	uvicorn renovate_agent.main:app --host 0.0.0.0 --port 8000

docker-build: ## Build Docker image
	@echo "$(YELLOW)Building Docker image...$(RESET)"
	docker build -t renovate-agent:latest .

docker-run: ## Run Docker container
	@echo "$(YELLOW)Running Docker container...$(RESET)"
	docker-compose up -d

docker-stop: ## Stop Docker container
	@echo "$(YELLOW)Stopping Docker container...$(RESET)"
	docker-compose down

docker-logs: ## View Docker logs
	@echo "$(YELLOW)Viewing Docker logs...$(RESET)"
	docker-compose logs -f renovate-agent

docker-clean: ## Clean Docker artifacts
	@echo "$(YELLOW)Cleaning Docker artifacts...$(RESET)"
	docker-compose down -v
	docker system prune -f

db-upgrade: ## Run database migrations
	@echo "$(YELLOW)Running database migrations...$(RESET)"
	alembic upgrade head

db-migrate: ## Create new database migration
	@echo "$(YELLOW)Creating new database migration...$(RESET)"
	@read -p "Enter migration message: " message; \
	alembic revision --autogenerate -m "$$message"

db-reset: ## Reset database
	@echo "$(YELLOW)Resetting database...$(RESET)"
	rm -f renovate_agent.db
	alembic upgrade head

check-all: lint type-check security-check test ## Run all checks
	@echo "$(GREEN)All checks passed!$(RESET)"

deps-update: ## Update dependencies
	@echo "$(YELLOW)Updating dependencies...$(RESET)"
	pip-compile requirements.in
	pip-compile requirements-dev.in

validate-env: ## Validate environment configuration
	@echo "$(YELLOW)Validating environment configuration...$(RESET)"
	python -c "from renovate_agent.config import settings; print('✓ Configuration valid')"

setup-github-app: ## Setup GitHub App (interactive)
	@echo "$(YELLOW)Setting up GitHub App...$(RESET)"
	@echo "Please follow the instructions at: https://docs.github.com/en/developers/apps/creating-a-github-app"
	@echo "Required permissions:"
	@echo "- Contents: Write"
	@echo "- Issues: Write"
	@echo "- Pull requests: Write"
	@echo "- Checks: Read"
	@echo "- Metadata: Read"

docs-serve: ## Serve documentation locally
	@echo "$(YELLOW)Serving documentation...$(RESET)"
	python -m http.server 8080 --directory docs/

health-check: ## Check application health
	@echo "$(YELLOW)Checking application health...$(RESET)"
	curl -f http://localhost:8000/health || echo "$(RED)Application is not responding$(RESET)"

# Development workflow targets
dev-setup: setup-dev ## Alias for setup-dev
dev-test: test-cov ## Alias for test-cov
dev-check: check-all ## Alias for check-all

# CI/CD targets
ci-test: install-dev test-cov lint type-check security-check ## CI test pipeline
ci-build: docker-build ## CI build pipeline
ci-deploy: docker-run ## CI deploy pipeline
