"""Tests for MCP server."""

import asyncio
import contextlib
import json
import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from skills_mcp.domain.exceptions import ResourceNotFoundError
from skills_mcp.domain.models.resource import ResourceType, SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.mcp.server import (
    SKILL_URI_SCHEME,
    SkillsMCPServer,
)
from skills_mcp.infrastructure.mcp.session import SessionManager


def create_mock_manifest(name: str, description: str = "Test description") -> MagicMock:
    """Create a mock manifest."""
    manifest = MagicMock()
    manifest.name = SkillName(name)
    manifest.description = description
    short = description[:50] if len(description) > 50 else description
    manifest.description_short = short
    return manifest


def create_mock_skill(
    name: str,
    body: str = "# Test\n\nBody content",
    scripts: list[SkillResource] | None = None,
    references: list[SkillResource] | None = None,
    assets: list[SkillResource] | None = None,
) -> Skill:
    """Create a mock skill for testing."""
    return Skill(
        manifest=create_mock_manifest(name),
        body=body,
        path=Path(f"/skills/{name}"),
        scripts=scripts or [],
        references=references or [],
        assets=assets or [],
        token_count=100,
    )


class TestSkillsMCPServerListResources:
    """Tests for resources/list handler."""

    async def test_list_resources_returns_skills(self) -> None:
        """Should return skill resources."""
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1"),
            create_mock_skill("skill2"),
        ]

        server = SkillsMCPServer(repo)
        resources = await server._handle_list_resources()

        assert len(resources) == 2
        assert any(r.name == "skill1" for r in resources)
        assert any(r.name == "skill2" for r in resources)

    async def test_list_resources_hides_sub_resources_initially(self) -> None:
        """Should NOT include sub-resources until skill is expanded."""
        script = SkillResource(
            name="test.py",
            path=Path("/skills/skill1/scripts/test.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=50,
        )
        reference = SkillResource(
            name="guide.md",
            path=Path("/skills/skill1/references/guide.md"),
            resource_type=ResourceType.REFERENCE,
            token_count=200,
        )

        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1", scripts=[script], references=[reference])
        ]

        server = SkillsMCPServer(repo)
        resources = await server._handle_list_resources()

        # Only 1 skill-level resource (progressive disclosure)
        assert len(resources) == 1
        assert resources[0].name == "skill1"

    async def test_list_resources_includes_sub_resources_when_expanded(self) -> None:
        """Should include sub-resources for expanded skills."""
        script = SkillResource(
            name="test.py",
            path=Path("/skills/skill1/scripts/test.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=50,
        )
        reference = SkillResource(
            name="guide.md",
            path=Path("/skills/skill1/references/guide.md"),
            resource_type=ResourceType.REFERENCE,
            token_count=200,
        )

        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1", scripts=[script], references=[reference])
        ]

        server = SkillsMCPServer(repo)

        # Set up session and mark skill as expanded
        server._session_manager.mark_expanded("test-session", SkillName("skill1"))

        # Mock _get_session_id to return our test session
        with patch.object(server, "_get_session_id", return_value="test-session"):
            resources = await server._handle_list_resources()

        # 1 skill + 1 script + 1 reference
        assert len(resources) == 3

        # Check URIs
        uris = [str(r.uri) for r in resources]
        assert f"{SKILL_URI_SCHEME}://skill1" in uris
        assert f"{SKILL_URI_SCHEME}://skill1/scripts/test.py" in uris
        assert f"{SKILL_URI_SCHEME}://skill1/references/guide.md" in uris

    async def test_list_resources_empty_repository(self) -> None:
        """Should return empty list for empty repository."""
        repo = AsyncMock()
        repo.list_all.return_value = []

        server = SkillsMCPServer(repo)
        resources = await server._handle_list_resources()

        assert resources == []


