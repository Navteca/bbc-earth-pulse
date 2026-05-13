FROM python:3.12-slim

WORKDIR /app

# Copy pre-exported requirements (generated via: uv export --no-dev --no-hashes -o requirements.txt)
# Using pip instead of uv avoids QEMU segfaults when building for non-native architectures
COPY requirements.txt ./

# Install production dependencies into the system Python (no venv needed in container)
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and entrypoint
COPY earth_pulse/ ./earth_pulse/
COPY entrypoint.sh ./entrypoint.sh

# Create non-root user and data directory, fix permissions
RUN useradd -m -u 1000 appuser && mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Start both the worker (background) and MCP server (foreground).
# Both write to stdout — all logs visible via: kubectl logs <pod>
CMD ["/bin/sh", "/app/entrypoint.sh"]
