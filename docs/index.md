# Skills MCP Server

MCP server implementing the [Agent Skills specification](https://agentskills.io/specification).

## How It Works

The server exposes Agent Skills as MCP resources with **progressive disclosure**:

| Tier | Content | When Loaded |
|------|---------|-------------|
| 1. Metadata | Name + description (~100 tokens/skill) | On `resources/list` |
| 2. Instructions | SKILL.md body (<5000 tokens) | When skill is read |
| 3. Resources | Scripts, references, assets | On demand after Tier 2 |

When an agent reads a skill, the server:
1. Returns the full SKILL.md body
2. Marks the skill as "expanded" for that session
3. Sends `resources/list_changed` notification
4. Subsequent `resources/list` includes sub-resources for expanded skills

## Quick Start

```bash
export SKILLS_MCP_PATHS="/path/to/skills"
uv run skills-mcp
```

See [Architecture](architecture/mcp-server-design.md) for design details.

## Links

- [Agent Skills Spec](https://agentskills.io/specification)
- [MCP Spec](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [GitHub](https://github.com/stacklok/skills-mcp)