class TestSkillsMCPServerReadResource:
    """Tests for resources/read handler."""

    async def test_read_skill_instructions(self) -> None:
        """Should return skill body content."""
        skill = create_mock_skill("test-skill", body="# Test\n\nInstructions here")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill"
        )

        assert len(contents) == 1
        content = contents[0]
        assert content.mime_type == "text/markdown"
        assert "Instructions here" in content.content
        assert "<!-- tokens:" in content.content

    async def test_read_skill_not_found(self) -> None:
        """Should raise ValueError for unknown skill."""
        repo = AsyncMock()
        repo.find_by_name.return_value = None

        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="not found"):
            await server._handle_read_resource(f"{SKILL_URI_SCHEME}://unknown")

    async def test_read_script_resource(self) -> None:
        """Should return script content."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"print('hello')"

        server = SkillsMCPServer(repo)
        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill/scripts/test.py"
        )

        assert len(contents) == 1
        content = contents[0]
        assert content.mime_type == "text/x-python"
        assert "print('hello')" in content.content
        assert "# tokens:" in content.content

    async def test_read_reference_resource(self) -> None:
        """Should return reference content."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"# Guide\n\nSome guide content"

        server = SkillsMCPServer(repo)
        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill/references/guide.md"
        )

        assert len(contents) == 1
        content = contents[0]
        assert content.mime_type == "text/markdown"
        assert "Guide" in content.content

    async def test_read_binary_resource(self) -> None:
        """Should return binary content as bytes."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"\x89PNG\r\n\x1a\n"  # PNG header

        server = SkillsMCPServer(repo)
        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill/assets/image.png"
        )

        assert len(contents) == 1
        content = contents[0]
        assert content.mime_type == "application/octet-stream"
        # Content should be bytes for binary data
        assert isinstance(content.content, bytes)

    async def test_read_invalid_uri_scheme(self) -> None:
        """Should raise ValueError for invalid URI scheme."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="Invalid URI scheme"):
            await server._handle_read_resource("http://example.com/skill")

    async def test_read_uri_path_traversal_rejected(self) -> None:
        """Should reject URIs with path traversal attempts."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="path traversal not allowed"):
            await server._handle_read_resource(
                f"{SKILL_URI_SCHEME}://skill/../../../etc/passwd"
            )

    async def test_read_invalid_uri_format(self) -> None:
        """Should raise ValueError for invalid URI format."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="Invalid URI"):
            await server._handle_read_resource(f"{SKILL_URI_SCHEME}://")


class TestSkillsMCPServerBareURIReads:
    """Pin the SEP-2640 bare-URI read guarantee.

    A resource read must NOT be gated on a prior ``resources/list`` or on the
    skill having been expanded in the session. A client that already knows a
    resource URI (from a static registry, a prior session, or an out-of-band
    catalog) must be able to read it directly. These tests fail closed if a
    future change adds a listing/expansion precondition to a read handler.
    """

    async def test_read_instructions_without_prior_listing_or_expansion(self) -> None:
        """Skill instructions read succeeds with no prior list and no session."""
        skill = create_mock_skill("test-skill", body="# Test\n\nInstructions here")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)
        # No session context, no prior _handle_list_resources call.
        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill"
        )

        assert len(contents) == 1
        assert "Instructions here" in contents[0].content
        # list_resources was never consulted as a precondition.
        repo.list_all.assert_not_called()

    async def test_read_subresource_without_prior_listing_or_expansion(self) -> None:
        """Sub-resource read succeeds bare, without listing or expanding first."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"print('hello')"

        server = SkillsMCPServer(repo)
        # Read a sub-resource directly — never expanded, never listed.
        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill/scripts/analyze.py"
        )

        assert len(contents) == 1
        assert "print('hello')" in contents[0].content
        # The read went straight to the repository; no listing was required.
        repo.list_all.assert_not_called()
        repo.get_resource_content.assert_awaited_once()


class TestSkillsMCPServerListTools:
    """Tests for tools/list handler."""

    async def test_list_tools_returns_validate_skill(self) -> None:
        """Should include validate_skill tool."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()

        assert len(tools) >= 1
        tool_names = [t.name for t in tools]
        assert "validate_skill" in tool_names

    async def test_validate_skill_tool_has_schema(self) -> None:
        """validate_skill should have proper input schema."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()
        validate_tool = next(t for t in tools if t.name == "validate_skill")

        assert validate_tool.inputSchema is not None
        assert "path" in validate_tool.inputSchema.get("properties", {})

    async def test_list_tools_returns_all_four_tools(self) -> None:
        """Should expose exactly the four skill tools."""
        repo = AsyncMock()
        repo.list_all.return_value = []
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()

        assert {t.name for t in tools} == {
            "list_skills",
            "get_skill",
            "get_skill_resource",
            "validate_skill",
        }

    async def test_list_tools_list_skills_description_embeds_catalog(self) -> None:
        """list_skills description should embed the current skill catalog."""
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1"),
            create_mock_skill("skill2"),
        ]
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()
        list_skills = next(t for t in tools if t.name == "list_skills")

        assert "Currently available skills:" in list_skills.description
        assert "- skill1: Test description" in list_skills.description
        assert "- skill2: Test description" in list_skills.description

    async def test_list_tools_list_skills_description_empty_repo_shows_placeholder(
        self,
    ) -> None:
        """Empty repository should render a placeholder catalog line."""
        repo = AsyncMock()
        repo.list_all.return_value = []
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()
        list_skills = next(t for t in tools if t.name == "list_skills")

        assert "- (no skills currently loaded)" in list_skills.description

    async def test_list_tools_get_skill_schema_requires_name(self) -> None:
        """get_skill input schema should require exactly the name argument."""
        repo = AsyncMock()
        repo.list_all.return_value = []
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()
        get_skill = next(t for t in tools if t.name == "get_skill")

        assert get_skill.inputSchema["required"] == ["name"]

    async def test_list_tools_get_skill_resource_schema_requires_both_args(
        self,
    ) -> None:
        """get_skill_resource schema should require both skill_name and path."""
        repo = AsyncMock()
        repo.list_all.return_value = []
        server = SkillsMCPServer(repo)

        tools = await server._handle_list_tools()
        get_resource = next(t for t in tools if t.name == "get_skill_resource")

        assert get_resource.inputSchema["required"] == ["skill_name", "resource_path"]


class TestSkillsMCPServerCallTool:
    """Tests for tools/call handler."""

    async def test_call_unknown_tool_raises(self) -> None:
        """Should raise ValueError for unknown tool."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="Unknown tool"):
            await server._handle_call_tool("nonexistent", {})

    async def test_validate_skill_path_not_exists(self, tmp_path: Path) -> None:
        """Should return error for non-existent path."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": str(tmp_path / "nonexistent")}
        )

        assert len(result) == 1
        assert "does not exist" in result[0].text

    async def test_validate_skill_not_directory(self, tmp_path: Path) -> None:
        """Should return error for non-directory path."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": str(file_path)}
        )

        assert len(result) == 1
        assert "not a directory" in result[0].text

    async def test_validate_skill_no_manifest(self, tmp_path: Path) -> None:
        """Should return error when SKILL.md missing."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": str(skill_dir)}
        )

        assert len(result) == 1
        assert "SKILL.md not found" in result[0].text

    async def test_validate_skill_valid(self, tmp_path: Path) -> None:
        """Should return success for valid skill."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: test-skill
