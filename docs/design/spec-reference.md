# Specification Reference for MCP Server Design

This document captures the key details from the Agent Skills and MCP specifications
to inform the server implementation design.

---

## Part 1: Agent Skills Specification

Source: https://agentskills.io/specification

### 1.1 Skill Structure

Skills are directories containing a required `SKILL.md` file with YAML frontmatter.

```
skill-name/
├── SKILL.md        # Required - skill definition
├── scripts/        # Optional - executable code
├── references/     # Optional - domain documentation
└── assets/         # Optional - templates, images, data
```

### 1.2 SKILL.md Format

```yaml
---
name: skill-name
description: What this skill does and when to use it (1-1024 chars)
license: Apache-2.0                    # Optional
compatibility: "Python 3.10+"          # Optional (max 500 chars)
metadata:                              # Optional - arbitrary key-value pairs
  author: "Example Inc"
  version: "1.0.0"
allowed-tools: Read Grep Glob Bash     # Optional - space-delimited (experimental)
---

# Skill Title

Markdown content with instructions...
```

### 1.3 Name Validation Rules

The `name` field must:
- Be 1-64 characters long
- Contain only lowercase letters, numbers, and hyphens
- Start with a lowercase letter
- Not start or end with hyphens
- Not contain consecutive hyphens (`--`)
- Match the parent directory name exactly

**Regex pattern:**
```python
import re
SKILL_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')
```

**Valid examples:** `pdf-processing`, `data-analysis`, `code-review`, `my-skill-v2`
**Invalid examples:** `My-Skill`, `skill--name`, `-skill`, `skill-`, `SKILL`

### 1.4 Progressive Disclosure Model

Skills use a three-tier loading strategy:

1. **Metadata** (~100 tokens): Name and description loaded for ALL skills at startup
   - Used for skill discovery and matching
   - Should be concise and descriptive

2. **Instructions** (<5000 tokens recommended): Full SKILL.md body loaded on activation
   - Contains the main skill instructions
   - Should stay under 5000 tokens for efficiency

3. **Resources** (on-demand): Referenced files loaded as needed
   - Scripts in `scripts/` directory
   - Documentation in `references/` directory
   - Assets in `assets/` directory

### 1.5 File References

Use relative paths from skill root:
- `scripts/extract.py`
- `references/REFERENCE.md`
- `assets/template.json`

Supported script languages:
- Python (.py)
- Bash (.sh)
- JavaScript (.js)

### 1.6 Validation Tool

The official `skills-ref` tool provides validation:
```bash
skills-ref validate ./my-skill
```

---

## Part 2: Model Context Protocol (MCP) Specification

Source: https://modelcontextprotocol.io/specification/2025-11-25/basic

### 2.1 Protocol Overview

MCP is a standardized protocol for communication between AI clients and servers
that expose capabilities through **resources**, **tools**, and **prompts**.

**Protocol Version:** 2025-11-25

### 2.2 Core Architecture

```
┌─────────────┐         ┌─────────────┐
│   Client    │ ←────→  │   Server    │
│  (Claude)   │ JSON-RPC│ (skills-mcp)│
└─────────────┘         └─────────────┘
```

All implementations must support:
1. **Base Protocol** - JSON-RPC 2.0 message types
2. **Lifecycle Management** - Connection initialization and capability negotiation
3. **Authorization** - Authentication framework (for HTTP transports)
4. **Server Features** - Resources, prompts, and tools
5. **Client Features** - Sampling and root directories

### 2.3 JSON-RPC 2.0 Protocol

#### Request Format
```json
{
  "jsonrpc": "2.0",
  "id": "string | number",
  "method": "string",
  "params": {
    "[key: string]": "unknown"
  }
}
```

Requirements:
- `id` must be string or integer (NOT null)
- Each request ID must be unique within the session

#### Response Format (Success)
```json
{
  "jsonrpc": "2.0",
  "id": "string | number",
  "result": {
    "[key: string]": "unknown"
  }
}
```

#### Response Format (Error)
```json
{
  "jsonrpc": "2.0",
  "id": "string | number",
  "error": {
    "code": "number",
    "message": "string",
    "data": "unknown (optional)"
  }
}
```

#### Notification Format
```json
{
  "jsonrpc": "2.0",
  "method": "string",
  "params": {
    "[key: string]": "unknown"
  }
}
```

**Key:** Notifications have NO `id` field and require NO response.

