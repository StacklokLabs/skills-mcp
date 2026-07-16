"""Tests for __main__.py entry point."""

import argparse
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skills_mcp.__main__ import (
    get_skill_paths_from_env,
    load_configuration,
    parse_args,
    run_server,
    setup_logging,
)
from skills_mcp.infrastructure.config.models import (
    GitSkillConfig,
    GitSourceConfig,
    LocalSourceConfig,
    ServerConfig,
    SkillsConfig,
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_warning_log_level(self) -> None:
        """Should configure WARNING log level when passed."""
        with patch("skills_mcp.__main__.logging.basicConfig") as mock_basic:
            setup_logging("WARNING")

        mock_basic.assert_called_once()
        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.WARNING

    def test_debug_log_level(self) -> None:
        """Should configure DEBUG level when passed."""
        with patch("skills_mcp.__main__.logging.basicConfig") as mock_basic:
            setup_logging("DEBUG")

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    def test_info_log_level(self) -> None:
        """Should configure INFO level when passed."""
        with patch("skills_mcp.__main__.logging.basicConfig") as mock_basic:
            setup_logging("INFO")

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.INFO

    def test_error_log_level(self) -> None:
        """Should configure ERROR level when passed."""
        with patch("skills_mcp.__main__.logging.basicConfig") as mock_basic:
            setup_logging("ERROR")

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.ERROR

    def test_lowercase_log_level(self) -> None:
        """Should handle lowercase log level."""
        with patch("skills_mcp.__main__.logging.basicConfig") as mock_basic:
            setup_logging("debug")

        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    def test_invalid_log_level_defaults_to_warning(self) -> None:
        """Should default to WARNING for invalid log level."""
        with patch("skills_mcp.__main__.logging.basicConfig") as mock_basic:
            setup_logging("INVALID")

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
        """Should use None defaults when no args provided.

        Host and port defaults come from config system, not argparse.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SKILLS_MCP_HOST", None)
            os.environ.pop("SKILLS_MCP_PORT", None)
            with patch("sys.argv", ["skills-mcp"]):
                args = parse_args()

        assert args.config is None
        assert args.host is None
        assert args.port is None

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

    def test_cli_args_override_defaults(self) -> None:
        """Should use CLI args when provided, not defaults from env.

        CLI args take precedence over config/env vars.
        """
        with patch(
            "sys.argv", ["skills-mcp", "--host", "192.168.1.1", "--port", "9999"]
        ):
            args = parse_args()

        assert args.host == "192.168.1.1"
        assert args.port == 9999

    def test_validation_path_defaults_to_none(self) -> None:
        """No --validation-path yields None (distinct from an empty list)."""
        with patch("sys.argv", ["skills-mcp"]):
            args = parse_args()

        assert args.validation_paths is None

    def test_single_validation_path(self) -> None:
        """A single --validation-path is collected into a list."""
        with patch("sys.argv", ["skills-mcp", "--validation-path", "/skills"]):
            args = parse_args()

        assert args.validation_paths == [Path("/skills")]

    def test_validation_path_is_repeatable(self) -> None:
        """--validation-path may be given multiple times."""
        with patch(
            "sys.argv",
            [
                "skills-mcp",
                "--validation-path",
                "/skills",
                "--validation-path",
                "/more",
            ],
        ):
            args = parse_args()

        assert args.validation_paths == [Path("/skills"), Path("/more")]


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

        with patch("skills_mcp.__main__.find_config_file", return_value=config_file):
            result = load_configuration(None)

        assert result is not None
        assert result.version == "1"


class TestRunServerSourceGating:
    """Tests that any configured source type starts the server from config."""

    async def test_git_only_config_uses_skills_config_repository(self) -> None:
        """A git-only skills.yaml must not fall through to the env fallback.

        Regression: run_server used to gate on local/OCI sources only, so a
        valid git-only configuration exited with "no configuration found".
        """
        args = argparse.Namespace(
            config=None, host=None, port=None, validation_paths=None
        )
        config = SkillsConfig(
            git=GitSourceConfig(
                skills=[GitSkillConfig(repo="git://github.com/org/skill@v1")]
            )
        )
        server_cls = MagicMock()
        server_cls.return_value.run_http = AsyncMock()
        repo_factory = MagicMock(return_value=MagicMock())
        env_fallback = MagicMock()
        with (
            patch("skills_mcp.__main__.parse_args", return_value=args),
            patch("skills_mcp.__main__.load_configuration", return_value=config),
            patch(
                "skills_mcp.__main__.create_repository_from_skills_config",
                repo_factory,
            ),
            patch("skills_mcp.__main__.get_skill_paths_from_env", env_fallback),
            patch("skills_mcp.__main__.SkillsMCPServer", server_cls),
        ):
            await run_server()

        repo_factory.assert_called_once_with(config)
        env_fallback.assert_not_called()


class TestRunServerValidationPaths:
    """Tests for validation_paths precedence and wiring into the server."""

    @staticmethod
    def _args(validation_paths: list[Path] | None) -> argparse.Namespace:
        return argparse.Namespace(
            config=None,
            host=None,
            port=None,
            validation_paths=validation_paths,
        )

    @staticmethod
    def _config(validation_paths: list[Path]) -> SkillsConfig:
        return SkillsConfig(
            local=LocalSourceConfig(paths=[Path("/skills")]),
            server=ServerConfig(validation_paths=validation_paths),
        )

    async def _run(self, args: argparse.Namespace, config: SkillsConfig) -> MagicMock:
        """Run run_server with mocked repo + server, return the server mock."""
        server_cls = MagicMock()
        server_cls.return_value.run_http = AsyncMock()
        with (
            patch("skills_mcp.__main__.parse_args", return_value=args),
            patch("skills_mcp.__main__.load_configuration", return_value=config),
            patch(
                "skills_mcp.__main__.create_repository_from_skills_config",
                return_value=MagicMock(),
            ),
            patch("skills_mcp.__main__.SkillsMCPServer", server_cls),
        ):
            await run_server()
        return server_cls

    async def test_cli_overrides_config(self) -> None:
        """CLI --validation-path takes precedence over the config file."""
        args = self._args([Path("/cli")])
        config = self._config([Path("/config")])

        server_cls = await self._run(args, config)

        _, kwargs = server_cls.call_args
        assert kwargs["allowed_validation_paths"] == [Path("/cli")]

    async def test_falls_back_to_config(self) -> None:
        """Config validation_paths are used when no CLI flag is given."""
        args = self._args(None)
        config = self._config([Path("/config")])

        server_cls = await self._run(args, config)

        _, kwargs = server_cls.call_args
        assert kwargs["allowed_validation_paths"] == [Path("/config")]

    async def test_disabled_when_neither_set(self) -> None:
        """With no CLI flag and empty config, validation is disabled (None)."""
        args = self._args(None)
        config = self._config([])

        server_cls = await self._run(args, config)

        _, kwargs = server_cls.call_args
        assert kwargs["allowed_validation_paths"] is None

    async def test_warns_when_validation_path_missing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A nonexistent validation path warns but does not crash startup."""
        args = self._args([Path("/definitely/does/not/exist")])
        config = self._config([])

        with caplog.at_level(logging.WARNING, logger="skills_mcp.__main__"):
            await self._run(args, config)

        assert any(
            "Validation path does not exist or is not a directory" in r.message
            for r in caplog.records
        )

    async def test_enabled_disclosure_logged_at_warning(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """The validate_skill enable disclosure is visible at WARNING level."""
        args = self._args([tmp_path])
        config = self._config([])

        with caplog.at_level(logging.WARNING, logger="skills_mcp.__main__"):
            await self._run(args, config)

        enabled = [r for r in caplog.records if "validate_skill enabled" in r.message]
        assert enabled
        assert enabled[0].levelno == logging.WARNING
