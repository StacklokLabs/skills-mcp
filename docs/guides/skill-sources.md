# Skill sources

The server loads skills from three kinds of source, in any combination: local directories, git repositories, and OCI registries. Sources are declared in a `skills.yaml` config file (see the [configuration reference](../reference/configuration.md) for where the file lives and how precedence works).

When the same skill name appears in more than one source, local wins over git, and git wins over OCI. A shadowed skill is not dropped silently: each unique collision is logged once at `WARNING` with provenance (which source shadows which).

## Local directories

Directories are scanned for skills (directories containing a `SKILL.md`):

```yaml
local:
  paths:
    - ./skills           # Relative to current directory
    - ~/my-skills        # Home directory expansion supported
    - /opt/shared/skills # Absolute paths
```

## Git repositories

Skills are cloned from git repositories over HTTPS, and every directory containing a `SKILL.md` (matched case-insensitively) is discovered.

Public repositories need no auth configuration. The simplest possible git source points at a public repo with no `auth` block at all:

```yaml
git:
  skills:
    - repo: git://github.com/stacklok/skills@v1.0.0
```

That is a complete, working configuration. Add `cache_dir`, `auth`, and the other keys below only when you need them:

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

### Reference syntax

References use ToolHive notation: `git://host/owner/repo[@ref][#subdir]`. `git://` is notation only; repositories are always fetched over **HTTPS**, never the unauthenticated git daemon protocol.

| Part | Meaning |
|------|---------|
| `host/owner/repo` | The repository (nested owners like `group/subgroup` are allowed; a trailing `.git` is stripped) |
| `@ref` | A branch, tag, or 40-character commit SHA. Omitted: the remote's default branch. **Tag or commit pins are recommended** for reproducibility |
| `#subdir` | Restrict discovery to a subdirectory of the repository |

The resolved commit SHA is the skill's content version. Pinned (40-hex) commits are immutable and re-load from cache with no network access; branch references re-resolve on refresh and produce a new snapshot when the tip moves.

The optional `#subdir` scopes discovery to one subtree. Without it the whole repository is scanned:

```yaml
git:
  skills:
    - repo: git://github.com/org/skills@main            # scan the whole repo
    - repo: git://github.com/org/skills@main#packs/data # only packs/data/**
```

### When are repositories fetched?

Git references are **parsed and validated at startup** (a malformed `git://` string, a disallowed IP host, or a bad ref/subdir fails configuration loading). The repositories themselves are **fetched lazily on the first request** that lists or reads a skill, not at startup.

A fetch, resolve, or authentication failure is **non-fatal**: the affected reference is skipped (or served stale from cache, see below), other sources keep working, and the server does not exit. Because the failure is only visible in the **logs at WARNING level**, grep the server logs when a skill does not appear:

```
Failed to resolve git://...        # ref/host resolution or auth failed
Failed to fetch git repo git://... # clone or discovery failed
Serving stale ...; remote unreachable
```

Raise `server.log_level` to `INFO`/`DEBUG` for more detail (DEBUG also logs the credential *source*, never the secret).

### Authentication

Git access is **HTTPS-with-token only** (no SSH). The `password` field carries the token and the `username` defaults to `x-access-token`:

```yaml
git:
  auth:
    github.com:
      password: ${GITHUB_TOKEN}
    gitlab.example.com:
      username: ${GIT_USER}          # optional; defaults to x-access-token
      password_file: /run/secrets/git_token   # file-based creds also supported
```

The `x-access-token` default follows GitHub's convention, where the token goes in the password field and the username is ignored (any placeholder works). GitLab accepts any non-empty username alongside a personal access token, so the same default works there too; set `username` explicitly only if your host requires a specific value.

If no per-host `auth` entry matches, an environment token is used as a fallback: `GITHUB_TOKEN` for `github.com`, `GITLAB_TOKEN` for `gitlab.com`, and `GIT_TOKEN` for any host. This lets a single `GITHUB_TOKEN` work with zero `auth` configuration. Credentials are passed only as transport parameters, never embedded in a URL or written to logs.

