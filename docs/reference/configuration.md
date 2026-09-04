# Configuration reference

The server is configured through a YAML configuration file, environment variables, and command-line arguments. Sources are applied in the following order of precedence (highest to lowest):

1. Command-line arguments (`--host`, `--port`, `--validation-path`; `--config` selects the file)
2. Environment variables (`SKILLS_MCP_*`)
3. Configuration file (`skills.yaml`)
4. Default values

## Configuration file discovery

The server looks for a `skills.yaml` file in:

1. Current working directory
2. `~/.config/skills-mcp/skills.yaml`

You can also specify a config file explicitly with `--config`:

```bash
skills-mcp --config /path/to/skills.yaml
```

If no config file is found (or the file defines no skill sources), the server falls back to the `SKILLS_MCP_PATHS` environment variable for local skill directories. If that is also unset, the server exits with an error explaining the options.

## Full example

```yaml
version: "1"

# Local filesystem skill sources
local:
  paths:
    - ./skills
    - ~/.local/share/skills

# Git repository skill sources
git:
  cache_dir: ~/.cache/skills-mcp/git
  clone_timeout: 120        # seconds per repository
  allow_private_hosts: false
  skills:
    - repo: git://github.com/stacklok/skills@v1.0.0
    - repo: git://github.com/stacklok/skills@main#analysis
  auth:
    github.com:
      password: ${GITHUB_TOKEN}

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
  # Directories under which validate_skill may operate (empty = disabled)
  validation_paths:
    - ./skills
```

For task-oriented walkthroughs of each source type, see [skill sources](../guides/skill-sources.md).

## Configuration keys

### Top level

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `version` | string | `"1"` | Configuration schema version |
| `local` | section | unset | Local filesystem sources |
| `git` | section | unset | Git repository sources |
| `oci` | section | unset | OCI registry sources |
| `server` | section | defaults | Server settings |

At least one source section (`local`, `git`, or `oci`) with entries must be present, unless `SKILLS_MCP_PATHS` is set. Any combination works, including a git-only or OCI-only configuration. On exact canonical source-relative path collisions, local takes precedence over git, then OCI; duplicate names at distinct paths remain available.

### `local`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `paths` | list of paths | `[]` | Directories scanned for skills (directories containing `SKILL.md`). `~` is expanded |

### `git`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `skills` | list | `[]` | Entries of the form `repo: git://host/owner/repo[@ref][#subdir]`. Always fetched over HTTPS |
| `auth` | map | `{}` | Per-host credentials, keyed by hostname (see [auth fields](#auth-fields)). Username defaults to `x-access-token`. Env fallbacks: `GITHUB_TOKEN` (github.com), `GITLAB_TOKEN` (gitlab.com), `GIT_TOKEN` (any host) |
| `cache_dir` | path | unset | Directory for cloned snapshots (`host/owner/repo/<sha>/`). `~` is expanded |
| `clone_timeout` | int (>= 1) | `120` | Per-repository clone/resolve timeout in seconds |
| `allow_private_hosts` | bool | `false` | Permit hosts that resolve to private/loopback/link-local addresses (SSRF guard bypass) |

### `oci`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `skills` | list | `[]` | Entries of the form `image: <registry>/<repo>:<tag>` |
| `auth` | map | `{}` | Per-registry credentials, keyed by registry hostname (see [auth fields](#auth-fields)) |
| `cache_dir` | path | unset | Directory for cached pulled artifacts. `~` is expanded |
| `cache_ttl` | int (>= 0) | `3600` | Cache lifetime in seconds; `0` means never expire |
| `verify_tls` | bool | `true` | Verify TLS certificates when pulling |

### Auth fields

Each entry under `git.auth.<host>` or `oci.auth.<registry>` accepts:

| Key | Type | Description |
|-----|------|-------------|
| `username` | string | Username (for git, defaults to `x-access-token` when omitted) |
| `password` | string | Password or token |
| `username_file` | path | File containing the username (whitespace trimmed) |
| `password_file` | path | File containing the password/token (whitespace trimmed) |

File references take precedence over direct values when both are set.

### `server`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | `127.0.0.1` | Bind address |
| `port` | int (1-65535) | `8080` | Bind port |
| `log_level` | string | `WARNING` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (case-insensitive) |
| `validation_paths` | list of paths | `[]` | Directories under which `validate_skill` may operate; empty disables the tool. A bare string is accepted as a single path. See [enabling skill validation](../guides/validation.md) |

## Environment variable expansion

The configuration file supports environment variable expansion using `${VAR}` syntax:

- `${VAR}` expands to the value of `VAR` and errors if not set
- `${VAR:-default}` expands to `VAR` if set, otherwise uses `default`

This is useful for secrets like registry credentials:

```yaml
oci:
  auth:
    ghcr.io:
      username: ${GITHUB_USER}
      password: ${GITHUB_TOKEN:-}  # Empty default if not set
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SKILLS_MCP_HOST` | Server bind address | `127.0.0.1` |
| `SKILLS_MCP_PORT` | Server port (1-65535) | `8080` |
| `SKILLS_MCP_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | `WARNING` |
| `SKILLS_MCP_PATHS` | Colon-separated list of local skill directories, used only when no config file defines a skill source | unset |

`SKILLS_MCP_HOST`, `SKILLS_MCP_PORT`, and `SKILLS_MCP_LOG_LEVEL` override the corresponding `server` keys whether or not a config file is present.

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

## Command-line arguments

```
usage: skills-mcp [-h] [-c CONFIG] [--host HOST] [--port PORT]
                  [--validation-path PATH]

MCP server for Agent Skills

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to configuration file
  --host HOST           Host to bind to (overrides config/env)
  --port PORT           Port to bind to (overrides config/env)
  --validation-path PATH
                        Directory under which validate_skill may operate
                        (repeatable; overrides server.validation_paths)
```

## Startup validation

The server validates configuration on startup:

- **Port**: must be an integer between 1 and 65535
- **Log level**: must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Paths**: skill source and `validation_paths` directories are checked; a path that does not exist or is not a directory logs a warning at startup (the server keeps serving)
- **OCI images**: must be valid image references
- **Git references**: each `git://` reference is parsed and validated (scheme, host, ref, and subdir). A malformed reference fails startup

Invalid configuration causes the server to exit with a clear error message.

Network operations are **not** part of startup validation. OCI pulls and git clones happen lazily on first use; an unreachable registry or host, a missing ref, or an auth failure is non-fatal and surfaces only in the logs at WARNING (see [when are repositories fetched?](../guides/skill-sources.md#when-are-repositories-fetched) for the git log strings to grep). The server keeps serving the sources that do work.
