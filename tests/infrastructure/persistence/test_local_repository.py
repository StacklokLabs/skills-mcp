"""Tests for LocalSkillRepository."""

from pathlib import Path

import pytest

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.resource import ResourceType
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.persistence.local_repository import LocalSkillRepository


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
