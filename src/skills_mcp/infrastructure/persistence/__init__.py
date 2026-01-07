"""Persistence adapters for skill storage.

This package provides repository implementations for different storage backends:
- LocalSkillRepository: Reads skills from local filesystem directories
- CachingRepositoryDecorator: Wraps any repository with LRU caching
- create_repository: Factory function to create repositories from config
"""

from skills_mcp.infrastructure.persistence.cache import CachingRepositoryDecorator
from skills_mcp.infrastructure.persistence.factory import (
    RepositoryConfig,
    SourceConfig,
    SourceType,
    create_local_repository,
    create_repository,
)
from skills_mcp.infrastructure.persistence.local_repository import (
    LocalSkillRepository,
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
