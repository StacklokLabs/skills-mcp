"""SkillResource model representing a resource within a skill.

Resources are files within a skill directory that can be loaded on-demand:
- scripts/ - Executable code (Python, Bash, JavaScript)
- references/ - Documentation and reference materials
- assets/ - Static resources (templates, images, data)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path


class ResourceType(Enum):
    """Type of skill resource."""

    SCRIPT = "scripts"
    REFERENCE = "references"
    ASSET = "assets"

    @classmethod
    def from_path(cls, path: Path) -> ResourceType | None:
        """Determine resource type from file path.

        Args:
            path: Path to the resource file.

        Returns:
            The resource type, or None if not in a recognized directory.
        """
        parts = path.parts
        for part in parts:
            if part == "scripts":
                return cls.SCRIPT
            if part == "references":
                return cls.REFERENCE
            if part == "assets":
                return cls.ASSET
        return None


@dataclass(frozen=True, slots=True)
class SkillResource:
    """A resource within a skill (script, reference, or asset).

    Resources are loaded on-demand (Tier 3 in progressive disclosure)
    to minimize token usage until the agent explicitly needs them.

    Attributes:
        name: The filename of the resource (e.g., "analyze.py").
        path: The full path to the resource file.
        resource_type: The type of resource (script, reference, asset).
        token_count: Estimated token count for the resource content.
        last_modified: Last-modified timestamp of the resource file (UTC), or
            ``None`` if it could not be determined. Surfaced as the SEP-2640
            ``lastModified`` annotation on listed resources.
    """

    name: str
    path: Path
    resource_type: ResourceType
    token_count: int
    last_modified: datetime | None = None

    @classmethod
    def from_path(
        cls,
        path: Path,
        token_count: int,
        last_modified: datetime | None = None,
    ) -> SkillResource:
        """Create a SkillResource from a file path.

        Args:
            path: Path to the resource file.
            token_count: Estimated token count for the content.
            last_modified: Optional last-modified timestamp (UTC) for the file.

        Returns:
            A SkillResource instance.

        Raises:
            ValueError: If the path is not in a recognized resource directory.
        """
        resource_type = ResourceType.from_path(path)
        if resource_type is None:
            raise ValueError(
                f"Path '{path}' is not in a recognized resource directory "
                "(scripts/, references/, or assets/)"
            )

        return cls(
            name=path.name,
            path=path,
            resource_type=resource_type,
            token_count=token_count,
            last_modified=last_modified,
        )

    @property
    def uri_path(self) -> str:
        """Return the URI path segment for this resource.

        Returns:
            String like "scripts/analyze.py" for use in URIs.
        """
        return f"{self.resource_type.value}/{self.name}"

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.resource_type.value}/{self.name} ({self.token_count} tokens)"
