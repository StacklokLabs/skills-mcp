"""Tests for LocalSkillRepository."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.resource import ResourceType
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.persistence.local_repository import (
    MAX_RESOURCE_SIZE_BYTES,
    LocalSkillRepository,
)


# Path to test fixtures
FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures" / "skills"


class TestLocalSkillRepositoryListAll:
    """Tests for list_all method."""

    async def test_list_all_returns_valid_skills(self) -> None:
        """Should return all valid skills in the directory."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skills = await repo.list_all()

        # Should find valid-skill and minimal-skill
        # invalid-skill should be skipped (missing name)
        skill_names = {s.name.value for s in skills}
        assert "valid-skill" in skill_names
        assert "minimal-skill" in skill_names

    async def test_list_all_with_empty_directory(self, tmp_path: Path) -> None:
        """Should return empty list for empty directory."""
        repo = LocalSkillRepository([tmp_path])
        skills = await repo.list_all()
        assert skills == []

    async def test_list_all_with_nonexistent_directory(self, tmp_path: Path) -> None:
        """Should handle nonexistent directory gracefully."""
        nonexistent = tmp_path / "nonexistent"
        repo = LocalSkillRepository([nonexistent])
        skills = await repo.list_all()
        assert skills == []

    async def test_list_all_caches_results(self) -> None:
        """Should cache results after first call."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        skills1 = await repo.list_all()
        skills2 = await repo.list_all()

        # The underlying skills should be the same objects (cached)
        # even though the list wrapper is new
        assert len(skills1) == len(skills2)
        for s1, s2 in zip(skills1, skills2, strict=True):
            assert s1 is s2  # Same Skill objects from cache


class TestLocalSkillRepositoryFindByName:
    """Tests for find_by_name method."""

    async def test_find_existing_skill(self) -> None:
        """Should find existing skill by name."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skill = await repo.find_by_name(SkillName("valid-skill"))

        assert skill is not None
        assert skill.name.value == "valid-skill"
        assert skill.description == "A valid test skill with all features"
        assert skill.manifest.license == "MIT"

    async def test_find_nonexistent_skill(self) -> None:
        """Should return None for nonexistent skill."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skill = await repo.find_by_name(SkillName("nonexistent"))
        assert skill is None

    async def test_find_skill_with_resources(self) -> None:
        """Should include resources in found skill."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skill = await repo.find_by_name(SkillName("valid-skill"))

        assert skill is not None
        assert len(skill.scripts) == 1
        assert len(skill.references) == 1
        assert len(skill.assets) == 1

        # Check script resource
        script = skill.scripts[0]
        assert script.name == "analyze.py"
        assert script.resource_type == ResourceType.SCRIPT
        assert script.token_count > 0

    async def test_find_minimal_skill(self) -> None:
        """Should find skill without resources."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skill = await repo.find_by_name(SkillName("minimal-skill"))

        assert skill is not None
        assert skill.scripts == []
        assert skill.references == []
        assert skill.assets == []


class TestLocalSkillRepositoryGetResourceContent:
    """Tests for get_resource_content method."""

    async def test_get_script_content(self) -> None:
        """Should return script content."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        content = await repo.get_resource_content(
            SkillName("valid-skill"), "scripts", "analyze.py"
        )

        assert b"def analyze" in content
        assert b"#!/usr/bin/env python3" in content

    async def test_get_reference_content(self) -> None:
        """Should return reference content."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        content = await repo.get_resource_content(
            SkillName("valid-skill"), "references", "GUIDE.md"
        )

        assert b"# Usage Guide" in content

    async def test_get_asset_content(self) -> None:
        """Should return asset content."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        content = await repo.get_resource_content(
            SkillName("valid-skill"), "assets", "config.json"
        )

        assert b'"name": "valid-skill"' in content

    async def test_get_resource_nonexistent_skill(self) -> None:
        """Should raise SkillNotFoundError for nonexistent skill."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        with pytest.raises(SkillNotFoundError):
            await repo.get_resource_content(
                SkillName("nonexistent"), "scripts", "analyze.py"
            )

    async def test_get_resource_invalid_type(self) -> None:
        """Should raise ResourceNotFoundError for invalid type."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(
                SkillName("valid-skill"), "invalid-type", "file.txt"
            )

    async def test_get_resource_nonexistent_file(self) -> None:
        """Should raise ResourceNotFoundError for nonexistent file."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(
                SkillName("valid-skill"), "scripts", "nonexistent.py"
            )


class TestLocalSkillRepositoryRefresh:
    """Tests for refresh method."""

    async def test_refresh_clears_cache(self) -> None:
        """Should clear cache and reload on next access."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        # Load skills
        skills1 = await repo.list_all()
        assert len(skills1) > 0

        # Refresh (clears cache)
        await repo.refresh()

        # Next access should reload
        skills2 = await repo.list_all()

        # Should have same skills but be a new list
        assert len(skills2) == len(skills1)
        assert skills2 is not skills1


