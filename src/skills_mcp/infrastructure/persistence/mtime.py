"""Shared filesystem mtime helper for skill repositories.

Both the local and OCI repositories derive the SEP-2640 ``lastModified``
annotation from file mtime. OCI artifacts are extracted from tarballs
(``tar.extractall``) or copied with ``copytree``/``copy2``, all of which
preserve archived mtimes, so the extracted mtime is a meaningful last-modified
signal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path


def file_mtime_utc(path: Path) -> datetime | None:
    """Return a file's last-modified time as a UTC datetime, or None.

    A stat failure (missing file, permission error) yields ``None`` so the
    caller can simply omit the ``lastModified`` annotation rather than fail.

    Args:
        path: Path to stat.

    Returns:
        The file's mtime as an aware UTC datetime, or ``None`` on stat failure.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=UTC)
