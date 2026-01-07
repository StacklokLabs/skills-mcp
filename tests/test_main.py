"""Tests for __main__.py entry point."""

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skills_mcp.__main__ import (
    get_server_config,
    get_skill_paths,
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


class TestGetSkillPaths:
    """Tests for get_skill_paths function."""

    def test_returns_paths_from_env(self) -> None:
        """Should return paths from SKILLS_MCP_PATHS."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": "/path/one:/path/two"}):
            paths = get_skill_paths()

        assert paths == [Path("/path/one"), Path("/path/two")]

    def test_single_path(self) -> None:
        """Should handle single path."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": "/single/path"}):
            paths = get_skill_paths()

        assert paths == [Path("/single/path")]

    def test_strips_whitespace(self) -> None:
        """Should strip whitespace from paths."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": " /path/one : /path/two "}):
            paths = get_skill_paths()

        assert paths == [Path("/path/one"), Path("/path/two")]

    def test_ignores_empty_segments(self) -> None:
        """Should ignore empty segments."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": "/path/one::/path/two:"}):
            paths = get_skill_paths()

        assert paths == [Path("/path/one"), Path("/path/two")]

    def test_exits_when_env_not_set(self) -> None:
        """Should exit with error when SKILLS_MCP_PATHS not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SKILLS_MCP_PATHS", None)

            with pytest.raises(SystemExit) as exc_info:
                get_skill_paths()

            assert exc_info.value.code == 1

    def test_exits_when_env_is_empty(self) -> None:
        """Should exit with error when SKILLS_MCP_PATHS is empty."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": ""}):
            with pytest.raises(SystemExit) as exc_info:
                get_skill_paths()

            assert exc_info.value.code == 1

    def test_exits_when_env_is_only_colons(self) -> None:
        """Should exit with error when SKILLS_MCP_PATHS has only separators."""
        with patch.dict(os.environ, {"SKILLS_MCP_PATHS": ":::"}):
            with pytest.raises(SystemExit) as exc_info:
                get_skill_paths()

            assert exc_info.value.code == 1


class TestGetServerConfig:
    """Tests for get_server_config function."""

    def test_default_host_and_port(self) -> None:
        """Should use defaults when env not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SKILLS_MCP_HOST", None)
            os.environ.pop("SKILLS_MCP_PORT", None)

            host, port = get_server_config()

        assert host == DEFAULT_HOST
        assert port == DEFAULT_PORT

    def test_custom_host(self) -> None:
        """Should use custom host from env."""
        with patch.dict(os.environ, {"SKILLS_MCP_HOST": "192.168.1.100"}):
            host, port = get_server_config()

        assert host == "192.168.1.100"
        assert port == DEFAULT_PORT

    def test_custom_port(self) -> None:
        """Should use custom port from env."""
        with patch.dict(os.environ, {"SKILLS_MCP_PORT": "9999"}):
            host, port = get_server_config()

        assert host == DEFAULT_HOST
        assert port == 9999

    def test_custom_host_and_port(self) -> None:
        """Should use custom host and port from env."""
        all_interfaces = "0.0.0.0"  # noqa: S104
        with patch.dict(
            os.environ, {"SKILLS_MCP_HOST": all_interfaces, "SKILLS_MCP_PORT": "8080"}
        ):
            host, port = get_server_config()

        assert host == all_interfaces
        assert port == 8080

    def test_invalid_port_exits(self) -> None:
        """Should exit with error for invalid port."""
        with patch.dict(os.environ, {"SKILLS_MCP_PORT": "not_a_number"}):
            with pytest.raises(SystemExit) as exc_info:
                get_server_config()

            assert exc_info.value.code == 1

    def test_empty_port_exits(self) -> None:
        """Should exit with error for empty port."""
        with patch.dict(os.environ, {"SKILLS_MCP_PORT": ""}):
            with pytest.raises(SystemExit) as exc_info:
                get_server_config()

            assert exc_info.value.code == 1
