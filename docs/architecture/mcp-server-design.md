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
    expanded_skills: set[SkillName]  # Skills with visible sub-resources
    created_at: datetime
```

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
    ├── GitSkillRepository        ← Git repos (future)
    ├── OCISkillRepository        ← OCI registries (future)
    ├── DatabaseSkillRepository   ← SQL/NoSQL (future)
    └── CompositeSkillRepository  ← Combines multiple sources
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
    }
  }
}
```

## Security Considerations

1. **Path Traversal Prevention**: All file paths validated against skill root
2. **No Script Execution**: Server exposes content only; agents run scripts themselves
3. **Session Isolation**: Each connection has isolated state
4. **Input Validation**: All skill names validated against spec regex

## Configuration

Environment variables:

```bash
SKILLS_MCP_PATHS="/path/to/skills:/another/path"  # Colon-separated
SKILLS_MCP_TRANSPORT="stdio"                       # or "streamable-http"
SKILLS_MCP_LOG_LEVEL="info"
```

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
