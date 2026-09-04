# Architecture

This document describes the architecture for exposing Agent Skills via the Model Context Protocol (MCP) with token-efficient progressive disclosure. For the exact tool, resource, and prompt contracts, see the [MCP surface reference](../reference/mcp-surface.md).

## Design goals

1. **Token efficiency**: minimize context usage through progressive disclosure
2. **Multi-tenancy**: support concurrent agent sessions with isolated state
3. **Extensibility**: pluggable storage backends (filesystem, git, OCI)
4. **Standards alignment**: implement the accepted SEP-2640 snapshot without claiming final conformance

## Progressive disclosure model

Skills are exposed in three tiers, each loaded only when needed:

| Tier | Content | Token cost | MCP mechanism |
|------|---------|------------|---------------|
| 1. Metadata | Name + description | ~100 tokens/skill | `resources/list` / `list_skills` |
| 2. Instructions | SKILL.md body | <5000 tokens | `resources/read` / `get_skill` |
| 3. Resources | Scripts, references, assets | Varies | `resources/read` / `get_skill_resource` |

### Flow diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 1: METADATA (initial resources/list)                          │
│  resources/list returns ONLY skill-level resources:                 │
│  [skills://data-analysis, skills://code-review, skills://pdf-proc]  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ Agent reads a skill
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 2: INSTRUCTIONS (resources/read triggers expansion)           │
│  1. Agent calls: resources/read("skills://data-analysis")           │
│  2. Server returns: Full SKILL.md body                              │
│  3. Server marks skill as "expanded" in session state               │
│  4. Server sends: notifications/resources/list_changed              │
│  5. Agent calls: resources/list (in response to notification)       │
│  6. Server returns: NOW includes sub-resources for expanded skills  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ Agent needs specific resource
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 3: RESOURCES (direct read)                                    │
│  Agent calls: resources/read("skills://data-analysis/scripts/x.py") │
│  Server returns: Script content with token count header             │
└─────────────────────────────────────────────────────────────────────┘
```

## Why three surfaces

The tier model remains available through three legacy MCP surfaces (resources, tools, and prompts) because clients load skills differently. Extension-aware SDK v2 clients instead discover complete static snapshots through `skills/list` and `skills/get`, then read canonical `skill://` resources. Legacy resource-aware clients retain progressive `skills://` URIs; tool-calling agents retain `list_skills`/`get_skill`/`get_skill_resource`; prompt-oriented clients retain per-skill prompts. The exact contracts are in the [MCP surface reference](../reference/mcp-surface.md).

### Canonical snapshots and identity

The domain owns a normalized source-relative `SkillPath`; MCP URI and extension models remain in infrastructure. A skill name is display and legacy lookup metadata, not identity. Duplicate names at different paths coexist, while the configured source order resolves exact path collisions.

Loading is consolidated around one immutable, bounded snapshot representation. It retains exact `SKILL.md` bytes, complete JSON-compatible frontmatter, normalized convenience fields, and every recursively discovered regular file with captured bytes, mtime, exact byte size, SHA-256 digest, and optional token estimate. Symlinks and snapshots above 512 files or 16 MiB are rejected. Canonical reads use only captured bytes, so later mutation, deletion, or file-type replacement cannot change or block the snapshot; legacy name lookup remains first-match.

The extension uses `capabilities.extensions["io.modelcontextprotocol/skills"]`, `skills/list`, `skills/get`, and `skill://<path>/SKILL.md`. It does not expose `directoryRead` or `resources/directory/read`; complete static file lists make directory reads unnecessary in this snapshot.

## Multi-tenant session architecture

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

### Session state

```python
@dataclass
class SessionState:
    session_id: str
    expanded_skills: set[str]        # Skills with visible sub-resources
    created_at: datetime
    last_accessed: datetime          # Bumped on access; drives expiry
```

### Session lifecycle

- **Session identity**: the session ID comes from the `mcp-session-id` header, which the SDK assigns on `initialize`. Resolution **fails closed**: a request with no session ID is treated as *sessionless* rather than falling back to a shared session, so expanded-skill state cannot bleed across unrelated requests. Sessionless requests still return skill bodies and resources, but skip expansion tracking and the `resources/list_changed` notification.
- **Expiry**: sessions expire 24 hours after their last access (`last_accessed`).
- **Cleanup**: a periodic background task, started in the ASGI lifespan, sweeps expired sessions hourly so long-running servers do not accumulate stale state. The task is cancelled on shutdown.

### Canonical path collisions

When a `CompositeSkillRepository` combines sources, source precedence applies only to an exact source-relative canonical path collision. Duplicate frontmatter names at distinct paths remain visible. A shadowed canonical path is logged once at `WARNING` with source provenance. Legacy APIs intentionally resolve duplicate names by first match.

## Pluggable repository layer

The repository interface is defined in the domain layer, with implementations in infrastructure:

```
SkillRepository (Protocol - Domain Layer)
    │
    ├── LocalSkillRepository      ← Filesystem
    ├── GitSkillRepository        ← Git repos over HTTPS
    ├── OCISkillRepository        ← OCI registries
    └── CompositeSkillRepository  ← Combines multiple sources
```

The protocol admits further backends (for example a database-backed repository) without touching the domain or MCP layers.

### Repository interface

```python
class SkillRepository(Protocol):
    async def list_all(self) -> list[Skill]: ...
    async def find_by_name(self, name: SkillName) -> Skill | None: ...
    async def get_resource_content(self, skill: SkillName, resource_type: str, name: str) -> bytes: ...
    async def refresh(self) -> None: ...
```

### Caching strategy

```
┌─────────────────────────────────────────┐
│         CachingRepositoryDecorator       │
│  ┌─────────────────────────────────┐    │
│  │    LRU Cache (in-memory)        │    │
│  └─────────────────────────────────┘    │
│                  │                       │
│  ┌─────────────────────────────────┐    │
│  │    Inner SkillRepository        │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Token estimation

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

## Security considerations

1. **Path traversal prevention**: all file paths validated against the skill root
2. **No script execution**: the server exposes content only; agents run scripts themselves
3. **Session isolation**: each connection has isolated state
4. **Input validation**: all skill names validated against the spec regex

The git source's SSRF guards and accepted residual risks are documented in [skill sources](../guides/skill-sources.md#security-notes-and-accepted-residuals).

## References

- [Agent Skills specification](https://agentskills.io/specification)
- [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
