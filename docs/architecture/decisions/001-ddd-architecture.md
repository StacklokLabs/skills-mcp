# ADR-001: Domain-Driven Design Architecture

## Status

Accepted

## Context

We need to design the architecture for Skills MCP Server, a project that:

- Implements the Agent Skills specification
- Exposes functionality via MCP protocol
- Handles untrusted external data (skill definitions)
- Needs to be maintainable and testable

Key concerns:

1. **Security**: The system handles untrusted skill definitions that could contain
   malicious content
2. **Testability**: Core business logic should be easily testable without external
   dependencies
3. **Maintainability**: Clear separation of concerns makes the codebase easier to
   understand and modify
4. **Flexibility**: The architecture should support different deployment scenarios
   (local, remote, containerized)

## Decision

We will use Domain-Driven Design (DDD) with a layered architecture:

### Layers

1. **Domain Layer**: Pure Python, contains core business logic
   - Entities (Skill, Script, Reference)
   - Value Objects (SkillName, SkillManifest)
   - Domain Services (SkillValidator)
   - Repository interfaces

2. **Application Layer**: Orchestration and use cases
   - Command handlers (ValidateSkillCommand)
   - Query handlers (DiscoverSkillsQuery)
   - DTOs for layer boundary crossing

3. **Infrastructure Layer**: Technical implementations
   - MCP server (FastMCP)
   - File system repository
   - HTTP client for remote skills

4. **Interfaces Layer**: Entry points
   - CLI commands
   - Future: REST API, web UI

### Dependency Rule

Dependencies flow inward only:
- Domain depends on nothing
- Application depends on Domain
- Infrastructure depends on Domain and Application
- Interfaces depends on all layers

## Consequences

### Positive

- **Testability**: Domain logic can be tested without mocking external services
- **Security**: Validation logic is centralized in the domain layer
- **Flexibility**: Infrastructure can be swapped without changing business logic
- **Clear boundaries**: Easy to understand where code belongs

### Negative

- **Initial complexity**: More files and directories than a flat structure
- **Boilerplate**: DTOs and mapping between layers
- **Learning curve**: Team needs to understand DDD concepts

### Mitigations

- Provide clear documentation and examples
- Use dataclasses to reduce boilerplate
- Start simple and add complexity as needed

## References

- [Domain-Driven Design](https://www.domainlanguage.com/ddd/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
