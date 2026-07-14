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

## How Agents Consume Skills

The same skills are exposed through three complementary MCP surfaces, so a client can use whichever mechanism it supports:

- **Resources** (`skills://` URIs) - Progressive disclosure for resource-aware clients (e.g. Roo Code, Cline). `skills://{name}` returns a skill's instructions; `skills://{name}/{type}/{file}` returns a sub-resource (scripts, references, assets). Sub-resources appear in the resource list once the skill has been read in that session, but a client that already knows a sub-resource URI can read it directly at any time.
- **Tools** - Mirror the `Skill` tool pattern used by tool-calling agents (Claude Code, Roo Code, Cline, Continue):
  - `list_skills` - Tier 1 catalog (names, descriptions, resource counts). The available skills are also embedded directly in the tool's description, so a model can see what exists without a separate call.
  - `get_skill` - Tier 2 activation: load a skill's full instructions and its resource listing.
  - `get_skill_resource` - Tier 3: load a specific resource file (`type/filename`, e.g. `scripts/analyze.py`).
  - `validate_skill` - Validate a skill directory against the spec. Disabled by default; enable it by allow-listing directories with the repeatable `--validation-path` CLI flag or the `server.validation_paths` config option. A path outside the allow-list is refused, and with no paths configured the tool answers with a "validation is disabled" message.
- **Prompts** - Each skill is also exposed as an MCP prompt. Clients like Continue turn MCP prompts into slash commands, giving users `/skill-name` invocation.

The server also ships MCP **instructions** that point clients at the `list_skills` → `get_skill` → `get_skill_resource` workflow.

### SEP-2640 alignment

The server adopts the stable parts of the [SEP-2640](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2640) skills extension: resource annotations (`audience`, `priority`, and an ISO 8601 `lastModified`), a bare-URI read guarantee (a known resource URI can be read without a prior `resources/list` or expansion), and an experimental capability declaration (`experimental["io.modelcontextprotocol/skills"]`) on `initialize`. Still-churning parts — the `skill://` URI scheme, index/discovery, content digests, and directory reads — are deliberately deferred. See the [architecture doc](docs/architecture/mcp-server-design.md#sep-2640-alignment) for details.

## Quick Start

```bash
export SKILLS_MCP_PATHS="/path/to/skills"
uv run skills-mcp
```

Connect any Streamable-HTTP MCP client (Claude Code, Roo Code, Cline, Continue) to `http://localhost:8080/mcp`. For example, from Claude Desktop (`claude_desktop_config.json`):

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

### Skill Sources

A `skills.yaml` file can pull skills from three kinds of source, in any
combination (local takes precedence over git, then oci, on name collisions):

- **Local filesystem** (`local:`) — directories scanned for `SKILL.md`.
- **Git repositories** (`git:`) — cloned over HTTPS using
  `git://host/owner/repo[@ref][#subdir]` references (tag, branch, or pinned
  commit); HTTPS-with-token auth only, no SSH, no submodules.
- **OCI registries** (`oci:`) — skill artifacts pulled from a registry.

See [docs/configuration.md](docs/configuration.md) for the full schema.

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
