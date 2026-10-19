# Skills MCP Server

Serve [Agent Skills](https://agentskills.io/specification) over MCP with centralized hosting and token-efficient progressive disclosure.

## Why this

Agent Skills typically live as files in repositories (`.claude/skills/`, plugins, and so on). This server lets you:

- **Host skills centrally**: serve skills over HTTP to any MCP client, from local directories, git repositories, or OCI registries
- **Minimize token usage**: three-tier progressive disclosure loads only what agents need, when they need it
- **Isolate sessions**: each client connection keeps its own expansion state

## Quick start

```bash
export SKILLS_MCP_PATHS="/path/to/skills"
uv run skills-mcp
```

Connect any Streamable HTTP MCP client (Claude Code, Claude Desktop, Roo Code, Cline, Continue) to `http://localhost:8080/mcp`. See the [quickstart](docs/getting-started/quickstart.md) for installation options (including Docker) and [connect your client](docs/getting-started/clients.md) for per-client setup.

## How agents consume skills

The same skills are exposed through an accepted SEP-2640 snapshot for extension-aware clients (`skills/list`, `skills/get`, and canonical byte-faithful `skill://<path>/SKILL.md` resources) and through the existing legacy surfaces: progressive `skills://` resources, tools (`list_skills`, `get_skill`, `get_skill_resource`, `validate_skill`), and prompts. Names are display metadata; source-relative paths are canonical identity, so duplicate names can coexist. Canonical reads preserve exact bytes and never inject token headers.

Details: [MCP surface reference](docs/reference/mcp-surface.md), [getting agents to use your skills](docs/guides/agent-uptake.md), and the [SEP-2640 snapshot notes](docs/reference/mcp-surface.md#sep-2640-skills-extension). This is alignment with accepted PR head `d6b31a03504c15677d49b922b6b6ace0ef65728d`, not a claim of final conformance; `directoryRead` remains deferred.

## Skill sources

A `skills.yaml` file can pull skills from three kinds of source, in any combination (local takes precedence over git, then OCI, only on exact canonical-path collisions):

- **Local filesystem** (`local:`): directories scanned for `SKILL.md`
- **Git repositories** (`git:`): cloned over HTTPS from `git://host/owner/repo[@ref][#subdir]` references
- **OCI registries** (`oci:`): skill artifacts pulled from a registry

See [skill sources](docs/guides/skill-sources.md) for walkthroughs and the [configuration reference](docs/reference/configuration.md) for the full schema.

## Documentation

Full documentation lives at [stacklok.github.io/skills-mcp](https://stacklok.github.io/skills-mcp) (source under [docs/](docs/index.md)):

- [Quickstart](docs/getting-started/quickstart.md) and [client setup](docs/getting-started/clients.md)
- [Configuration reference](docs/reference/configuration.md)
- [Architecture](docs/explanation/architecture.md)
- [How agents discover served skills](docs/explanation/agent-discovery.md)

## Development

```bash
git clone https://github.com/stacklok/skills-mcp.git
cd skills-mcp
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy src/
```

## License

Proprietary. © Stacklok, Inc. All rights reserved.

## Links

- [Agent Skills spec](https://agentskills.io/specification)
- [MCP spec](https://modelcontextprotocol.io/specification/2025-11-25/basic)
