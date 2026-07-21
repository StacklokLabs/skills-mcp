# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-07-21

### Added

- MCP server with progressive disclosure for Agent Skills
- Session-based state tracking for expanded skills
- Local filesystem skill repository with caching
- Git skill source (`git:` config): HTTPS clones from `git://host/owner/repo[@ref][#subdir]` references (tag, branch, or pinned commit) with case-insensitive `SKILL.md` discovery, `#subdir` scoping, a commit-SHA-keyed snapshot cache, stale-serve-when-offline, and token auth (per-host config or `GITHUB_TOKEN`/`GITLAB_TOKEN`/`GIT_TOKEN` fallback; `GIT_TOKEN` is unscoped, prefer host-scoped tokens). SSRF-hardened (parse-time IP-literal rejection plus a pre-clone `getaddrinfo` check, bypassable with `allow_private_hosts`); references validated at startup, fetched lazily, failures non-fatal at WARNING. SSH, submodules (ignored with a warning), and marketplace/index parsing are out of scope; residual risks (DNS-rebinding/redirect TOCTOU, unbounded clone size) documented in [skill sources](guides/skill-sources.md#security-notes-and-accepted-residuals)
- SEP-2640 resource annotations on every listed resource: `audience` (`["assistant"]`), `priority` (0.8 skill-level, 0.3 sub-resources), ISO 8601 `lastModified` from file mtime (omitted when unknown); see [MCP surface](reference/mcp-surface.md#sep-2640-alignment)
- `last_modified` on the `Skill` and `SkillResource` domain models, populated from file mtime by the local and OCI repositories
- Experimental `io.modelcontextprotocol/skills` capability on `initialize`, via a `Server` subclass that also corrects `resources.listChanged` to `true`
- `validate_skill` tool, disabled by default; allow-list directories with the repeatable `--validation-path` CLI flag or `server.validation_paths` (CLI takes precedence); see [enabling skill validation](guides/validation.md)
- Tests pinning the SEP-2640 bare-URI read guarantee (a resource can be read by URI with no prior listing or expansion)

### Changed

- License changed to **Proprietary** (was declared Apache-2.0): pyproject metadata, OSI classifier, and README updated. © Stacklok, Inc.
- Pinned `mcp[cli]` to `>=1.28.1,<2` (upstream `main` is v2 dev); raised floors: `pydantic>=2.11`, `uvicorn>=0.31.1`, `anyio>=4.5`
- New dependency `dulwich>=1.2.10` (pure-Python git) backing the git source: dual-licensed Apache-2.0 OR GPL-2.0-or-later, consumed under Apache-2.0 (compatible with proprietary use); ships `py.typed`; single-maintainer project, noted for supply-chain awareness
- Toolchain refresh: `ruff>=0.15` (2026 formatter style), `mypy>=2.0` (strict-clean under 2.x defaults)
- CI test matrix updated to Python 3.12-3.14 (dropped the 3.11 leg, which contradicted `requires-python >=3.12`)
- Dockerfile build stage bumped to the uv 0.11 builder image; ruff `target-version` raised to `py312`

### Fixed

- A `skills.yaml` with only git sources now starts the server instead of falling back to `SKILLS_MCP_PATHS` and exiting
- Declared `starlette>=0.50` as a direct dependency (`server.py` imports it directly but relied on it transitively via `mcp`)
- `get_skill` and prompt expansion handle invalid skill names gracefully (the previous `except ValueError` guards were dead code: `SkillName` raises `InvalidSkillNameError` and `TypeError`, which propagated uncaught)
- Skill name collisions across composite repositories surface once at WARNING with source provenance instead of being dropped silently at DEBUG
- Expired sessions are evicted by a periodic cleanup task wired into the ASGI lifespan, so long-running servers no longer accumulate stale session state unboundedly
- Session-ID resolution fails closed: requests without an MCP session ID are sessionless rather than sharing a single `"default"` session, preventing expanded-skill state from bleeding across unrelated requests
- `resources.listChanged` is advertised as `true` to match actual behavior (notifications were emitted while the capability said `false`)
- A bare-string `validation_paths` in the config file (e.g. `validation_paths: ./skills`) is treated as a single path instead of being iterated character by character

## [0.1.0] - TBD

Initial release.

[Unreleased]: https://github.com/StacklokLabs/skills-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/StacklokLabs/skills-mcp/compare/v0.0.2...v0.2.0
[0.1.0]: https://github.com/stacklok/skills-mcp/releases/tag/v0.1.0
