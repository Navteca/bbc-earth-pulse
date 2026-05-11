FROM python:3.12-slim

WORKDIR /app

# Install uv via pip (avoids ghcr.io which may be unreachable in some environments)
RUN pip install --no-cache-dir uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only into the project venv
RUN uv sync --frozen --no-dev

# Copy source
COPY earth_pulse/ ./earth_pulse/

# Create non-root user and data directory, fix permissions
RUN useradd -m -u 1000 appuser && mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Use the venv Python directly — avoids uv re-syncing dev deps at runtime
ENV PATH="/app/.venv/bin:$PATH"
