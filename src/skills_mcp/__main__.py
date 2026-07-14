"""Entry point for skills-mcp server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from skills_mcp.infrastructure.config.parser import (
    ConfigError,
    create_default_config,
    find_config_file,
    load_config_from_file,
)


if TYPE_CHECKING:
    from skills_mcp.infrastructure.config.models import SkillsConfig

from skills_mcp.infrastructure.mcp.server import SkillsMCPServer
from skills_mcp.infrastructure.persistence.factory import (
    create_local_repository,
    create_repository_from_skills_config,
)


def setup_logging(log_level: str) -> None:
    """Set up logging configuration.

    Args:
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    level = getattr(logging, log_level.upper(), logging.WARNING)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="skills-mcp",
        description="MCP server for Agent Skills",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help=(
            "Path to configuration file (default: skills.yaml in CWD). "
            "If not specified and no skills.yaml exists, falls back to "
            "SKILLS_MCP_PATHS environment variable."
        ),
    )

    parser.add_argument(
        "--host",
        help="Host to bind to (overrides config file and SKILLS_MCP_HOST env var)",
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind to (overrides config file and SKILLS_MCP_PORT env var)",
    )

    parser.add_argument(
        "--validation-path",
        type=Path,
        action="append",
        dest="validation_paths",
        metavar="PATH",
        help=(
            "Directory under which the validate_skill tool may operate "
            "(repeatable). Overrides validation_paths in the config file. "
            "If neither is set, validate_skill is disabled."
        ),
    )

    return parser.parse_args()


def get_skill_paths_from_env() -> list[Path]:
    """Get skill paths from environment variable.

    Returns:
        List of paths to scan for skills.

    Raises:
        SystemExit: If no paths are configured.
    """
    paths_str = os.environ.get("SKILLS_MCP_PATHS", "")
    if not paths_str:
        sys.stderr.write(
            "Error: No configuration found.\n\n"
            "Either:\n"
            "  1. Create a skills.yaml config file in the current directory, or\n"
            "  2. Use --config to specify a config file path, or\n"
            "  3. Set SKILLS_MCP_PATHS environment variable\n\n"
            "Example config file (skills.yaml):\n"
            "  version: '1'\n"
            "  local:\n"
            "    paths:\n"
            "      - ./skills\n"
            "  oci:\n"
            "    skills:\n"
            "      - image: ghcr.io/stacklok/skills/example:v1.0.0\n\n"
            "Example env var:\n"
            "  export SKILLS_MCP_PATHS='/path/to/skills:/another/path'\n"
        )
        sys.exit(1)

    paths = [Path(p.strip()).expanduser() for p in paths_str.split(":") if p.strip()]
    if not paths:
        sys.stderr.write("Error: No valid paths found in SKILLS_MCP_PATHS.\n")
        sys.exit(1)

    return paths


def load_configuration(config_path: Path | None) -> SkillsConfig | None:
    """Load configuration from file if available.

    Args:
        config_path: Explicit config path, or None to search.

    Returns:
        Loaded SkillsConfig, or None if no config file found.

    Raises:
        SystemExit: If config file is specified but cannot be loaded.
    """
    logger = logging.getLogger(__name__)

    # If explicit path provided, it must exist
    if config_path is not None:
        if not config_path.exists():
            sys.stderr.write(f"Error: Config file not found: {config_path}\n")
            sys.exit(1)
        try:
            config = load_config_from_file(config_path)
            logger.info("Loaded configuration from: %s", config_path)
            return config
        except ConfigError as e:
            sys.stderr.write(f"Error loading config: {e}\n")
            sys.exit(1)

    # Search for default config file
    default_path = find_config_file()
    if default_path is not None:
        try:
            config = load_config_from_file(default_path)
            logger.info("Loaded configuration from: %s", default_path)
            return config
        except ConfigError as e:
            sys.stderr.write(f"Error loading config: {e}\n")
            sys.exit(1)

    return None


async def run_server() -> None:
    """Run the MCP server."""
    args = parse_args()

    # Load config (or create default with env var overrides)
    config = load_configuration(args.config)
    if config is None:
        config = create_default_config()

    # Set up logging using config (env vars already applied via parser)
    setup_logging(config.server.log_level)
    logger = logging.getLogger(__name__)

    # CLI args override config (which already has env var overrides applied)
    host = args.host if args.host is not None else config.server.host
    port = args.port if args.port is not None else config.server.port
    validation_paths = (
        args.validation_paths
        if args.validation_paths is not None
        else config.server.validation_paths
    )

    # Create repository
    if config.has_local_sources() or config.has_oci_sources():
        try:
            repository = create_repository_from_skills_config(config)
        except ValueError as e:
            sys.stderr.write(f"Error: {e}\n")
            sys.exit(1)
    else:
        # Fall back to environment variable
        paths = get_skill_paths_from_env()
        logger.info("Using paths from SKILLS_MCP_PATHS: %s", paths)
        repository = create_local_repository(paths, enable_caching=True)

    # Create and run server
    logger.info("Starting skills-mcp server on %s:%d", host, port)
    if validation_paths:
        # Enabling a filesystem-probing capability is a posture change the
        # operator should see even at the default WARNING log level.
        logger.warning("validate_skill enabled for paths: %s", validation_paths)
        for path in validation_paths:
            if not path.is_dir():
                logger.warning(
                    "Validation path does not exist or is not a directory: %s",
                    path,
                )
    server = SkillsMCPServer(
        repository,
        allowed_validation_paths=validation_paths or None,
    )
    await server.run_http(host=host, port=port)


def main() -> None:
    """Main entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
