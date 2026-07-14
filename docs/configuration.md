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

# Server settings
server:
  host: 127.0.0.1
  port: 8080
  log_level: WARNING
  # Directories under which validate_skill may operate (empty = disabled)
  validation_paths:
    - ./skills
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

### Enabling `validate_skill`

The `validate_skill` tool is disabled by default. Enable it by allow-listing
one or more directories it may inspect, either on the command line (repeatable,
takes precedence) or in the config file:

```bash
skills-mcp --validation-path ./skills --validation-path /srv/skills
```

```yaml
server:
  validation_paths:
    - ./skills
    - /srv/skills
```

A path passed to `validate_skill` that resolves outside every allow-listed
directory is refused. With no paths configured, the tool reports that
validation is disabled.

!!! warning "Scope the allow-list narrowly"
    `validate_skill` intentionally reports whether a path exists and whether it
    has a valid skill structure *within* the allow-listed roots, to any
    connected client. Point `validation_paths` at the directories that hold
    your skills — not at a broad or shared location such as `/`, `$HOME`, or a
    multi-tenant data directory — so this probing cannot be used to
    fingerprint unrelated files.

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

### Git Repositories

Clones skills from Git repositories over HTTPS and discovers every directory
containing a `SKILL.md` (matched case-insensitively):

```yaml
git:
  cache_dir: ~/.cache/skills-mcp/git  # Where cloned snapshots are cached
  clone_timeout: 120                  # Per-repository clone/resolve timeout (s)
  allow_private_hosts: false          # SSRF guard (see below)
  skills:
    - repo: git://github.com/org/skills@v1.0.0        # pin to a tag
    - repo: git://github.com/org/skills@main          # track a branch
    - repo: git://github.com/org/skills@<40-hex-sha>  # pin to a commit
    - repo: git://github.com/org/skills@main#analysis # scope to a subdir
```

#### Reference syntax

References use ToolHive notation: `git://host/owner/repo[@ref][#subdir]`.
`git://` is *notation only* — repositories are always fetched over **HTTPS**,
never the unauthenticated git daemon protocol.

| Part | Meaning |
|------|---------|
| `host/owner/repo` | The repository (nested owners like `group/subgroup` are allowed; a trailing `.git` is stripped) |
| `@ref` | A branch, tag, or 40-character commit SHA. Omitted → the remote's default branch. **Tag or commit pins are recommended** for reproducibility |
| `#subdir` | Restrict discovery to a subdirectory of the repository |

The resolved commit SHA is the skill's content version. Pinned (40-hex)
commits are immutable and re-load from cache with no network access; branch
references re-resolve on refresh and produce a new snapshot when the tip moves.

#### Authentication

Git access is **HTTPS-with-token only** (no SSH). The `password` field carries
the token and the username defaults to `x-access-token`:

```yaml
git:
  auth:
    github.com:
      password: ${GITHUB_TOKEN}
    gitlab.example.com:
      username: ${GIT_USER}          # optional; defaults to x-access-token
      password_file: /run/secrets/git_token   # file-based creds also supported
```

If no per-host `auth` entry matches, an environment token is used as a
fallback: `GITHUB_TOKEN` for `github.com`, `GITLAB_TOKEN` for `gitlab.com`, and
`GIT_TOKEN` for any host. This lets a single `GITHUB_TOKEN` work with zero
`auth` configuration. Credentials are passed only as transport parameters —
never embedded in a URL or written to logs.

#### Cache and offline behavior

Snapshots accumulate under `cache_dir` as `host/owner/repo/<sha>/`. There is no
automatic eviction this release: pinned refs are immutable, and each new branch
tip adds one directory. Reclaim space by removing snapshot directories manually
(`rm -rf`). When a remote is unreachable, a previously cached snapshot for the
same reference is served stale with a warning; otherwise that reference is
skipped and the other sources keep working.

#### Private-host protection (SSRF)

Before cloning, the host is resolved and rejected if it points at a
private/loopback/link-local/reserved address; literal private IPs are rejected
at parse time. Set `allow_private_hosts: true` to permit internal Git hosts
(e.g. an on-prem GitLab). This narrows, but does not fully close, a
time-of-check/time-of-use window, so enable it only for trusted networks.

#### Limitations

- **HTTPS + token only** — SSH remotes are not supported.
- **Submodules are ignored** — a `.gitmodules` file logs a warning and is not
  recursed.
- **No marketplace/index parsing** — `marketplace.json` / `index.json` files
  are not interpreted; discovery is purely directory-based.

## Validation

The server validates configuration on startup:

- **Port**: Must be an integer between 1 and 65535
- **Log level**: Must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Paths**: Skill source and `validation_paths` directories are checked; a
  path that does not exist or is not a directory logs a warning at startup
  (the server keeps serving)
- **OCI images**: Must be valid image references

Invalid configuration will cause the server to exit with a clear error message.
