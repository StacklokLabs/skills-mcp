"""Canonical source-relative identity for a skill."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class SkillPath:
    """Normalized relative POSIX path identifying a skill within its source."""

    value: str

    def __post_init__(self) -> None:
        """Validate and normalize the relative path."""
        if not isinstance(self.value, str):
            raise TypeError("skill path must be a string")
        if "\\" in self.value or self.value.startswith("/"):
            raise ValueError("skill path must be a relative POSIX path")
        path = PurePosixPath(self.value)
        if (
            not self.value
            or self.value.endswith("/")
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("skill path contains an invalid segment")
        normalized = path.as_posix()
        if normalized != self.value:
            raise ValueError("skill path must be normalized")
