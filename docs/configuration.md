# Configuration

The Skills MCP server can be configured through a YAML configuration file, environment variables, or command-line arguments. Configuration sources are applied in the following order of precedence (highest to lowest):

1. Command-line arguments (`--host`, `--port`, `--config`)
2. Environment variables (`SKILLS_MCP_*`)
3. Configuration file (`skills.yaml`)
4. Default values

## Configuration File

The server looks for a `skills.yaml` file in:

1. Current working directory
2. `~/.config/skills-mcp/skills.yaml`

You can also specify a config file explicitly with `--config`:

```bash
skills-mcp --config /path/to/skills.yaml
```

### Full Example

```yaml
version: "1"

# Local filesystem skill sources
local:
  paths:
    - ./skills
    - ~/.local/share/skills

# OCI registry skill sources
oci:
  cache_dir: ~/.cache/skills-mcp
  cache_ttl: 3600  # seconds (0 = never expire)
  verify_tls: true
  skills:
    - image: ghcr.io/stacklok/skills/data-analysis:v1.0.0
    - image: ghcr.io/stacklok/skills/code-review:latest
  auth:
    ghcr.io:
      username: ${GITHUB_USER}
      password: ${GITHUB_TOKEN}

# Server settings
server:
  host: 127.0.0.1
  port: 8080
  log_level: WARNING
```

### Environment Variable Expansion

The configuration file supports environment variable expansion using `${VAR}` syntax:

- `${VAR}` - Expands to the value of `VAR`, errors if not set
- `${VAR:-default}` - Expands to `VAR` if set, otherwise uses `default`

This is useful for secrets like registry credentials:

```yaml
oci:
  auth:
    ghcr.io:
      username: ${GITHUB_USER}
      password: ${GITHUB_TOKEN:-}  # Empty default if not set
```

## Environment Variables

The following environment variables can be used to configure the server:

| Variable | Description | Default |
|----------|-------------|---------|
| `SKILLS_MCP_HOST` | Server bind address | `127.0.0.1` |
| `SKILLS_MCP_PORT` | Server port (1-65535) | `8080` |
| `SKILLS_MCP_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | `WARNING` |
| `SKILLS_MCP_PATHS` | Colon-separated list of skill directories (fallback if no config file) | - |

### Examples

```bash
# Override server host and port
export SKILLS_MCP_HOST=0.0.0.0
export SKILLS_MCP_PORT=9090

# Enable debug logging
export SKILLS_MCP_LOG_LEVEL=DEBUG

# Quick start without config file
export SKILLS_MCP_PATHS=/path/to/skills:~/my-skills
skills-mcp
```

## Command-Line Arguments

```
usage: skills-mcp [-h] [-c CONFIG] [--host HOST] [--port PORT]

MCP server for Agent Skills

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to configuration file
  --host HOST           Host to bind to (overrides config/env)
  --port PORT           Port to bind to (overrides config/env)
```

## Skill Sources

### Local Filesystem

Scans directories for skills (directories containing `SKILL.md`):

```yaml
local:
  paths:
    - ./skills           # Relative to current directory
    - ~/my-skills        # Home directory expansion supported
    - /opt/shared/skills # Absolute paths
```

### OCI Registry

Pulls skills from OCI-compliant registries:

```yaml
oci:
  cache_dir: ~/.cache/skills-mcp  # Where to cache pulled artifacts
  cache_ttl: 3600                 # Cache lifetime in seconds
  verify_tls: true                # Verify TLS certificates
  skills:
    - image: ghcr.io/org/skill:v1.0.0
    - image: docker.io/user/skill:latest
```

#### Authentication

Per-registry authentication using environment variables:

```yaml
oci:
  auth:
    ghcr.io:
      username: ${GITHUB_USER}
      password: ${GITHUB_TOKEN}
    docker.io:
      username: ${DOCKER_USER}
      password: ${DOCKER_TOKEN}
```

#### File-Based Credentials (Docker Secrets Pattern)

For environments like Docker Swarm or Kubernetes where credentials are mounted as files,
you can use `username_file` and `password_file` instead of inline values:

```yaml
oci:
  auth:
    ghcr.io:
      username_file: /run/secrets/github_user
      password_file: /run/secrets/github_token
```

This is useful for:

- **Kubernetes secrets**: Mounted as files in pods
- **High-security environments**: Credentials never appear in config files or environment variables

File reference fields:

| Field | Description |
|-------|-------------|
| `username_file` | Path to file containing username (whitespace trimmed) |
| `password_file` | Path to file containing password/token (whitespace trimmed) |

**Note**: If both direct values (`username`/`password`) and file references are specified,
file references take precedence.

## Validation

The server validates configuration on startup:

- **Port**: Must be an integer between 1 and 65535
- **Log level**: Must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Paths**: Must be valid directories (warning if not found)
- **OCI images**: Must be valid image references

Invalid configuration will cause the server to exit with a clear error message.
