"""Tests for composite repository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from skills_mcp.domain.exceptions import SkillNotFoundError
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.persistence.composite_repository import (
    CompositeSkillRepository,
)


def create_mock_skill(name: str) -> MagicMock:
    """Create a mock skill with the given name."""
    skill = MagicMock()
    # SkillName is frozen, so we need to create a real one and use it
    skill_name = SkillName(name)
    skill.name = skill_name
    return skill


def create_mock_repository(skills: list[MagicMock]) -> MagicMock:
    """Create a mock repository with the given skills."""
    repo = MagicMock()
    repo.list_all = AsyncMock(return_value=skills)

    async def find_by_name(name: SkillName) -> MagicMock | None:
        for skill in skills:
            if skill.name.value == name.value:
                return skill
        return None

    repo.find_by_name = AsyncMock(side_effect=find_by_name)
    repo.get_resource_content = AsyncMock(return_value=b"content")
    repo.refresh = AsyncMock()
    return repo


class TestCompositeSkillRepository:
    """Tests for CompositeSkillRepository."""

    def test_requires_at_least_one_repository(self) -> None:
        """Should raise ValueError when no repositories provided."""
        with pytest.raises(ValueError, match=r"(?i)at least one repository"):
            CompositeSkillRepository([])

    async def test_list_all_single_repository(self) -> None:
        """Should list skills from single repository."""
        skill1 = create_mock_skill("skill-one")
        skill2 = create_mock_skill("skill-two")
        repo = create_mock_repository([skill1, skill2])

        composite = CompositeSkillRepository([repo])
        skills = await composite.list_all()

        assert len(skills) == 2
        assert skill1 in skills
        assert skill2 in skills

    async def test_list_all_multiple_repositories(self) -> None:
        """Should aggregate skills from multiple repositories."""
        skill1 = create_mock_skill("skill-one")
        skill2 = create_mock_skill("skill-two")
        skill3 = create_mock_skill("skill-three")

        repo1 = create_mock_repository([skill1])
        repo2 = create_mock_repository([skill2, skill3])

        composite = CompositeSkillRepository([repo1, repo2])
        skills = await composite.list_all()

        assert len(skills) == 3

    async def test_list_all_deduplicates_by_name(self) -> None:
        """Should use first repository's skill when names conflict."""
        skill1_v1 = create_mock_skill("same-skill")
        skill1_v1.version = "v1"
        skill1_v2 = create_mock_skill("same-skill")
        skill1_v2.version = "v2"

        repo1 = create_mock_repository([skill1_v1])
        repo2 = create_mock_repository([skill1_v2])

        composite = CompositeSkillRepository([repo1, repo2])
        skills = await composite.list_all()

        assert len(skills) == 1
        assert skills[0].version == "v1"

    async def test_find_by_name_found_in_first_repo(self) -> None:
        """Should find skill in first repository."""
        skill = create_mock_skill("target-skill")
        repo1 = create_mock_repository([skill])
        repo2 = create_mock_repository([])

        composite = CompositeSkillRepository([repo1, repo2])
        found = await composite.find_by_name(SkillName("target-skill"))

        assert found is skill
        repo2.find_by_name.assert_not_called()

    async def test_find_by_name_found_in_second_repo(self) -> None:
        """Should search subsequent repos when not found in first."""
        skill = create_mock_skill("target-skill")
        repo1 = create_mock_repository([])
        repo2 = create_mock_repository([skill])

        composite = CompositeSkillRepository([repo1, repo2])
        found = await composite.find_by_name(SkillName("target-skill"))

        assert found is skill

    async def test_find_by_name_not_found(self) -> None:
        """Should return None when skill not in any repository."""
        repo1 = create_mock_repository([])
        repo2 = create_mock_repository([])

        composite = CompositeSkillRepository([repo1, repo2])
        found = await composite.find_by_name(SkillName("missing-skill"))

        assert found is None

    async def test_get_resource_content_delegates_to_owning_repo(self) -> None:
        """Should delegate to repository that owns the skill."""
        skill = create_mock_skill("my-skill")
        repo1 = create_mock_repository([])
        repo2 = create_mock_repository([skill])
        repo2.get_resource_content = AsyncMock(return_value=b"resource content")

        composite = CompositeSkillRepository([repo1, repo2])
        content = await composite.get_resource_content(
            SkillName("my-skill"), "scripts", "run.py"
        )

        assert content == b"resource content"
        repo2.get_resource_content.assert_called_once_with(
            SkillName("my-skill"), "scripts", "run.py"
        )

    async def test_get_resource_content_raises_when_skill_not_found(self) -> None:
        """Should raise SkillNotFoundError when skill doesn't exist."""
        repo1 = create_mock_repository([])

        composite = CompositeSkillRepository([repo1])

        with pytest.raises(SkillNotFoundError):
            await composite.get_resource_content(
                SkillName("missing-skill"), "scripts", "run.py"
            )

    async def test_refresh_calls_all_repositories(self) -> None:
        """Should refresh all underlying repositories."""
        repo1 = create_mock_repository([])
        repo2 = create_mock_repository([])

        composite = CompositeSkillRepository([repo1, repo2])
        await composite.refresh()

        repo1.refresh.assert_called_once()
        repo2.refresh.assert_called_once()