### 2.4 Server Features

#### Tools

Executable functions that servers expose to clients:

```json
{
  "name": "discover_skills",
  "description": "Find skills in a directory",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Directory path to search"
      }
    },
    "required": ["path"]
  }
}
```

Tool characteristics:
- Include name, description, and JSON Schema for input
- Clients call tools to perform actions
- Results returned as structured data

#### Resources

Data that servers can provide to clients:

```json
{
  "uri": "skills://my-skill",
  "name": "My Skill",
  "description": "A sample skill definition",
  "mimeType": "text/markdown"
}
```

Resource characteristics:
- Identified by URI (can use custom schemes like `skills://`)
- Can be files, databases, web content, etc.
- Support reading and subscription patterns

#### Prompts

Pre-defined, reusable prompt templates:

```json
{
  "name": "review_skill",
  "description": "Review a skill definition",
  "arguments": [
    {
      "name": "skill_name",
      "description": "Name of the skill to review",
      "required": true
    }
  ]
}
```

### 2.5 Transport Mechanisms

MCP supports multiple transports:

1. **STDIO** - Standard input/output (local processes)
   - Simple subprocess communication
   - Best for local integrations

2. **HTTP/SSE** - Server-Sent Events (deprecated)
   - Unidirectional server-to-client streaming
   - Being phased out

3. **Streamable HTTP** - Bidirectional HTTP with streaming
   - Modern replacement for SSE
   - Supports CORS for browser clients
   - **Recommended for new implementations**

### 2.6 Authorization

For HTTP-based transports:
- Use OAuth 2.1 for secure authentication
- STDIO transports retrieve credentials from environment variables
- Clients and servers may negotiate custom auth strategies

### 2.7 Reserved Metadata

The `_meta` field allows attaching additional metadata:
- Key format: `[prefix/]name`
- Reserved prefixes: `io.modelcontextprotocol/`, `dev.mcp/`

### 2.8 JSON Schema Support

- **Default dialect:** JSON Schema 2020-12
- **Explicit dialect:** Specify via `$schema` field
- Implementations MUST support 2020-12

---

## Part 3: MCP Python SDK

Source: https://github.com/modelcontextprotocol/python-sdk

### 3.1 Installation

```bash
pip install mcp[cli]
# or
uv add mcp[cli]
```

### 3.2 FastMCP Server

