"""Repository interfaces for skill storage.

Defines the abstract interfaces that storage implementations must follow.
This allows the domain layer to remain independent of specific storage
mechanisms (filesystem, Git, OCI, database, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill import Skill
    from skills_mcp.domain.models.skill_name import SkillName


@runtime_checkable
class SkillRepository(Protocol):
    """Abstract skill repository interface.

    This protocol defines the contract that all skill storage implementations
    must follow. The domain layer depends only on this interface, allowing
    different storage backends to be used interchangeably.

    Implementations:
        - LocalSkillRepository: Reads from local filesystem
        - GitSkillRepository: Clones/pulls from Git repositories (future)
        - OCISkillRepository: Pulls from OCI registries (future)
        - DatabaseSkillRepository: Queries from SQL/NoSQL database (future)
        - CompositeSkillRepository: Combines multiple sources (future)

    Example:
        async def get_skill(repo: SkillRepository, name: str) -> Skill:
            skill_name = SkillName(name)
            skill = await repo.find_by_name(skill_name)
            if skill is None:
                raise SkillNotFoundError(name)
            return skill
    """

    async def list_all(self) -> list[Skill]:
        """List all available skills.

        Returns:
            List of all skills in the repository.
        """
        ...

    async def find_by_name(self, name: SkillName) -> Skill | None:
        """Find a skill by its name.

        Args:
            name: The skill name to find.

        Returns:
            The skill if found, None otherwise.
        """
        ...

    async def get_resource_content(
        self, skill_name: SkillName, resource_type: str, resource_name: str
    ) -> bytes:
        """Get the content of a resource within a skill.

        Args:
            skill_name: The name of the skill.
            resource_type: The type of resource ("scripts", "references", "assets").
            resource_name: The filename of the resource.

        Returns:
            The raw content of the resource.

        Raises:
            SkillNotFoundError: If the skill doesn't exist.
            ResourceNotFoundError: If the resource doesn't exist.
        """
        ...

    async def refresh(self) -> None:
        """Refresh the repository cache.

        This method should reload skills from the underlying storage,
        invalidating any cached data. Useful for detecting changes
        to skills on disk or in remote sources.
        """
        ...


@runtime_checkable
class SkillSource(Protocol):
    """Protocol for individual skill sources.

    A skill source represents a single source of skills (e.g., a directory,
    a Git repository, an OCI registry). Multiple sources can be combined
    using CompositeSkillRepository.

    This is a lower-level interface than SkillRepository, used internally
    for composing multiple sources.
    """

    @property
    def source_id(self) -> str:
        """Return a unique identifier for this source.

        Returns:
            String identifier (e.g., path, URL, registry).
        """
        ...

    async def discover(self) -> list[Skill]:
        """Discover all skills from this source.

        Returns:
            List of skills found in this source.
        """
        ...

    async def load_resource(
        self, skill_name: SkillName, resource_type: str, resource_name: str
    ) -> bytes:
        """Load a resource from a skill in this source.

        Args:
            skill_name: The name of the skill.
            resource_type: The type of resource.
            resource_name: The filename of the resource.

        Returns:
            The raw content of the resource.

        Raises:
            ResourceNotFoundError: If the resource doesn't exist.
        """
        ...
