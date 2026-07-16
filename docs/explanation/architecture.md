# Architecture

This document describes the architecture for exposing Agent Skills via the Model Context Protocol (MCP) with token-efficient progressive disclosure. For the exact tool, resource, and prompt contracts, see the [MCP surface reference](../reference/mcp-surface.md).

## Design goals

1. **Token efficiency**: minimize context usage through progressive disclosure
2. **Multi-tenancy**: support concurrent agent sessions with isolated state
3. **Extensibility**: pluggable storage backends (filesystem, git, OCI)
4. **Spec compliance**: follow both the Agent Skills and MCP specifications

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

The tier model is exposed through three complementary MCP surfaces (resources, tools, and prompts) rather than betting on one, because different AI coding agents load skills in different ways: resource-aware clients (Roo Code, Cline) browse `skills://` URIs, tool-calling agents (Claude Code, Roo Code, Cline, Continue) mirror the native `Skill` tool pattern via `list_skills`/`get_skill`/`get_skill_resource`, and prompt-oriented clients (Continue) turn per-skill MCP prompts into slash commands. The contracts for each surface are in the [MCP surface reference](../reference/mcp-surface.md); the measures that make tool-calling agents actually use the server unprompted are explained in [how agents discover served skills](agent-discovery.md).

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

### Skill name collisions

When a `CompositeSkillRepository` combines sources, the first source to register a name wins. A shadowed skill is not dropped silently: each unique collision is logged once at `WARNING` with provenance (which repository shadows which), so operators can see and resolve overlapping skill names.

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
    async def get_resource(self, skill: SkillName, resource_type: str, name: str) -> bytes: ...
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
