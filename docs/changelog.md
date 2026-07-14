# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- MCP server with progressive disclosure for Agent Skills
- Skill validation tool
- Session-based state tracking for expanded skills
- Local filesystem skill repository with caching

### Changed

- Raised dependency floors and pinned `mcp[cli]` to `>=1.28.1,<2` (per upstream
  guidance, as `main` is v2 dev); `pydantic>=2.11`, `uvicorn>=0.31.1`,
  `anyio>=4.5`.
- Toolchain refresh: `ruff>=0.15` (adopts the 2026 formatter style) and
  `mypy>=2.0` (strict-clean under mypy 2.x defaults).
- CI test matrix updated to Python 3.12–3.14 (dropped the 3.11 leg, which
  contradicted `requires-python >=3.12`).
- Dockerfile build stage bumped to the uv 0.11 builder image.

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

## [0.1.0] - TBD

Initial release.

[Unreleased]: https://github.com/stacklok/skills-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stacklok/skills-mcp/releases/tag/v0.1.0
