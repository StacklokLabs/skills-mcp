# Configuration

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SKILLS_MCP_PORT` | Server port | `8080` |
| `SKILLS_MCP_HOST` | Server host | `0.0.0.0` |
| `SKILLS_MCP_LOG_LEVEL` | Logging level | `INFO` |
| `SKILLS_MCP_SKILLS_DIR` | Default skills directory | `./skills` |

## Configuration File

Create `skills-mcp.toml` in your project root:

```toml
[server]
port = 8080
host = "0.0.0.0"
log_level = "INFO"

[skills]
# Default directory to search for skills
directory = "./skills"

# Allow remote skill fetching
allow_remote = false

# Trusted remote sources (if allow_remote = true)
trusted_sources = [
    "https://skills.example.com",
]

[security]
# Enable script sandboxing
sandbox_scripts = true

# Maximum script execution time (seconds)
script_timeout = 30

# Maximum response size (bytes)
max_response_size = 1048576  # 1MB
```

## CLI Options

```bash
skills-mcp serve --help

Options:
  --port INTEGER          Server port [default: 8080]
  --host TEXT             Server host [default: 0.0.0.0]
  --config PATH           Path to config file
  --log-level TEXT        Logging level [default: INFO]
  --skills-dir PATH       Skills directory
```

## Logging

Configure logging with the `SKILLS_MCP_LOG_LEVEL` environment variable:

- `DEBUG`: Detailed debugging information
- `INFO`: General operational information
- `WARNING`: Warning messages
- `ERROR`: Error messages only

```bash
SKILLS_MCP_LOG_LEVEL=DEBUG skills-mcp serve
```
