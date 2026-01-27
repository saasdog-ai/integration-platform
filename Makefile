.PHONY: help install install-dev run test lint format mypy docker-up docker-down migrate migrate-upgrade migrate-downgrade clean

help:
	@echo "Available commands:"
	@echo "  install        Install production dependencies"
	@echo "  install-dev    Install development dependencies"
	@echo "  run            Run the application"
	@echo "  test           Run tests with coverage"
	@echo "  lint           Run linting (ruff)"
	@echo "  format         Format code (black, ruff)"
	@echo "  mypy           Run type checking"
	@echo "  docker-up      Start Docker services"
	@echo "  docker-down    Stop Docker services"
	@echo "  migrate        Create new migration"
	@echo "  migrate-upgrade   Apply migrations"
	@echo "  migrate-downgrade Rollback last migration"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,aws]"

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -v

test-cov:
	pytest --cov=app --cov-report=html --cov-report=term-missing

lint:
	ruff check app tests
	black --check app tests

format:
	black app tests
	ruff check --fix app tests

mypy:
	mypy app

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

migrate:
	@read -p "Migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

migrate-upgrade:
	alembic upgrade head

migrate-downgrade:
	alembic downgrade -1

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
