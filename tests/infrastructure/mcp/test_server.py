"""Tests for MCP server."""

import asyncio
import contextlib
import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

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