description: A test skill
---

# Test Skill

Instructions here.
"""
        )

        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": str(skill_dir)}
        )

        assert len(result) == 1
        assert "Valid skill" in result[0].text
        assert "test-skill" in result[0].text

    async def test_validate_skill_disabled_without_paths(self) -> None:
        """Should return error when no allowed paths configured."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._handle_call_tool(
            "validate_skill", {"path": "/some/path"}
        )

        assert len(result) == 1
        assert "validation is disabled" in result[0].text

    async def test_validate_skill_rejects_outside_path(self, tmp_path: Path) -> None:
        """Should reject paths outside allowed directories."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": "/etc/passwd"}
        )

        assert len(result) == 1
        assert "outside allowed" in result[0].text


class TestSkillsMCPServerMimeTypes:
    """Tests for MIME type detection."""

    def test_get_mime_type_python(self) -> None:
        """Should return Python MIME type."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        assert server._get_mime_type("script.py") == "text/x-python"

    def test_get_mime_type_javascript(self) -> None:
        """Should return JavaScript MIME type."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        # stdlib mimetypes returns text/javascript
        assert server._get_mime_type("script.js") == "text/javascript"

    def test_get_mime_type_markdown(self) -> None:
        """Should return Markdown MIME type."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        assert server._get_mime_type("README.md") == "text/markdown"

    def test_get_mime_type_json(self) -> None:
        """Should return JSON MIME type."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        assert server._get_mime_type("config.json") == "application/json"

    def test_get_mime_type_unknown(self) -> None:
        """Should return text/plain for unknown extension."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        # Use a truly unknown extension that mimetypes won't recognize
        assert server._get_mime_type("file.zzz123unknown") == "text/plain"

    def test_get_mime_type_no_extension(self) -> None:
        """Should return text/plain for files without extension."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        assert server._get_mime_type("Makefile") == "text/plain"


class TestSkillsMCPServerNotifications:
    """Tests for resource list change notifications."""

    async def test_read_skill_sends_list_changed_on_first_access(self) -> None:
        """Should send list_changed notification when skill is first read."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)

        # Mock the notification method and session ID
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        with patch.object(server, "_get_session_id", return_value="test-session"):
            await server._handle_read_resource(f"{SKILL_URI_SCHEME}://test-skill")

        # Should have called the notification
        server._send_resources_list_changed.assert_called_once()

    async def test_read_skill_no_notification_on_subsequent_access(self) -> None:
        """Should NOT send list_changed notification on subsequent reads."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)

        # Pre-expand the skill
        server._session_manager.mark_expanded("test-session", SkillName("test-skill"))

        # Mock the notification method
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        with patch.object(server, "_get_session_id", return_value="test-session"):
            await server._handle_read_resource(f"{SKILL_URI_SCHEME}://test-skill")

        # Should NOT have called the notification (already expanded)
        server._send_resources_list_changed.assert_not_called()

    async def test_read_skill_no_session_context_skips_expansion_and_notification(
        self,
    ) -> None:
        """Sessionless read returns content but tracks no expansion state."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)

        # Mock the notification method
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        # No request context -> _get_session_id returns None (fail closed).
        contents = await server._handle_read_resource(
            f"{SKILL_URI_SCHEME}://test-skill"
        )

        # Content is still returned to the caller.
        assert len(contents) == 1
        # No notification and no session state created for a sessionless request.
        server._send_resources_list_changed.assert_not_called()
        assert server._session_manager.session_count == 0


