"""Tests for configuration parser."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skills_mcp.infrastructure.config.parser import (
    ConfigError,
    create_default_config,
    find_config_file,
    load_config,
    load_config_from_file,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_empty_yaml(self) -> None:
        """Should return default config for empty YAML."""
        config = load_config("")

        assert config.version == "1"
        assert config.local is None
        assert config.oci is None

    def test_minimal_local_config(self) -> None:
        """Should parse minimal local config."""
        yaml_content = """
version: "1"
local:
  paths:
    - /path/to/skills
"""
        config = load_config(yaml_content)

        assert config.version == "1"
        assert config.local is not None
        assert len(config.local.paths) == 1
        assert config.local.paths[0] == Path("/path/to/skills")

    def test_minimal_oci_config(self) -> None:
        """Should parse minimal OCI config."""
        yaml_content = """
version: "1"
oci:
  skills:
    - image: ghcr.io/org/skill:v1.0.0
"""
        config = load_config(yaml_content)

        assert config.oci is not None
        assert len(config.oci.skills) == 1
        assert config.oci.skills[0].image == "ghcr.io/org/skill:v1.0.0"

    def test_full_config(self) -> None:
        """Should parse full config with all options."""
        yaml_content = """
version: "1"
local:
  paths:
    - /local/skills
    - ~/my-skills
oci:
  cache_dir: ~/.cache/my-skills
  cache_ttl: 7200
  verify_tls: false
  skills:
    - image: ghcr.io/org/skill1:v1
    - image: ghcr.io/org/skill2:v2
  auth:
    ghcr.io:
      username: myuser
      password: mypass
"""
        config = load_config(yaml_content)

        assert len(config.local.paths) == 2
        assert config.oci.cache_ttl == 7200
        assert config.oci.verify_tls is False
        assert len(config.oci.skills) == 2
        assert "ghcr.io" in config.oci.auth
        assert config.oci.auth["ghcr.io"].username == "myuser"

    def test_env_var_expansion(self) -> None:
        """Should expand environment variables."""
        yaml_content = """
version: "1"
oci:
  skills:
    - image: ghcr.io/${TEST_ORG}/skill:${TEST_VERSION}
"""
        with patch.dict(os.environ, {"TEST_ORG": "myorg", "TEST_VERSION": "v2.0"}):
            config = load_config(yaml_content)

        assert config.oci.skills[0].image == "ghcr.io/myorg/skill:v2.0"

    def test_env_var_with_default(self) -> None:
        """Should use default when env var not set."""
        yaml_content = """
version: "1"
oci:
  skills:
    - image: ghcr.io/${TEST_ORG:-defaultorg}/skill:v1
"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TEST_ORG", None)
            config = load_config(yaml_content)

        assert config.oci.skills[0].image == "ghcr.io/defaultorg/skill:v1"

    def test_missing_env_var_raises(self) -> None:
        """Should raise ConfigError for missing env var without default."""
        yaml_content = """
oci:
  skills:
    - image: ghcr.io/${MISSING_VAR}/skill:v1
"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MISSING_VAR", None)
            with pytest.raises(ConfigError, match="MISSING_VAR"):
                load_config(yaml_content)

    def test_invalid_yaml_raises(self) -> None:
        """Should raise ConfigError for invalid YAML."""
        yaml_content = """
this: is: not: valid: yaml:
  - missing
"""
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(yaml_content)

    def test_non_mapping_raises(self) -> None:
        """Should raise ConfigError when YAML is not a mapping."""
        yaml_content = """
- item1
- item2
"""
        with pytest.raises(ConfigError, match="must be a YAML mapping"):
            load_config(yaml_content)

    def test_validation_error_raises(self) -> None:
        """Should raise ConfigError for validation errors."""
        yaml_content = """
oci:
  cache_ttl: -1
"""
        with pytest.raises(ConfigError, match="validation error"):
            load_config(yaml_content)


class TestLoadConfigFromFile:
    """Tests for load_config_from_file function."""

    def test_loads_file(self, tmp_path: Path) -> None:
        """Should load config from file."""
        config_file = tmp_path / "skills.yaml"
        config_file.write_text("version: '1'\nlocal:\n  paths:\n    - ./skills\n")

        config = load_config_from_file(config_file)

        assert config.version == "1"
        assert config.has_local_sources()

    def test_missing_file_raises(self) -> None:
        """Should raise ConfigError for missing file."""
        with pytest.raises(ConfigError, match="Cannot read"):
            load_config_from_file(Path("/nonexistent/file.yaml"))


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_in_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should find skills.yaml in current directory."""
        config_file = tmp_path / "skills.yaml"
        config_file.write_text("version: '1'")
        monkeypatch.chdir(tmp_path)

        found = find_config_file()

        assert found == config_file

    def test_returns_none_when_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return None when no config file found."""
        monkeypatch.chdir(tmp_path)

        found = find_config_file()

        assert found is None

    def test_checks_additional_paths(self, tmp_path: Path) -> None:
        """Should check additional search paths."""
        config_file = tmp_path / "custom" / "skills.yaml"
        config_file.parent.mkdir()
        config_file.write_text("version: '1'")

        found = find_config_file([config_file])

        assert found == config_file


class TestServerEnvOverrides:
    """Tests for server environment variable overrides."""

    def test_host_override(self) -> None:
        """Should override host from SKILLS_MCP_HOST."""
        with patch.dict(os.environ, {"SKILLS_MCP_HOST": "0.0.0.0"}):  # noqa: S104
            config = create_default_config()

        assert config.server.host == "0.0.0.0"  # noqa: S104

    def test_port_override(self) -> None:
        """Should override port from SKILLS_MCP_PORT."""
        with patch.dict(os.environ, {"SKILLS_MCP_PORT": "9090"}):
            config = create_default_config()

        assert config.server.port == 9090

    def test_log_level_override(self) -> None:
        """Should override log level from SKILLS_MCP_LOG_LEVEL."""
        with patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "DEBUG"}):
            config = create_default_config()

        assert config.server.log_level == "DEBUG"

    def test_log_level_normalized_to_uppercase(self) -> None:
        """Should normalize log level to uppercase."""
        with patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "debug"}):
            config = create_default_config()

        assert config.server.log_level == "DEBUG"

    def test_invalid_port_not_integer_raises(self) -> None:
        """Should raise ConfigError for non-integer port."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_PORT": "not-a-number"}),
            pytest.raises(ConfigError, match="must be a valid integer"),
        ):
            create_default_config()

    def test_invalid_port_out_of_range_raises(self) -> None:
        """Should raise ConfigError for port out of range."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_PORT": "99999"}),
            pytest.raises(ConfigError, match="must be between 1 and 65535"),
        ):
            create_default_config()

    def test_invalid_port_zero_raises(self) -> None:
        """Should raise ConfigError for port 0."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_PORT": "0"}),
            pytest.raises(ConfigError, match="must be between 1 and 65535"),
        ):
            create_default_config()

    def test_invalid_log_level_raises(self) -> None:
        """Should raise ConfigError for invalid log level."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "INVALID"}),
            pytest.raises(ConfigError, match="must be DEBUG, INFO, WARNING"),
        ):
            create_default_config()