The primary interface for building MCP servers:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server-name")
```

### 3.3 Defining Tools

```python
@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description for LLM.

    Args:
        param: Description of parameter

    Returns:
        Description of return value
    """
    return f"Result: {param}"
```

Key points:
- Function parameters become tool arguments automatically
- Docstring becomes tool description
- Return type annotations enable structured output validation
- Async functions are supported

### 3.4 Defining Resources

```python
@mcp.resource("skills://{skill_name}")
async def get_skill(skill_name: str) -> str:
    """Return skill content."""
    return skill_content
```

URI templates support path parameters in `{braces}`.

### 3.5 Defining Prompts

```python
@mcp.prompt()
def review_skill(skill_name: str) -> str:
    """Create a prompt to review a skill."""
    return f"Please review the skill: {skill_name}"
```

### 3.6 Context Object

For logging and progress reporting:

```python
from mcp.server.fastmcp import Context

@mcp.tool()
async def long_task(ctx: Context) -> str:
    await ctx.info("Starting task...")
    await ctx.report_progress(50, 100)
    await ctx.warning("Something to note")
    return "Done"
```

Context methods:
- `ctx.info(message)` - Log info message
- `ctx.warning(message)` - Log warning
- `ctx.error(message)` - Log error
- `ctx.report_progress(current, total)` - Report progress

### 3.7 Running the Server

```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

Transport options:
- `"stdio"` - Standard input/output
- `"sse"` - Server-Sent Events (deprecated)
- `"streamable-http"` - Streamable HTTP (recommended)

### 3.8 Lifespan Management

For initialization and cleanup:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(server: FastMCP):
    # Initialization
    await setup_database()
    yield
    # Cleanup
    await close_database()

mcp = FastMCP("server-name", lifespan=lifespan)
```

### 3.9 CallToolResult

For advanced tool responses:

```python
from mcp.types import CallToolResult, TextContent

@mcp.tool()
async def advanced_tool() -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text="Result")],
        isError=False
    )
```

---

## Part 4: Design Considerations for Skills MCP Server

### 4.1 Tools to Implement

| Tool | Description | Input | Output |
|------|-------------|-------|--------|
| `discover_skills` | Find skills in directory | `path: str` | List of skill summaries |
| `validate_skill` | Validate skill definition | `path: str` | Validation result |
| `get_skill` | Get full skill content | `name: str` | Skill details |
| `list_scripts` | List scripts in a skill | `skill: str` | Script names |
| `execute_script` | Run a skill script | `skill: str, script: str, args: dict` | Execution result |

### 4.2 Resources to Implement

| URI Pattern | Description |
|-------------|-------------|
| `skills://` | List all available skills |
| `skills://{name}` | Get specific skill content |
| `skills://{name}/scripts/{script}` | Get script content |

### 4.3 Prompts to Implement

| Prompt | Description |
|--------|-------------|
| `review_skill` | Generate prompt to review a skill |
| `create_skill` | Generate prompt to create a new skill |

### 4.4 Security Requirements

1. **Path Traversal Prevention**
   - Sanitize all file paths
   - Validate paths are within allowed directories
   - Use `Path.resolve()` and `is_relative_to()`

2. **Script Sandboxing**
   - Execute scripts in isolated environment
   - Set resource limits (CPU, memory, time)
   - Disable network access by default

3. **Input Validation**
   - Validate all skill names against spec
   - Validate YAML/Markdown parsing
   - Set size limits on content

4. **HTTPS Enforcement**
   - Require HTTPS for remote skill fetching
   - Validate certificates
   - Set request timeouts

### 4.5 Domain Model Candidates

**Entities:**
- `Skill` - Aggregate root, represents a complete skill
- `SkillScript` - Executable script within a skill

**Value Objects:**
- `SkillName` - Validated skill name
- `SkillManifest` - Parsed frontmatter
- `ValidationResult` - Validation outcome with errors/warnings

**Domain Services:**
- `SkillValidator` - Validates skills against spec
- `ManifestParser` - Parses SKILL.md frontmatter
- `NameValidator` - Validates skill names

**Repository Interfaces:**
- `SkillRepository` - Abstract skill storage
  - `find_by_name(name: str) -> Skill | None`
  - `list_all() -> list[Skill]`
  - `save(skill: Skill) -> None`

### 4.6 Open Questions for Design

1. **Remote Skills**: Should we support fetching skills from URLs?
   - If yes, how to handle authentication?
   - Caching strategy?

2. **Script Execution**: How to sandbox script execution?
   - Docker containers?
   - Python subprocess with resource limits?
   - WebAssembly?

3. **Skill Caching**: How to cache parsed skills?
   - In-memory cache?
   - File-based cache?
   - Cache invalidation strategy?

4. **Configuration**: How to configure the server?
   - Environment variables?
   - Config file (TOML/YAML)?
   - CLI arguments?

5. **Observability**: What metrics/tracing to implement?
   - Request counts per tool
   - Validation error rates
   - Script execution times

---

## Appendix A: Example SKILL.md

```yaml
---
name: data-analysis
description: Analyze datasets and generate insights. Use when working with CSV, Excel, or database exports.
license: MIT
compatibility: "Python 3.10+, pandas, matplotlib"
metadata:
  author: "Data Team"
  version: "2.0.0"
allowed-tools: Read Bash
---

# Data Analysis Skill

## Quick Start

Load and analyze data:

\`\`\`python
import pandas as pd
df = pd.read_csv('data.csv')
print(df.describe())
\`\`\`

## Available Scripts

- `scripts/analyze.py` - Run statistical analysis
- `scripts/visualize.py` - Generate charts

## Usage

See [references/GUIDE.md](references/GUIDE.md) for detailed usage instructions.
```

## Appendix B: Example MCP Tool Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 3 skills:\n- data-analysis\n- code-review\n- pdf-processing"
      }
    ],
    "isError": false
  }
}
```

## Appendix C: Example Validation Result

```json
{
  "is_valid": false,
  "skill_name": "my-skill",
  "errors": [
    {
      "code": "MISSING_DESCRIPTION",
      "message": "Skill manifest missing required 'description' field",
      "location": "SKILL.md:1"
    }
  ],
  "warnings": [
    {
      "code": "BODY_TOO_LONG",
      "message": "Skill body exceeds recommended 5000 tokens (actual: 7500)",
      "location": "SKILL.md"
    }
  ]
}
```
