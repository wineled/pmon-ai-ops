# PMON-AI-OPS - Top-Level Harness Makefile
# Unified command interface for development, testing, and deployment

.PHONY: help install dev test build docker clean lint format check deploy

# Default target
help:
	@echo "PMON-AI-OPS - Harness Command Center"
	@echo ""
	@echo "Development:"
	@echo "  make install          Install all dependencies"
	@echo "  make dev              Start development environment"
	@echo "  make dev-backend      Start backend only"
	@echo "  make dev-frontend     Start frontend only"
	@echo "  make stop             Stop all services"
	@echo "  make restart          Restart all services"
	@echo "  make status           Check service status"
	@echo "  make logs             Tail all logs"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run all linters"
	@echo "  make lint-backend     Lint Python code (ruff)"
	@echo "  make lint-frontend    Lint TypeScript (eslint)"
	@echo "  make format           Format all code"
	@echo "  make typecheck        Type checking (mypy + tsc)"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-backend     Run Python tests (pytest)"
	@echo "  make test-frontend    Run frontend tests"
	@echo "  make coverage         Generate coverage reports"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build all Docker images"
	@echo "  make docker-up        Start with docker-compose"
	@echo "  make docker-down      Stop docker-compose"
	@echo "  make docker-logs      View Docker logs"
	@echo ""
	@echo "Deployment:"
	@echo "  make build            Build production artifacts"
	@echo "  make deploy           Deploy to production"
	@echo "  make health           Check health endpoints"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            Clean temporary files"
	@echo "  make clean-all        Deep clean"
	@echo "  make update           Update all dependencies"

# Environment Detection
PYTHON := python
BACKEND_DIR := backend
FRONTEND_DIR := frontend
DOCKER_DIR := docker

# Installation
install: install-backend install-frontend
	@echo "All dependencies installed"

install-backend:
	@echo "Installing backend dependencies..."
	cd $(BACKEND_DIR) && $(PYTHON) -m pip install -e ".[dev]"

install-frontend:
	@echo "Installing frontend dependencies..."
	cd $(FRONTEND_DIR) && npm install

# Development
dev:
	@echo "Starting development environment..."
	$(PYTHON) pmon.py start

dev-backend:
	@echo "Starting backend only..."
	cd $(BACKEND_DIR) && $(PYTHON) -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	@echo "Starting frontend only..."
	cd $(FRONTEND_DIR) && npm run dev

stop:
	@echo "Stopping all services..."
	$(PYTHON) pmon.py stop

restart:
	@echo "Restarting all services..."
	$(PYTHON) pmon.py restart

status:
	@echo "Checking service status..."
	$(PYTHON) pmon.py status

logs:
	@echo "Tailing logs (Ctrl+C to exit)..."
	$(PYTHON) pmon.py logs

# Code Quality
lint: lint-backend lint-frontend
	@echo "All linting passed"

lint-backend:
	@echo "Linting Python code..."
	cd $(BACKEND_DIR) && ruff check src tests
	cd $(BACKEND_DIR) && ruff format --check src tests

lint-frontend:
	@echo "Linting TypeScript code..."
	cd $(FRONTEND_DIR) && npx eslint src --ext .ts,.tsx

format:
	@echo "Formatting code..."
	cd $(BACKEND_DIR) && ruff format src tests
	cd $(FRONTEND_DIR) && npx prettier --write "src/**/*.{ts,tsx,json,css,md}"

typecheck: typecheck-backend typecheck-frontend
	@echo "Type checking passed"

typecheck-backend:
	@echo "Type checking Python..."
	cd $(BACKEND_DIR) && mypy src --ignore-missing-imports

typecheck-frontend:
	@echo "Type checking TypeScript..."
	cd $(FRONTEND_DIR) && npm run typecheck

check: lint typecheck test
	@echo "All checks passed"

# Testing
test: test-backend test-frontend
	@echo "All tests passed"

test-backend:
	@echo "Running Python tests..."
	cd $(BACKEND_DIR) && pytest -v

test-frontend:
	@echo "Running frontend tests..."
	cd $(FRONTEND_DIR) && npm test

coverage:
	@echo "Generating coverage reports..."
	cd $(BACKEND_DIR) && pytest --cov=src --cov-report=html --cov-report=term

# Docker
docker-build:
	@echo "Building Docker images..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml build

docker-up:
	@echo "Starting Docker environment..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml up -d

docker-down:
	@echo "Stopping Docker environment..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml down

docker-logs:
	@echo "Docker logs..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml logs -f

# Build & Deploy
build: build-frontend
	@echo "Build complete"

build-frontend:
	@echo "Building frontend..."
	cd $(FRONTEND_DIR) && npm run build

health:
	@echo "Health check..."
	@curl -s http://localhost:8000/api/health || echo "Backend not responding"

# Maintenance
clean:
	@echo "Cleaning temporary files..."
	cd $(BACKEND_DIR) && ruff clean 2>nul || true

clean-all: clean
	@echo "Deep cleaning..."
	rm -rf $(FRONTEND_DIR)/node_modules
	cd $(BACKEND_DIR) && pip uninstall -y pmon-ai-ops-backend 2>nul || true

update:
	@echo "Updating dependencies..."
	cd $(BACKEND_DIR) && $(PYTHON) -m pip install --upgrade -e ".[dev]"
	cd $(FRONTEND_DIR) && npm update
