# Security

Security is a primary concern for Skills MCP Server since it handles untrusted skill
definitions.

## Threat Model

### Untrusted Skills

Skills may come from untrusted sources and could contain:

- Malicious scripts
- Path traversal attempts
- Oversized content (DoS)
- Malformed YAML/Markdown

### Mitigations

1. **Input Validation**: All skill content is validated before processing
2. **Sandboxing**: Script execution is sandboxed
3. **Path Sanitization**: File paths are sanitized to prevent traversal
4. **Size Limits**: Content size limits prevent resource exhaustion

## Security Guidelines

### Never Trust External Data

```python
# Bad: Direct path usage
def read_skill(path: str) -> str:
    return Path(path).read_text()

# Good: Validate and sanitize
def read_skill(path: str, base_dir: Path) -> str:
    resolved = (base_dir / path).resolve()
    if not resolved.is_relative_to(base_dir):
        raise SecurityError("Path traversal detected")
    return resolved.read_text()
```

### Validate All Inputs

```python
from pydantic import BaseModel, validator

class SkillManifest(BaseModel):
    name: str
    description: str

    @validator("name")
    def validate_name(cls, v: str) -> str:
        if not SKILL_NAME_PATTERN.match(v):
            raise ValueError("Invalid skill name")
        if len(v) > 64:
            raise ValueError("Name too long")
        return v
```

### Sandbox Script Execution

Never execute scripts directly:

```python
# Bad: Direct execution
import subprocess
subprocess.run(["python", script_path])

# Good: Sandboxed execution
from skills_mcp.infrastructure.sandbox import Sandbox

async def execute_script(script: Path) -> ExecutionResult:
    sandbox = Sandbox(
        timeout=30,
        memory_limit="256M",
        network=False,
    )
    return await sandbox.run(script)
```

### Use HTTPS for Remote Skills

```python
# Bad: Allow HTTP
async def fetch_skill(url: str) -> Skill:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

# Good: Require HTTPS
async def fetch_skill(url: str) -> Skill:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise SecurityError("Only HTTPS URLs are allowed")

    async with httpx.AsyncClient(verify=True) as client:
        response = await client.get(url, timeout=30.0)
```

## Reporting Vulnerabilities

If you discover a security vulnerability:

1. **Do not** open a public issue
2. Email security concerns to the maintainers
3. Include detailed reproduction steps
4. Allow time for a fix before public disclosure

## Security Checklist

Before submitting code, verify:

- [ ] All external input is validated
- [ ] File paths are sanitized
- [ ] No secrets are hardcoded
- [ ] HTTPS is enforced for remote operations
- [ ] Timeouts are set for external calls
- [ ] Size limits are enforced
- [ ] Error messages don't leak sensitive information

## Dependencies

Keep dependencies updated to patch security vulnerabilities:

```bash
# Check for vulnerable dependencies
uv pip audit

# Update dependencies
uv sync --upgrade
```
