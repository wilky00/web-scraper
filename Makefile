.PHONY: test test-unit test-api test-integration lint format check

# Unit tests only — no running DB or Redis required
test-unit:
	uv run pytest tests/unit/ -v

# API/web integration tests — no running DB required (uses mocks)
test-api:
	uv run pytest tests/api/ -v

# Full test suite — requires running DB and Redis (use docker compose up first)
test:
	docker compose run --rm app pytest tests/ -v

# Integration tests only — requires running DB and Redis
test-integration:
	docker compose run --rm app pytest tests/integration/ -v

lint:
	uv run ruff check .

format:
	uv run ruff format .

# Run lint + format check together (for CI)
check:
	uv run ruff check . && uv run ruff format --check .
