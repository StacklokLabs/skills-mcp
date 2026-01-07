# Skills MCP Server

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Serve [Agent Skills](https://agentskills.io/specification) over MCP with centralized hosting and token-efficient progressive disclosure.

## Why This?

Agent Skills typically live as files in repositories (`.claude/skills/`, plugins, etc.). This server lets you:

- **Host skills centrally** - Serve skills over HTTP to any MCP client without requiring local files
- **Minimize token usage** - Progressive disclosure loads only what agents need, when they need it
- **Isolate sessions** - Each client connection maintains its own expansion state

## Progressive Disclosure

Skills load in three tiers to optimize context usage:

```
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: METADATA (~100 tokens/skill)                       │
│  Agent sees: skill names and descriptions                   │
└─────────────────────────────────────────────────────────────┘
                          ↓ Agent reads a skill
┌─────────────────────────────────────────────────────────────┐
│  TIER 2: INSTRUCTIONS (<5000 tokens)                        │
│  Agent gets: full SKILL.md body, sub-resources now visible  │
└─────────────────────────────────────────────────────────────┘
                          ↓ Agent needs a resource
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: RESOURCES (on-demand)                              │
│  Agent loads: scripts, references, assets as needed         │
└─────────────────────────────────────────────────────────────┘
```

**Example:** Initially 2 resources visible. After reading a skill, sub-resources appear:

```
Before:                          After reading skill:
- skills://data-analysis         - skills://data-analysis
- skills://code-review           - skills://data-analysis/scripts/analyze.py
                                 - skills://data-analysis/references/GUIDE.md
                                 - skills://code-review
```

## Quick Start

```bash
export SKILLS_MCP_PATHS="/path/to/skills"
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

See [docs/architecture/mcp-server-design.md](docs/architecture/mcp-server-design.md) for technical details.

## License

Apache License 2.0

## Links

- [Agent Skills Spec](https://agentskills.io/specification)
- [MCP Spec](https://modelcontextprotocol.io/specification/2025-11-25/basic)
