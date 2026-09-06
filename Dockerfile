# Skills MCP Server
# Using Chainguard Python image - minimal, zero CVEs, no auth required
# https://edu.chainguard.dev/chainguard/chainguard-images/getting-started/python/

# Build stage: install dependencies with uv
# NOTE: the python version here must match cgr.dev/chainguard/python:latest
# (currently 3.14) — the venv is copied across stages and a version mismatch
# breaks module resolution at runtime. Chainguard's free tier only offers
# :latest, so this drifts when Chainguard bumps Python; the CI Docker job
# only verifies the build, not a runtime import.
FROM ghcr.io/astral-sh/uv:0.12-python3.14-trixie-slim@sha256:d5ddd498c5a28ec77ff1c70276f8f3c4a116a303c8b5583a018ea43c2e89e366 AS builder

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

# Runtime stage: Chainguard minimal image (no auth required for :latest).
# Digest-pinned so Renovate proposes digest bumps as reviewable PRs; the CI
# smoke test catches a Python version drift against the builder stage.
FROM cgr.dev/chainguard/python:latest@sha256:1f37785e5cdb70151f36aaa15e1e3cef4571424dbefbf4b0d8a9222535cb13ff

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# The venv's bin/python symlinks point at the builder's interpreter path,
# which does not exist in the Chainguard image — so the runtime python is
# used directly with the venv's site-packages on PYTHONPATH (version dir
# must match the builder python above).
ENV PYTHONPATH="/app/.venv/lib/python3.14/site-packages" \
    PYTHONUNBUFFERED=1 \
    SKILLS_MCP_HOST=0.0.0.0 \
    SKILLS_MCP_PORT=8080

EXPOSE 8080

# Chainguard images run as non-root by default
ENTRYPOINT ["python", "-m", "skills_mcp"]
