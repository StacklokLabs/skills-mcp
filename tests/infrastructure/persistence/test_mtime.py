"""Tests for the shared file_mtime_utc helper."""

from datetime import UTC, datetime
from pathlib import Path

from skills_mcp.infrastructure.persistence.mtime import file_mtime_utc


class TestFileMtimeUtc:
    """Tests for file_mtime_utc."""

    def test_returns_none_on_stat_failure(self, tmp_path: Path) -> None:
        """Returns None when the file cannot be stat'd."""
        assert file_mtime_utc(tmp_path / "does-not-exist") is None

    def test_returns_aware_utc_datetime(self, tmp_path: Path) -> None:
        """Returns an aware UTC datetime matching the file's mtime."""
        f = tmp_path / "file.txt"
        f.write_text("hi")

        result = file_mtime_utc(f)

        assert result is not None
        assert result.tzinfo is not None
        assert result == datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