!!! warning "`GIT_TOKEN` is unscoped"
    `GIT_TOKEN` is sent to **any** git host you configure a reference for, not just one. If you point at repositories on more than one host, a leaked or over-broad `GIT_TOKEN` is exposed to all of them. Prefer the host-scoped `GITHUB_TOKEN`/`GITLAB_TOKEN` fallbacks, or an explicit per-host `auth` entry, so each token only ever reaches its intended host.

### Cache and offline behavior

Snapshots accumulate under `cache_dir` as `host/owner/repo/<sha>/`. There is no automatic eviction this release: pinned refs are immutable, and each new branch tip adds one directory. Reclaim space by removing snapshot directories manually (`rm -rf`). When a remote is unreachable, a previously cached snapshot for the same reference is served stale with a warning; otherwise that reference is skipped and the other sources keep working.

### Private-host protection (SSRF)

Before cloning, the host is resolved and rejected if it points at a private/loopback/link-local/reserved address; literal private IPs are rejected at parse time. Set `allow_private_hosts: true` to permit internal git hosts (for example an on-prem GitLab). This narrows, but does not fully close, a time-of-check/time-of-use window, so enable it only for trusted networks.

### Security notes and accepted residuals

The git source is designed for **operator-controlled** references: the `git://` strings and tokens in your configuration are trusted inputs. With that in mind, two residual risks are documented rather than fully mitigated in this release:

!!! warning "Accepted residual risks"
    - **DNS-rebinding / redirect TOCTOU.** The pre-clone private-host check (above) resolves the hostname once; a hostile DNS server or HTTP redirect could still steer the actual connection elsewhere afterwards. The check raises the bar against accidental SSRF but is not a hard guarantee. Mitigate by pinning to trusted hosts and keeping `allow_private_hosts: false`.
    - **Unbounded clone size.** Unlike the OCI source, there are no per-artifact size caps on a git clone (dulwich exposes no clean surface for it). A hostile or accidentally huge repository can fill the cache disk. Mitigate with filesystem disk quotas on `cache_dir` and by pinning to trusted repositories.

### Limitations

- **HTTPS + token only**: SSH remotes are not supported.
- **Submodules are ignored**: a `.gitmodules` file logs a warning and is not recursed.
- **No marketplace/index parsing**: `marketplace.json` / `index.json` files are not interpreted; discovery is purely directory-based.

## OCI registries

Skills are pulled as artifacts from OCI-compliant registries:

```yaml
oci:
  cache_dir: ~/.cache/skills-mcp  # Where to cache pulled artifacts
  cache_ttl: 3600                 # Cache lifetime in seconds (0 = never expire)
  verify_tls: true                # Verify TLS certificates
  skills:
    - image: ghcr.io/org/skill:v1.0.0
    - image: docker.io/user/skill:latest
```

### Authentication

Per-registry authentication, typically fed from environment variables:

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

### File-based credentials (Docker secrets pattern)

For environments like Docker Swarm or Kubernetes where credentials are mounted as files, use `username_file` and `password_file` instead of inline values:

```yaml
oci:
  auth:
    ghcr.io:
      username_file: /run/secrets/github_user
      password_file: /run/secrets/github_token
```

This is useful for:

- **Kubernetes secrets**: mounted as files in pods
- **High-security environments**: credentials never appear in config files or environment variables

| Field | Description |
|-------|-------------|
| `username_file` | Path to file containing username (whitespace trimmed) |
| `password_file` | Path to file containing password/token (whitespace trimmed) |

File-based credentials work the same way for git host auth. If both direct values (`username`/`password`) and file references are specified, file references take precedence.

## Next steps

- [Configuration reference](../reference/configuration.md): every key on the source blocks above, with defaults and constraints.
- [Enabling skill validation](validation.md): let skill authors validate directories over MCP once sources are serving.
- [MCP surface reference](../reference/mcp-surface.md): how the served skills appear to clients (tools, resources, prompts).
