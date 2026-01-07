"""Tests for repository factory."""

from pathlib import Path

import pytest

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
)
from skills_mcp.infrastructure.persistence.local_repository import LocalSkillRepository
from skills_mcp.infrastructure.persistence.oci_models import OCISkillReference
from skills_mcp.infrastructure.persistence.oci_repository import OCISkillRepository


FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures" / "skills"


class TestCreateRepository:
    """Tests for create_repository function."""

    def test_create_local_repository_with_caching(self) -> None:
        """Should create cached local repository."""
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.LOCAL, paths=[FIXTURES_PATH])],
            enable_caching=True,
        )
        repo = create_repository(config)

        # Should be wrapped with caching
        assert isinstance(repo, CachingRepositoryDecorator)

    def test_create_local_repository_without_caching(self) -> None:
        """Should create local repository without caching."""
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.LOCAL, paths=[FIXTURES_PATH])],
            enable_caching=False,
        )
        repo = create_repository(config)

        # Should be raw LocalSkillRepository
        assert isinstance(repo, LocalSkillRepository)

    def test_create_repository_no_sources_raises(self) -> None:
        """Should raise ValueError if no sources configured."""
        config = RepositoryConfig(sources=[])

        with pytest.raises(ValueError, match="At least one source"):
            create_repository(config)

    def test_create_repository_local_no_paths_raises(self) -> None:
        """Should raise ValueError if local source has no paths."""
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.LOCAL, paths=[])],
        )

        with pytest.raises(ValueError, match="at least one path"):
            create_repository(config)

    def test_create_repository_multiple_sources_creates_composite(self) -> None:
        """Should create CompositeSkillRepository for multiple sources."""
        config = RepositoryConfig(
            sources=[
                SourceConfig(source_type=SourceType.LOCAL, paths=[FIXTURES_PATH]),
                SourceConfig(source_type=SourceType.LOCAL, paths=[FIXTURES_PATH]),
            ],
            enable_caching=False,
        )

        repo = create_repository(config)
        assert isinstance(repo, CompositeSkillRepository)

    def test_create_repository_git_source_raises(self) -> None:
        """Should raise NotImplementedError for git source."""
        config = RepositoryConfig(
            sources=[
                SourceConfig(source_type=SourceType.GIT, url="https://example.com")
            ],
        )

        with pytest.raises(NotImplementedError, match="Git source"):
            create_repository(config)

    def test_create_repository_oci_source_without_skills_raises(self) -> None:
        """Should raise ValueError for OCI source without skills."""
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.OCI)],
        )

        with pytest.raises(ValueError, match="at least one skill reference"):
            create_repository(config)

    def test_create_repository_oci_source_with_skills(self) -> None:
        """Should create OCISkillRepository for OCI source with skills."""
        skill_ref = OCISkillReference.from_string("ghcr.io/stacklok/test:v1")
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.OCI, oci_skills=[skill_ref])],
            enable_caching=False,
        )

        repo = create_repository(config)
        assert isinstance(repo, OCISkillRepository)


class TestCreateLocalRepository:
    """Tests for create_local_repository convenience function."""

    def test_create_with_defaults(self) -> None:
        """Should create cached repository with defaults."""
        repo = create_local_repository([FIXTURES_PATH])

        # Should be wrapped with caching by default
        assert isinstance(repo, CachingRepositoryDecorator)

    def test_create_without_caching(self) -> None:
        """Should create repository without caching."""
        repo = create_local_repository([FIXTURES_PATH], enable_caching=False)

        assert isinstance(repo, LocalSkillRepository)

    async def test_created_repository_works(self) -> None:
        """Should create a working repository."""
        repo = create_local_repository([FIXTURES_PATH])
        skills = await repo.list_all()

        # Should find skills in fixtures
        skill_names = {s.name.value for s in skills}
        assert "valid-skill" in skill_names
