"""Tests for configuration models."""

from pathlib import Path

import pytest

from skills_mcp.infrastructure.config.models import (
    LocalSourceConfig,
    OCIAuthConfig,
    OCISkillConfig,
    OCISourceConfig,
    SkillsConfig,
)


class TestLocalSourceConfig:
    """Tests for LocalSourceConfig."""

    def test_empty_paths(self) -> None:
        """Should allow empty paths list."""
        config = LocalSourceConfig()
        assert config.paths == []

    def test_expands_tilde(self) -> None:
        """Should expand ~ in paths."""
        config = LocalSourceConfig(paths=["~/skills"])
        assert config.paths[0] == Path.home() / "skills"

    def test_multiple_paths(self) -> None:
        """Should handle multiple paths."""
        config = LocalSourceConfig(paths=["/path/one", "/path/two"])
        assert len(config.paths) == 2


class TestOCIAuthConfig:
    """Tests for OCIAuthConfig."""

    def test_empty_auth(self) -> None:
        """Should allow empty auth."""
        config = OCIAuthConfig()
        assert config.username is None
        assert config.password is None

    def test_with_credentials(self) -> None:
        """Should store credentials."""
        config = OCIAuthConfig(username="user", password="pass")  # noqa: S106
        assert config.username == "user"
        assert config.password == "pass"  # noqa: S105


class TestOCISkillConfig:
    """Tests for OCISkillConfig."""

    def test_requires_image(self) -> None:
        """Should require image field."""
        config = OCISkillConfig(image="ghcr.io/org/skill:v1")
        assert config.image == "ghcr.io/org/skill:v1"


class TestOCISourceConfig:
    """Tests for OCISourceConfig."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        config = OCISourceConfig()

        assert config.cache_dir is None
        assert config.cache_ttl == 3600
        assert config.verify_tls is True
        assert config.skills == []
        assert config.auth == {}

    def test_expands_cache_dir(self) -> None:
        """Should expand ~ in cache_dir."""
        config = OCISourceConfig(cache_dir="~/.cache/test")
        assert config.cache_dir == Path.home() / ".cache" / "test"

    def test_cache_dir_accepts_path_object(self) -> None:
        """Should accept Path object for cache_dir."""
        path = Path("/absolute/path/to/cache")
        config = OCISourceConfig(cache_dir=path)
        assert config.cache_dir == path

    def test_cache_ttl_validation(self) -> None:
        """Should reject negative cache_ttl."""
        with pytest.raises(ValueError):
            OCISourceConfig(cache_ttl=-1)

    def test_with_skills(self) -> None:
        """Should accept list of skills."""
        config = OCISourceConfig(
            skills=[
                OCISkillConfig(image="ghcr.io/org/skill1:v1"),
                OCISkillConfig(image="ghcr.io/org/skill2:v2"),
            ]
        )
        assert len(config.skills) == 2

    def test_with_auth(self) -> None:
        """Should accept auth config per registry."""
        config = OCISourceConfig(
            auth={
                "ghcr.io": OCIAuthConfig(username="user", password="pass"),  # noqa: S106
            }
        )
        assert "ghcr.io" in config.auth


class TestSkillsConfig:
    """Tests for SkillsConfig."""

    def test_empty_config(self) -> None:
        """Should allow empty config."""
        config = SkillsConfig()

        assert config.version == "1"
        assert config.local is None
        assert config.oci is None

    def test_has_local_sources_empty(self) -> None:
        """Should return False when no local sources."""
        config = SkillsConfig()
        assert config.has_local_sources() is False

    def test_has_local_sources_with_paths(self) -> None:
        """Should return True when local paths configured."""
        config = SkillsConfig(local=LocalSourceConfig(paths=["/skills"]))
        assert config.has_local_sources() is True

    def test_has_local_sources_empty_paths(self) -> None:
        """Should return False when local config but no paths."""
        config = SkillsConfig(local=LocalSourceConfig(paths=[]))
        assert config.has_local_sources() is False

    def test_has_oci_sources_empty(self) -> None:
        """Should return False when no OCI sources."""
        config = SkillsConfig()
        assert config.has_oci_sources() is False

    def test_has_oci_sources_with_skills(self) -> None:
        """Should return True when OCI skills configured."""
        config = SkillsConfig(
            oci=OCISourceConfig(
                skills=[OCISkillConfig(image="ghcr.io/org/skill:v1")]
            )
        )
        assert config.has_oci_sources() is True

    def test_has_oci_sources_empty_skills(self) -> None:
        """Should return False when OCI config but no skills."""
        config = SkillsConfig(oci=OCISourceConfig(skills=[]))
        assert config.has_oci_sources() is False

    def test_is_empty_when_no_sources(self) -> None:
        """Should return True when no sources configured."""
        config = SkillsConfig()
        assert config.is_empty() is True

    def test_is_empty_with_local(self) -> None:
        """Should return False when local sources configured."""
        config = SkillsConfig(local=LocalSourceConfig(paths=["/skills"]))
        assert config.is_empty() is False

    def test_is_empty_with_oci(self) -> None:
        """Should return False when OCI sources configured."""
        config = SkillsConfig(
            oci=OCISourceConfig(
                skills=[OCISkillConfig(image="ghcr.io/org/skill:v1")]
            )
        )
        assert config.is_empty() is False
