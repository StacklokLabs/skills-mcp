"""Entry point for skills-mcp server."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from skills_mcp.infrastructure.mcp.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    SkillsMCPServer,
)
from skills_mcp.infrastructure.persistence.factory import create_local_repository


def setup_logging() -> None:
    """Set up logging configuration."""
    level_str = os.environ.get("SKILLS_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_str, logging.WARNING)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )


def get_skill_paths() -> list[Path]:
    """Get skill paths from environment variable.

    Returns:
        List of paths to scan for skills.

    Raises:
        SystemExit: If no paths are configured.
    """
    paths_str = os.environ.get("SKILLS_MCP_PATHS", "")
    if not paths_str:
        sys.stderr.write(
            "Error: SKILLS_MCP_PATHS environment variable not set.\n"
            "Set it to a colon-separated list of directories containing skills.\n"
            "Example: export SKILLS_MCP_PATHS='/path/to/skills:/another/path'\n"
        )
        sys.exit(1)

    paths = [Path(p.strip()) for p in paths_str.split(":") if p.strip()]
    if not paths:
        sys.stderr.write("Error: No valid paths found in SKILLS_MCP_PATHS.\n")
        sys.exit(1)

    return paths


def get_server_config() -> tuple[str, int]:
    """Get server host and port from environment.

    Returns:
        Tuple of (host, port).
    """
    host = os.environ.get("SKILLS_MCP_HOST", DEFAULT_HOST)
    port_str = os.environ.get("SKILLS_MCP_PORT", str(DEFAULT_PORT))

    try:
        port = int(port_str)
    except ValueError:
        sys.stderr.write(f"Error: Invalid port number: {port_str}\n")
        sys.exit(1)

    return host, port


async def run_server() -> None:
    """Run the MCP server."""
    setup_logging()
    logger = logging.getLogger(__name__)

    paths = get_skill_paths()
    host, port = get_server_config()

    logger.info("Starting skills-mcp with paths: %s", paths)

    # Create repository
    repository = create_local_repository(
        paths,
        enable_caching=True,
    )

    # Create and run server
    server = SkillsMCPServer(repository)
    await server.run_http(host=host, port=port)


def main() -> None:
    """Main entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