class TestLocalSkillRepositoryTokenCounts:
    """Tests for token counting."""

    async def test_skill_body_token_count(self) -> None:
        """Should estimate token count for skill body."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skill = await repo.find_by_name(SkillName("valid-skill"))

        assert skill is not None
        assert skill.token_count > 0

    async def test_resource_token_count(self) -> None:
        """Should estimate token count for resources."""
        repo = LocalSkillRepository([FIXTURES_PATH])
        skill = await repo.find_by_name(SkillName("valid-skill"))

        assert skill is not None
        for resource in skill.all_resources:
            assert resource.token_count > 0


class TestLocalSkillRepositoryResourceSizeLimits:
    """Tests for resource size limits."""

    async def test_reject_oversized_resource(self, tmp_path: Path) -> None:
        """Should reject resources that exceed the size limit."""
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
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        # Create a small script file (actual content doesn't matter for this test)
        script_file = scripts_dir / "large.py"
        script_file.write_text("# small content")

        repo = LocalSkillRepository([tmp_path])

        # Load skills first so cache is populated before we mock stat
        await repo.list_all()

        # Mock stat to report a file size over the limit
        original_stat = Path.stat

        def mock_stat(self: Path, **kwargs: object) -> object:
            result = original_stat(self)
            if self == script_file.resolve():
                # Return a mock stat result with large size
                class MockStat:
                    st_size = MAX_RESOURCE_SIZE_BYTES + 1
                    st_mode = result.st_mode
                    st_ino = result.st_ino
                    st_dev = result.st_dev
                    st_nlink = result.st_nlink
                    st_uid = result.st_uid
                    st_gid = result.st_gid
                    st_atime = result.st_atime
                    st_mtime = result.st_mtime
                    st_ctime = result.st_ctime

                return MockStat()
            return result

        with patch.object(Path, "stat", mock_stat):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await repo.get_resource_content(
                    SkillName("test-skill"), "scripts", "large.py"
                )

            assert "too large" in str(exc_info.value).lower()

    async def test_accept_resource_within_limit(self, tmp_path: Path) -> None:
        """Should accept resources within the size limit."""
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
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        # Create a small script file
        script_file = scripts_dir / "small.py"
        script_file.write_text("print('hello')")

        repo = LocalSkillRepository([tmp_path])

        # Should succeed without error
        content = await repo.get_resource_content(
            SkillName("test-skill"), "scripts", "small.py"
        )

        assert b"print('hello')" in content


class TestLocalSkillRepositoryConcurrency:
    """Tests for concurrent access to repository."""

    async def test_concurrent_list_all_calls(self) -> None:
        """Should handle concurrent list_all calls safely."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        # Call list_all concurrently multiple times
        results = await asyncio.gather(*[repo.list_all() for _ in range(10)])

        # All results should be consistent
        first_len = len(results[0])
        for result in results:
            assert len(result) == first_len

    async def test_concurrent_find_and_list(self) -> None:
        """Should handle concurrent find_by_name and list_all calls."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        async def find_skill() -> bool:
            skill = await repo.find_by_name(SkillName("valid-skill"))
            return skill is not None

        async def list_skills() -> int:
            skills = await repo.list_all()
            return len(skills)

        # Mix of find and list operations
        tasks = [find_skill() for _ in range(5)] + [list_skills() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All find operations should succeed
        for result in results[:5]:
            assert result is True

        # All list operations should return same count
        counts = results[5:]
        assert all(c == counts[0] for c in counts)

    async def test_concurrent_refresh_and_read(self) -> None:
        """Should handle refresh during concurrent reads without errors."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        async def read_loop() -> int:
            """Repeatedly read skills."""
            count = 0
            for _ in range(5):
                skills = await repo.list_all()
                count += len(skills)
                await asyncio.sleep(0.01)
            return count

        async def refresh_loop() -> None:
            """Repeatedly refresh the cache."""
            for _ in range(3):
                await repo.refresh()
                await asyncio.sleep(0.02)

        # Run reads and refreshes concurrently
        results = await asyncio.gather(
            read_loop(), read_loop(), refresh_loop(), return_exceptions=True
        )

        # No exceptions should be raised
        for result in results:
            assert not isinstance(result, Exception)

    async def test_cache_populated_once_under_concurrent_access(self) -> None:
        """Cache should be populated exactly once even with concurrent first access."""
        repo = LocalSkillRepository([FIXTURES_PATH])

        # Multiple concurrent first calls to list_all
        results = await asyncio.gather(*[repo.list_all() for _ in range(10)])

        # All should return same skills (cache was populated atomically)
        first_names = {s.name.value for s in results[0]}
        for result in results[1:]:
            names = {s.name.value for s in result}
            assert names == first_names
