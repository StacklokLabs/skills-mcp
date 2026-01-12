"""Configuration parser for skills-mcp.

This module provides functions to load and parse configuration files
with support for environment variable expansion.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from skills_mcp.infrastructure.config.models import SkillsConfig


class ConfigError(Exception):
    """Error loading or parsing configuration."""


# Pattern for environment variable expansion: ${VAR} or ${VAR:-default}
_ENV_VAR_PATTERN = re.compile(
    r"\$\{(?P<var>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}"
)


def _expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} and ${VAR:-default} syntax.

    Args:
        value: String that may contain environment variable references.

    Returns:
        String with environment variables expanded.

    Raises:
        ConfigError: If a required environment variable is not set.
    """

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group("var")
        default = match.group("default")

        env_value = os.environ.get(var_name)

        if env_value is not None:
            return env_value

        if default is not None:
            return default

        raise ConfigError(
            f"Environment variable '{var_name}' is not set and has no default"
        )

    return _ENV_VAR_PATTERN.sub(replacer, value)


def _expand_env_vars_recursive(obj: Any) -> Any:
    """Recursively expand environment variables in a data structure.

    Args:
        obj: A dict, list, string, or other value.

    Returns:
        The same structure with all string values expanded.
    """
    if isinstance(obj, dict):
        return {k: _expand_env_vars_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars_recursive(item) for item in obj]
    if isinstance(obj, str):
        return _expand_env_vars(obj)
    return obj


def _apply_server_env_overrides(config: SkillsConfig) -> SkillsConfig:
    """Apply environment variable overrides to server configuration.

    Environment variables take precedence over config file values:
    - SKILLS_MCP_HOST: Server host
    - SKILLS_MCP_PORT: Server port
    - SKILLS_MCP_LOG_LEVEL: Log level

    Args:
        config: The loaded configuration.

    Returns:
        Configuration with env var overrides applied.
    """
    if host := os.environ.get("SKILLS_MCP_HOST"):
        config.server.host = host
    if port := os.environ.get("SKILLS_MCP_PORT"):
        config.server.port = int(port)
    if log_level := os.environ.get("SKILLS_MCP_LOG_LEVEL"):
        config.server.log_level = log_level.upper()
    return config


def load_config(content: str) -> SkillsConfig:
    """Load configuration from a YAML string.

    Args:
        content: YAML content to parse.

    Returns:
        Parsed and validated SkillsConfig.

    Raises:
        ConfigError: If the configuration is invalid.
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML: {e}") from e

    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise ConfigError("Configuration must be a YAML mapping")

    # Expand environment variables
    try:
        data = _expand_env_vars_recursive(data)
    except ConfigError:
        raise

    # Validate with Pydantic
    try:
        config = SkillsConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"Configuration validation error: {e}") from e

    # Apply env var overrides for server settings
    return _apply_server_env_overrides(config)


def load_config_from_file(path: Path) -> SkillsConfig:
    """Load configuration from a YAML file.

    Args:
        path: Path to the configuration file.

    Returns:
        Parsed and validated SkillsConfig.

    Raises:
        ConfigError: If the file cannot be read or the configuration is invalid.
    """
    try:
        content = path.read_text()
    except OSError as e:
        raise ConfigError(f"Cannot read configuration file '{path}': {e}") from e

    return load_config(content)


def create_default_config() -> SkillsConfig:
    """Create a default configuration with environment variable overrides.

    Returns:
        Default SkillsConfig with env var overrides applied.
    """
    return _apply_server_env_overrides(SkillsConfig())


def find_config_file(search_paths: list[Path] | None = None) -> Path | None:
    """Find a configuration file in common locations.

    Searches for 'skills.yaml' in:
    1. Current working directory
    2. User config directory (~/.config/skills-mcp/)
    3. Additional search paths if provided

    Args:
        search_paths: Additional paths to search (optional).

    Returns:
        Path to the first configuration file found, or None.
    """
    candidates: list[Path] = [
        Path.cwd() / "skills.yaml",
        Path.home() / ".config" / "skills-mcp" / "skills.yaml",
    ]

    if search_paths:
        candidates.extend(search_paths)

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    return None
