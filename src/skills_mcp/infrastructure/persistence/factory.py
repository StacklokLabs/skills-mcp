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
from skills_mcp.infrastructure.persistence.composite_repository import (
    CompositeSkillRepository,
)
from skills_mcp.infrastructure.persistence.local_repository import LocalSkillRepository
from skills_mcp.infrastructure.persistence.oci_models import (
    OCIAuthConfig,
    OCIRepositoryConfig,
    OCISkillReference,
)
from skills_mcp.infrastructure.persistence.oci_repository import OCISkillRepository


if TYPE_CHECKING:
    from skills_mcp.domain.repositories import SkillRepository
    from skills_mcp.infrastructure.config.models import SkillsConfig


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
        oci_skills: List of OCI skill references for OCI sources.
        oci_auth: Per-registry authentication for OCI sources.
        oci_cache_dir: Cache directory for OCI sources.
    """

    source_type: SourceType
    paths: list[Path] = field(default_factory=list)
    url: str | None = None
    branch: str | None = None
    tag: str | None = None
    oci_skills: list[OCISkillReference] = field(default_factory=list)
    oci_auth: dict[str, OCIAuthConfig] | None = None
    oci_cache_dir: Path | None = None


@dataclass
class RepositoryConfig:
    """Configuration for the skill repository.

    Attributes:
        sources: List of source configurations.
        enable_caching: Whether to wrap repository with caching.
        resource_cache_size: Maximum number of resources to cache.
    """

    sources: list[SourceConfig] = field(default_factory=list)
    enable_caching: bool = True
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

    # If multiple sources, combine them with CompositeSkillRepository
    if len(repositories) == 1:
        repo = repositories[0]
    else:
        repo = CompositeSkillRepository(repositories)
        logger.info("Created composite repository with %d sources", len(repositories))

    # Wrap with caching if enabled
    if config.enable_caching:
        repo = CachingRepositoryDecorator(
            repo,
            resource_cache_size=config.resource_cache_size,
        )
        logger.info(
            "Created cached repository with resource_cache=%d",
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
            if not source.oci_skills:
                raise ValueError("OCI source requires at least one skill reference")
            oci_config = OCIRepositoryConfig(
                skills=source.oci_skills,
                auth=source.oci_auth or {},
                cache_dir=source.oci_cache_dir,
            )
            return OCISkillRepository(oci_config)


def create_local_repository(
    paths: list[Path],
    *,
    enable_caching: bool = True,
    resource_cache_size: int = 500,
) -> SkillRepository:
    """Convenience function to create a local repository.

    Args:
        paths: List of directories to scan for skills.
        enable_caching: Whether to enable caching.
        resource_cache_size: Maximum number of resources to cache.

    Returns:
        A configured SkillRepository instance.
    """
    config = RepositoryConfig(
        sources=[SourceConfig(source_type=SourceType.LOCAL, paths=paths)],
        enable_caching=enable_caching,
        resource_cache_size=resource_cache_size,
    )
    return create_repository(config)


def create_repository_from_skills_config(
    skills_config: SkillsConfig,
    *,
    enable_caching: bool = True,
    resource_cache_size: int = 500,
) -> SkillRepository:
    """Create a skill repository from a SkillsConfig.

    This function creates the appropriate repositories based on the
    configuration file settings (local and/or OCI sources).

    Args:
        skills_config: The parsed configuration.
        enable_caching: Whether to enable caching.
        resource_cache_size: Maximum number of resources to cache.

    Returns:
        A configured SkillRepository instance.

    Raises:
        ValueError: If no sources are configured.
    """
    sources: list[SourceConfig] = []

    # Add local sources if configured
    if skills_config.has_local_sources() and skills_config.local is not None:
        sources.append(
            SourceConfig(
                source_type=SourceType.LOCAL,
                paths=skills_config.local.paths,
            )
        )

    # Add OCI sources if configured
    if skills_config.has_oci_sources() and skills_config.oci is not None:
        oci_skills = [
            OCISkillReference.from_string(skill.image)
            for skill in skills_config.oci.skills
        ]

        # Convert auth config models to OCIAuthConfig
        oci_auth: dict[str, OCIAuthConfig] = {}
        for registry, auth_model in skills_config.oci.auth.items():
            oci_auth[registry] = OCIAuthConfig(
                registry=registry,
                username=auth_model.get_username(),
                password=auth_model.get_password(),
            )

        sources.append(
            SourceConfig(
                source_type=SourceType.OCI,
                oci_skills=oci_skills,
                oci_auth=oci_auth if oci_auth else None,
                oci_cache_dir=skills_config.oci.cache_dir,
            )
        )

    if not sources:
        raise ValueError(
            "No skill sources configured. "
            "Add 'local' or 'oci' section to your configuration."
        )

    config = RepositoryConfig(
        sources=sources,
        enable_caching=enable_caching,
        resource_cache_size=resource_cache_size,
    )

    return create_repository(config)
