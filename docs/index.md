# Skills MCP Server

MCP server implementing the [Agent Skills specification](https://agentskills.io/specification).

## Overview

Skills MCP Server enables AI agents to discover, validate, and execute skills via the
[Model Context Protocol](https://modelcontextprotocol.io/). It provides a bridge between
the Agent Skills ecosystem and MCP-compatible AI clients like Claude.

## Features

- **Skill Discovery**: Find and list available skills from local directories or remote sources
- **Validation**: Validate skill definitions against the Agent Skills specification
- **Execution**: Safely execute skill scripts in a sandboxed environment
- **MCP Integration**: Full MCP protocol support with streamable HTTP transport

## Quick Start

```bash
# Install with uv
uv add skills-mcp

# Run the server
skills-mcp serve --port 8080
```

See the [Quick Start Guide](getting-started/quick-start.md) for detailed instructions.

## Architecture

This project follows Domain-Driven Design principles with a layered architecture:

- **Domain Layer**: Core business logic and entities
- **Application Layer**: Use cases and orchestration
- **Infrastructure Layer**: MCP server, persistence, HTTP clients
- **Interfaces Layer**: CLI and entry points

Learn more in the [Architecture Overview](architecture/overview.md).

## Links

- [Agent Skills Specification](https://agentskills.io/specification)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [GitHub Repository](https://github.com/stacklok/skills-mcp)
