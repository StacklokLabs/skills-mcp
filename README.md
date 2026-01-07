# Skills MCP Server

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

MCP server implementing the [Agent Skills specification](https://agentskills.io/specification).

## Overview

Exposes Agent Skills as MCP resources with progressive disclosure:
1. **Tier 1 (Metadata)**: Skill names and descriptions visible immediately
2. **Tier 2 (Instructions)**: Full SKILL.md body loaded when skill is accessed
3. **Tier 3 (Resources)**: Scripts, references, assets exposed on demand

## Quick Start

```bash
# Set skill paths (required)
export SKILLS_MCP_PATHS="/path/to/skills:/another/path"

# Run the server
uv run skills-mcp
```

Connect from Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "skills-mcp": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SKILLS_MCP_PATHS` | Colon-separated skill directories | (required) |
| `SKILLS_MCP_HOST` | Server host | `127.0.0.1` |
| `SKILLS_MCP_PORT` | Server port | `8080` |
| `SKILLS_MCP_LOG_LEVEL` | Log level (DEBUG/INFO/WARNING/ERROR) | `WARNING` |

## Development

```bash
git clone https://github.com/stacklok/skills-mcp.git
cd skills-mcp
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy src/
```

## License

Apache License 2.0

## Links

- [Agent Skills Spec](https://agentskills.io/specification)
- [MCP Spec](https://modelcontextprotocol.io/specification/2025-11-25/basic)
