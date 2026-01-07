# Skills MCP Server

[![Python Version](https://img.shields.io/pypi/pyversions/skills-mcp.svg)](https://pypi.org/project/skills-mcp/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

MCP server implementing the [Agent Skills specification](https://agentskills.io/specification).

## Overview

Skills MCP Server enables AI agents to discover, validate, and execute skills via the
[Model Context Protocol](https://modelcontextprotocol.io/). It provides a bridge between
the Agent Skills ecosystem and MCP-compatible AI clients like Claude.

## Installation

```bash
# With uv (recommended)
uv add skills-mcp

# With pip
pip install skills-mcp
```

## Quick Start

```bash
# Start the server
skills-mcp serve --port 8080
```

Connect from Claude Desktop by adding to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "skills-mcp": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Features

- **Skill Discovery**: Find and list available skills from local directories
- **Validation**: Validate skill definitions against the Agent Skills specification
- **Execution**: Safely execute skill scripts in a sandboxed environment
- **MCP Integration**: Full MCP protocol support with streamable HTTP transport

## Documentation

Full documentation is available at [stacklok.github.io/skills-mcp](https://stacklok.github.io/skills-mcp).

- [Installation Guide](https://stacklok.github.io/skills-mcp/getting-started/installation/)
- [Quick Start](https://stacklok.github.io/skills-mcp/getting-started/quick-start/)
- [Architecture](https://stacklok.github.io/skills-mcp/architecture/overview/)
- [Contributing](https://stacklok.github.io/skills-mcp/development/contributing/)

## Development

```bash
# Clone the repository
git clone https://github.com/stacklok/skills-mcp.git
cd skills-mcp

# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uv run mypy src/
```

## Contributing

Contributions are welcome! Please see our [Contributing Guide](https://stacklok.github.io/skills-mcp/development/contributing/) for details.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Links

- [Agent Skills Specification](https://agentskills.io/specification)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
