# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- MCP server with progressive disclosure for Agent Skills
- Skill validation tool
- Session-based state tracking for expanded skills
- Local filesystem skill repository with caching
- Git repository skill source (`git:` config section): clones skills over
  HTTPS from `git://host/owner/repo[@ref][#subdir]` references (tag, branch, or
  pinned commit), with case-insensitive `SKILL.md` discovery, `#subdir`
  scoping, a commit-SHA-keyed snapshot cache, stale-serve-when-offline, and
  HTTPS-token auth (per-host config or `GITHUB_TOKEN`/`GITLAB_TOKEN`/`GIT_TOKEN`
  fallback). Hardened against SSRF (parse-time IP-literal rejection plus a
  pre-clone `getaddrinfo` check, bypassable with `allow_private_hosts`).
  Git references are validated at startup but fetched lazily on first request;
  fetch/auth failures are non-fatal and logged at WARNING. Scope for this
  release excludes SSH, submodules (ignored with a warning), and
  marketplace/index parsing; two residual risks are documented in the git
  configuration section (DNS-rebinding/redirect TOCTOU after the pre-clone host
  check, and unbounded clone size — mitigate with trusted-repo pinning and disk
  quotas). `GIT_TOKEN` is an unscoped fallback sent to any configured host;
  prefer host-scoped tokens.
- SEP-2640 resource annotations on every listed resource: `audience`
  (`["assistant"]`), `priority` (0.8 skill-level, 0.3 sub-resources), and an
  ISO 8601 `lastModified` derived from file mtime (omitted when unknown).
- `last_modified` on the `Skill` and `SkillResource` domain models, populated
  from file mtime by the local and OCI repositories.
- Experimental capability declaration on `initialize`:
  `experimental["io.modelcontextprotocol/skills"]`, advertised via a
  `Server` subclass that also corrects `resources.listChanged` to `true`.
- `validate_skill` is now reachable: allow-list its directories with the
  repeatable `--validation-path` CLI flag or the `server.validation_paths`
  config option (CLI takes precedence).
- Tests pinning the SEP-2640 bare-URI read guarantee (a resource can be read
  by URI with no prior listing or expansion).

### Changed

- Raised dependency floors and pinned `mcp[cli]` to `>=1.28.1,<2` (per upstream
  guidance, as `main` is v2 dev); `pydantic>=2.11`, `uvicorn>=0.31.1`,
  `anyio>=4.5`.
- New dependency `dulwich>=1.2.10` (pure-Python Git) backs the Git skill
  source. It is dual-licensed **Apache-2.0 OR GPL-2.0-or-later** and is
  consumed here under **Apache-2.0**, matching this project's license; it
  ships `py.typed`, so no mypy `ignore_missing_imports` override is added.
  Single-maintainer project — noted for supply-chain awareness.
- Toolchain refresh: `ruff>=0.15` (adopts the 2026 formatter style) and
  `mypy>=2.0` (strict-clean under mypy 2.x defaults).
- CI test matrix updated to Python 3.12–3.14 (dropped the 3.11 leg, which
  contradicted `requires-python >=3.12`).
- Dockerfile build stage bumped to the uv 0.11 builder image.
- Ruff `target-version` raised to `py312` to match `requires-python >=3.12`.

### Fixed

- Declared `starlette>=0.50` as a direct dependency; `server.py` imports
  Starlette APIs directly but relied on it transitively via `mcp`.
- `get_skill` and prompt expansion now handle invalid skill names gracefully:
  the previous `except ValueError` guards were dead code because `SkillName`
  raises `InvalidSkillNameError` (not a `ValueError`) and `TypeError` for
  non-string input, both of which propagated uncaught to in-process callers.
- Skill name collisions across composite repositories now surface at WARNING
  level with source provenance (which repository is shadowed by which) instead
  of being dropped silently at DEBUG; each unique collision warns once.
- Expired sessions are now evicted by a periodic cleanup task wired into the
  server's ASGI lifespan, so long-running servers no longer accumulate stale
  session state unboundedly.
- Session-ID resolution now fails closed: requests without an MCP session ID
  are treated as sessionless rather than sharing a single `"default"` session,
  preventing expanded-skill state from bleeding across unrelated requests.
- `resources.listChanged` is now advertised as `true` to match actual
  behavior; the server emits `resources/list_changed` notifications on first
  expansion but previously advertised the capability as `false`.
- A bare-string `validation_paths` in the config file (e.g.
  `validation_paths: ./skills`) is now treated as a single path instead of
  being iterated character by character into nonsense paths.

## [0.1.0] - TBD

Initial release.

[Unreleased]: https://github.com/stacklok/skills-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stacklok/skills-mcp/releases/tag/v0.1.0
