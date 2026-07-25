.PHONY: lint typecheck test test-unit test-integration test-contract test-schema test-benchmark test-all security check

lint:
	black --check src/ tests/
	isort --check-only src/ tests/
	flake8 src/ tests/

typecheck:
	mypy src/miie/ --ignore-missing-imports

test-unit:
	pytest tests/unit/ -x -q --tb=short

test-integration:
	pytest tests/integration/ -x -q --tb=short

test-contract:
	pytest tests/contract/ -x -q --tb=short

test-schema:
	pytest tests/schema/ -x -q --tb=short

test-benchmark:
	pytest tests/benchmark/ -x -q --tb=short

test-all:
	pytest tests/ -x -q --tb=short

security:
	pip-audit

check: lint typecheck test-all security
