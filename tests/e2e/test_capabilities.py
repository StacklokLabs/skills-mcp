"""E2E tests pinning the initialize capability advertisement over the wire.

The MCP client discards the InitializeResult inside the shared factory, so
these tests open their own client so they can capture and assert on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


if TYPE_CHECKING:
    from tests.e2e.conftest import ServerInfo


@pytest.mark.e2e
class TestInitializeCapabilitiesE2E:
    """initialize result as seen by a real client over Streamable HTTP."""

    async def test_initialize_advertises_skills_extension_and_list_changed(
        self, e2e_server: ServerInfo
    ) -> None:
        """The initialize result carries the skills capability and listChanged."""
        async with streamable_http_client(e2e_server.mcp_url) as (  # noqa: SIM117
            read,
            write,
        ):
            async with ClientSession(
                read,
                write,
                extensions={"io.modelcontextprotocol/skills": {}},
            ) as session:
                result = await session.discover()

                # Standard SEP-2133 extension capability is declared.
                assert result.capabilities.extensions is not None
                assert (
                    "io.modelcontextprotocol/skills" in result.capabilities.extensions
                )
                assert result.capabilities.experimental in (None, {})

                # Modern v2 discovery delivers changes through subscriptions/listen;
                # this server intentionally has no directory/subscription stream.
                assert result.capabilities.resources is not None
                assert result.capabilities.resources.list_changed is False
