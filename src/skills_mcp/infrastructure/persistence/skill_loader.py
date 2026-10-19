"""Shared skill-loading helpers for filesystem-materialized repositories.

Both the OCI and Git repositories ultimately load skills from a directory tree
of extracted or cloned files. This module owns the pieces they genuinely
share — path-safety containment, resource discovery, and ``Skill`` assembly —
so the logic lives in exactly one place.

Each repository supplies its own manifest-reading strategy through the
``read_manifest`` callback: the OCI repository parses strictly (a missing
``name`` is an error), while the Git repository falls back to the directory
name. The loader owns the security-critical containment checks that must hold
regardless of strategy.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from skills_mcp.domain.models.resource import SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.models.skill_file import SkillFile
from skills_mcp.domain.models.skill_path import SkillPath
from skills_mcp.infrastructure.persistence.mtime import file_mtime_utc


if TYPE_CHECKING:
    from collections.abc import Callable

    from skills_mcp.domain.models.manifest import SkillManifest
    from skills_mcp.domain.services.manifest_parser import ManifestParser
    from skills_mcp.domain.services.token_estimator import TokenEstimator


logger = logging.getLogger(__name__)


MAX_RESOURCE_SIZE_BYTES = 10 * 1024 * 1024

# Accepted SEP-2640 limits for a static skill snapshot.
MAX_STATIC_SKILL_FILES = 512
MAX_STATIC_SKILL_BYTES = 16 * 1024 * 1024


def is_path_safe(path: Path, base_path: Path) -> bool:
    """Check that ``path`` resolves within ``base_path`` (traversal guard).

    Args:
        path: The path to check.
        base_path: The base path that should contain ``path``.

    Returns:
        True if ``path`` resolves inside ``base_path``, False otherwise.
    """
    try:
        resolved = path.resolve()
        base_resolved = base_path.resolve()
        return resolved.is_relative_to(base_resolved)
    except (ValueError, OSError):
        return False


class SkillLoader:
    """Loads ``Skill`` aggregates from a materialized skill directory."""

    def __init__(self, parser: ManifestParser, token_estimator: TokenEstimator) -> None:
        """Initialize the loader.

        Args:
            parser: Manifest parser used for token estimation defaults.
            token_estimator: Estimator for body and resource token counts.
        """
        self._parser = parser
        self._token_estimator = token_estimator

    def load_skill(
        self,
        skill_dir: Path,
        manifest_path: Path,
        read_manifest: Callable[
            [bytes, str, str], tuple[SkillManifest, str, bool] | None
        ],
        source_relative_path: str | None = None,
        expected_directory_name: str | None = None,
    ) -> Skill | None:
        """Load a single skill from a directory.

        Captures the directory through descriptor-relative traversal so every
        component is opened without following symlinks, then delegates parsing
        to the supplied strategy.

        Args:
            skill_dir: The directory containing the manifest.
            manifest_path: Path to the manifest file (any casing).
            read_manifest: Strategy accepting captured bytes, source label, and
                directory name, then returning ``(manifest, body, SEP eligible)``
                or ``None``.
            source_relative_path: Canonical path relative to the configured source.
            expected_directory_name: Logical directory name when the materialized
                backing directory is an implementation detail.

        Returns:
            The loaded Skill, or None if it was skipped.
        """
        manifest_relative_path = manifest_path.relative_to(skill_dir).as_posix()
        files = self.discover_files(skill_dir)
        manifest_file = next(
            (item for item in files if item.relative_path == manifest_relative_path),
            None,
        )
        if manifest_file is None:
            raise ValueError("Manifest must appear exactly once in the skill snapshot")
        parsed = read_manifest(
            manifest_file.content, str(manifest_path), skill_dir.name
        )
        if parsed is None:
            return None
        manifest, body, parser_sep_eligible = parsed
        is_source_root = source_relative_path == "."
        expected_directory_name = expected_directory_name or (
            source_relative_path.rsplit("/", 1)[-1]
            if source_relative_path is not None and not is_source_root
            else skill_dir.name
        )
        identity_matches = manifest.name.value == expected_directory_name
        if not identity_matches:
            logger.warning(
                "Skill %s frontmatter name %r does not match directory %r; "
                "keeping it for legacy access only",
                skill_dir,
                manifest.name.value,
                expected_directory_name,
            )
        try:
            skill_path = SkillPath(
                manifest.name.value
                if is_source_root
                else source_relative_path or skill_dir.name
            )
        except (TypeError, ValueError):
            skill_path = None
        return self.build_skill(
            skill_dir,
            manifest,
            body,
            skill_path,
            files,
            parser_sep_eligible
            and identity_matches
            and skill_path is not None
            and manifest_relative_path == "SKILL.md",
            manifest_relative_path,
        )

    def build_skill(
        self,
        skill_dir: Path,
        manifest: SkillManifest,
        body: str,
        skill_path: SkillPath | None,
        files: list[SkillFile],
        sep_eligible: bool,
        manifest_relative_path: str = "SKILL.md",
    ) -> Skill:
        """Assemble a Skill from a parsed manifest and discovered resources.

        Args:
            skill_dir: The skill directory.
            manifest: The parsed manifest.
            body: The manifest body content.
            skill_path: Source-relative identity, if valid.
            files: Complete immutable file snapshot.
            sep_eligible: Whether strict canonical identity validation passed.
            manifest_relative_path: Captured manifest path within the snapshot.

        Returns:
            The assembled Skill.
        """
        token_count = self._token_estimator.estimate(body)
        scripts = self._resources_from_snapshot(files, "scripts", skill_dir)
        references = self._resources_from_snapshot(files, "references", skill_dir)
        assets = self._resources_from_snapshot(files, "assets", skill_dir)

        return Skill(
            manifest=manifest,
            body=body,
            path=skill_dir.resolve(),
            skill_path=skill_path,
            raw_manifest=next(
                item.content
                for item in files
                if item.relative_path == manifest_relative_path
            ),
            files=files,
            sep_eligible=sep_eligible,
            scripts=scripts,
            references=references,
            assets=assets,
            token_count=token_count,
            last_modified=next(
                item.last_modified
                for item in files
                if item.relative_path == manifest_relative_path
            ),
        )

    def discover_files(self, skill_dir: Path) -> list[SkillFile]:
        """Capture every regular file without following traversed symlinks.

        Descriptor-relative traversal anchors the walk at one opened root and
        applies ``O_NOFOLLOW`` when each child is opened, closing the pathname
        race between discovery and capture. Platforms without the required
        ``dir_fd`` APIs use a post-open containment and inode-identity fallback.

        Args:
            skill_dir: Directory to snapshot.

        Returns:
            Sorted immutable file records.

        Raises:
            ValueError: If a file is unsafe, non-regular, or limits are exceeded.
        """
        if self._supports_descriptor_walk():
            return self._discover_files_at(skill_dir)
        return self._discover_files_fallback(skill_dir)

    @staticmethod
    def _supports_descriptor_walk() -> bool:
        """Return whether this platform supports the required openat-style APIs."""
        return (
            os.open in os.supports_dir_fd
            and os.listdir in os.supports_fd
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
        )

    def _discover_files_at(self, skill_dir: Path) -> list[SkillFile]:
        """Walk an opened root using descriptor-relative child opens."""
        root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            root_flags |= os.O_CLOEXEC
        try:
            root_fd = os.open(skill_dir, root_flags)
        except OSError as exc:
            raise ValueError(
                f"Cannot safely open skill directory {skill_dir}: {exc}"
            ) from exc

        files: list[SkillFile] = []
        total_size = 0
        try:
            if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
                raise ValueError(f"Skill root is not a directory: {skill_dir}")
            total_size = self._walk_directory_fd(
                root_fd, PurePosixPath(), files, total_size
            )
        finally:
            os.close(root_fd)
        return sorted(files, key=lambda item: item.relative_path)

    def _walk_directory_fd(
        self,
        directory_fd: int,
        relative_dir: PurePosixPath,
        files: list[SkillFile],
        total_size: int,
    ) -> int:
        """Recursively capture children of one already-open directory."""
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise ValueError(
                f"Cannot list skill directory {relative_dir}: {exc}"
            ) from exc

        for name in names:
            relative_path = relative_dir / name
            flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                descriptor = os.open(name, flags, dir_fd=directory_fd)
            except OSError as exc:
                raise ValueError(
                    f"Cannot safely open skill entry {relative_path}: {exc}"
                ) from exc
            try:
                source_stat = os.fstat(descriptor)
                if stat.S_ISDIR(source_stat.st_mode):
                    total_size = self._walk_directory_fd(
                        descriptor, relative_path, files, total_size
                    )
                    continue
                if not stat.S_ISREG(source_stat.st_mode):
                    raise ValueError(
                        f"Skill entry is not a regular file: {relative_path}"
                    )
                if len(files) >= MAX_STATIC_SKILL_FILES:
                    raise ValueError(
                        f"Static skill has more than {MAX_STATIC_SKILL_FILES} files"
                    )
                remaining = MAX_STATIC_SKILL_BYTES - total_size
                captured = self._read_bounded(descriptor, remaining)
                total_size += len(captured)
                if total_size > MAX_STATIC_SKILL_BYTES:
                    raise ValueError(
                        f"Static skill exceeds {MAX_STATIC_SKILL_BYTES} bytes"
                    )
                files.append(
                    self._skill_file(
                        relative_path.as_posix(), captured, source_stat.st_mtime
                    )
                )
            finally:
                os.close(descriptor)
        return total_size

    @staticmethod
    def _read_bounded(descriptor: int, remaining: int) -> bytes:
        """Read at most ``remaining + 1`` bytes from an opened regular file."""
        chunks: list[bytes] = []
        captured_size = 0
        while captured_size <= remaining:
            chunk = os.read(descriptor, remaining + 1 - captured_size)
            if not chunk:
                break
            chunks.append(chunk)
            captured_size += len(chunk)
        return b"".join(chunks)

    def _skill_file(
        self, relative_path: str, content: bytes, modified_timestamp: float
    ) -> SkillFile:
        """Build one immutable file record from descriptor-captured metadata."""
        return SkillFile(
            relative_path=relative_path,
            content=content,
            size=len(content),
            digest=f"sha256:{hashlib.sha256(content).hexdigest()}",
            last_modified=datetime.fromtimestamp(modified_timestamp, tz=UTC),
            token_count=self._token_estimator.estimate_file(content),
        )

    def _discover_files_fallback(self, skill_dir: Path) -> list[SkillFile]:
        """Capture files safely where descriptor-relative traversal is unavailable."""
        files: list[SkillFile] = []
        total_size = 0
        try:
            root = skill_dir.resolve(strict=True)
        except OSError as exc:
            raise ValueError(
                f"Cannot resolve skill directory {skill_dir}: {exc}"
            ) from exc

        for item in sorted(skill_dir.rglob("*"), key=lambda path: path.as_posix()):
            if item.is_symlink():
                raise ValueError(f"Skill snapshot cannot contain symlinks: {item}")
            if not item.is_file():
                continue
            if len(files) >= MAX_STATIC_SKILL_FILES:
                raise ValueError(
                    f"Static skill has more than {MAX_STATIC_SKILL_FILES} files"
                )
            flags = os.O_RDONLY | os.O_NONBLOCK
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(item, flags)
                try:
                    source_stat = os.fstat(descriptor)
                    resolved = item.resolve(strict=True)
                    path_stat = resolved.stat()
                    if not resolved.is_relative_to(root) or (
                        source_stat.st_dev,
                        source_stat.st_ino,
                    ) != (path_stat.st_dev, path_stat.st_ino):
                        raise ValueError(f"Skill file escapes its directory: {item}")
                    if not stat.S_ISREG(source_stat.st_mode):
                        raise ValueError(f"Skill entry is not a regular file: {item}")
                    remaining = MAX_STATIC_SKILL_BYTES - total_size
                    captured = self._read_bounded(descriptor, remaining)
                finally:
                    os.close(descriptor)
            except OSError as exc:
                raise ValueError(
                    f"Cannot safely snapshot skill file {item}: {exc}"
                ) from exc

            total_size += len(captured)
            if total_size > MAX_STATIC_SKILL_BYTES:
                raise ValueError(f"Static skill exceeds {MAX_STATIC_SKILL_BYTES} bytes")
            relative_path = item.relative_to(skill_dir).as_posix()
            files.append(
                self._skill_file(relative_path, captured, source_stat.st_mtime)
            )
        return files

    @staticmethod
    def _resources_from_snapshot(
        files: list[SkillFile], resource_type: str, skill_dir: Path
    ) -> list[SkillResource]:
        """Project legacy resources from already captured immutable bytes."""
        prefix = f"{resource_type}/"
        resources: list[SkillResource] = []
        for item in files:
            if not item.relative_path.startswith(prefix):
                continue
            name = item.relative_path.removeprefix(prefix)
            if "/" in name or name.startswith("."):
                continue
            resources.append(
                SkillResource.from_path(
                    skill_dir / item.relative_path,
                    item.token_count or 0,
                    last_modified=item.last_modified,
                )
            )
        return resources

    def discover_resources(
        self, resource_dir: Path, skill_dir: Path
    ) -> list[SkillResource]:
        """Discover legacy resources for compatibility-only repository callers."""
        if not resource_dir.is_dir():
            return []
        resources: list[SkillResource] = []
        for path in resource_dir.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            resolved = path.resolve()
            if not is_path_safe(resolved, skill_dir):
                continue
            try:
                with resolved.open("rb") as stream:
                    content = stream.read(MAX_RESOURCE_SIZE_BYTES + 1)
            except OSError:
                continue
            if len(content) > MAX_RESOURCE_SIZE_BYTES:
                continue
            resources.append(
                SkillResource.from_path(
                    resolved,
                    self._token_estimator.estimate_file(content),
                    last_modified=file_mtime_utc(resolved),
                )
            )
        return resources
