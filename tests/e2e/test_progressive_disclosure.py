"""Tests for progressive disclosure (3-tier resource loading)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import ClientSession
from pydantic import AnyUrl


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


@pytest.mark.e2e
class TestTier1Metadata:
    """Tier 1: Initial resource listing shows only skill metadata."""

    async def test_list_resources_shows_skills_only(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Initial list should show only skill-level resources."""
        async with mcp_client_factory() as mcp_client:
            resources = await mcp_client.list_resources()

            # Should have skills from fixtures (valid-skill, minimal-skill)
            assert len(resources.resources) >= 2

            # All URIs should be skill-level (no sub-paths after skill name)
            for resource in resources.resources:
                uri_str = str(resource.uri)
                # Remove the scheme prefix
                path = uri_str.replace("skills://", "")
                assert "/" not in path, (
                    f"Sub-resource visible before expansion: {resource.uri}"
                )

    async def test_skill_resources_have_metadata(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Skill resources should include name and description."""
        async with mcp_client_factory() as mcp_client:
            resources = await mcp_client.list_resources()

            # Find the valid-skill resource
            valid_skill = next(
                (r for r in resources.resources if "valid-skill" in str(r.uri)), None
            )
            assert valid_skill is not None, "valid-skill not found in resources"
            assert valid_skill.name is not None
            assert valid_skill.description is not None
            assert len(valid_skill.description) > 0


@pytest.mark.e2e
class TestTier2Instructions:
    """Tier 2: Reading skill expands and reveals sub-resources."""

    async def test_read_skill_returns_instructions(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Reading skill should return SKILL.md body content."""
        async with mcp_client_factory() as mcp_client:
            content = await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            assert len(content.contents) == 1
            text_content = content.contents[0]
            assert hasattr(text_content, "text")
            # Check for content from SKILL.md body
            assert "Valid Skill" in text_content.text
            # Token count header should be present
            assert "<!-- tokens:" in text_content.text

    async def test_read_skill_expands_sub_resources(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Reading skill should make sub-resources visible in subsequent list."""
        async with mcp_client_factory() as mcp_client:
            # First, list resources (should be skill-level only)
            resources_before = await mcp_client.list_resources()
            uris_before = {str(r.uri) for r in resources_before.resources}

            # Verify no sub-resources yet
            assert not any(
                "scripts" in uri or "references" in uri or "assets" in uri
                for uri in uris_before
            ), "Sub-resources visible before expansion"

            # Read the skill (triggers expansion)
            await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            # List resources again (should now include sub-resources)
            resources_after = await mcp_client.list_resources()
            uris_after = {str(r.uri) for r in resources_after.resources}

            # Should have more resources now
            assert len(uris_after) > len(uris_before)

            # Should include sub-resources for valid-skill
            assert any("valid-skill/scripts/analyze.py" in uri for uri in uris_after), (
                f"scripts/analyze.py not found in {uris_after}"
            )
            assert any(
                "valid-skill/references/GUIDE.md" in uri for uri in uris_after
            ), f"references/GUIDE.md not found in {uris_after}"
            assert any("valid-skill/assets/config.json" in uri for uri in uris_after), (
                f"assets/config.json not found in {uris_after}"
            )


@pytest.mark.e2e
class TestTier3SubResources:
    """Tier 3: Reading sub-resources after skill expansion."""

    async def test_read_script_content(self, mcp_client_factory: ClientFactory) -> None:
        """Should be able to read script content after expansion."""
        async with mcp_client_factory() as mcp_client:
            # First expand the skill
            await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            # Now read the script
            content = await mcp_client.read_resource(
                AnyUrl("skills://valid-skill/scripts/analyze.py")
            )

            assert len(content.contents) == 1
            text_content = content.contents[0]
            assert hasattr(text_content, "text")
            # Check for content from analyze.py
            assert "def analyze" in text_content.text
            # Token count header for Python should be a comment
            assert "# tokens:" in text_content.text

    async def test_read_reference_content(
        self, mcp_client_factory: ClientFactory
    ) -> None:
        """Should be able to read reference content after expansion."""
        async with mcp_client_factory() as mcp_client:
            await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            content = await mcp_client.read_resource(
                AnyUrl("skills://valid-skill/references/GUIDE.md")
            )

            assert len(content.contents) == 1
            text_content = content.contents[0]
            assert hasattr(text_content, "text")
            # Check for content from GUIDE.md
            assert "Usage Guide" in text_content.text

    async def test_read_asset_content(self, mcp_client_factory: ClientFactory) -> None:
        """Should be able to read asset content after expansion."""
        async with mcp_client_factory() as mcp_client:
            await mcp_client.read_resource(AnyUrl("skills://valid-skill"))

            content = await mcp_client.read_resource(
                AnyUrl("skills://valid-skill/assets/config.json")
            )

            assert len(content.contents) == 1
            text_content = content.contents[0]
            assert hasattr(text_content, "text")
            # Check for content from config.json
            assert '"name": "valid-skill"' in text_content.text
