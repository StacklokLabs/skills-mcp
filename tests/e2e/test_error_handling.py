"""Tests for error handling in E2E scenarios."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import ClientSession, McpError
from pydantic import AnyUrl


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


@pytest.mark.e2e
class TestMissingResources:
    """Tests for missing skill/resource handling."""

    async def test_nonexistent_skill(self, mcp_client_factory: ClientFactory) -> None:
        """Reading nonexistent skill should raise error."""
        async with mcp_client_factory() as mcp_client:
            with pytest.raises(McpError):
                await mcp_client.read_resource(AnyUrl("skills://nonexistent-skill"))

    async def test_nonexistent_sub_resource(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Reading nonexistent sub-resource should raise error."""
        async with mcp_client_factory() as mcp_client:
            # First expand the skill
            await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            # Try to read nonexistent script
            with pytest.raises(McpError):
                await mcp_client.read_resource(
                    AnyUrl("skills://valid-skill/scripts/nonexistent.py")
                )

    async def test_invalid_resource_type(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Invalid resource type should raise error."""
        async with mcp_client_factory() as mcp_client:
            await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            with pytest.raises(McpError):
                await mcp_client.read_resource(
                    AnyUrl("skills://valid-skill/invalid-type/file.txt")
                )


@pytest.mark.e2e
class TestInvalidURIs:
    """Tests for invalid URI handling."""

    async def test_empty_skill_name(self, mcp_client_factory: ClientFactory) -> None:
        """Empty skill name should raise error."""
        async with mcp_client_factory() as mcp_client:
            with pytest.raises(McpError):
                await mcp_client.read_resource(AnyUrl("skills://"))

    async def test_path_traversal_rejected(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Path traversal attempts should be rejected."""
        async with mcp_client_factory() as mcp_client:
            with pytest.raises(McpError):
                await mcp_client.read_resource(
                    AnyUrl("skills://valid-skill/../../../etc/passwd")
                )
