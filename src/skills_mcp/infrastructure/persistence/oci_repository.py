"""OCI registry skill repository.

Pulls skills from OCI registries using the oras library,
compatible with skillet's artifact format.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import oras.client

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.resource import ResourceType, SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.services.manifest_parser import ManifestParser
from skills_mcp.domain.services.token_estimator import TokenEstimator
from skills_mcp.infrastructure.persistence.oci_models import (
    OCIRepositoryConfig,
    OCISkillReference,
)


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill_name import SkillName


logger = logging.getLogger(__name__)


SKILL_MANIFEST_FILENAME = "SKILL.md"

# Maximum resource size (10 MB) to prevent memory exhaustion
MAX_RESOURCE_SIZE_BYTES = 10 * 1024 * 1024

# Security limits for tarball extraction
MAX_TARBALL_FILES = 1000  # Maximum files per skill
MAX_TARBALL_TOTAL_SIZE = 100 * 1024 * 1024  # 100 MB total extracted size


def _file_mtime_utc(path: Path) -> datetime | None:
    """Return a file's last-modified time as a UTC datetime, or None.

    OCI artifacts are extracted from tarballs (``tar.extractall``) or copied
    with ``copytree``/``copy2``, both of which preserve the archived mtimes, so
    the extracted mtime is a meaningful last-modified signal. A stat failure
    yields ``None`` so the caller omits the ``lastModified`` annotation.

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


