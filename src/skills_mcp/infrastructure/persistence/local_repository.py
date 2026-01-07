"""Local filesystem skill repository.

Reads skills from local filesystem directories, parsing SKILL.md files
and discovering resources in scripts/, references/, and assets/ subdirectories.
"""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import TYPE_CHECKING

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.resource import ResourceType, SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.services.manifest_parser import ManifestParser
from skills_mcp.domain.services.token_estimator import TokenEstimator


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill_name import SkillName


logger = logging.getLogger(__name__)


SKILL_MANIFEST_FILENAME = "SKILL.md"


class LocalSkillRepository:
    """Repository that reads skills from local filesystem directories.

    This repository scans specified directories for skill folders containing
    SKILL.md manifest files. Each skill folder may also contain:
    - scripts/ - Executable scripts
    - references/ - Reference documentation
    - assets/ - Static assets

    The repository provides path traversal protection to prevent accessing
    files outside the configured skill directories.

    Example:
        repo = LocalSkillRepository([Path("/path/to/skills")])
        skills = await repo.list_all()
        skill = await repo.find_by_name(SkillName("data-analysis"))
    """

    def __init__(
        self,
        paths: list[Path],
        *,
        parser: ManifestParser | None = None,
        token_estimator: TokenEstimator | None = None,
    ) -> None:
        """Initialize the local skill repository.

        Args:
            paths: List of directories to scan for skills.
            parser: Optional ManifestParser instance. If not provided, a new one
                is created.
            token_estimator: Optional TokenEstimator instance. If not provided,
                a new one is created.
        """
        self._paths = [p.resolve() for p in paths]
        self._parser = parser or ManifestParser()
        self._token_estimator = token_estimator or TokenEstimator()
        self._skills_cache: dict[str, Skill] | None = None

    async def list_all(self) -> list[Skill]:
        """List all available skills.

        Returns:
            List of all discovered skills.
        """
        if self._skills_cache is None:
            await self._load_skills()
        return list(self._skills_cache.values()) if self._skills_cache else []

    async def find_by_name(self, name: SkillName) -> Skill | None:
        """Find a skill by its name.

        Args:
            name: The skill name to search for.

        Returns:
            The matching skill, or None if not found.
        """
        if self._skills_cache is None:
            await self._load_skills()
        return self._skills_cache.get(name.value) if self._skills_cache else None

    async def get_resource_content(
        self, skill_name: SkillName, resource_type: str, resource_name: str
    ) -> bytes:
        """Get the content of a skill resource.

        Args:
            skill_name: The name of the skill.
            resource_type: The resource type (scripts, references, or assets).
            resource_name: The filename of the resource.

        Returns:
            The resource content as bytes.

        Raises:
            SkillNotFoundError: If the skill doesn't exist.
            ResourceNotFoundError: If the resource doesn't exist.
        """
        skill = await self.find_by_name(skill_name)
        if skill is None:
            raise SkillNotFoundError(skill_name.value)

        # Validate resource type
        try:
            res_type = ResourceType(resource_type)
        except ValueError as exc:
            raise ResourceNotFoundError(
                skill_name.value, resource_type, resource_name
            ) from exc

        # Find the resource in the skill
        resource = skill.get_resource(res_type, resource_name)
        if resource is None:
            raise ResourceNotFoundError(skill_name.value, resource_type, resource_name)

        # Validate path is within skill directory (path traversal protection)
        resolved_path = resource.path.resolve()
        if not self._is_path_safe(resolved_path, skill.path):
            raise ResourceNotFoundError(skill_name.value, resource_type, resource_name)

        try:
            return resolved_path.read_bytes()
        except OSError as exc:
            raise ResourceNotFoundError(
                skill_name.value, resource_type, resource_name
            ) from exc

    async def refresh(self) -> None:
        """Refresh the skill cache from disk.

        This clears the internal cache and forces a rescan of all skill
        directories on the next access.
        """
        self._skills_cache = None
        logger.info("Skill cache cleared, will reload on next access")

    async def _load_skills(self) -> None:
        """Scan directories and load all skills into cache."""
        self._skills_cache = {}

        for base_path in self._paths:
            if not base_path.exists():
                logger.warning("Skill path does not exist: %s", base_path)
                continue

            if not base_path.is_dir():
                logger.warning("Skill path is not a directory: %s", base_path)
                continue

            await self._scan_directory(base_path)

        logger.info(
            "Loaded %d skills from %d paths",
            len(self._skills_cache),
            len(self._paths),
        )

    async def _scan_directory(self, base_path: Path) -> None:
        """Scan a directory for skill folders.

        Args:
            base_path: The directory to scan.
        """
        for item in base_path.iterdir():
            if not item.is_dir():
                continue

            manifest_path = item / SKILL_MANIFEST_FILENAME
            if not manifest_path.exists():
                continue

            try:
                skill = await self._load_skill(item, manifest_path)
                if self._skills_cache is not None:
                    self._skills_cache[skill.name.value] = skill
                logger.debug("Loaded skill: %s", skill.name.value)
            except Exception:
                logger.exception("Failed to load skill from %s", item)

    async def _load_skill(self, skill_dir: Path, manifest_path: Path) -> Skill:
        """Load a single skill from disk.

        Args:
            skill_dir: The skill directory.
            manifest_path: Path to the SKILL.md file.

        Returns:
            The loaded Skill object.
        """
        # Parse the manifest
        manifest, body = self._parser.parse_file(manifest_path)

        # Estimate tokens for the body
        token_count = self._token_estimator.estimate(body)

        # Discover resources
        scripts = await self._discover_resources(skill_dir / "scripts")
        references = await self._discover_resources(skill_dir / "references")
        assets = await self._discover_resources(skill_dir / "assets")

        return Skill(
            manifest=manifest,
            body=body,
            path=skill_dir.resolve(),
            scripts=scripts,
            references=references,
            assets=assets,
            token_count=token_count,
        )

    async def _discover_resources(self, resource_dir: Path) -> list[SkillResource]:
        """Discover resources in a resource directory.

        Args:
            resource_dir: The directory to scan (scripts/, references/, or assets/).

        Returns:
            List of discovered resources.
        """
        if not resource_dir.exists() or not resource_dir.is_dir():
            return []

        resources = []
        for item in resource_dir.iterdir():
            if not item.is_file():
                continue

            # Skip hidden files
            if item.name.startswith("."):
                continue

            try:
                # Estimate token count for the resource
                content = item.read_bytes()
                token_count = self._token_estimator.estimate_file(content)

                resource = SkillResource.from_path(item.resolve(), token_count)
                resources.append(resource)
            except Exception:
                logger.exception("Failed to load resource: %s", item)

        return resources

    def _is_path_safe(self, path: Path, base_path: Path) -> bool:
        """Check if a path is safe (within the base path).

        This prevents path traversal attacks by ensuring the resolved path
        is within the expected skill directory.

        Args:
            path: The path to check.
            base_path: The base path that should contain the file.

        Returns:
            True if the path is safe, False otherwise.
        """
        try:
            resolved = path.resolve()
            base_resolved = base_path.resolve()
            return resolved.is_relative_to(base_resolved)
        except (ValueError, OSError):
            return False
