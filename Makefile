# Makefile for Cheshire development

.PHONY: help install install-dev test test-fast test-cov clean lint format type-check all

help:
	@echo "Available commands:"
	@echo "  make install      - Install the package in editable mode"
	@echo "  make install-dev  - Install package with development dependencies"
	@echo "  make test         - Run all tests"
	@echo "  make test-fast    - Run tests in parallel"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo "  make clean        - Remove build artifacts and cache files"
	@echo "  make lint         - Run linting tools"
	@echo "  make format       - Format code with black and isort"
	@echo "  make type-check   - Run mypy type checking"
	@echo "  make all          - Run format, lint, type-check, and test"

install:
	pip install -e .

install-dev: install
	pip install -r requirements-dev.txt

test:
	pytest

test-fast:
	pytest -n auto

test-cov:
	pytest --cov=cheshire --cov-report=html --cov-report=term

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true

lint:
	flake8 cheshire tests --max-line-length=120 --ignore=E203,W503
	pylint cheshire

format:
	black cheshire tests --line-length=120
	isort cheshire tests --profile=black --line-length=120

type-check:
	mypy cheshire --ignore-missing-imports

all: format lint type-check test