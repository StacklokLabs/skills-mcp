# Quickstart

Get the server running and serving skills in a few minutes. The package is not published to a package index; you run it from a checkout or as a container.

## Prerequisites

- Python 3.12 or newer and [uv](https://docs.astral.sh/uv/), or
- Docker (or another OCI-compatible runtime)

You also need at least one skill: a directory containing a `SKILL.md` file, per the [Agent Skills specification](https://agentskills.io/specification).

## Run from a checkout

```bash
git clone https://github.com/stacklok/skills-mcp.git
cd skills-mcp
uv sync
export SKILLS_MCP_PATHS="/path/to/skills"
uv run skills-mcp
```

`SKILLS_MCP_PATHS` is a colon-separated list of directories to scan for skills. The server listens on `http://127.0.0.1:8080/mcp` by default.

For anything beyond a single local directory, use a `skills.yaml` config file instead of the environment variable:

```yaml
version: "1"

local:
  paths:
    - ./skills
```

Place it in the working directory (or `~/.config/skills-mcp/skills.yaml`, or pass `--config`) and start the server with no arguments:

```bash
uv run skills-mcp
```

Config files can also pull skills from git repositories and OCI registries; see [skill sources](../guides/skill-sources.md).

## Run with Docker

The repository ships a `Dockerfile`. Build the image, mount your skills, and point `SKILLS_MCP_PATHS` at the mount:

```bash
docker build -t skills-mcp .
docker run --rm -p 8080:8080 \
  -v /path/to/skills:/skills:ro \
  -e SKILLS_MCP_PATHS=/skills \
  skills-mcp
```

The image binds to `0.0.0.0:8080` inside the container. Note that the image does not currently drop root privileges; run it with your container runtime's user remapping (for example `--user`) if that matters in your environment.

## Verify it works

The default log level is `WARNING`, so a healthy startup prints nothing. To see the startup line, raise the log level:

```bash
SKILLS_MCP_LOG_LEVEL=INFO uv run skills-mcp
```

You should see `Starting skills-mcp server on 127.0.0.1:8080`. Then connect a client (see [connect your client](clients.md)) and ask the agent to call the `list_skills` tool. It should return your skills as a JSON catalog.

## Next steps

- [Connect your client](clients.md): per-client setup for Claude Code, Claude Desktop, Cline, Roo Code, and Continue.
- [Skill sources](../guides/skill-sources.md): serve skills from git repositories and OCI registries.
- [Getting agents to use your skills](../guides/agent-uptake.md): make agents pick up served skills on natural prompts.
- [Configuration reference](../reference/configuration.md): every config key, environment variable, and CLI flag.
