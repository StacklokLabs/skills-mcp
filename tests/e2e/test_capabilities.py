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
            _,
        ):
            async with ClientSession(read, write) as session:
                result = await session.initialize()

                # Experimental skills extension capability is declared.
                assert result.capabilities.experimental is not None
                assert (
                    "io.modelcontextprotocol/skills" in result.capabilities.experimental
                )

                # resources.listChanged is advertised True (we send the
                # list_changed notification on first expansion).
                assert result.capabilities.resources is not None
                assert result.capabilities.resources.listChanged is True
