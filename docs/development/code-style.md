# Code Style

This project uses automated tools to enforce consistent code style.

## Tools

- **ruff**: Linting and formatting
- **mypy**: Type checking

## Formatting

Code is formatted with `ruff format`:

```bash
uv run ruff format .
```

Key settings:
- Line length: 88 characters
- Quote style: Double quotes
- Indent style: Spaces

## Linting

Linting is done with `ruff check`:

```bash
uv run ruff check .
```

Enabled rule sets:
- `E`, `W`: pycodestyle
- `F`: Pyflakes
- `I`: isort (imports)
- `B`: flake8-bugbear
- `S`: flake8-bandit (security)
- `D`: pydocstyle (docstrings)
- And more (see `ruff.toml`)

## Type Hints

All code must have type hints. We use strict mypy settings:

```bash
uv run mypy src/
```

### Examples

```python
# Function with type hints
def validate_skill_name(name: str) -> bool:
    ...

# Class with type hints
class SkillValidator:
    def __init__(self, strict: bool = False) -> None:
        self._strict = strict

    async def validate(self, path: Path) -> ValidationResult:
        ...

# Generic types
def find_skills(directory: Path) -> list[Skill]:
    ...

# Optional types
def get_skill(name: str) -> Skill | None:
    ...
```

## Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Functions | snake_case | `validate_skill` |
| Variables | snake_case | `skill_name` |
| Classes | PascalCase | `SkillValidator` |
| Constants | UPPER_SNAKE_CASE | `MAX_NAME_LENGTH` |
| Modules | snake_case | `skill_validator.py` |
| Type aliases | PascalCase | `SkillList = list[Skill]` |

## Docstrings

Use Google-style docstrings:

```python
def validate_skill(path: Path, strict: bool = False) -> ValidationResult:
    """Validate a skill definition.

    Checks the skill at the given path against the Agent Skills
    specification.

    Args:
        path: Path to the skill directory.
        strict: If True, treat warnings as errors.

    Returns:
        ValidationResult containing errors and warnings.

    Raises:
        SkillNotFoundError: If the skill doesn't exist.
        InvalidManifestError: If SKILL.md is malformed.

    Example:
        >>> result = validate_skill(Path("./my-skill"))
        >>> if result.is_valid:
        ...     print("Skill is valid!")
    """
```

## Imports

Imports are organized by ruff in this order:

1. Standard library
2. Third-party packages
3. Local packages

```python
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from skills_mcp.domain.models import Skill
from skills_mcp.domain.services import SkillValidator
```

## Architecture Rules

Follow DDD layer dependencies:

- Domain layer: No imports from other layers
- Application layer: Only import from domain
- Infrastructure layer: Import from domain and application
- Interfaces layer: Can import from all layers

See [DDD Layers](../architecture/ddd-layers.md) for details.
