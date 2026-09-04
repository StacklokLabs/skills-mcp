"""Byte-faithful file metadata for extension-published skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class SkillFile:
    """An immutable file captured in a static skill snapshot.

    Attributes:
        relative_path: Normalized path relative to the skill directory.
        content: Exact bytes captured while loading the snapshot.
        size: Byte length of ``content``.
        digest: SHA-256 digest of ``content`` in ``sha256:<hex>`` form.
        last_modified: Best-effort source modification time.
        token_count: Optional estimated token count.
    """

    relative_path: str
    content: bytes
    size: int
    digest: str
    last_modified: datetime | None = None
    token_count: int | None = None
