"""Tests for session isolation between clients."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import ClientSession


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


def _uri(value: str) -> str:
    return value


@pytest.mark.e2e
class TestSessionIsolation:
    """Different clients should have isolated expanded states."""

    async def test_two_clients_have_isolated_state(
        self,
        mcp_client_factory: ClientFactory,
    ) -> None:
        """Client A expanding skill should not affect Client B."""
        async with (
            mcp_client_factory() as client_a,
            mcp_client_factory() as client_b,
        ):
            # Client A lists resources (skill-level only)
            resources_a_before = await client_a.list_resources()
            uris_a_before = {str(r.uri) for r in resources_a_before.resources}

            # Client B lists resources (should also be skill-level only)
            resources_b_before = await client_b.list_resources()
            uris_b_before = {str(r.uri) for r in resources_b_before.resources}

            # Both should see same resources initially
            assert uris_a_before == uris_b_before

            # Client A expands valid-skill
            await client_a.read_resource(_uri("skills://valid-skill"))

            # Client A should now see sub-resources
            resources_a_after = await client_a.list_resources()
            uris_a_after = {str(r.uri) for r in resources_a_after.resources}
            assert any(
                "valid-skill/scripts/analyze.py" in uri for uri in uris_a_after
            ), "Client A should see sub-resources after expansion"

            # Client B should NOT see sub-resources (isolated session)
            resources_b_after = await client_b.list_resources()
            uris_b_after = {str(r.uri) for r in resources_b_after.resources}
            assert not any(
                "scripts" in uri or "references" in uri or "assets" in uri
                for uri in uris_b_after
            ), "Client B should NOT see sub-resources (session isolation)"

    async def test_multiple_clients_independent_expansion(
        self,
        mcp_client_factory: ClientFactory,
    ) -> None:
        """Multiple clients can expand different skills independently."""
        async with (
            mcp_client_factory() as client_a,
            mcp_client_factory() as client_b,
        ):
            # Client A expands valid-skill
            await client_a.read_resource(_uri("skills://valid-skill"))

            # Client B expands minimal-skill (which has no sub-resources)
            await client_b.read_resource(_uri("skills://minimal-skill"))

            # Client A should see valid-skill sub-resources
            resources_a = await client_a.list_resources()
            uris_a = {str(r.uri) for r in resources_a.resources}
            assert any("valid-skill/scripts/analyze.py" in uri for uri in uris_a), (
                "Client A should see valid-skill sub-resources"
            )

            # Client B should NOT see valid-skill sub-resources
            # (minimal-skill has no sub-resources, and valid-skill is not expanded)
            resources_b = await client_b.list_resources()
            uris_b = {str(r.uri) for r in resources_b.resources}
            assert not any("valid-skill/scripts" in uri for uri in uris_b), (
                "Client B should NOT see valid-skill sub-resources"
            )

    async def test_reconnecting_client_starts_fresh(
        self,
        mcp_client_factory: ClientFactory,
    ) -> None:
        """A new connection should start with unexpanded state."""
        # First connection expands a skill
        async with mcp_client_factory() as client_1:
            await client_1.read_resource(_uri("skills://valid-skill"))
            resources_1 = await client_1.list_resources()
            uris_1 = {str(r.uri) for r in resources_1.resources}
            assert any("valid-skill/scripts/analyze.py" in uri for uri in uris_1), (
                "First client should see sub-resources after expansion"
            )

        # Second connection (new session) should start fresh
        async with mcp_client_factory() as client_2:
            resources_2 = await client_2.list_resources()
            uris_2 = {str(r.uri) for r in resources_2.resources}
            # Should NOT see sub-resources (fresh session)
            assert not any(
                "scripts" in uri or "references" in uri or "assets" in uri
                for uri in uris_2
            ), "New connection should start with unexpanded state"