class TestSkillsMCPServerSessionIsolation:
    """Tests for multi-client session isolation."""

    async def test_two_clients_have_isolated_expanded_state(self) -> None:
        """Two clients should see different expanded states."""
        script = SkillResource(
            name="helper.py",
            path=Path("/skills/skill1/scripts/helper.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=100,
        )
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1", scripts=[script]),
            create_mock_skill("skill2"),
        ]
        repo.find_by_name.return_value = create_mock_skill("skill1", scripts=[script])

        server = SkillsMCPServer(repo)

        # Client A expands skill1
        server._session_manager.mark_expanded("client-a", SkillName("skill1"))

        # Client A should see skill1 sub-resources
        with patch.object(server, "_get_session_id", return_value="client-a"):
            resources_a = await server._handle_list_resources()
        uris_a = [str(r.uri) for r in resources_a]
        assert f"{SKILL_URI_SCHEME}://skill1/scripts/helper.py" in uris_a

        # Client B has not expanded anything
        with patch.object(server, "_get_session_id", return_value="client-b"):
            resources_b = await server._handle_list_resources()
        uris_b = [str(r.uri) for r in resources_b]

        # Client B should NOT see skill1 sub-resources
        assert f"{SKILL_URI_SCHEME}://skill1/scripts/helper.py" not in uris_b

        # Both should see the base skill resources
        assert f"{SKILL_URI_SCHEME}://skill1" in uris_a
        assert f"{SKILL_URI_SCHEME}://skill1" in uris_b
        assert f"{SKILL_URI_SCHEME}://skill2" in uris_a
        assert f"{SKILL_URI_SCHEME}://skill2" in uris_b

    async def test_client_expansion_does_not_affect_other_client(self) -> None:
        """Expanding a skill for one client should not affect another."""
        skill = create_mock_skill("shared-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)

        # Mock the notification to prevent errors
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        # Client A reads the skill (triggers expansion)
        with patch.object(server, "_get_session_id", return_value="client-a"):
            await server._handle_read_resource(f"{SKILL_URI_SCHEME}://shared-skill")

        # Client A should have skill expanded
        assert server._session_manager.is_expanded(
            "client-a", SkillName("shared-skill")
        )

        # Client B should NOT have skill expanded
        assert not server._session_manager.is_expanded(
            "client-b", SkillName("shared-skill")
        )


class TestSkillsMCPServerSessionIdFailClosed:
    """Tests for fail-closed session-ID resolution (no shared 'default')."""

    async def test_get_session_id_no_request_context_returns_none(self) -> None:
        """Should return None when there is no request context."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        # No active request context -> LookupError -> None.
        assert server._get_session_id() is None

    def test_get_session_id_returns_header_value(self) -> None:
        """Should return the mcp-session-id header value when present."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        mock_request = MagicMock()
        mock_request.headers = {"mcp-session-id": "abc123"}
        mock_ctx = MagicMock()
        mock_ctx.request = mock_request

        with patch.object(
            type(server.server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_ctx,
        ):
            assert server._get_session_id() == "abc123"

    def test_get_session_id_in_context_without_header_returns_none_logs_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """In-context request lacking the header returns None and logs at DEBUG.

        This is the happy-path initialize case, so it must NOT warn.
        """
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        mock_request = MagicMock()
        mock_request.headers = {}  # no mcp-session-id header
        mock_ctx = MagicMock()
        mock_ctx.request = mock_request

        with (
            patch.object(
                type(server.server),
                "request_context",
                new_callable=PropertyMock,
                return_value=mock_ctx,
            ),
            caplog.at_level(logging.DEBUG),
        ):
            result = server._get_session_id()

        assert result is None
        debug_records = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG
            and "no mcp session id header" in r.getMessage().lower()
        ]
        assert len(debug_records) == 1
        # Must not warn on the happy path.
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    async def test_list_resources_no_session_context_hides_sub_resources(self) -> None:
        """Sessionless listing must not leak sub-resources from prior pollution."""
        script = SkillResource(
            name="helper.py",
            path=Path("/skills/skill1/scripts/helper.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=100,
        )
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1", scripts=[script]),
            create_mock_skill("skill2"),
        ]

        server = SkillsMCPServer(repo)

        # Simulate pre-fix pollution: something marked "default" as expanded.
        server._session_manager.mark_expanded("default", SkillName("skill1"))

        # No request context -> sessionless -> sub-resources must stay hidden.
        resources = await server._handle_list_resources()
        uris = [str(r.uri) for r in resources]

        assert f"{SKILL_URI_SCHEME}://skill1/scripts/helper.py" not in uris
        # Base skill resources remain visible.
        assert f"{SKILL_URI_SCHEME}://skill1" in uris
        assert f"{SKILL_URI_SCHEME}://skill2" in uris

    async def test_tool_get_skill_no_session_context_returns_full_content(self) -> None:
        """get_skill returns full content even for a sessionless request."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        result = await server._tool_get_skill("test-skill")

        assert len(result) == 1
        assert "Error" not in result[0].text
        server._send_resources_list_changed.assert_not_called()
        assert server._session_manager.session_count == 0

    async def test_tool_get_skill_resource_no_session_context_returns_content(
        self,
    ) -> None:
        """get_skill_resource returns content sessionlessly, tracks no state."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"print('hi')\n"

        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        result = await server._tool_get_skill_resource("test-skill", "scripts/run.py")

        assert len(result) == 1
        assert result[0].text == "print('hi')\n"
        server._send_resources_list_changed.assert_not_called()
        assert server._session_manager.session_count == 0

    async def test_get_prompt_no_session_context_returns_content(self) -> None:
        """get_prompt returns the skill body sessionlessly, tracks no state."""
        skill = create_mock_skill("test-skill", body="# Body\n\nInstructions")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill

        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        result = await server._handle_get_prompt("test-skill")

        assert len(result.messages) == 1
        assert "Instructions" in result.messages[0].content.text  # type: ignore[union-attr]
        server._send_resources_list_changed.assert_not_called()
        assert server._session_manager.session_count == 0


class TestSkillsMCPServerSessionCleanup:
    """Tests for the periodic session-cleanup background task."""

    async def test_session_cleanup_loop_removes_expired_sessions(self) -> None:
        """The cleanup loop should evict expired sessions on its interval."""
        repo = AsyncMock()
        manager = SessionManager(timeout=timedelta(seconds=0))
        server = SkillsMCPServer(
            repo,
            session_manager=manager,
            session_cleanup_interval=0.01,
        )

        manager.get_or_create("stale")
        assert manager.session_count == 1

        task = asyncio.create_task(server._session_cleanup_loop())
        try:
            deadline = 2.0
            elapsed = 0.0
            while manager.session_count != 0 and elapsed < deadline:
                await asyncio.sleep(0.01)
                elapsed += 0.01
            assert manager.session_count == 0
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def test_session_cleanup_loop_continues_after_cleanup_error(self) -> None:
        """A failing sweep must not kill the loop; it retries next interval."""
        repo = AsyncMock()
        manager = MagicMock()
        call_count = 0

        def cleanup_expired() -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            return 0

        manager.cleanup_expired.side_effect = cleanup_expired
        server = SkillsMCPServer(
            repo,
            session_manager=manager,
            session_cleanup_interval=0.01,
        )

        task = asyncio.create_task(server._session_cleanup_loop())
        try:
            deadline = 2.0
            elapsed = 0.0
            while call_count < 2 and elapsed < deadline:
                await asyncio.sleep(0.01)
                elapsed += 0.01
            assert call_count >= 2
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def test_create_asgi_app_lifespan_starts_and_cancels_cleanup_task(
        self,
    ) -> None:
        """Lifespan should start exactly one cleanup task and cancel it on exit."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo, session_cleanup_interval=3600.0)
        app = server.create_asgi_app()

        async with app.router.lifespan_context(app):
            task = server._session_cleanup_task
            assert task is not None
            assert not task.done()

        # After lifespan exit the task is cancelled/awaited and cleared.
        assert server._session_cleanup_task is None
        assert task.done()


class TestSkillsMCPServerToolListSkills:
    """Tests for the list_skills tool response shape."""

    async def test_list_skills_returns_json_catalog_with_name_and_description(
        self,
    ) -> None:
        """Should return a JSON array of name/description dicts."""
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1"),
            create_mock_skill("skill2"),
        ]
        server = SkillsMCPServer(repo)

        result = await server._tool_list_skills()

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data == [
            {"name": "skill1", "description": "Test description"},
            {"name": "skill2", "description": "Test description"},
        ]

    async def test_list_skills_with_resources_includes_exact_counts(self) -> None:
        """Should include exact per-type resource counts when present."""
        script = SkillResource(
            name="test.py",
            path=Path("/skills/skill1/scripts/test.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=50,
        )
        reference = SkillResource(
            name="guide.md",
            path=Path("/skills/skill1/references/guide.md"),
            resource_type=ResourceType.REFERENCE,
            token_count=200,
        )
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1", scripts=[script], references=[reference])
        ]
        server = SkillsMCPServer(repo)

        result = await server._tool_list_skills()

        data = json.loads(result[0].text)
        assert data[0]["resources"] == {"scripts": 1, "references": 1, "assets": 0}

    async def test_list_skills_without_resources_omits_resources_key(self) -> None:
        """Should omit the resources key entirely when a skill has no resources."""
        repo = AsyncMock()
        repo.list_all.return_value = [create_mock_skill("skill1")]
        server = SkillsMCPServer(repo)

        result = await server._tool_list_skills()

        data = json.loads(result[0].text)
        assert "resources" not in data[0]

    async def test_list_skills_empty_repository_returns_empty_json_array(self) -> None:
        """Should return an empty JSON array for an empty repository."""
        repo = AsyncMock()
        repo.list_all.return_value = []
        server = SkillsMCPServer(repo)

        result = await server._tool_list_skills()

        assert json.loads(result[0].text) == []


class TestSkillsMCPServerToolGetSkill:
    """Tests for the get_skill tool response shape and error handling."""

    async def test_get_skill_returns_instructions_dict_shape(self) -> None:
        """Should return the full Skill.to_instructions_dict shape."""
        script = SkillResource(
            name="test.py",
            path=Path("/skills/test-skill/scripts/test.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=50,
        )
        skill = create_mock_skill("test-skill", scripts=[script])
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill("test-skill")

        data = json.loads(result[0].text)
        assert set(data.keys()) == {
            "name",
            "description",
            "body",
            "token_count",
            "resources",
        }
        assert data["body"] == "# Test\n\nBody content"
        assert data["token_count"] == 100
        assert data["resources"]["scripts"] == [{"name": "test.py", "tokens": 50}]
        assert data["resources"]["references"] == []
        assert data["resources"]["assets"] == []

    async def test_get_skill_resources_keys_match_accepted_resource_path_types(
        self,
    ) -> None:
        """The resources dict keys must round-trip as get_skill_resource types.

        This pins the implicit cross-layer contract that the keys of the
        get_skill ``resources`` dict are exactly the ``ResourceType`` values
        that get_skill_resource accepts, so a model can build a valid
        ``resource_path`` from the get_skill response alone.
        """
        script = SkillResource(
            name="run.py",
            path=Path("/skills/test-skill/scripts/run.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=50,
        )
        reference = SkillResource(
            name="guide.md",
            path=Path("/skills/test-skill/references/guide.md"),
            resource_type=ResourceType.REFERENCE,
            token_count=200,
        )
        asset = SkillResource(
            name="logo.png",
            path=Path("/skills/test-skill/assets/logo.png"),
            resource_type=ResourceType.ASSET,
            token_count=10,
        )
        skill = create_mock_skill(
            "test-skill", scripts=[script], references=[reference], assets=[asset]
        )
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        repo.get_resource_content.return_value = b"data"
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill("test-skill")
        data = json.loads(result[0].text)

        assert set(data["resources"].keys()) == {rt.value for rt in ResourceType}

        # Round-trip: build resource_path from each key and confirm the repo
        # is called with resource_type == key.
        for key, entries in data["resources"].items():
            for entry in entries:
                repo.get_resource_content.reset_mock()
                await server._tool_get_skill_resource(
                    "test-skill", f"{key}/{entry['name']}"
                )
                _, called_type, called_name = repo.get_resource_content.call_args.args
                assert called_type == key
                assert called_name == entry["name"]

    async def test_get_skill_empty_name_returns_error(self) -> None:
        """Should return the exact error for an empty skill name."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill("")

        assert result[0].text == "Error: skill name is required"

    async def test_get_skill_invalid_name_returns_error(self) -> None:
        """An invalid skill name should return a graceful error string.

        SkillName raises InvalidSkillNameError (a SkillError, not a
        ValueError) and raises TypeError for non-string input; the handler
        must catch both rather than the never-raised ValueError.
        """
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill("UPPER CASE!!")

        assert result[0].text.startswith("Error: invalid skill name:")
        repo.find_by_name.assert_not_called()

    async def test_get_skill_non_string_name_returns_error(self) -> None:
        """A non-string name (bypassing SDK validation) should not crash."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill(123)  # type: ignore[arg-type]

        assert result[0].text.startswith("Error: invalid skill name:")
        repo.find_by_name.assert_not_called()

    async def test_get_skill_unknown_skill_returns_error(self) -> None:
        """Should return the exact not-found error for an unknown skill."""
        repo = AsyncMock()
        repo.find_by_name.return_value = None
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill("missing-skill")

        assert result[0].text == "Error: skill not found: missing-skill"

    async def test_get_skill_with_session_marks_expanded_and_notifies_once(
        self,
    ) -> None:
        """A session-scoped get_skill should expand and notify exactly once."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        with patch.object(server, "_get_session_id", return_value="sess-1"):
            await server._tool_get_skill("test-skill")

        assert server._session_manager.is_expanded("sess-1", SkillName("test-skill"))
        server._send_resources_list_changed.assert_called_once()

    async def test_get_skill_second_call_same_session_sends_no_second_notification(
        self,
    ) -> None:
        """A repeat get_skill in the same session must not notify again."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        with patch.object(server, "_get_session_id", return_value="sess-1"):
            await server._tool_get_skill("test-skill")
            await server._tool_get_skill("test-skill")

        server._send_resources_list_changed.assert_called_once()

    async def test_call_tool_get_skill_missing_args_returns_required_error(
        self,
    ) -> None:
        """call_tool('get_skill', {}) should surface the required-name error."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._handle_call_tool("get_skill", {})

        assert result[0].text == "Error: skill name is required"


class TestSkillsMCPServerToolGetSkillResource:
    """Tests for the get_skill_resource tool response shape and errors."""

    async def test_get_skill_resource_returns_raw_text_without_token_header(
        self,
    ) -> None:
        """Should return raw resource text with no token header prepended."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"print('hi')\n"
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("test-skill", "scripts/run.py")

        assert result[0].text == "print('hi')\n"

    async def test_get_skill_resource_missing_skill_name_returns_error(self) -> None:
        """Should return the exact error for a missing skill name."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("", "scripts/run.py")

        assert result[0].text == "Error: skill_name is required"

    async def test_get_skill_resource_missing_path_returns_error(self) -> None:
        """Should return the exact error for a missing resource path."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("test-skill", "")

        assert result[0].text == "Error: resource_path is required"

    async def test_get_skill_resource_traversal_returns_error(self) -> None:
        """Path traversal should be rejected before touching the repository."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource(
            "test-skill", "scripts/../../etc/passwd"
        )

        assert result[0].text == "Error: path traversal not allowed"
        repo.get_resource_content.assert_not_called()

    async def test_get_skill_resource_pathless_format_returns_error(self) -> None:
        """A resource path without a type prefix should be rejected."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("test-skill", "analyze.py")

        assert "must be in format 'type/filename'" in result[0].text

    async def test_get_skill_resource_strips_slashes_and_splits_type_name(
        self,
    ) -> None:
        """Leading slashes are stripped and only the first slash splits type."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"x"
        server = SkillsMCPServer(repo)

        await server._tool_get_skill_resource("test-skill", "/scripts/run.py")
        _, rtype, rname = repo.get_resource_content.call_args.args
        assert (rtype, rname) == ("scripts", "run.py")

        repo.get_resource_content.reset_mock()
        await server._tool_get_skill_resource("test-skill", "scripts/sub/run.py")
        _, rtype, rname = repo.get_resource_content.call_args.args
        assert (rtype, rname) == ("scripts", "sub/run.py")

    async def test_get_skill_resource_binary_content_returns_error(self) -> None:
        """Undecodable (binary) content should return the exact binary error."""
        repo = AsyncMock()
        repo.get_resource_content.return_value = b"\x89PNG\r\n\x1a\n"
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("test-skill", "assets/logo.png")

        assert (
            result[0].text == "Error: resource is binary and cannot be returned as text"
        )

    async def test_get_skill_resource_repo_value_error_maps_to_error_prefix(
        self,
    ) -> None:
        """A ValueError from the repo maps to the 'Error: ' prefix."""
        repo = AsyncMock()
        repo.get_resource_content.side_effect = ValueError("bad input")
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("test-skill", "scripts/run.py")

        assert result[0].text == "Error: bad input"

    async def test_get_skill_resource_not_found_returns_error(self) -> None:
        """ResourceNotFoundError (a SkillError, not ValueError) hits the generic
        handler and is prefixed with 'Error loading resource:'."""
        repo = AsyncMock()
        repo.get_resource_content.side_effect = ResourceNotFoundError(
            "test-skill", "scripts", "run.py"
        )
        server = SkillsMCPServer(repo)

        result = await server._tool_get_skill_resource("test-skill", "scripts/run.py")

        assert result[0].text.startswith("Error loading resource: Resource not found:")


