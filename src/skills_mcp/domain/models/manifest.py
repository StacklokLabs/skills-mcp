"""SkillManifest model representing parsed SKILL.md frontmatter.

The manifest contains metadata about a skill, parsed from the YAML
frontmatter in the SKILL.md file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill_name import SkillName

# Field length limits from Agent Skills specification
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
SHORT_DESCRIPTION_LENGTH = 100
SHORT_DESCRIPTION_ELLIPSIS_LENGTH = 97


@dataclass(frozen=True, slots=True)
class SkillManifest:
    """Parsed SKILL.md frontmatter.

    Contains all metadata fields from the Agent Skills specification.

    Required fields:
        - name: Validated skill name
        - description: What the skill does (1-1024 chars)

    Optional fields:
        - license: License name or reference
        - compatibility: Environment requirements (max 500 chars)
        - metadata: Arbitrary key-value pairs
        - allowed_tools: Pre-approved tools list (experimental)

    Attributes:
        name: The validated skill name.
        description: What the skill does and when to use it.
        license: Optional license identifier.
        compatibility: Optional environment requirements.
        metadata: Optional arbitrary key-value metadata.
        allowed_tools: Optional list of pre-approved tools.
    """

    name: SkillName
    description: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    raw_frontmatter: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate manifest fields after initialization."""
        # Validate description length
        if not self.description:
            raise ValueError("description cannot be empty")
        if len(self.description) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"description exceeds maximum length of {MAX_DESCRIPTION_LENGTH} "
                f"characters (got {len(self.description)})"
            )

        # Validate compatibility length if present
        if self.compatibility and len(self.compatibility) > MAX_COMPATIBILITY_LENGTH:
            raise ValueError(
                f"compatibility exceeds maximum length of {MAX_COMPATIBILITY_LENGTH} "
                f"characters (got {len(self.compatibility)})"
            )

    @property
    def description_short(self) -> str:
        """Return a shortened description for listings.

        Returns:
            Description truncated to 100 characters with ellipsis if needed.
        """
        if len(self.description) <= SHORT_DESCRIPTION_LENGTH:
            return self.description
        return self.description[:SHORT_DESCRIPTION_ELLIPSIS_LENGTH] + "..."

    def to_dict(self) -> dict[str, object]:
        """Convert manifest to a dictionary.

        Returns:
            Dictionary representation of the manifest.
        """
        if self.raw_frontmatter:
            return dict(self.raw_frontmatter)

        result: dict[str, object] = {
            "name": self.name.value,
            "description": self.description,
        }

        if self.license:
            result["license"] = self.license
        if self.compatibility:
            result["compatibility"] = self.compatibility
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        if self.allowed_tools:
            result["allowed_tools"] = list(self.allowed_tools)

        return result
