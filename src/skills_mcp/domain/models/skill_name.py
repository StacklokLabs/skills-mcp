"""SkillName value object with validation.

Skill names must follow the Agent Skills specification:
- 1-64 characters long
- Contain only lowercase letters, numbers, and hyphens
- Start with a lowercase letter
- Not start or end with hyphens
- Not contain consecutive hyphens
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills_mcp.domain.exceptions import InvalidSkillNameError


# Regex pattern from Agent Skills specification
# Matches: lowercase letter, followed by optional groups of (hyphen + alphanumeric)
_SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

_MIN_LENGTH = 1
_MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class SkillName:
    """Validated skill name following the Agent Skills specification.

    This is an immutable value object that ensures the skill name is valid
    upon construction. Invalid names will raise InvalidSkillNameError.

    Examples of valid names:
        - "pdf-processing"
        - "data-analysis"
        - "code-review"
        - "my-skill-v2"

    Examples of invalid names:
        - "My-Skill" (uppercase)
        - "skill--name" (consecutive hyphens)
        - "-skill" (starts with hyphen)
        - "skill-" (ends with hyphen)
    """

    value: str

    def __post_init__(self) -> None:
        """Validate the skill name after initialization."""
        self._validate(self.value)

    @staticmethod
    def _validate(name: str) -> None:
        """Validate that a name follows the skill name specification.

        Args:
            name: The skill name to validate.

        Raises:
            InvalidSkillNameError: If the name is invalid.
        """
        if not name:
            raise InvalidSkillNameError(name, "name cannot be empty")

        if len(name) < _MIN_LENGTH:
            raise InvalidSkillNameError(
                name, f"name must be at least {_MIN_LENGTH} character(s)"
            )

        if len(name) > _MAX_LENGTH:
            raise InvalidSkillNameError(
                name, f"name must be at most {_MAX_LENGTH} characters"
            )

        if not _SKILL_NAME_PATTERN.match(name):
            reason = (
                "name must contain only lowercase letters, numbers, "
                "and single hyphens; must start with a letter and not "
                "end with a hyphen"
            )
            raise InvalidSkillNameError(name, reason)

    @classmethod
    def from_string(cls, name: str) -> SkillName:
        """Create a SkillName from a string.

        Args:
            name: The skill name string.

        Returns:
            A validated SkillName instance.

        Raises:
            InvalidSkillNameError: If the name is invalid.
        """
        return cls(value=name)

    @classmethod
    def is_valid(cls, name: str) -> bool:
        """Check if a name is valid without raising an exception.

        Args:
            name: The skill name to check.

        Returns:
            True if the name is valid, False otherwise.
        """
        try:
            cls._validate(name)
            return True
        except InvalidSkillNameError:
            return False

    def __str__(self) -> str:
        """Return the string representation of the skill name."""
        return self.value

    def __repr__(self) -> str:
        """Return the repr of the skill name."""
        return f"SkillName({self.value!r})"
