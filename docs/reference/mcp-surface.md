# MCP surface

The server exposes skills over MCP via Streamable HTTP at `/mcp`. The same skills are available through three complementary surfaces (tools, resources, and prompts), so a client can use whichever mechanism it supports. All three follow the same three-tier progressive disclosure model; see the [architecture](../explanation/architecture.md) for the rationale.

## Tools

| Tool | Tier | Purpose |
|------|------|---------|
| `list_skills` | 1 | Catalog of skill names, descriptions, and resource counts |
| `get_skill` | 2 | Full SKILL.md body plus resource listing; marks the skill expanded |
| `get_skill_resource` | 3 | One resource file, addressed as `type/filename` |
| `validate_skill` | - | Validate a skill directory against the spec (opt-in) |

All tools declare `readOnlyHint=True`, `idempotentHint=True`, and `openWorldHint=False` annotations, which clients use to relax permission handling and parallelize calls. Every tool description states when to call it and shows one example call.

### `list_skills`

Returns the Tier 1 catalog as JSON: each skill's name, description, and resource *counts* (scripts/references/assets), not the resource names. Individual resource names are revealed at Tier 2 via `get_skill`, which keeps the catalog cheap.

The tool's own description embeds the current skill catalog, so a model can see what exists without a separate call. The embedded list is built against a byte budget of roughly 1.9 KB (clients such as Claude Code truncate tool descriptions at about 2 KB): up to 10 full name+description entries, then a names-only "Also available: ..." overflow line, then a bare count.

The tool also carries the `anthropic/alwaysLoad` meta flag, Claude Code's per-tool exemption from tool-search deferral, so the catalog and trigger text stay in context from the first turn. Only this one discovery tool is always loaded; the rest stay deferred. Both behaviors exist because of measured agent behavior; see [how agents discover served skills](../explanation/agent-discovery.md).

### `get_skill`

Tier 2 activation: returns a skill's full instructions (the SKILL.md body) and its resource listing, and marks the skill expanded for the session (see [sessions](#sessions)).

### `get_skill_resource`

Tier 3: returns a specific resource file, addressed as `type/filename` (for example `scripts/analyze.py`). Returns the raw file text with no token-count header (headers apply to the resources surface only; see [surface behavior notes](#surface-behavior-notes)).

### `validate_skill`

Validates a skill directory against the Agent Skills spec. Disabled by default: unless the server is started with an allow-list of validation paths (the repeatable `--validation-path` CLI flag or the `server.validation_paths` config option; CLI takes precedence), it returns a "validation is disabled" message. A path outside the allow-list is refused. See [enabling skill validation](../guides/validation.md).

## Resources

### URI scheme

```
skills://{name}                          → Skill instructions (SKILL.md body)
skills://{name}/scripts/{script}         → Script content
skills://{name}/references/{ref}         → Reference document
skills://{name}/assets/{asset}           → Asset content
```

### Dynamic resource list

The initial `resources/list` returns only skill-level resources. Reading a skill triggers expansion:

1. Agent calls `resources/read("skills://data-analysis")`
2. Server returns the full SKILL.md body
3. Server marks the skill as expanded in session state
4. Server sends a `notifications/resources/list_changed` notification
5. A subsequent `resources/list` includes sub-resources for expanded skills

**Initial state** (before any skill is read):

```json
[
  {"uri": "skills://data-analysis", "name": "data-analysis", "description": "..."},
  {"uri": "skills://code-review", "name": "code-review", "description": "..."}
]
```

**After reading `skills://data-analysis`**:

```json
[
  {"uri": "skills://data-analysis", "name": "data-analysis", "description": "..."},
  {"uri": "skills://data-analysis/scripts/analyze.py", "name": "analyze.py", "description": "Analysis script (450 tokens)"},
  {"uri": "skills://data-analysis/references/GUIDE.md", "name": "GUIDE.md", "description": "Usage guide (1200 tokens)"},
  {"uri": "skills://code-review", "name": "code-review", "description": "..."}
]
```

### Bare-URI reads

A resource can be read directly by URI without a prior `resources/list` or skill expansion, so a client holding a known URI is never gated on discovery. This is a guarantee (pinned by tests) adopted from SEP-2640.

### Resource annotations

Every listed resource carries SEP-2640-style annotations:

- `audience`: `["assistant"]`
- `priority`: `0.8` for skill-level resources, `0.3` for on-demand sub-resources
- `lastModified`: an ISO 8601 timestamp derived from file mtime, omitted when unknown

### Token-count headers

`resources/read` prepends a token-count header to text content: `<!-- tokens: N -->` for Markdown and plain text, `# tokens: N` for Python. This applies to the resources surface only.

## Sessions

Session identity comes from the `mcp-session-id` header, which the SDK assigns on `initialize`. Expansion state (which skills have visible sub-resources) is tracked per session. Requests without a session ID are treated as sessionless: they still return skill bodies and resources but skip expansion tracking and the `resources/list_changed` notification. Session lifecycle details are in the [architecture](../explanation/architecture.md#session-lifecycle).

## Prompts

Each skill is also exposed as an MCP prompt (one per skill). `prompts/get` returns the SKILL.md body as a user message, appending any `args` and a resource listing, mimicking how Claude Code injects skill content via prompt expansion. Clients like Continue convert MCP prompts into slash commands (`/skill-name`); interactive Claude Code exposes them as `/mcp__<server-name>__<skill-name>`.

## Server instructions

The server declares MCP instructions that direct clients to the `list_skills` → `get_skill` → `get_skill_resource` workflow. They are written as imperative trigger text rather than a capability statement: they name concrete trigger tasks (commit messages, release notes, PR descriptions), tell the model to check the catalog "even if you already know how to do the task", and explicitly state that these skills are separate from any built-in skills feature of the client. That last point matters in practice; see [how agents discover served skills](../explanation/agent-discovery.md#why-agents-ignored-the-server).

## Capabilities

The server declares these capabilities on `initialize`:

```json
{
  "capabilities": {
    "resources": {
      "listChanged": true
    },
    "experimental": {
      "io.modelcontextprotocol/skills": {}
    }
  }
}
```

`resources.listChanged` is `true` because the server emits a `resources/list_changed` notification the first time a skill is expanded in a session. The `experimental` map declares the SEP-2640 skills extension.

## SEP-2640 alignment

[SEP-2640](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2640) proposes a first-class skills extension for MCP. This server tracks the parts of that proposal that have reached stable consensus and defers the parts still churning upstream.

**Adopted now:**

- **Resource annotations**: `audience`, `priority`, and `lastModified` as described [above](#resource-annotations)
- **Bare-URI reads**: a known resource URI can be read with no prior listing or expansion
- **Experimental capability declaration**: `experimental["io.modelcontextprotocol/skills"]` on `initialize`

**Deliberately deferred** (pending upstream stabilization):

- The dedicated `skill://` URI scheme (this server keeps its `skills://` scheme)
- Index / discovery (`index.json`, skills-list) mechanisms
- Content digests on resources (their consumer is the deferred discovery layer)
- Directory (collection) reads

## Surface behavior notes

Two behaviors differ between the resources and tools surfaces and are intentional:

- **Token-count headers apply to the resources surface only.** The `get_skill_resource` tool returns the raw file text with no header.
- **`list_skills` is a Tier 1 catalog.** It returns resource counts, not resource names; names are revealed at Tier 2 via `get_skill`.
