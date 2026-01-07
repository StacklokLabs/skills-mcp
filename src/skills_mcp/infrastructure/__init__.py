"""Infrastructure layer for skills-mcp.

This layer contains external concerns:
- persistence/ - Storage adapters (local filesystem, git, OCI)
- mcp/ - MCP server implementation
- http/ - HTTP clients for remote skill sources
"""

from skills_mcp.infrastructure.persistence import (
    CachingRepositoryDecorator,
    LocalSkillRepository,
    RepositoryConfig,
    SourceConfig,
    SourceType,
    create_local_repository,
    create_repository,
)


__all__ = [
    "CachingRepositoryDecorator",
    "LocalSkillRepository",
    "RepositoryConfig",
    "SourceConfig",
    "SourceType",
    "create_local_repository",
    "create_repository",
]
