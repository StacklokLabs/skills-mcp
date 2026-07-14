"""E2E tests for the validate_skill tool wired via --validation-path.

Starts a real server with ``--validation-path`` pointing at the fixture skills
directory and drives the ``validate_skill`` tool over Streamable HTTP: a skill
inside the allow-list validates successfully, and a path outside it errors.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.e2e.conftest import (
    FIXTURES_PATH,
    ServerInfo,
    find_free_port,
    shutdown_server,
    wait_for_server_ready,
)


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _text(result: object) -> str:
    """Extract the first text block from a CallToolResult."""
    return result.content[0].text  # type: ignore[attr-defined,no-any-return]


@pytest.fixture
async def validation_server() -> AsyncIterator[ServerInfo]:
    """Start a server with validate_skill enabled for the fixtures directory."""
    port = find_free_port()
    host = "127.0.0.1"
    env = {**os.environ, "SKILLS_MCP_PATHS": str(FIXTURES_PATH)}

    log_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")  # noqa: SIM115
    process = subprocess.Popen(  # noqa: ASYNC220, S603
        [
            sys.executable,
            "-m",
            "skills_mcp",
            "--host",
            host,
            "--port",
            str(port),
            "--validation-path",
            str(FIXTURES_PATH),
        ],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    server_info = ServerInfo(process=process, host=host, port=port)
    try:
        await wait_for_server_ready(server_info.url, timeout=10.0)
        yield server_info
    finally:
        await shutdown_server(server_info)
        log_file.close()


@pytest.mark.e2e
class TestValidateSkillE2E:
    """validate_skill over the wire with an allow-list configured."""

    async def test_validates_skill_inside_allowlist(
        self, validation_server: ServerInfo
    ) -> None:
        """A fixture skill under the allow-list validates successfully."""
        skill_dir = FIXTURES_PATH / "valid-skill"
        async with streamable_http_client(validation_server.mcp_url) as (  # noqa: SIM117
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "validate_skill", {"path": str(skill_dir)}
                )

                text = _text(result)
                assert "Valid skill: valid-skill" in text

    async def test_rejects_path_outside_allowlist(
        self, validation_server: ServerInfo
    ) -> None:
        """A path outside the allow-list is refused before any filesystem read."""
        async with streamable_http_client(validation_server.mcp_url) as (  # noqa: SIM117
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("validate_skill", {"path": "/etc"})

                text = _text(result)
                assert "outside allowed validation directories" in text
