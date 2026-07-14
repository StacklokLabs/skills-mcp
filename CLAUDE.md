# Skills MCP Server

## Project Overview

Python MCP server implementing the Agent Skills specification (agentskills.io).
Exposes skills as MCP resources with progressive disclosure (3-tier loading).

## Technology Stack

- **Language**: Python 3.12+ (3.12–3.14 in CI)
- **Package Manager**: uv
- **MCP SDK**: mcp[cli] (python-sdk)
- **Validation**: Pydantic v2
- **Transport**: Streamable HTTP

## Architecture

```
src/skills_mcp/
├── domain/              # Core business logic (no external deps)
│   ├── models/          # Skill, SkillName, Manifest, Resource
│   ├── services/        # ManifestParser, TokenEstimator
│   ├── repositories.py  # SkillRepository protocol
│   └── exceptions.py    # Domain exceptions
├── infrastructure/      # External concerns
│   ├── mcp/             # SkillsMCPServer, SessionManager
│   └── persistence/     # LocalSkillRepository, CachingDecorator
└── __main__.py          # Entry point
```

### Layer Rules

- **Domain**: Core business logic and models
- **Infrastructure**: External integrations (MCP server, persistence). MAY import from domain

## Code Style

- **Formatting**: ruff format (88 char line length)
- **Linting**: ruff check with strict rules
- **Types**: Full mypy strict mode, no implicit Any
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Imports**: isort-compatible ordering via ruff
- **Docstrings**: Google style for all public APIs

## Testing

- Run tests: `uv run pytest`
- Coverage: `uv run pytest --cov=src/skills_mcp`
- Test files: `tests/` mirror `src/` structure
- Naming: `test_<function>_<scenario>_<expected_outcome>`

## Security Guidelines

- Never commit secrets or API keys
- Validate all skill names against spec regex
- Sanitize file paths to prevent traversal attacks
- Use HTTPS for remote skill fetching (when implemented)

## Common Commands

- `uv sync` - Install dependencies
- `uv sync --all-extras` - Install with dev and docs deps
- `uv run pytest` - Run tests
- `uv run ruff check .` - Lint code
- `uv run ruff format .` - Format code
- `uv run mypy src/` - Type check
- `uv run mkdocs serve` - Preview documentation

## Git Workflow

- Never use `git add -A`
- Branch naming: `feature/<description>` or `fix/<description>`
- Commits: Use conventional commits format
- Always run tests before committing

## References

- Agent Skills Spec: https://agentskills.io/specification
- MCP Spec: https://modelcontextprotocol.io/specification/2025-11-25/basic
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
