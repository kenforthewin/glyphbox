# Multi-stage build for the NetHack Agent Python app (api + worker)
FROM python:3.12-bookworm AS base

# System dependencies for NLE (NetHack Learning Environment)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    ninja-build \
    libncurses-dev \
    flex \
    bison \
    libbz2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src/ src/
COPY config/ config/
COPY alembic/ alembic/
COPY alembic.ini .
COPY skills/ skills/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directory for logs
RUN mkdir -p data/logs

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
