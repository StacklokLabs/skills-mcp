# Skills MCP Server

Serve [Agent Skills](https://agentskills.io/specification) to AI agents over MCP. Skills live on the server (local directories, git repositories, or OCI registries) and load into agent context progressively, in three tiers, so agents only pay for the skills they actually use.

## Start in 60 seconds

```bash
export SKILLS_MCP_PATHS="/path/to/skills"
uv run skills-mcp
```

Connect any Streamable HTTP MCP client to `http://localhost:8080/mcp`. That's it: agents on that connection can now discover and follow your skills.

## Find what you need

- **New here?** Follow the [quickstart](getting-started/quickstart.md), then [connect your client](getting-started/clients.md).
- **Serving skills from git or OCI registries?** See [skill sources](guides/skill-sources.md).
- **Agents not picking up your skills?** See [getting agents to use your skills](guides/agent-uptake.md).
- **Want to validate skill directories over MCP?** See [enabling skill validation](guides/validation.md).
- **Looking up a config key, env var, or tool contract?** See the [configuration reference](reference/configuration.md) and the [MCP surface reference](reference/mcp-surface.md).
- **Curious how it works inside?** Read the [architecture](explanation/architecture.md) and [how agents discover served skills](explanation/agent-discovery.md).
- **What changed recently?** See the [changelog](changelog.md).

## Links

- [Agent Skills specification](https://agentskills.io/specification)
- [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [GitHub](https://github.com/stacklok/skills-mcp)
