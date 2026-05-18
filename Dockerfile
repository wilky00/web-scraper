# ABOUTME: App container — Python 3.12, uv package manager, Playwright + Chromium, non-root user.
# ABOUTME: Playwright is available here for future use; browser automation stays in app/worker/.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /uvx /usr/local/bin/

RUN useradd --system --create-home --shell /bin/bash appuser

WORKDIR /app

# Install dependencies as a separate layer (only rebuilt when deps change)
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system --no-cache .

# Install Playwright browsers + system dependencies (requires root)
RUN playwright install --with-deps chromium

COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
