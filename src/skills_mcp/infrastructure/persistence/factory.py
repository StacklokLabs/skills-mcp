"""Repository factory for creating skill repositories from configuration.

This module provides factory functions to create the appropriate repository
implementation based on configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import TYPE_CHECKING

from skills_mcp.infrastructure.persistence.cache import CachingRepositoryDecorator
from skills_mcp.infrastructure.persistence.local_repository import LocalSkillRepository


if TYPE_CHECKING:
    from skills_mcp.domain.repositories import SkillRepository


logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Type of skill source."""

    LOCAL = "local"
    GIT = "git"  # Future
    OCI = "oci"  # Future


@dataclass
class SourceConfig:
    """Configuration for a skill source.

    Attributes:
        source_type: The type of source (local, git, oci).
        paths: List of paths for local sources.
        url: URL for git/oci sources (future).
        branch: Branch for git sources (future).
        tag: Tag for OCI sources (future).
    """

    source_type: SourceType
    paths: list[Path] = field(default_factory=list)
    url: str | None = None
    branch: str | None = None
    tag: str | None = None


@dataclass
class RepositoryConfig:
    """Configuration for the skill repository.

    Attributes:
        sources: List of source configurations.
        enable_caching: Whether to wrap repository with caching.
        skill_cache_size: Maximum number of skills to cache.
        resource_cache_size: Maximum number of resources to cache.
    """

    sources: list[SourceConfig] = field(default_factory=list)
    enable_caching: bool = True
    skill_cache_size: int = 100
    resource_cache_size: int = 500


def create_repository(config: RepositoryConfig) -> SkillRepository:
    """Create a skill repository based on configuration.

    Args:
        config: The repository configuration.

    Returns:
        A configured SkillRepository instance.

    Raises:
        ValueError: If no sources are configured.
        NotImplementedError: If a source type is not yet implemented.
    """
    if not config.sources:
        raise ValueError("At least one source must be configured")

    repositories: list[SkillRepository] = []

    for source in config.sources:
        repo = _create_source_repository(source)
        repositories.append(repo)

    # If multiple sources, combine them (future: CompositeSkillRepository)
    if len(repositories) == 1:
        repo = repositories[0]
    else:
        # For now, only support single source
        # Future: implement CompositeSkillRepository
        raise NotImplementedError(
            "Multiple sources not yet supported. Use a single source for now."
        )

    # Wrap with caching if enabled
    if config.enable_caching:
        repo = CachingRepositoryDecorator(
            repo,
            skill_cache_size=config.skill_cache_size,
            resource_cache_size=config.resource_cache_size,
        )
        logger.info(
            "Created cached repository with skill_cache=%d, resource_cache=%d",
            config.skill_cache_size,
            config.resource_cache_size,
        )

    return repo


def _create_source_repository(source: SourceConfig) -> SkillRepository:
    """Create a repository for a specific source configuration.

    Args:
        source: The source configuration.

    Returns:
        A repository for the source.

    Raises:
        NotImplementedError: If the source type is not yet implemented.
        ValueError: If required configuration is missing.
    """
    match source.source_type:
        case SourceType.LOCAL:
            if not source.paths:
                raise ValueError("Local source requires at least one path")
            return LocalSkillRepository(source.paths)

        case SourceType.GIT:
            raise NotImplementedError(
                "Git source support coming in a future release. "
                "Track progress at https://github.com/stacklok/skills-mcp/issues"
            )

        case SourceType.OCI:
            raise NotImplementedError(
                "OCI registry support coming in a future release. "
                "Track progress at https://github.com/stacklok/skills-mcp/issues"
            )


def create_local_repository(
    paths: list[Path],
    *,
    enable_caching: bool = True,
    skill_cache_size: int = 100,
    resource_cache_size: int = 500,
) -> SkillRepository:
    """Convenience function to create a local repository.

    Args:
        paths: List of directories to scan for skills.
        enable_caching: Whether to enable caching.
        skill_cache_size: Maximum number of skills to cache.
        resource_cache_size: Maximum number of resources to cache.

    Returns:
        A configured SkillRepository instance.
    """
    config = RepositoryConfig(
        sources=[SourceConfig(source_type=SourceType.LOCAL, paths=paths)],
        enable_caching=enable_caching,
        skill_cache_size=skill_cache_size,
        resource_cache_size=resource_cache_size,
    )
    return create_repository(config)
