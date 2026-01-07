---
name: python-docs
description: Python documentation patterns and best practices. Use when writing docstrings, README, or technical docs.
---

# Python Documentation Guide

## Docstring Styles

### Google Style (Project Standard)

```python
def function(arg1: str, arg2: int) -> bool:
    """Short description of function.

    Longer description if needed. Can span multiple lines
    and include additional context.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When validation fails.

    Example:
        >>> function("test", 42)
        True
    """
```

### Class Docstrings

```python
class SkillValidator:
    """Validates skill definitions against the specification.

    This class provides methods to validate SKILL.md files,
    checking both structure and content requirements.

    Attributes:
        strict: Whether to enforce strict validation rules.

    Example:
        >>> validator = SkillValidator(strict=True)
        >>> result = validator.validate(Path("./my-skill"))
        >>> print(result.is_valid)
    """
```

## README Structure

1. Project name and badges
2. One-line description
3. Installation
4. Quick start example
5. Documentation link
6. Contributing
7. License

## mkdocs.yml Configuration

```yaml
site_name: Skills MCP Server
site_description: MCP server for Agent Skills specification
repo_url: https://github.com/stacklok/skills-mcp

theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - content.code.copy
    - content.code.annotate

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: google
            show_source: true

markdown_extensions:
  - pymdownx.highlight
  - pymdownx.superfences
  - admonition
```

## Architecture Decision Records (ADRs)

Use this template in `docs/architecture/decisions/`:

```markdown
# ADR-NNN: Title

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
What is the issue we're addressing?

## Decision
What did we decide to do?

## Consequences
What are the results of this decision?
```
