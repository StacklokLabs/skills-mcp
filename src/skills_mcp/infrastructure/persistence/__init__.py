"""Persistence adapters for skill storage.

This package provides repository implementations for different storage backends:
- LocalSkillRepository: Reads skills from local filesystem directories
- OCISkillRepository: Pulls skills from OCI registries (Docker Hub, GHCR, etc.)
- GitSkillRepository: Clones skills from Git repositories over HTTPS
- CachingRepositoryDecorator: Wraps any repository with LRU caching
- create_repository: Factory function to create repositories from config
"""

from skills_mcp.infrastructure.persistence.cache import CachingRepositoryDecorator
from skills_mcp.infrastructure.persistence.composite_repository import (
    CompositeSkillRepository,
)
from skills_mcp.infrastructure.persistence.factory import (
    RepositoryConfig,
    SourceConfig,
    SourceType,
    create_local_repository,
    create_repository,
    create_repository_from_skills_config,
)
from skills_mcp.infrastructure.persistence.git_models import (
    GitAuthConfig,
    GitRepositoryConfig,
    GitSkillReference,
)
from skills_mcp.infrastructure.persistence.git_repository import GitSkillRepository
from skills_mcp.infrastructure.persistence.local_repository import (
    LocalSkillRepository,
)
from skills_mcp.infrastructure.persistence.oci_models import (
    OCIAuthConfig,
    OCIRepositoryConfig,
    OCISkillReference,
)
from skills_mcp.infrastructure.persistence.oci_repository import OCISkillRepository


__all__ = [
    "CachingRepositoryDecorator",
    "CompositeSkillRepository",
    "GitAuthConfig",
    "GitRepositoryConfig",
    "GitSkillReference",
    "GitSkillRepository",
    "LocalSkillRepository",
    "OCIAuthConfig",
    "OCIRepositoryConfig",
    "OCISkillReference",
    "OCISkillRepository",
    "RepositoryConfig",
    "SourceConfig",
    "SourceType",
    "create_local_repository",
    "create_repository",
    "create_repository_from_skills_config",
]
