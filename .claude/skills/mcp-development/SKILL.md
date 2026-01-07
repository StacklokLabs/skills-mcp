---
name: mcp-development
description: Guide for developing MCP servers with Python SDK. Use when implementing MCP tools, resources, or prompts.
---

# MCP Development Guide

## Quick Reference

### Creating Tools

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skills-mcp")

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description for LLM."""
    return f"Result: {param}"
```

### Creating Resources

```python
@mcp.resource("skills://{skill_name}")
async def get_skill(skill_name: str) -> str:
    """Return skill content."""
    return skill_content
```

### Creating Prompts

```python
@mcp.prompt()
def review_skill(skill_name: str) -> str:
    """Create a prompt to review a skill."""
    return f"Please review the skill: {skill_name}"
```

### Running Server

```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

## Context Object

Use `Context` for logging and progress:

```python
from mcp.server.fastmcp import Context

@mcp.tool()
async def long_task(ctx: Context) -> str:
    await ctx.info("Starting task...")
    await ctx.report_progress(50, 100)
    return "Done"
```

## Project-Specific Patterns

See @src/skills_mcp/infrastructure/mcp/ for implementation examples.