class TestSkillsMCPServerListPrompts:
    """Tests for the prompts/list handler."""

    async def test_list_prompts_returns_one_prompt_per_skill(self) -> None:
        """Should return one prompt per skill with the short description."""
        repo = AsyncMock()
        repo.list_all.return_value = [
            create_mock_skill("skill1"),
            create_mock_skill("skill2"),
        ]
        server = SkillsMCPServer(repo)

        prompts = await server._handle_list_prompts()

        assert len(prompts) == 2
        assert {p.name for p in prompts} == {"skill1", "skill2"}
        for prompt in prompts:
            assert prompt.description == "Test description"

    async def test_list_prompts_prompt_declares_optional_args_argument(self) -> None:
        """Each prompt should declare a single optional 'args' argument."""
        repo = AsyncMock()
        repo.list_all.return_value = [create_mock_skill("skill1")]
        server = SkillsMCPServer(repo)

        prompts = await server._handle_list_prompts()

        assert prompts[0].arguments is not None
        assert len(prompts[0].arguments) == 1
        assert prompts[0].arguments[0].name == "args"
        assert prompts[0].arguments[0].required is False

    async def test_list_prompts_empty_repository_returns_empty_list(self) -> None:
        """Should return an empty list for an empty repository."""
        repo = AsyncMock()
        repo.list_all.return_value = []
        server = SkillsMCPServer(repo)

        assert await server._handle_list_prompts() == []


