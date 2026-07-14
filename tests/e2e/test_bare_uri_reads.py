"""E2E tests pinning the SEP-2640 bare-URI read guarantee.

A brand-new session must be able to read a resource by URI without first
calling ``resources/list`` and without expanding the parent skill. This mirrors
a real client that already holds a URI (static registry, prior session, or an
out-of-band catalog) and reads it directly over the wire.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import ClientSession
from pydantic import AnyUrl


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


@pytest.mark.e2e
class TestBareURIReadsE2E:
    """Reads over the wire with no prior listing/expansion in the session."""

    async def test_read_instructions_bare_without_listing(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """A fresh session reads skill instructions bare, with no resources/list."""
        async with mcp_client_factory() as client:
            # First contact with the server for resources: a direct read.
            content = await client.read_resource(AnyUrl("skills://valid-skill"))

            assert len(content.contents) == 1
            text = content.contents[0]
            assert hasattr(text, "text")
            assert "Valid Skill" in text.text

    async def test_read_subresource_bare_without_expansion(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """A fresh session reads a sub-resource bare — no list, no prior expand."""
        async with mcp_client_factory() as client:
            # Read the sub-resource directly. The skill was never expanded in
            # this session and resources/list was never called.
            content = await client.read_resource(
                AnyUrl("skills://valid-skill/scripts/analyze.py")
            )

            assert len(content.contents) == 1
            text = content.contents[0]
            assert hasattr(text, "text")
            assert "def analyze" in text.text
