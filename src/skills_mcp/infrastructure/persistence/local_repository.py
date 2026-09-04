"""Local filesystem skill repository.

Reads skills from local filesystem directories, parsing SKILL.md files
and discovering resources in scripts/, references/, and assets/ subdirectories.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import TYPE_CHECKING

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.resource import ResourceType
from skills_mcp.domain.services.manifest_parser import ManifestParser
from skills_mcp.domain.services.token_estimator import TokenEstimator
from skills_mcp.infrastructure.persistence.skill_loader import SkillLoader, is_path_safe


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill import Skill
    from skills_mcp.domain.models.skill_name import SkillName


logger = logging.getLogger(__name__)


SKILL_MANIFEST_FILENAME = "SKILL.md"

# Maximum resource size (10 MB) to prevent memory exhaustion
MAX_RESOURCE_SIZE_BYTES = 10 * 1024 * 1024


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
        self._loader = SkillLoader(self._parser, self._token_estimator)
        self._skills_cache: dict[str, Skill] | None = None
        self._cache_lock = asyncio.Lock()

    async def list_all(self) -> list[Skill]:
        """List all available skills.

        Returns:
            List of all discovered skills.
        """
        async with self._cache_lock:
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
        async with self._cache_lock:
            if self._skills_cache is None:
                await self._load_skills()
            if not self._skills_cache:
                return None
            return next(
                (skill for skill in self._skills_cache.values() if skill.name == name),
                None,
            )

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
            # Check file size to prevent memory exhaustion
            file_size = resolved_path.stat().st_size
            if file_size > MAX_RESOURCE_SIZE_BYTES:
                reason = f"Resource too large: {file_size} > {MAX_RESOURCE_SIZE_BYTES}"
                raise ResourceNotFoundError(
                    skill_name.value, resource_type, resource_name, reason
                )
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
        async with self._cache_lock:
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
        """Recursively scan one source root for strict skills."""
        manifests = sorted(
            (
                path
                for path in base_path.rglob(  # noqa: ASYNC240
                    SKILL_MANIFEST_FILENAME
                )
                if path.is_file()
            ),
            key=lambda path: path.as_posix(),
        )
        for manifest_path in manifests:
            skill_dir = manifest_path.parent
            try:
                skill = await self._load_skill(
                    skill_dir,
                    manifest_path,
                    skill_dir.relative_to(base_path).as_posix(),
                )
                assert skill.skill_path is not None
                canonical_path = skill.skill_path.value
                if self._skills_cache is not None:
                    if canonical_path in self._skills_cache:
                        logger.warning(
                            "Skill path %r from root %s is shadowed by an earlier "
                            "configured root",
                            canonical_path,
                            base_path,
                        )
                        continue
                    self._skills_cache[canonical_path] = skill
                logger.debug("Loaded skill path: %s", canonical_path)
            except Exception:
                logger.exception("Failed to load skill from %s", skill_dir)

    async def _load_skill(
        self,
        skill_dir: Path,
        manifest_path: Path,
        source_relative_path: str | None = None,
    ) -> Skill:
        """Load a strict skill from disk with the shared loader."""
        skill = self._loader.load_skill(
            skill_dir,
            manifest_path,
            lambda content, source, _name: (
                *self._parser.parse_bytes(content, source),
                True,
            ),
            source_relative_path,
        )
        if skill is None:
            raise ValueError(
                "Skill manifest is unsafe or its name mismatches its directory"
            )
        return skill

    def _is_path_safe(self, path: Path, base_path: Path) -> bool:
        """Check whether a path resolves within its skill directory."""
        return is_path_safe(path, base_path)
