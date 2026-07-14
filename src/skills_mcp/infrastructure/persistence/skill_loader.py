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

import logging
from typing import TYPE_CHECKING

from skills_mcp.domain.models.resource import SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.infrastructure.persistence.mtime import file_mtime_utc


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from skills_mcp.domain.models.manifest import SkillManifest
    from skills_mcp.domain.services.manifest_parser import ManifestParser
    from skills_mcp.domain.services.token_estimator import TokenEstimator


logger = logging.getLogger(__name__)


# Maximum resource size (10 MB) to prevent memory exhaustion.
MAX_RESOURCE_SIZE_BYTES = 10 * 1024 * 1024


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
        read_manifest: Callable[[Path, str], tuple[SkillManifest, str] | None],
    ) -> Skill | None:
        """Load a single skill from a directory.

        Refuses a manifest that resolves outside its skill directory (e.g. a
        symlinked ``SKILL.md`` pointing at an arbitrary file) *before* reading
        it, then delegates parsing to the supplied strategy.

        Args:
            skill_dir: The directory containing the manifest.
            manifest_path: Path to the manifest file (any casing).
            read_manifest: Strategy returning ``(manifest, body)`` or ``None``.

        Returns:
            The loaded Skill, or None if it was skipped.
        """
        if not is_path_safe(manifest_path.resolve(), skill_dir):
            logger.warning(
                "Skipping skill: manifest resolves outside its directory: %s",
                manifest_path,
            )
            return None

        parsed = read_manifest(manifest_path, skill_dir.name)
        if parsed is None:
            return None
        manifest, body = parsed
        return self.build_skill(skill_dir, manifest, body, manifest_path)

    def build_skill(
        self,
        skill_dir: Path,
        manifest: SkillManifest,
        body: str,
        manifest_path: Path,
    ) -> Skill:
        """Assemble a Skill from a parsed manifest and discovered resources.

        Args:
            skill_dir: The skill directory.
            manifest: The parsed manifest.
            body: The manifest body content.
            manifest_path: Path to the manifest (for the last-modified stamp).

        Returns:
            The assembled Skill.
        """
        token_count = self._token_estimator.estimate(body)
        scripts = self.discover_resources(skill_dir / "scripts", skill_dir)
        references = self.discover_resources(skill_dir / "references", skill_dir)
        assets = self.discover_resources(skill_dir / "assets", skill_dir)

        return Skill(
            manifest=manifest,
            body=body,
            path=skill_dir.resolve(),
            scripts=scripts,
            references=references,
            assets=assets,
            token_count=token_count,
            last_modified=file_mtime_utc(manifest_path),
        )

    def discover_resources(
        self, resource_dir: Path, skill_dir: Path
    ) -> list[SkillResource]:
        """Discover resources in a resource directory.

        Args:
            resource_dir: The directory to scan (scripts/, references/, assets/).
            skill_dir: The skill directory (for path safety checks).

        Returns:
            List of discovered resources.
        """
        if not resource_dir.exists() or not resource_dir.is_dir():
            return []

        resources = []
        for item in resource_dir.iterdir():
            if not item.is_file():
                continue
            if item.name.startswith("."):
                continue

            try:
                resolved_path = item.resolve()
                if not is_path_safe(resolved_path, skill_dir):
                    logger.warning(
                        "Skipping resource outside skill directory: %s", item
                    )
                    continue

                content = item.read_bytes()
                token_count = self._token_estimator.estimate_file(content)
                resource = SkillResource.from_path(
                    resolved_path,
                    token_count,
                    last_modified=file_mtime_utc(resolved_path),
                )
                resources.append(resource)
            except OSError as exc:
                logger.warning("Failed to read resource %s: %s", item, exc)
            except ValueError as exc:
                logger.warning("Invalid resource %s: %s", item, exc)

        return resources
