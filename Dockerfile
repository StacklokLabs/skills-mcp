# Skills MCP Server
# Using Chainguard Python image - minimal, zero CVEs, no auth required
# https://edu.chainguard.dev/chainguard/chainguard-images/getting-started/python/

# Build stage: install dependencies with uv
FROM ghcr.io/astral-sh/uv:0.11-python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Install the application
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# Runtime stage: Chainguard minimal image (no auth required for :latest)
FROM cgr.dev/chainguard/python:latest

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SKILLS_MCP_HOST=0.0.0.0 \
    SKILLS_MCP_PORT=8080

EXPOSE 8080

# Chainguard images run as non-root by default
ENTRYPOINT ["python", "-m", "skills_mcp"]
