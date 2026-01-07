"""Tests for __main__.py entry point."""

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skills_mcp.__main__ import (
    get_skill_paths_from_env,
    load_configuration,
    parse_args,
    setup_logging,
)
from skills_mcp.infrastructure.mcp.server import DEFAULT_HOST, DEFAULT_PORT


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_default_log_level_is_warning(self) -> None:
        """Should configure WARNING as default log level."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("skills_mcp.__main__.logging.basicConfig") as mock_basic,
        ):
            os.environ.pop("SKILLS_MCP_LOG_LEVEL", None)
            setup_logging()

        mock_basic.assert_called_once()
        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.WARNING

    def test_respects_debug_log_level(self) -> None:
        """Should configure DEBUG level when set in env."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "DEBUG"}),
            patch("skills_mcp.__main__.logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    def test_respects_info_log_level(self) -> None:
        """Should configure INFO level when set in env."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "INFO"}),
            patch("skills_mcp.__main__.logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.INFO

    def test_respects_error_log_level(self) -> None:
        """Should configure ERROR level when set in env."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "ERROR"}),
            patch("skills_mcp.__main__.logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.ERROR

    def test_lowercase_log_level(self) -> None:
        """Should handle lowercase log level."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "debug"}),
            patch("skills_mcp.__main__.logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    def test_invalid_log_level_defaults_to_warning(self) -> None:
        """Should default to WARNING for invalid log level."""
        with (
            patch.dict(os.environ, {"SKILLS_MCP_LOG_LEVEL": "INVALID"}),
            patch("skills_mcp.__main__.logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.WARNING


class TestGetSkillPathsFromEnv:
    """Tests for get_skill_paths_from_env function."""

    def test_returns_paths_from_env(self) -> None:
        """Should return paths from SKILLS_MCP_PATHS."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": "/path/one:/path/two"}):
            paths = get_skill_paths_from_env()

        assert paths == [Path("/path/one"), Path("/path/two")]

    def test_single_path(self) -> None:
        """Should handle single path."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": "/single/path"}):
            paths = get_skill_paths_from_env()

        assert paths == [Path("/single/path")]

    def test_strips_whitespace(self) -> None:
        """Should strip whitespace from paths."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": " /path/one : /path/two "}):
            paths = get_skill_paths_from_env()

        assert paths == [Path("/path/one"), Path("/path/two")]

    def test_ignores_empty_segments(self) -> None:
        """Should ignore empty segments."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": "/path/one::/path/two:"}):
            paths = get_skill_paths_from_env()

        assert paths == [Path("/path/one"), Path("/path/two")]

    def test_exits_when_env_not_set(self) -> None:
        """Should exit with error when SKILLS_MCP_PATHS not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SKILLS_MCP_PATHS", None)

            with pytest.raises(SystemExit) as exc_info:
                get_skill_paths_from_env()

            assert exc_info.value.code == 1

    def test_exits_when_env_is_empty(self) -> None:
        """Should exit with error when SKILLS_MCP_PATHS is empty."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": ""}):
            with pytest.raises(SystemExit) as exc_info:
                get_skill_paths_from_env()

            assert exc_info.value.code == 1

    def test_exits_when_env_is_only_colons(self) -> None:
        """Should exit with error when SKILLS_MCP_PATHS has only separators."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": ":::"}):
            with pytest.raises(SystemExit) as exc_info:
                get_skill_paths_from_env()

            assert exc_info.value.code == 1


class TestParseArgs:
    """Tests for parse_args function."""

    def test_default_values(self) -> None:
        """Should use defaults when no args provided."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SKILLS_MCP_HOST", None)
            os.environ.pop("SKILLS_MCP_PORT", None)
            with patch("sys.argv", ["skills-mcp"]):
                args = parse_args()

        assert args.config is None
        assert args.host == DEFAULT_HOST
        assert args.port == DEFAULT_PORT

    def test_config_short_flag(self) -> None:
        """Should accept -c for config file."""
        with patch("sys.argv", ["skills-mcp", "-c", "/path/to/config.yaml"]):
            args = parse_args()

        assert args.config == Path("/path/to/config.yaml")

    def test_config_long_flag(self) -> None:
        """Should accept --config for config file."""
        with patch("sys.argv", ["skills-mcp", "--config", "/path/to/config.yaml"]):
            args = parse_args()

        assert args.config == Path("/path/to/config.yaml")

    def test_custom_host(self) -> None:
        """Should accept --host flag."""
        with patch("sys.argv", ["skills-mcp", "--host", "192.168.1.100"]):
            args = parse_args()

        assert args.host == "192.168.1.100"

    def test_custom_port(self) -> None:
        """Should accept --port flag."""
        with patch("sys.argv", ["skills-mcp", "--port", "9999"]):
            args = parse_args()

        assert args.port == 9999

    def test_env_vars_as_defaults(self) -> None:
        """Should use env vars as defaults for host/port."""
        all_interfaces = "0.0.0.0"  # noqa: S104
        with (
            patch.dict(
                os.environ,
                {"SKILLS_MCP_HOST": all_interfaces, "SKILLS_MCP_PORT": "8080"},
            ),
            patch("sys.argv", ["skills-mcp"]),
        ):
            args = parse_args()

        assert args.host == all_interfaces
        assert args.port == 8080


class TestLoadConfiguration:
    """Tests for load_configuration function."""

    def test_returns_none_when_no_config_found(self) -> None:
        """Should return None when no config file exists."""
        with patch("skills_mcp.__main__.find_config_file", return_value=None):
            result = load_configuration(None)

        assert result is None

    def test_exits_when_explicit_config_not_found(self) -> None:
        """Should exit when explicit config path doesn't exist."""
        with pytest.raises(SystemExit) as exc_info:
            load_configuration(Path("/nonexistent/config.yaml"))

        assert exc_info.value.code == 1

    def test_loads_explicit_config(self, tmp_path: Path) -> None:
        """Should load config from explicit path."""
        config_file = tmp_path / "skills.yaml"
        config_file.write_text("version: '1'\nlocal:\n  paths:\n    - ./skills\n")

        result = load_configuration(config_file)

        assert result is not None
        assert result.version == "1"

    def test_loads_default_config(self, tmp_path: Path) -> None:
        """Should load config from default location."""
        config_file = tmp_path / "skills.yaml"
        config_file.write_text("version: '1'\nlocal:\n  paths:\n    - ./skills\n")

        with patch(
            "skills_mcp.__main__.find_config_file", return_value=config_file
        ):
            result = load_configuration(None)

        assert result is not None
        assert result.version == "1"
