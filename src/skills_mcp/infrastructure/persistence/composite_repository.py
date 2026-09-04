"""Composite repository that combines multiple skill repositories.

This module provides a repository implementation that aggregates skills
from multiple underlying repositories (e.g., local + OCI).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from skills_mcp.domain.exceptions import SkillNotFoundError


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill import Skill
    from skills_mcp.domain.models.skill_name import SkillName
    from skills_mcp.domain.repositories import SkillRepository


logger = logging.getLogger(__name__)


class CompositeSkillRepository:
    """Repository that combines multiple skill repositories.

    Skills from all repositories are aggregated, with earlier repositories
    taking precedence for name conflicts. This allows local skills to
    override remote skills with the same name.

    When two repositories expose a skill with the same name, the lower-priority
    one is shadowed. The first such collision for a given (name, winner, loser)
    triple is surfaced at WARNING level with source provenance so operators can
    diagnose unexpected shadowing; subsequent occurrences of the same collision
    are logged at DEBUG to avoid log spam (``list_all`` runs on every
    ``resources/list``, ``tools/list``, ``prompts/list``, and ``list_skills``).

    Example:
        local_repo = LocalSkillRepository([Path("./skills")])
        oci_repo = OCISkillRepository(oci_config)
        combined = CompositeSkillRepository([local_repo, oci_repo])
        # Local skills take precedence over OCI skills
    """

    def __init__(self, repositories: list[SkillRepository]) -> None:
        """Initialize the composite repository.

        Args:
            repositories: List of repositories to aggregate, in priority order.
        """
        if not repositories:
            raise ValueError("At least one repository is required")
        self._repositories = repositories
        # Tracks (name, winner index, loser index) collisions already warned
        # about, so each unique collision is surfaced at WARNING only once.
        self._warned_collisions: set[tuple[str, int, int]] = set()

    def _source_label(self, index: int) -> str:
        """Return a human-readable provenance label for a repository index.

        Args:
            index: The index of the repository in the priority-ordered list.

        Returns:
            A label like ``LocalSkillRepository[0]`` identifying the source.
        """
        return f"{type(self._repositories[index]).__name__}[{index}]"

    async def list_all(self) -> list[Skill]:
        """List all skills from all repositories.

        If multiple repositories expose a skill with the same name, the
        first (highest-priority) repository's version wins and the shadowed
        version is dropped. The first occurrence of each unique collision is
        logged at WARNING with source provenance; repeats are logged at DEBUG.

        Returns:
            Combined list of skills. If multiple repositories have a skill
            with the same name, the first repository's version is used.
        """
        first_seen: dict[str, int] = {}
        all_skills: list[Skill] = []

        for idx, repo in enumerate(self._repositories):
            skills = await repo.list_all()
            for skill in skills:
                assert skill.skill_path is not None
                canonical_path = skill.skill_path.value
                if canonical_path not in first_seen:
                    first_seen[canonical_path] = idx
                    all_skills.append(skill)
                else:
                    winner_idx = first_seen[canonical_path]
                    collision = (canonical_path, winner_idx, idx)
                    # First sighting of a unique collision warns; repeats drop
                    # to DEBUG so per-request list_all calls don't flood logs.
                    if collision in self._warned_collisions:
                        level = logging.DEBUG
                    else:
                        self._warned_collisions.add(collision)
                        level = logging.WARNING
                    logger.log(
                        level,
                        "Skill path collision: '%s' from %s is shadowed by %s "
                        "(first-listed repository wins)",
                        canonical_path,
                        self._source_label(idx),
                        self._source_label(winner_idx),
                    )

        return all_skills

    async def find_by_name(self, name: SkillName) -> Skill | None:
        """Find a skill by name across all repositories.

        Args:
            name: The skill name to search for.

        Returns:
            The first matching skill found, or None if not found.
        """
        for repo in self._repositories:
            skill = await repo.find_by_name(name)
            if skill is not None:
                return skill
        return None

    async def get_resource_content(
        self, skill_name: SkillName, resource_type: str, resource_name: str
    ) -> bytes:
        """Get resource content, delegating to the repository that owns the skill.

        Args:
            skill_name: The skill name.
            resource_type: The resource type.
            resource_name: The resource filename.

        Returns:
            The resource content.

        Raises:
            SkillNotFoundError: If no repository has the skill.
            ResourceNotFoundError: If the resource doesn't exist.
        """
        for repo in self._repositories:
            skill = await repo.find_by_name(skill_name)
            if skill is not None:
                return await repo.get_resource_content(
                    skill_name, resource_type, resource_name
                )

        raise SkillNotFoundError(skill_name.value)

    async def refresh(self) -> None:
        """Refresh all underlying repositories."""
        for repo in self._repositories:
            await repo.refresh()
