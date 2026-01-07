---
name: ddd-patterns
description: Domain-Driven Design patterns for Python. Use when designing domain models or implementing use cases.
---

# DDD Patterns for Python

## Entity Pattern

Entities have identity that persists over time:

```python
from dataclasses import dataclass, field
from uuid import UUID, uuid4

@dataclass
class Skill:
    """Skill aggregate root."""

    id: UUID = field(default_factory=uuid4)
    name: str
    description: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Skill):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
```

## Value Object Pattern

Value objects are immutable and compared by value:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SkillName:
    """Validated skill name value object."""

    value: str

    def __post_init__(self) -> None:
        if not SKILL_NAME_PATTERN.match(self.value):
            raise ValueError(f"Invalid skill name: {self.value}")
```

## Repository Interface

Define in domain, implement in infrastructure:

```python
from abc import ABC, abstractmethod

class SkillRepository(ABC):
    """Abstract repository for Skill aggregate."""

    @abstractmethod
    async def find_by_name(self, name: str) -> Skill | None:
        """Find a skill by its name."""
        ...

    @abstractmethod
    async def save(self, skill: Skill) -> None:
        """Persist a skill."""
        ...

    @abstractmethod
    async def list_all(self) -> list[Skill]:
        """List all skills."""
        ...
```

## Use Case / Command Pattern

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ValidateSkillCommand:
    """Command to validate a skill."""

    skill_path: Path

class ValidateSkillHandler:
    """Handler for skill validation use case."""

    def __init__(self, repository: SkillRepository) -> None:
        self._repository = repository

    async def handle(self, command: ValidateSkillCommand) -> ValidationResult:
        """Execute the validation use case."""
        # Implementation
        pass
```

## Domain Events

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class SkillValidated:
    """Event raised when a skill is validated."""

    skill_name: str
    is_valid: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
```
