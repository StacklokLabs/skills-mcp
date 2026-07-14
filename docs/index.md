# Skills MCP Server

MCP server implementing the [Agent Skills specification](https://agentskills.io/specification).

## How It Works

Skills are exposed through three complementary MCP surfaces so any client can consume them:

- **Resources** (`skills://` URIs) - progressive disclosure for resource-aware clients.
- **Tools** (`list_skills`, `get_skill`, `get_skill_resource`, `validate_skill`) - the same tiers for tool-calling agents.
- **Prompts** - each skill as an MCP prompt, which clients like Continue turn into slash commands.

All three follow the same **progressive disclosure** tiers:

| Tier | Content | When Loaded |
|------|---------|-------------|
| 1. Metadata | Name + description (~100 tokens/skill) | On `resources/list` / `list_skills` |
| 2. Instructions | SKILL.md body (<5000 tokens) | When skill is read (`get_skill`) |
| 3. Resources | Scripts, references, assets | On demand after Tier 2 |

When an agent reads a skill via the resources surface, the server:
1. Returns the full SKILL.md body
2. Marks the skill as "expanded" for that session (an MCP connection, identified by its `mcp-session-id`)
3. Sends `resources/list_changed` notification
4. Subsequent `resources/list` includes sub-resources for expanded skills

Sessionless requests (no `mcp-session-id`) still return skill bodies but skip expansion tracking and the notification.

The server also advertises MCP **instructions** pointing clients at the `list_skills` → `get_skill` → `get_skill_resource` workflow, so tool-calling agents discover the intended flow at initialization.

## Quick Start

```bash
export SKILLS_MCP_PATHS="/path/to/skills"
uv run skills-mcp
```

See [Architecture](architecture/mcp-server-design.md) for design details.

## SEP-2640 Alignment

The server tracks the stable parts of the SEP-2640 skills extension: resource
annotations (`audience`, `priority`, `lastModified`), a bare-URI read guarantee,
and an experimental capability declaration on `initialize`. Still-churning parts
(the `skill://` scheme, index/discovery, content digests, directory reads) are
deliberately deferred. See
[SEP-2640 Alignment](architecture/mcp-server-design.md#sep-2640-alignment).

## Links

- [Agent Skills Spec](https://agentskills.io/specification)
- [MCP Spec](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [GitHub](https://github.com/stacklok/skills-mcp)
