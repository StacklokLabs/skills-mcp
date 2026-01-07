# DDD Layers

This document details the Domain-Driven Design layers used in Skills MCP Server.

## Domain Layer

The domain layer contains the core business logic and is completely independent of
external frameworks and libraries.

### Entities

Entities have identity and lifecycle:

```python
@dataclass
class Skill:
    """Skill aggregate root."""
    id: UUID
    name: SkillName
    description: str
    manifest: SkillManifest
    scripts: list[SkillScript]
```

### Value Objects

Value objects are immutable and compared by value:

```python
@dataclass(frozen=True)
class SkillName:
    """Validated skill name."""
    value: str

    def __post_init__(self) -> None:
        validate_skill_name(self.value)
```

### Domain Services

Services that don't belong to a single entity:

```python
class SkillValidator:
    """Validates skill definitions against specification."""

    def validate(self, skill: Skill) -> ValidationResult:
        ...
```

### Repository Interfaces

Abstract interfaces defined in domain, implemented in infrastructure:

```python
class SkillRepository(ABC):
    @abstractmethod
    async def find_by_name(self, name: str) -> Skill | None: ...
```

## Application Layer

Orchestrates domain objects to implement use cases.

### Commands (Write Operations)

```python
@dataclass
class ValidateSkillCommand:
    skill_path: Path

class ValidateSkillHandler:
    def __init__(self, repository: SkillRepository):
        self._repository = repository

    async def handle(self, cmd: ValidateSkillCommand) -> ValidationResult:
        ...
```

### Queries (Read Operations)

```python
@dataclass
class DiscoverSkillsQuery:
    directory: Path

class DiscoverSkillsHandler:
    async def handle(self, query: DiscoverSkillsQuery) -> list[SkillSummary]:
        ...
```

### DTOs

Data Transfer Objects for crossing layer boundaries:

```python
@dataclass
class SkillDTO:
    name: str
    description: str
    scripts: list[str]
```

## Infrastructure Layer

Technical implementations and external integrations.

### Repository Implementations

```python
class FileSystemSkillRepository(SkillRepository):
    """File system based skill repository."""

    async def find_by_name(self, name: str) -> Skill | None:
        path = self._base_path / name / "SKILL.md"
        ...
```

### MCP Server

```python
class SkillsMCPServer:
    """MCP server exposing skill operations as tools."""

    @mcp.tool()
    async def validate_skill(self, path: str) -> dict:
        ...
```

## Interfaces Layer

Entry points to the application.

### CLI

```python
@click.command()
@click.option("--port", default=8080)
def serve(port: int) -> None:
    """Start the MCP server."""
    ...
```

## Layer Rules Summary

| Layer | Can Import From | Cannot Import From |
|-------|-----------------|-------------------|
| Domain | (none) | Application, Infrastructure, Interfaces |
| Application | Domain | Infrastructure, Interfaces |
| Infrastructure | Domain, Application | Interfaces |
| Interfaces | All | (none) |
