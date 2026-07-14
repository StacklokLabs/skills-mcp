"""E2E tests pinning SEP-2640 resource annotations over the wire.

These assert that annotations survive real Streamable HTTP serialization: a
listed skill resource carries audience ["assistant"], priority 0.8, and an
ISO 8601 lastModified; an expanded sub-resource carries priority 0.3.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime

import pytest
from mcp import ClientSession
from pydantic import AnyUrl


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


def _last_modified(resource: object) -> str | None:
    """Extract the lastModified extra field from a resource's annotations."""
    annotations = resource.annotations  # type: ignore[attr-defined]
    if annotations is None:
        return None
    dumped = annotations.model_dump(by_alias=True, mode="json", exclude_none=True)
    value = dumped.get("lastModified")
    return value if isinstance(value, str) else None


@pytest.mark.e2e
class TestResourceAnnotationsE2E:
    """resources/list annotations as seen by a real client."""

    async def test_skill_resource_annotations_over_wire(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """A listed skill resource shows audience/priority/lastModified."""
        async with mcp_client_factory() as client:
            resources = await client.list_resources()

            valid = next(
                r for r in resources.resources if str(r.uri) == "skills://valid-skill"
            )
            assert valid.annotations is not None
            assert valid.annotations.audience == ["assistant"]
            assert valid.annotations.priority == 0.8

            last_modified = _last_modified(valid)
            assert last_modified is not None
            # Must be a valid ISO 8601 timestamp.
            parsed = datetime.fromisoformat(last_modified)
            assert parsed.tzinfo is not None

    async def test_sub_resource_annotations_over_wire(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """After expansion, a sub-resource shows priority 0.3."""
        async with mcp_client_factory() as client:
            # Expand the skill so its sub-resources are listed.
            await client.read_resource(AnyUrl("skills://valid-skill"))

            resources = await client.list_resources()
            script = next(
                r
                for r in resources.resources
                if str(r.uri) == "skills://valid-skill/scripts/analyze.py"
            )

            assert script.annotations is not None
            assert script.annotations.priority == 0.3
            assert script.annotations.audience == ["assistant"]
