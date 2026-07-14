"""Tests for configuration models."""

from pathlib import Path

import pytest

from skills_mcp.infrastructure.config.models import (
    LocalSourceConfig,
    OCIAuthConfig,
    OCISkillConfig,
    OCISourceConfig,
    ServerConfig,
    SkillsConfig,
)


class TestServerConfigValidationPaths:
    """Tests for ServerConfig.validation_paths."""

    def test_defaults_to_empty(self) -> None:
        """validation_paths defaults to an empty list (validation disabled)."""
        config = ServerConfig()
        assert config.validation_paths == []

    def test_parses_paths(self) -> None:
        """validation_paths accepts a list of path strings."""
        config = ServerConfig(validation_paths=["/skills", "/more"])
        assert config.validation_paths == [Path("/skills"), Path("/more")]

    def test_expands_tilde(self) -> None:
        """validation_paths expands ~ to the home directory."""
        config = ServerConfig(validation_paths=["~/skills"])
        assert config.validation_paths[0] == Path.home() / "skills"


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

    def test_get_username_direct_value(self) -> None:
        """Should return direct username value."""
        config = OCIAuthConfig(username="myuser")
        assert config.get_username() == "myuser"

    def test_get_password_direct_value(self) -> None:
        """Should return direct password value."""
        config = OCIAuthConfig(password="mypass")  # noqa: S106
        assert config.get_password() == "mypass"

    def test_get_username_from_file(self, tmp_path: Path) -> None:
        """Should read username from file."""
        cred_file = tmp_path / "username"
        cred_file.write_text("file-user\n")

        config = OCIAuthConfig(username_file=cred_file)
        assert config.get_username() == "file-user"

    def test_get_password_from_file(self, tmp_path: Path) -> None:
        """Should read password from file."""
        cred_file = tmp_path / "password"
        cred_file.write_text("file-pass\n")

        config = OCIAuthConfig(password_file=cred_file)
        assert config.get_password() == "file-pass"

    def test_file_takes_precedence(self, tmp_path: Path) -> None:
        """File reference should take precedence over direct value."""
        cred_file = tmp_path / "password"
        cred_file.write_text("from-file")

        config = OCIAuthConfig(
            password="direct-value",  # noqa: S106
            password_file=cred_file,
        )
        assert config.get_password() == "from-file"

    def test_strips_whitespace_from_file(self, tmp_path: Path) -> None:
        """Should strip leading/trailing whitespace from file content."""
        cred_file = tmp_path / "password"
        cred_file.write_text("  secret-token  \n\n")

        config = OCIAuthConfig(password_file=cred_file)
        assert config.get_password() == "secret-token"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Should raise ValueError when file doesn't exist."""
        config = OCIAuthConfig(password_file=tmp_path / "nonexistent")
        with pytest.raises(ValueError, match="file not found"):
            config.get_password()

    def test_expands_tilde_in_file_path(self) -> None:
        """Should expand ~ in file paths."""
        config = OCIAuthConfig(password_file="~/.secrets/token")  # noqa: S106
        assert config.password_file == Path.home() / ".secrets" / "token"


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
            oci=OCISourceConfig(skills=[OCISkillConfig(image="ghcr.io/org/skill:v1")])
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
            oci=OCISourceConfig(skills=[OCISkillConfig(image="ghcr.io/org/skill:v1")])
        )
        assert config.is_empty() is False
