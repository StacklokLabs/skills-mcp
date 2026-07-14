"""Tests for composite repository."""

import logging
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

    async def test_list_all_name_collision_logs_warning_with_provenance(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn once with source provenance when names collide."""
        skill_v1 = create_mock_skill("dup-skill")
        skill_v2 = create_mock_skill("dup-skill")

        repo1 = create_mock_repository([skill_v1])
        repo2 = create_mock_repository([skill_v2])

        composite = CompositeSkillRepository([repo1, repo2])

        with caplog.at_level(logging.WARNING):
            skills = await composite.list_all()

        # Winner selection unchanged: single skill from repo[0].
        assert len(skills) == 1
        assert skills[0] is skill_v1

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "dup-skill" in message
        # Ordered assertion: repo[1] is shadowed BY repo[0] (winner). Swapping
        # the winner/loser labels must fail this test. Mocks are MagicMock
        # instances -> labels reflect the class name + index.
        assert "from MagicMock[1] is shadowed by MagicMock[0]" in message

    async def test_list_all_repeated_collision_warns_only_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn only once even across repeated list_all calls."""
        repo1 = create_mock_repository([create_mock_skill("dup-skill")])
        repo2 = create_mock_repository([create_mock_skill("dup-skill")])

        composite = CompositeSkillRepository([repo1, repo2])

        with caplog.at_level(logging.WARNING):
            await composite.list_all()
            await composite.list_all()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1

    async def test_list_all_repeated_collision_logs_debug_on_repeat(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log the repeat collision at DEBUG (not silently drop it)."""
        repo1 = create_mock_repository([create_mock_skill("dup-skill")])
        repo2 = create_mock_repository([create_mock_skill("dup-skill")])

        composite = CompositeSkillRepository([repo1, repo2])

        with caplog.at_level(logging.DEBUG):
            await composite.list_all()  # first call -> WARNING
            caplog.clear()
            await composite.list_all()  # repeat -> DEBUG

        debug_records = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and "dup-skill" in r.getMessage()
        ]
        assert len(debug_records) == 1
        assert (
            "from MagicMock[1] is shadowed by MagicMock[0]"
            in debug_records[0].getMessage()
        )
        # And no second WARNING was emitted on the repeat.
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 0

    async def test_list_all_no_collision_emits_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should not warn when skill names are disjoint."""
        repo1 = create_mock_repository([create_mock_skill("skill-one")])
        repo2 = create_mock_repository([create_mock_skill("skill-two")])

        composite = CompositeSkillRepository([repo1, repo2])

        with caplog.at_level(logging.WARNING):
            await composite.list_all()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 0

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
