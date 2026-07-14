# MCP Server Design: Progressive Disclosure Architecture

This document describes the architecture for exposing Agent Skills via the Model Context Protocol (MCP) with token-efficient progressive disclosure.

## Design Goals

1. **Token Efficiency**: Minimize context usage through progressive disclosure
2. **Multi-Tenancy**: Support concurrent agent sessions with isolated state
3. **Extensibility**: Pluggable storage backends (filesystem, Git, OCI, database)
4. **Spec Compliance**: Follow both Agent Skills and MCP specifications

## Progressive Disclosure Model

Skills are exposed in three tiers, each loaded only when needed:

| Tier | Content | Token Cost | MCP Mechanism |
|------|---------|------------|---------------|
| 1. Metadata | Name + description | ~100 tokens/skill | `resources/list` |
| 2. Instructions | SKILL.md body | <5000 tokens | `resources/read` |
| 3. Resources | Scripts, references, assets | Varies | `resources/read` |

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 1: METADATA (initial resources/list)                         │
│  resources/list returns ONLY skill-level resources:                 │
│  [skills://data-analysis, skills://code-review, skills://pdf-proc] │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ Agent reads a skill
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 2: INSTRUCTIONS (resources/read triggers expansion)          │
│  1. Agent calls: resources/read("skills://data-analysis")          │
│  2. Server returns: Full SKILL.md body                              │
│  3. Server marks skill as "expanded" in session state              │
│  4. Server sends: notifications/resources/list_changed              │
│  5. Agent calls: resources/list (in response to notification)      │
│  6. Server returns: NOW includes sub-resources for expanded skills │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ Agent needs specific resource
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 3: RESOURCES (direct read)                                   │
│  Agent calls: resources/read("skills://data-analysis/scripts/x.py")│
│  Server returns: Script content with token count header            │
└─────────────────────────────────────────────────────────────────────┘
```

## MCP Surfaces: Resources, Tools, and Prompts

The tier model above is exposed through three complementary MCP surfaces. Different AI coding agents load skills in different ways, so the server offers all three rather than betting on one:

- **Resources** (`skills://` URIs) - the progressive-disclosure model described above, for resource-aware clients (Roo Code, Cline).
- **Tools** - mirror the `Skill` tool pattern used natively by Claude Code, Roo Code, Cline, and Continue, giving universal tool-calling compatibility:
  - `list_skills` - Tier 1 catalog. The tool's own description embeds the current `<available_skills>` list (name + short description), matching Claude Code's pattern of surfacing the catalog in the description so a model knows what exists without a separate call.
  - `get_skill` - Tier 2 activation; also marks the skill expanded for the session.
  - `get_skill_resource` - Tier 3 resource load, addressed as `type/filename`.
  - `validate_skill` - validates a skill directory against the spec. It is gated: unless the server is given an explicit allow-list of validation paths it returns a "validation is disabled" message. The entry point wires this allow-list from the repeatable `--validation-path` CLI flag or the `server.validation_paths` config option (CLI takes precedence), so the tool is off by default and opt-in.
- **Prompts** - each skill is exposed as an MCP prompt (one per skill). Clients like Continue convert MCP prompts into slash commands, so users get `/skill-name` invocation. `prompts/get` returns the SKILL.md body as a user message, appending any `args` and a resource listing, mimicking how Claude Code injects skill content via prompt expansion.

The server also declares MCP **instructions** that direct clients to the `list_skills` → `get_skill` → `get_skill_resource` workflow.

### Surface behavior notes

Two behaviors differ between the resources and tools surfaces and are intentional:

- **Token-count headers apply to the resources surface only.** `resources/read` prepends a token-count header to text content (`<!-- tokens: N -->` for Markdown/plain text, `# tokens: N` for Python). The `get_skill_resource` tool returns the raw file text with no such header.
- **`list_skills` is a Tier 1 catalog.** It returns each skill's name, description, and resource *counts* (scripts/references/assets), not the resource names. Individual resource names are revealed at Tier 2 via `get_skill`. This keeps the catalog cheap.

## Multi-Tenant Session Architecture

Each MCP connection maintains isolated session state:

```
┌─────────────────┐     ┌─────────────────┐
│  Agent A        │     │  Agent B        │
│  (Session 1)    │     │  (Session 2)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────────┐
│              MCP Server                      │
│  ┌───────────────┐   ┌───────────────┐      │
│  │ Session 1     │   │ Session 2     │      │
│  │ expanded: [   │   │ expanded: [   │      │
│  │   data-anlys  │   │   code-review │      │
│  │ ]             │   │   pdf-proc    │      │
│  │               │   │ ]             │      │
│  └───────────────┘   └───────────────┘      │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │  Shared Skill Repository (read-only) │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Session State

```python
@dataclass
class SessionState:
    session_id: str
    expanded_skills: set[str]        # Skills with visible sub-resources
    created_at: datetime
    last_accessed: datetime          # Bumped on access; drives expiry
```

### Session Lifecycle

- **Session identity**: the session ID comes from the `mcp-session-id` header, which the SDK assigns on `initialize`. Resolution **fails closed** — a request with no session ID is treated as *sessionless* rather than falling back to a shared session, so expanded-skill state cannot bleed across unrelated requests. Sessionless requests still return skill bodies and resources, but skip expansion tracking and the `resources/list_changed` notification.
- **Expiry**: sessions expire 24 hours after their last access (`last_accessed`).
- **Cleanup**: a periodic background task, started in the ASGI lifespan, sweeps expired sessions hourly so long-running servers do not accumulate stale state. The task is cancelled on shutdown.

### Skill Name Collisions

When a `CompositeSkillRepository` combines sources, the first source to register a name wins. A shadowed skill is not dropped silently: each unique collision is logged once at `WARNING` with provenance (which repository shadows which), so operators can see and resolve overlapping skill names.

## URI Scheme

```
skills://{name}                          → Skill instructions (SKILL.md body)
skills://{name}/scripts/{script}         → Script content
skills://{name}/references/{ref}         → Reference document
skills://{name}/assets/{asset}           → Asset content
```

### Dynamic Resource List

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

## Pluggable Repository Layer

Repository interface is defined in the domain layer, with implementations in infrastructure:

```
SkillRepository (Protocol - Domain Layer)
    │
    ├── LocalSkillRepository      ← Filesystem (implemented)
    ├── OCISkillRepository        ← OCI registries (implemented)
    ├── CompositeSkillRepository  ← Combines multiple sources (implemented)
    ├── GitSkillRepository        ← Git repos (future)
    └── DatabaseSkillRepository   ← SQL/NoSQL (future)
```

### Repository Interface

```python
class SkillRepository(Protocol):
    async def list_all(self) -> list[Skill]: ...
    async def find_by_name(self, name: SkillName) -> Skill | None: ...
    async def get_resource(self, skill: SkillName, resource_type: str, name: str) -> bytes: ...
    async def refresh(self) -> None: ...
```

### Caching Strategy

```
┌─────────────────────────────────────────┐
│         CachingRepositoryDecorator       │
│  ┌─────────────────────────────────┐    │
│  │    LRU Cache (in-memory)        │    │
│  └─────────────────────────────────┘    │
│                  │                       │
│                  ▼                       │
│  ┌─────────────────────────────────┐    │
│  │    Inner SkillRepository        │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Token Estimation

Hybrid approach for token counting:

```python
def estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // 4  # ~4 chars per token
```

## MCP Capabilities

Server declares these capabilities:

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

`resources.listChanged` is `true` because the server emits a
`resources/list_changed` notification the first time a skill is expanded in a
session. The `experimental` map declares the SEP-2640 skills extension (see
[SEP-2640 Alignment](#sep-2640-alignment)).

## Security Considerations

1. **Path Traversal Prevention**: All file paths validated against skill root
2. **No Script Execution**: Server exposes content only; agents run scripts themselves
3. **Session Isolation**: Each connection has isolated state
4. **Input Validation**: All skill names validated against spec regex

## Configuration

Environment variables:

```bash
SKILLS_MCP_PATHS="/path/to/skills:/another/path"  # Colon-separated (required)
SKILLS_MCP_HOST="127.0.0.1"                        # Default host
SKILLS_MCP_PORT="8080"                             # Default port
SKILLS_MCP_LOG_LEVEL="WARNING"                     # Log level
```

## SEP-2640 Alignment

[SEP-2640](https://github.com/modelcontextprotocol/modelcontextprotocol) proposes
a first-class skills extension for MCP. This server tracks the parts of that
proposal that have reached stable consensus and defers the parts still churning
upstream.

**Adopted now:**

- **Resource annotations** — every listed resource carries `audience`
  (`["assistant"]`), `priority` (`0.8` for skill-level resources, `0.3` for
  on-demand sub-resources), and, when known, an ISO 8601 `lastModified`
  timestamp derived from file mtime.
- **Bare-URI reads** — a resource can be read directly by URI without a prior
  `resources/list` or skill expansion, so a client holding a known URI is never
  gated on discovery.
- **Experimental capability declaration** — the server advertises
  `experimental["io.modelcontextprotocol/skills"]` on `initialize`.

**Deliberately deferred** (pending upstream stabilization):

- The dedicated `skill://` URI scheme (this server keeps its `skills://` scheme).
- Index / discovery (`index.json`, skills-list) mechanisms.
- Content digests on resources — their consumer is the deferred discovery layer.
- Directory (collection) reads.

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