class TestSkillsMCPServerGetPrompt:
    """Tests for the prompts/get handler."""

    async def test_get_prompt_returns_body_as_user_message(self) -> None:
        """A resourceless skill returns exactly its body as a user message."""
        # Use a description longer than the 50-char short form so we can assert
        # the result carries the FULL description, not the short one.
        full_description = (
            "A valid test skill with a description longer than fifty characters"
        )
        manifest = create_mock_manifest("test-skill", description=full_description)
        skill = Skill(
            manifest=manifest,
            body="# Test\n\nBody content",
            path=Path("/skills/test-skill"),
            token_count=100,
        )
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)

        result = await server._handle_get_prompt("test-skill")

        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        text = result.messages[0].content.text  # type: ignore[union-attr]
        assert text == "# Test\n\nBody content"
        assert "ARGUMENTS" not in text
        assert "Available resources" not in text
        # Full description, not the truncated short form.
        assert result.description == full_description
        assert result.description != manifest.description_short

    async def test_get_prompt_with_args_appends_arguments_line(self) -> None:
        """Non-empty args should be appended as an ARGUMENTS line."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)

        result = await server._handle_get_prompt(
            "test-skill", {"args": "focus on auth"}
        )

        text = result.messages[0].content.text  # type: ignore[union-attr]
        assert text.endswith("\n\nARGUMENTS: focus on auth")

    async def test_get_prompt_empty_args_value_omits_arguments_line(self) -> None:
        """An empty args value must not add an ARGUMENTS line."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)

        result = await server._handle_get_prompt("test-skill", {"args": ""})

        text = result.messages[0].content.text  # type: ignore[union-attr]
        assert "ARGUMENTS:" not in text

    async def test_get_prompt_with_resources_appends_typed_resource_listing(
        self,
    ) -> None:
        """Skills with resources append a typed, human-readable listing."""
        script = SkillResource(
            name="test.py",
            path=Path("/skills/test-skill/scripts/test.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=50,
        )
        reference = SkillResource(
            name="guide.md",
            path=Path("/skills/test-skill/references/guide.md"),
            resource_type=ResourceType.REFERENCE,
            token_count=200,
        )
        asset = SkillResource(
            name="logo.png",
            path=Path("/skills/test-skill/assets/logo.png"),
            resource_type=ResourceType.ASSET,
            token_count=5,
        )
        skill = create_mock_skill(
            "test-skill", scripts=[script], references=[reference], assets=[asset]
        )
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)

        result = await server._handle_get_prompt("test-skill")

        text = result.messages[0].content.text  # type: ignore[union-attr]
        assert "Available resources for this skill:" in text
        assert "- scripts/test.py (50 tokens)" in text
        assert "- references/guide.md (200 tokens)" in text
        assert "- assets/logo.png (" in text
        assert "Use get_skill_resource to load any of these." in text

    async def test_get_prompt_invalid_name_raises_value_error(self) -> None:
        """An invalid skill name should raise a plain ValueError.

        SkillName raises InvalidSkillNameError (a SkillError, not a
        ValueError) and raises TypeError for non-string input; the handler
        must catch both and translate to the documented ValueError.
        """
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="Invalid skill name"):
            await server._handle_get_prompt("UPPER CASE!!")
        repo.find_by_name.assert_not_called()

    async def test_get_prompt_unknown_skill_raises_value_error(self) -> None:
        """An unknown skill should raise a ValueError."""
        repo = AsyncMock()
        repo.find_by_name.return_value = None
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="Skill not found"):
            await server._handle_get_prompt("missing-skill")

    async def test_get_prompt_with_session_marks_expanded_and_notifies_once(
        self,
    ) -> None:
        """A session-scoped get_prompt should expand and notify exactly once."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        with patch.object(server, "_get_session_id", return_value="sess-1"):
            await server._handle_get_prompt("test-skill")

        assert server._session_manager.is_expanded("sess-1", SkillName("test-skill"))
        server._send_resources_list_changed.assert_called_once()

    async def test_get_prompt_second_call_same_session_sends_no_second_notification(
        self,
    ) -> None:
        """A repeat get_prompt in the same session must not notify again."""
        skill = create_mock_skill("test-skill")
        repo = AsyncMock()
        repo.find_by_name.return_value = skill
        server = SkillsMCPServer(repo)
        server._send_resources_list_changed = AsyncMock()  # type: ignore[method-assign]

        with patch.object(server, "_get_session_id", return_value="sess-1"):
            await server._handle_get_prompt("test-skill")
            await server._handle_get_prompt("test-skill")

        server._send_resources_list_changed.assert_called_once()
