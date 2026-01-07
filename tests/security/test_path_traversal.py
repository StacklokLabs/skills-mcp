"""Security tests for path traversal protection.

These tests verify that the system properly prevents path traversal attacks
through various vectors (URIs, resource names, symlinks).
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from skills_mcp.infrastructure.mcp.server import SKILL_URI_SCHEME, SkillsMCPServer
from skills_mcp.infrastructure.persistence.local_repository import LocalSkillRepository


class TestURIPathTraversal:
    """Tests for URI-based path traversal protection."""

    async def test_reject_dotdot_in_skill_name(self) -> None:
        """Should reject URIs with .. in skill name."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="path traversal"):
            await server._handle_read_resource(f"{SKILL_URI_SCHEME}://../etc/passwd")

    async def test_reject_dotdot_in_resource_type(self) -> None:
        """Should reject URIs with .. in resource type."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="path traversal"):
            await server._handle_read_resource(
                f"{SKILL_URI_SCHEME}://skill/../../../scripts/file.py"
            )

    async def test_reject_dotdot_in_resource_name(self) -> None:
        """Should reject URIs with .. in resource name."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        with pytest.raises(ValueError, match="path traversal"):
            await server._handle_read_resource(
                f"{SKILL_URI_SCHEME}://skill/scripts/../../passwd"
            )

    async def test_reject_encoded_dotdot(self) -> None:
        """Should reject URIs with encoded .. sequences."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo)

        # The skill name validation will reject this, but check URI parsing too
        # Either path traversal or invalid name error is acceptable
        with pytest.raises((ValueError, Exception)):
            await server._handle_read_resource(
                f"{SKILL_URI_SCHEME}://..%2F..%2Fetc/scripts/passwd"
            )


class TestRepositoryPathTraversal:
    """Tests for repository-level path traversal protection."""

    async def test_is_path_safe_rejects_parent_traversal(self, tmp_path: Path) -> None:
        """Should reject paths that escape via parent directory."""
        repo = LocalSkillRepository([tmp_path])

        # Path that tries to escape
        malicious_path = tmp_path / ".." / "etc" / "passwd"

        assert repo._is_path_safe(malicious_path, tmp_path) is False

    async def test_is_path_safe_accepts_valid_subpath(self, tmp_path: Path) -> None:
        """Should accept paths within the base directory."""
        repo = LocalSkillRepository([tmp_path])

        valid_path = tmp_path / "skill" / "scripts" / "file.py"

        assert repo._is_path_safe(valid_path, tmp_path) is True

    async def test_is_path_safe_handles_nonexistent_path(self, tmp_path: Path) -> None:
        """Should safely handle paths that don't exist."""
        repo = LocalSkillRepository([tmp_path])

        nonexistent = tmp_path / "nonexistent" / "path"

        # Should return True (path is valid even if doesn't exist)
        # The actual existence check happens elsewhere
        result = repo._is_path_safe(nonexistent, tmp_path)
        assert result is True

    @pytest.mark.skipif(os.name == "nt", reason="Symlinks may require admin on Windows")
    async def test_symlink_outside_directory_rejected(self, tmp_path: Path) -> None:
        """Should reject symlinks pointing outside skill directory."""
        # Create a skill directory
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        # Create a target outside the skill directory
        outside_target = tmp_path / "outside_file.txt"
        outside_target.write_text("secret data")

        # Create a symlink inside scripts pointing outside
        symlink_path = scripts_dir / "malicious_link.py"
        symlink_path.symlink_to(outside_target)

        repo = LocalSkillRepository([tmp_path])

        # The resolved path should be outside skill_dir
        resolved = symlink_path.resolve()
        assert repo._is_path_safe(resolved, skill_dir) is False


class TestValidateSkillPathTraversal:
    """Tests for validate_skill tool path traversal protection."""

    async def test_validate_skill_rejects_outside_path(self, tmp_path: Path) -> None:
        """Should reject paths outside allowed directories."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": "/etc/passwd"}
        )

        assert "outside allowed" in result[0].text

    async def test_validate_skill_rejects_traversal_attempt(
        self, tmp_path: Path
    ) -> None:
        """Should reject paths that traverse outside allowed directories."""
        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        # Attempt to traverse out of allowed directory
        result = await server._handle_call_tool(
            "validate_skill", {"path": str(tmp_path / ".." / "etc" / "passwd")}
        )

        assert "outside allowed" in result[0].text

    async def test_validate_skill_accepts_valid_path(self, tmp_path: Path) -> None:
        """Should accept paths within allowed directories."""
        # Create a valid skill structure
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: test-skill
description: A test skill
---

# Test Skill
"""
        )

        repo = AsyncMock()
        server = SkillsMCPServer(repo, allowed_validation_paths=[tmp_path])

        result = await server._handle_call_tool(
            "validate_skill", {"path": str(skill_dir)}
        )

        assert "Valid skill" in result[0].text
