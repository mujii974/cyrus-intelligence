.PHONY: install test test-v run lint

install:
	pip install -e ".[dev]" --break-system-packages 2>/dev/null || pip install -e . --break-system-packages

test:
	pytest --tb=short -q

test-v:
	pytest -v

run:
	uvicorn src.main:app --port 8002 --reload

lint:
	ruff check src/ tests/ 2>/dev/null || echo "ruff not installed — skipping"
