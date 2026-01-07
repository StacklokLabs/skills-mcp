# Architecture Overview

Skills MCP Server follows Domain-Driven Design (DDD) principles with a clean layered
architecture.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Interfaces Layer                          │
│                   (CLI, Entry Points)                        │
├─────────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                        │
│         (MCP Server, Persistence, HTTP Clients)              │
├─────────────────────────────────────────────────────────────┤
│                   Application Layer                          │
│            (Use Cases, Commands, Queries)                    │
├─────────────────────────────────────────────────────────────┤
│                     Domain Layer                             │
│          (Entities, Value Objects, Services)                 │
└─────────────────────────────────────────────────────────────┘
```

## Layer Dependencies

Dependencies flow inward only:

- **Domain**: Pure Python, no external dependencies
- **Application**: Depends on Domain only
- **Infrastructure**: Depends on Domain and Application
- **Interfaces**: Depends on all layers

## Directory Structure

```
src/skills_mcp/
├── domain/              # Core business logic
│   ├── models/          # Entities and Value Objects
│   ├── services/        # Domain services
│   └── exceptions.py    # Domain exceptions
├── application/         # Use cases
│   ├── commands/        # Write operations
│   ├── queries/         # Read operations
│   └── dto/             # Data Transfer Objects
├── infrastructure/      # External concerns
│   ├── mcp/             # MCP server implementation
│   ├── persistence/     # Storage adapters
│   └── http/            # HTTP client adapters
└── interfaces/          # Entry points
    └── cli/             # Command-line interface
```

## Key Components

### Domain Layer

- **Skill**: Aggregate root representing a skill definition
- **SkillManifest**: Value object for SKILL.md frontmatter
- **SkillValidator**: Domain service for validation

### Application Layer

- **ValidateSkillCommand**: Command to validate a skill
- **DiscoverSkillsQuery**: Query to find available skills
- **SkillDTO**: Data transfer object for skill data

### Infrastructure Layer

- **MCPServer**: FastMCP-based server implementation
- **FileSystemSkillRepository**: File-based skill storage
- **HttpSkillFetcher**: Remote skill fetching

## Design Decisions

See [ADR-001: DDD Architecture](decisions/001-ddd-architecture.md) for the rationale
behind this architectural approach.