class OCISkillRepository:
    """Repository that pulls skills from OCI registries.

    This repository fetches skills packaged as OCI artifacts from
    container registries like Docker Hub, GHCR, or private registries.
    Skills are cached locally after first pull for performance.

    The repository is compatible with skillet's artifact format.

    Example:
        config = OCIRepositoryConfig(
            skills=[
                OCISkillReference.from_string("ghcr.io/org/skill:v1.0"),
            ]
        )
        repo = OCISkillRepository(config)
        skills = await repo.list_all()
    """

    def __init__(
        self,
        config: OCIRepositoryConfig,
        *,
        parser: ManifestParser | None = None,
        token_estimator: TokenEstimator | None = None,
    ) -> None:
        """Initialize the OCI skill repository.

        Args:
            config: Repository configuration with skill references and auth.
            parser: Optional ManifestParser instance.
            token_estimator: Optional TokenEstimator instance.
        """
        self._config = config
        self._parser = parser or ManifestParser()
        self._token_estimator = token_estimator or TokenEstimator()
        self._skills_cache: dict[str, Skill] | None = None
        self._cache_lock = asyncio.Lock()
        self._cache_dir = config.cache_dir or OCIRepositoryConfig.default_cache_dir()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def list_all(self) -> list[Skill]:
        """List all configured skills from OCI registries.

        Returns:
            List of all skills that were successfully pulled.
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
        """Refresh skills from registries, invalidating cache.

        This clears the internal cache and forces re-pull of all skills
        on the next access.
        """
        async with self._cache_lock:
            self._skills_cache = None
            logger.info("OCI skill cache cleared, will reload on next access")

    async def _load_skills(self) -> None:
        """Pull and load all configured skills."""
        self._skills_cache = {}

        for skill_ref in self._config.skills:
            skill = await self._try_pull_skill(skill_ref)
            if skill is not None:
                self._skills_cache[skill.name.value] = skill

        logger.info("Loaded %d skills from OCI registries", len(self._skills_cache))

    async def _try_pull_skill(self, skill_ref: OCISkillReference) -> Skill | None:
        """Try to pull a skill, logging errors but not raising."""
        try:
            skill = await self._pull_skill(skill_ref)
            if skill is not None:
                logger.info("Loaded skill from OCI: %s", skill_ref.full_ref)
            return skill
        except (OSError, ValueError) as e:
            logger.warning("Failed to pull skill %s: %s", skill_ref.full_ref, e)
            return None
        except Exception:  # catch-all for unexpected oras/network errors
            logger.exception("Unexpected error pulling skill: %s", skill_ref.full_ref)
            return None

    async def _pull_skill(self, ref: OCISkillReference) -> Skill | None:
        """Pull a single skill from OCI registry.

        Args:
            ref: Reference to the skill artifact.

        Returns:
            The loaded Skill object, or None if pull failed.
        """
        # Check if already cached locally
        skill_dir = self._get_skill_cache_dir(ref)
        manifest_path = skill_dir / SKILL_MANIFEST_FILENAME

        if manifest_path.exists():
            logger.debug("Using cached skill: %s", ref.full_ref)
            return await self._load_skill_from_dir(skill_dir, manifest_path)

        # Pull from registry using oras
        logger.info("Pulling skill from registry: %s", ref.full_ref)

        # Run oras pull in thread pool (it's synchronous)
        loop = asyncio.get_event_loop()
        try:
            extracted_files = await loop.run_in_executor(
                None, self._pull_with_oras, ref, skill_dir
            )
        except (OSError, ValueError) as e:
            logger.warning("Failed to pull skill %s: %s", ref.full_ref, e)
            return None
        except Exception:  # catch-all for oras library errors
            logger.exception("Registry error pulling skill: %s", ref.full_ref)
            return None

        if not extracted_files:
            logger.warning("No files extracted for skill: %s", ref.full_ref)
            return None

        # Load the skill from extracted files
        if manifest_path.exists():
            return await self._load_skill_from_dir(skill_dir, manifest_path)

        logger.warning("No SKILL.md found in pulled artifact: %s", ref.full_ref)
        return None

    def _pull_with_oras(self, ref: OCISkillReference, output_dir: Path) -> list[str]:
        """Pull artifact using oras library (synchronous).

        Args:
            ref: Reference to the skill artifact.
            output_dir: Directory to extract files to.

        Returns:
            List of extracted file paths.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create oras client
        client = oras.client.OrasClient(hostname=ref.registry, insecure=False)

        # Configure auth if available
        if ref.registry in self._config.auth:
            auth_config = self._config.auth[ref.registry]
            if auth_config.username and auth_config.password:
                client.login(
                    hostname=ref.registry,
                    username=auth_config.username,
                    password=auth_config.password,
                )

        # Pull the artifact
        try:
            # Use a temporary directory for the pull
            with tempfile.TemporaryDirectory() as tmp_dir:
                result = client.pull(
                    target=ref.full_ref,
                    outdir=tmp_dir,
                )

                # result is a list of extracted files (or empty if response object)
                extracted_files: list[str] = result if isinstance(result, list) else []

                # Check if we got a tar.gz layer (skillet format)
                # and need to extract it
                tmp_path = Path(tmp_dir)
                for item in tmp_path.iterdir():
                    if item.suffix == ".gz" or item.name.endswith(".tar.gz"):
                        # Extract tar.gz to output directory
                        self._extract_tarball(item, output_dir)
                        extracted_files = [
                            str(f) for f in output_dir.rglob("*") if f.is_file()
                        ]
                    elif item.is_file():
                        # Copy individual files
                        dest = output_dir / item.name
                        shutil.copy2(item, dest)
                        extracted_files.append(str(dest))
                    elif item.is_dir():
                        # Copy directory tree
                        dest = output_dir / item.name
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                        extracted_files.extend(
                            str(f) for f in dest.rglob("*") if f.is_file()
                        )

                return extracted_files

        except Exception:  # re-raised after logging for debugging
            logger.exception("oras pull failed for: %s", ref.full_ref)
            raise

    def _extract_tarball(self, tarball_path: Path, output_dir: Path) -> None:
        """Extract a tar.gz archive safely.

        Args:
            tarball_path: Path to the tarball.
            output_dir: Directory to extract to.

        Raises:
            ValueError: If tarball contains unsafe paths or content.
        """
        with tarfile.open(tarball_path, "r:gz") as tar:
            members = tar.getmembers()

            # Security: validate all paths and types before extraction
            total_size = 0
            for member in members:
                # Check for path traversal
                if member.name.startswith("/") or ".." in member.name:
                    raise ValueError(f"Unsafe path in tarball: {member.name}")

                # Check for absolute paths
                member_path = Path(member.name)
                if member_path.is_absolute():
                    raise ValueError(f"Absolute path in tarball: {member.name}")

                # Reject symlinks (potential for traversal attacks)
                if member.issym() or member.islnk():
                    raise ValueError(f"Symlink not allowed in tarball: {member.name}")

                # Reject device files (security risk)
                if member.isblk() or member.ischr():
                    msg = f"Device file not allowed in tarball: {member.name}"
                    raise ValueError(msg)

                # Reject FIFOs/pipes (security risk)
                if member.isfifo():
                    raise ValueError(f"FIFO not allowed in tarball: {member.name}")

                # Track total size
                total_size += member.size

            # Enforce aggregate limits
            if len(members) > MAX_TARBALL_FILES:
                raise ValueError(
                    f"Too many files in tarball: {len(members)} > {MAX_TARBALL_FILES}"
                )

            if total_size > MAX_TARBALL_TOTAL_SIZE:
                raise ValueError(
                    f"Tarball too large: {total_size} > {MAX_TARBALL_TOTAL_SIZE}"
                )

            # Extract all members (filter="data" provides additional safety)
            tar.extractall(output_dir, filter="data")

    async def _load_skill_from_dir(self, skill_dir: Path, manifest_path: Path) -> Skill:
        """Load a skill from an extracted directory.

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
        scripts = await self._discover_resources(skill_dir / "scripts", skill_dir)
        references = await self._discover_resources(skill_dir / "references", skill_dir)
        assets = await self._discover_resources(skill_dir / "assets", skill_dir)

        return Skill(
            manifest=manifest,
            body=body,
            path=skill_dir.resolve(),  # noqa: ASYNC240  # sync local-fs by design
            scripts=scripts,
            references=references,
            assets=assets,
            token_count=token_count,
            # sync local-fs by design
            last_modified=_file_mtime_utc(manifest_path),
        )

    async def _discover_resources(
        self, resource_dir: Path, skill_dir: Path
    ) -> list[SkillResource]:
        """Discover resources in a resource directory.

        Args:
            resource_dir: The directory to scan (scripts/, references/, or assets/).
            skill_dir: The skill directory (for path safety checks).

        Returns:
            List of discovered resources.
        """
        # sync local-fs by design
        if not resource_dir.exists() or not resource_dir.is_dir():  # noqa: ASYNC240
            return []

        resources = []
        for item in resource_dir.iterdir():  # noqa: ASYNC240  # sync local-fs by design
            if not item.is_file():
                continue

            # Skip hidden files
            if item.name.startswith("."):
                continue

            try:
                # Resolve the path and check for path traversal
                resolved_path = item.resolve()
                if not self._is_path_safe(resolved_path, skill_dir):
                    logger.warning(
                        "Skipping resource outside skill directory: %s", item
                    )
                    continue

                # Estimate token count for the resource
                content = item.read_bytes()
                token_count = self._token_estimator.estimate_file(content)

                resource = SkillResource.from_path(
                    resolved_path,
                    token_count,
                    last_modified=_file_mtime_utc(resolved_path),
                )
                resources.append(resource)
            except OSError as e:
                logger.warning("Failed to read resource %s: %s", item, e)
            except ValueError as e:
                logger.warning("Invalid resource %s: %s", item, e)

        return resources

    def _get_skill_cache_dir(self, ref: OCISkillReference) -> Path:
        """Get the local cache directory for a skill.

        Args:
            ref: Reference to the skill.

        Returns:
            Path to the skill's cache directory.
        """
        # Use registry/namespace/name/tag structure
        safe_registry = ref.registry.replace(":", "_")
        safe_namespace = ref.namespace.replace("/", "_") if ref.namespace else "_"
        safe_tag = ref.tag.replace("/", "_")

        return self._cache_dir / safe_registry / safe_namespace / ref.name / safe_tag

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
