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

## [0.1.0] - TBD

Initial release.

[Unreleased]: https://github.com/stacklok/skills-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stacklok/skills-mcp/releases/tag/v0.1.0
