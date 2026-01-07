"""Skill aggregate representing a complete skill definition.

The Skill is the aggregate root that combines:
- Manifest (parsed frontmatter metadata)
- Body (markdown instructions)
- Resources (scripts, references, assets)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from skills_mcp.domain.models.resource import ResourceType


if TYPE_CHECKING:
    from pathlib import Path

    from skills_mcp.domain.models.manifest import SkillManifest
    from skills_mcp.domain.models.resource import SkillResource
    from skills_mcp.domain.models.skill_name import SkillName


@dataclass(slots=True)
class Skill:
    """Complete skill with content and resources.

    This is the aggregate root for the skill domain. It contains:
    - manifest: Parsed SKILL.md frontmatter (Tier 1 metadata)
    - body: SKILL.md markdown content (Tier 2 instructions)
    - resources: Scripts, references, assets (Tier 3 on-demand)
    - token_count: Total estimated tokens for the body

    The skill follows the progressive disclosure model:
    - Tier 1: Only manifest.name and manifest.description are exposed
    - Tier 2: Full body is loaded when skill is accessed
    - Tier 3: Individual resources are loaded on-demand

    Attributes:
        manifest: The parsed SKILL.md frontmatter.
        body: The markdown body content of SKILL.md.
        path: The filesystem path to the skill directory.
        scripts: List of script resources.
        references: List of reference resources.
        assets: List of asset resources.
        token_count: Estimated token count for the body.
    """

    manifest: SkillManifest
    body: str
    path: Path
    scripts: list[SkillResource] = field(default_factory=list)
    references: list[SkillResource] = field(default_factory=list)
    assets: list[SkillResource] = field(default_factory=list)
    token_count: int = 0

    @property
    def name(self) -> SkillName:
        """Return the skill name from the manifest."""
        return self.manifest.name

    @property
    def description(self) -> str:
        """Return the skill description from the manifest."""
        return self.manifest.description

    @property
    def all_resources(self) -> list[SkillResource]:
        """Return all resources across all types."""
        return self.scripts + self.references + self.assets

    def get_resource(
        self, resource_type: ResourceType, name: str
    ) -> SkillResource | None:
        """Find a resource by type and name.

        Args:
            resource_type: The type of resource to find.
            name: The filename of the resource.

        Returns:
            The matching resource, or None if not found.
        """
        resources = self._get_resources_by_type(resource_type)
        for resource in resources:
            if resource.name == name:
                return resource
        return None

    def _get_resources_by_type(
        self, resource_type: ResourceType
    ) -> list[SkillResource]:
        """Get the resource list for a given type."""
        match resource_type:
            case ResourceType.SCRIPT:
                return self.scripts
            case ResourceType.REFERENCE:
                return self.references
            case ResourceType.ASSET:
                return self.assets
            case _:
                # Exhaustive match - this should never be reached
                return []

    @property
    def total_resource_tokens(self) -> int:
        """Return total estimated tokens across all resources."""
        return sum(r.token_count for r in self.all_resources)

    def to_metadata_dict(self) -> dict[str, object]:
        """Return minimal metadata for Tier 1 disclosure.

        Returns:
            Dictionary with name and description only.
        """
        return {
            "name": self.manifest.name.value,
            "description": self.manifest.description,
        }

    def to_instructions_dict(self) -> dict[str, object]:
        """Return full instructions for Tier 2 disclosure.

        Returns:
            Dictionary with body, token count, and resource summary.
        """
        return {
            "name": self.manifest.name.value,
            "description": self.manifest.description,
            "body": self.body,
            "token_count": self.token_count,
            "resources": {
                "scripts": [
                    {"name": r.name, "tokens": r.token_count} for r in self.scripts
                ],
                "references": [
                    {"name": r.name, "tokens": r.token_count} for r in self.references
                ],
                "assets": [
                    {"name": r.name, "tokens": r.token_count} for r in self.assets
                ],
            },
        }
