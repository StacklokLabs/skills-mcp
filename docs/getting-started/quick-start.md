# Quick Start

Get up and running with Skills MCP Server in 5 minutes.

## Start the Server

```bash
# Start with default settings (streamable HTTP on port 8080)
skills-mcp serve

# Or specify a custom port
skills-mcp serve --port 3000
```

## Connect from Claude Desktop

Add to your Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "skills-mcp": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Available Tools

Once connected, the following MCP tools are available:

### `discover_skills`

Find skills in a directory:

```
discover_skills(path="/path/to/skills")
```

### `validate_skill`

Validate a skill definition:

```
validate_skill(path="/path/to/skill")
```

### `get_skill`

Get full skill content:

```
get_skill(name="my-skill")
```

## Example Workflow

1. **Discover available skills**:
   ```
   "What skills are available in ./my-skills?"
   ```

2. **Validate a skill**:
   ```
   "Validate the skill at ./my-skills/data-analysis"
   ```

3. **Use a skill**:
   ```
   "Use the data-analysis skill to process this CSV"
   ```

## Next Steps

- [Configuration](configuration.md) - Customize server behavior
- [Architecture Overview](../architecture/overview.md) - Understand how it works
