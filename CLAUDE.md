# Skills MCP Server

## Project Overview

Python MCP server implementing the Agent Skills specification (agentskills.io).
Enables AI agents to discover, validate, and execute skills via MCP protocol.

## Technology Stack

- **Language**: Python 3.14 (MCP SDK requires >=3.10)
- **Package Manager**: uv
- **MCP SDK**: mcp[cli] (python-sdk)
- **Validation**: Pydantic v2
- **HTTP Client**: httpx
- **Transport**: Streamable HTTP

## Architecture (DDD)

```
src/skills_mcp/
├── domain/           # Core business logic (no external deps)
│   ├── models/       # Domain entities (Skill, Manifest, etc.)
│   ├── services/     # Domain services
│   └── exceptions/   # Domain-specific exceptions
├── application/      # Use cases and orchestration
│   ├── commands/     # Command handlers
│   ├── queries/      # Query handlers
│   └── dto/          # Data transfer objects
├── infrastructure/   # External concerns
│   ├── mcp/          # MCP server implementation
│   ├── persistence/  # Storage adapters
│   └── http/         # HTTP clients
└── interfaces/       # Entry points
    └── cli/          # CLI commands
```

### Layer Dependencies

- **Domain**: Pure Python, NO external dependencies. MUST NOT import from other layers.
- **Application**: MAY import from domain only.
- **Infrastructure**: MAY import from domain and application.
- **Interfaces**: MAY import from all layers.

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
- Validate all external skill content before execution
- Sandbox script execution
- Use HTTPS for all remote skill fetching
- Validate skill signatures when available
- Sanitize file paths to prevent traversal attacks

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
