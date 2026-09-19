# Skills MCP Server
# Using Chainguard Python image - minimal, zero CVEs, no auth required
# https://edu.chainguard.dev/chainguard/chainguard-images/getting-started/python/

# Build stage: install dependencies with uv
# NOTE: the python version here must match cgr.dev/chainguard/python:latest
# (currently 3.14) — the venv is copied across stages and a version mismatch
# breaks module resolution at runtime. Chainguard's free tier only offers
# :latest, so this drifts when Chainguard bumps Python; the CI Docker job
# only verifies the build, not a runtime import.
FROM ghcr.io/astral-sh/uv:0.12-python3.14-trixie-slim@sha256:63018e7b676ef735eee4da4f9c2e7b5f5e3851fa023745d78ce91d1a099a35fd AS builder

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
FROM cgr.dev/chainguard/python:latest@sha256:011e73b4e30e0fe9407a42b82a920b4fa13ebc0bf029a48b714f950df254ca20

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
