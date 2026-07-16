# Connect your client

The server speaks MCP over Streamable HTTP at `http://<host>:<port>/mcp` (by default `http://localhost:8080/mcp`). If you don't have a server running yet, the [quickstart](quickstart.md) gets you one; host, port, and skill sources are covered in the [configuration reference](../reference/configuration.md). Any MCP client that supports Streamable HTTP can connect. This page covers the clients the server is tested or designed against; for how each surface behaves once connected, see the [MCP surface reference](../reference/mcp-surface.md).

## Claude Code

Add the server from the command line:

```bash
claude mcp add --transport http skills http://localhost:8080/mcp
```

Or declare it in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "skills": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

Notes for Claude Code:

- No extra configuration is needed for agents to pick up served skills on natural prompts. The `list_skills` tool stays loaded in context via the `anthropic/alwaysLoad` flag; see [getting agents to use your skills](../guides/agent-uptake.md).
- In interactive sessions, each served skill is also available as a slash command: `/mcp__<server-name>__<skill-name>`. This path does not work in print mode (`claude -p` rejects MCP prompt commands).

## Claude Desktop

Add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "skills-mcp": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Cline and Roo Code

Both are resource-aware clients: besides the tools, they can browse skills directly as `skills://` resources with progressive disclosure (sub-resources appear after a skill is read). Add the server in the client's MCP settings as a remote (Streamable HTTP) server pointing at `http://localhost:8080/mcp`.

## Continue

Continue turns MCP prompts into slash commands, so each served skill becomes `/skill-name`. Add the server in Continue's MCP configuration as a Streamable HTTP server pointing at `http://localhost:8080/mcp`.

## Other clients

Any client that can call MCP tools gets the full three-tier workflow (`list_skills`, `get_skill`, `get_skill_resource`). The server's instructions, sent at initialization, point agents at that workflow. Client behavior around tool-description loading differs, and only Claude Code has been measured for unprompted uptake; see [how agents discover served skills](../explanation/agent-discovery.md).
