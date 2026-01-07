---
name: agent-skills-spec
description: Reference for Agent Skills specification. Use when implementing skill parsing, validation, or discovery.
---

# Agent Skills Specification Reference

## SKILL.md Structure

### Required Frontmatter

- `name`: 1-64 chars, lowercase alphanumeric + hyphens
- `description`: 1-1024 chars

### Optional Frontmatter

- `license`: License identifier
- `compatibility`: Environment requirements (max 500 chars)
- `metadata`: Key-value pairs for extensibility
- `allowed-tools`: Space-delimited tool list

### Directory Layout

```
skill-name/
├── SKILL.md        # Required
├── scripts/        # Executable code
├── references/     # Documentation
└── assets/         # Templates, data
```

## Name Validation

```python
import re

SKILL_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')

def validate_skill_name(name: str) -> bool:
    """Validate skill name against specification.

    Rules:
    - 1-64 characters
    - Lowercase letters, numbers, hyphens only
    - Must start with a letter
    - Cannot start/end with hyphen
    - No consecutive hyphens
    """
    if not 1 <= len(name) <= 64:
        return False
    if '--' in name:
        return False
    return bool(SKILL_NAME_PATTERN.match(name))
```

## Validation Rules

- Name must match parent directory name
- No consecutive hyphens allowed
- Cannot start or end with hyphen
- Body recommended < 5000 tokens

## Progressive Disclosure

1. **Metadata** (~100 tokens): Name and description loaded for all skills
2. **Instructions** (<5000 tokens): Full body loaded upon activation
3. **Resources** (on-demand): Scripts, references, assets loaded as needed
