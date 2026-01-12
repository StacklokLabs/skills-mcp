---
name: dockerfile-best-practices
description: Write secure, efficient Dockerfiles following container best practices
license: Apache-2.0
compatibility: claude-3
metadata:
  author: skills-mcp
  version: "1.0"
  category: devops
allowed-tools: Read Write
---

# Dockerfile Best Practices

Create secure, efficient, and maintainable Docker images.

## Multi-Stage Builds

Reduce final image size by separating build and runtime stages.

```dockerfile
# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

COPY . .
RUN python -m compileall .

# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app .

ENV PATH=/root/.local/bin:$PATH
CMD ["python", "main.py"]
```

## Base Image Selection

### Use Specific Tags
```dockerfile
# BAD: Mutable tag
FROM python:latest

# GOOD: Immutable digest
FROM python:3.12-slim@sha256:abc123...

# ACCEPTABLE: Specific version
FROM python:3.12.1-slim-bookworm
```

### Prefer Minimal Images
| Base Image | Size | Use Case |
|------------|------|----------|
| alpine | ~5MB | Small, musl-based |
| slim | ~50MB | Debian minimal |
| distroless | ~20MB | No shell, minimal |
| scratch | 0MB | Static binaries |

## Layer Optimization

### Combine Commands
```dockerfile
# BAD: Multiple layers
RUN apt-get update
RUN apt-get install -y curl
RUN apt-get clean

# GOOD: Single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
```

### Order by Change Frequency
```dockerfile
# Least frequently changed first
FROM python:3.12-slim

# System deps (rarely change)
RUN apt-get update && apt-get install -y libpq-dev

# Python deps (change sometimes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (changes often)
COPY . .

CMD ["python", "main.py"]
```

## Security Best Practices

### Run as Non-Root
```dockerfile
# Create non-root user
RUN groupadd -r appgroup && \
    useradd -r -g appgroup appuser

# Set ownership
COPY --chown=appuser:appgroup . /app

# Switch to non-root
USER appuser
```

### Don't Store Secrets
```dockerfile
# BAD: Secret in image
ENV API_KEY=secret123

# GOOD: Inject at runtime
# docker run -e API_KEY=secret123 myimage
ENV API_KEY=""
```

### Scan for Vulnerabilities
```bash
# Using Trivy
trivy image myimage:latest

# Using Docker Scout
docker scout cves myimage:latest
```

### Use .dockerignore
```dockerignore
.git
.env
*.pyc
__pycache__
node_modules
.pytest_cache
*.log
```

## Caching Best Practices

### Leverage Build Cache
```dockerfile
# Copy only what's needed for deps first
COPY package.json package-lock.json ./
RUN npm ci

# Then copy rest of code
COPY . .
```

### Use BuildKit Cache Mounts
```dockerfile
# syntax=docker/dockerfile:1.4

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

## Health Checks

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
```

## Labels and Metadata

```dockerfile
LABEL org.opencontainers.image.source="https://github.com/org/repo"
LABEL org.opencontainers.image.description="My application"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.licenses="Apache-2.0"
```

## Language-Specific Examples

### Python
```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -r appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
```

### Node.js
```dockerfile
FROM node:20-slim

ENV NODE_ENV=production
WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

RUN chown -R node:node /app
USER node

EXPOSE 3000
CMD ["node", "server.js"]
```

### Go
```dockerfile
FROM golang:1.22 AS builder

WORKDIR /app
COPY go.* ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /app/server

FROM gcr.io/distroless/static-debian12
COPY --from=builder /app/server /server
USER nonroot:nonroot
ENTRYPOINT ["/server"]
```

## Common Anti-Patterns

| Anti-Pattern | Issue | Fix |
|--------------|-------|-----|
| `FROM :latest` | Non-reproducible | Use specific versions |
| Running as root | Security risk | Use USER directive |
| Large images | Slow deploys | Multi-stage builds |
| Secrets in ENV | Security risk | Use secrets management |
| No .dockerignore | Large context | Add .dockerignore |
| `apt-get upgrade` | Non-reproducible | Pin versions instead |

## Checklist

- [ ] Using specific base image version
- [ ] Multi-stage build if applicable
- [ ] Running as non-root user
- [ ] No secrets in image
- [ ] .dockerignore configured
- [ ] Health check defined
- [ ] Labels added
- [ ] Layers optimized
- [ ] Security scan passed
