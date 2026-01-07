# Installation

## Requirements

- Python 3.10 or later (3.14 recommended)
- [uv](https://docs.astral.sh/uv/) package manager (recommended)

## Install with uv

```bash
# Install the package
uv add skills-mcp

# Or install with all extras
uv add "skills-mcp[dev,docs]"
```

## Install with pip

```bash
pip install skills-mcp
```

## Development Installation

Clone the repository and install in development mode:

```bash
git clone https://github.com/stacklok/skills-mcp.git
cd skills-mcp

# Install with uv (recommended)
uv sync --all-extras

# Or with pip
pip install -e ".[dev,docs]"
```

## Verify Installation

```bash
# Check the CLI is available
skills-mcp --version

# Run the test suite
uv run pytest
```

## Next Steps

- [Quick Start Guide](quick-start.md) - Get up and running in 5 minutes
- [Configuration](configuration.md) - Configure the server for your needs
