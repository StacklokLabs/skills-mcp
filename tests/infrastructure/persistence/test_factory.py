"""Tests for repository factory."""

from pathlib import Path

import pytest

from skills_mcp.infrastructure.config.models import (
    GitAuthConfig,
    GitSkillConfig,
    GitSourceConfig,
    SkillsConfig,
)
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
from skills_mcp.infrastructure.persistence.git_models import GitSkillReference
from skills_mcp.infrastructure.persistence.git_repository import GitSkillRepository
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

    def test_create_repository_git_source_with_skills(self) -> None:
        """Should create GitSkillRepository for a git source with references."""
        skill_ref = GitSkillReference.from_string("git://github.com/org/repo@v1")
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.GIT, git_skills=[skill_ref])],
            enable_caching=False,
        )

        repo = create_repository(config)
        assert isinstance(repo, GitSkillRepository)

    def test_create_repository_git_source_without_skills_raises(self) -> None:
        """Should raise ValueError for a git source without references."""
        config = RepositoryConfig(
            sources=[SourceConfig(source_type=SourceType.GIT)],
        )

        with pytest.raises(ValueError, match="at least one skill reference"):
            create_repository(config)

    def test_mixed_local_git_oci_creates_composite(self) -> None:
        """Local + git + oci sources compose in precedence order."""
        config = RepositoryConfig(
            sources=[
                SourceConfig(source_type=SourceType.LOCAL, paths=[FIXTURES_PATH]),
                SourceConfig(
                    source_type=SourceType.GIT,
                    git_skills=[
                        GitSkillReference.from_string("git://github.com/org/repo@v1")
                    ],
                ),
                SourceConfig(
                    source_type=SourceType.OCI,
                    oci_skills=[OCISkillReference.from_string("ghcr.io/o/s:v1")],
                ),
            ],
            enable_caching=False,
        )

        repo = create_repository(config)
        assert isinstance(repo, CompositeSkillRepository)
        assert isinstance(repo._repositories[0], LocalSkillRepository)
        assert isinstance(repo._repositories[1], GitSkillRepository)
        assert isinstance(repo._repositories[2], OCISkillRepository)

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


class TestCreateRepositoryFromSkillsConfig:
    """Tests for create_repository_from_skills_config with a git section."""

    def test_git_section_creates_git_repository(self) -> None:
        """A git section produces a working GitSkillRepository."""
        config = SkillsConfig(
            git=GitSourceConfig(
                skills=[GitSkillConfig(repo="git://github.com/org/repo@v1.0.0")],
                auth={"github.com": GitAuthConfig(password="tok")},  # noqa: S106
            )
        )
        repo = create_repository_from_skills_config(config, enable_caching=False)
        assert isinstance(repo, GitSkillRepository)

    def test_no_sources_error_names_git(self) -> None:
        """The no-sources error mentions the git section (DONE #6)."""
        config = SkillsConfig()
        with pytest.raises(ValueError, match="git"):
            create_repository_from_skills_config(config)
