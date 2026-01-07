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
    find_config_file,
    load_config_from_file,
)


if TYPE_CHECKING:
    from skills_mcp.infrastructure.config.models import SkillsConfig

from skills_mcp.infrastructure.mcp.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    SkillsMCPServer,
)
from skills_mcp.infrastructure.persistence.factory import (
    create_local_repository,
    create_repository_from_skills_config,
)


def setup_logging() -> None:
    """Set up logging configuration."""
    level_str = os.environ.get("SKILLS_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_str, logging.WARNING)

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
        default=os.environ.get("SKILLS_MCP_HOST", DEFAULT_HOST),
        help=f"Host to bind to (default: {DEFAULT_HOST})",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SKILLS_MCP_PORT", str(DEFAULT_PORT))),
        help=f"Port to bind to (default: {DEFAULT_PORT})",
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
    setup_logging()
    logger = logging.getLogger(__name__)

    args = parse_args()

    # Try to load config file
    config = load_configuration(args.config)

    if config is not None:
        # Create repository from config
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
    logger.info("Starting skills-mcp server on %s:%d", args.host, args.port)
    server = SkillsMCPServer(repository)
    await server.run_http(host=args.host, port=args.port)


def main() -> None:
    """Main entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
