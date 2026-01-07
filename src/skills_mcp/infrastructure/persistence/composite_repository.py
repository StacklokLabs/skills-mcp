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

    async def list_all(self) -> list[Skill]:
        """List all skills from all repositories.

        Returns:
            Combined list of skills. If multiple repositories have a skill
            with the same name, the first repository's version is used.
        """
        seen_names: set[str] = set()
        all_skills: list[Skill] = []

        for repo in self._repositories:
            skills = await repo.list_all()
            for skill in skills:
                if skill.name.value not in seen_names:
                    seen_names.add(skill.name.value)
                    all_skills.append(skill)
                else:
                    logger.debug(
                        "Skipping duplicate skill '%s' from lower-priority repository",
                        skill.name.value,
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
