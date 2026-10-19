"""Git repository skill source backed by dulwich.

Fetches skills from Git repositories over HTTPS using dulwich's ``porcelain``
API. Each reference is materialized into a content-addressed cache directory
keyed by the resolved commit SHA; the ``.git`` metadata is deleted so the cache
is a plain snapshot that discovery walks directly.

Security posture:
    - Transport is always HTTPS; credentials are passed only as dulwich
      ``username``/``password`` keyword arguments, never interpolated into URLs.
    - A single ``getaddrinfo`` check runs before any clone and refuses hosts
      resolving to non-public addresses (bypass with ``allow_private_hosts``).
    - The discovery walk never follows symlinks and rejects resources that
      resolve outside the skill directory.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import ipaddress
import logging
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

import frontmatter
from dulwich import porcelain

from skills_mcp.domain.exceptions import (
    ManifestParseError,
    MissingRequiredFieldError,
    ResourceNotFoundError,
    SkillNotFoundError,
)
from skills_mcp.domain.models.resource import ResourceType
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.domain.services.manifest_parser import ManifestParser
from skills_mcp.domain.services.token_estimator import TokenEstimator
from skills_mcp.infrastructure.persistence.git_models import (
    GitRepositoryConfig,
    GitSkillReference,
    resolve_git_credentials,
)
from skills_mcp.infrastructure.persistence.skill_loader import (
    MAX_RESOURCE_SIZE_BYTES,
    SkillLoader,
    is_path_safe,
)


if TYPE_CHECKING:
    from collections.abc import Iterator

    from dulwich.repo import Repo

    from skills_mcp.domain.models.manifest import SkillManifest
    from skills_mcp.domain.models.skill import Skill


logger = logging.getLogger(__name__)


# Marker file written into a cache snapshot once it is fully materialized.
CACHE_COMPLETE_MARKER = ".skills-mcp-complete"

# Exact manifest filename required by the Agent Skills specification.
SKILL_MANIFEST_FILENAME = "SKILL.md"

# Directory names pruned from the discovery walk (besides dot-prefixed dirs),
# compared case-insensitively.
PRUNED_DIR_NAMES = frozenset({"template", "readme"})

# Prefix for in-progress clone temp dirs (created under the repo cache subtree
# so an atomic rename stays on one filesystem and orphans are recognizable).
CLONE_TMP_PREFIX = ".tmp-clone-"

# Per-repository cross-process lock filename.
REPO_LOCK_FILENAME = ".skills-mcp.lock"

# Orphaned clone temp dirs older than this (seconds) are swept before cloning.
ORPHAN_TMP_MAX_AGE_S = 3600

# Default HTTPS port used for the pre-clone DNS/SSRF check.
_DEFAULT_HTTPS_PORT = 443


class _PrivateHostError(ValueError):
    """Raised when a host resolves to a disallowed (non-public) address."""


class GitSkillRepository:
    """Repository that fetches skills from Git repositories over HTTPS.

    Skills are materialized into a content-addressed cache keyed by the
    resolved commit SHA. Pinned (40-hex) references are immutable and never
    re-fetch once cached; branch references re-resolve on refresh, producing a
    new snapshot directory when the branch tip moves.

    Example:
        config = GitRepositoryConfig(
            skills=[
                GitSkillReference.from_string("git://github.com/org/repo@v1.0"),
            ]
        )
        repo = GitSkillRepository(config)
        skills = await repo.list_all()
    """

    def __init__(
        self,
        config: GitRepositoryConfig,
        *,
        parser: ManifestParser | None = None,
        token_estimator: TokenEstimator | None = None,
    ) -> None:
        """Initialize the Git skill repository.

        Args:
            config: Repository configuration with references and per-host auth.
            parser: Optional ManifestParser instance.
            token_estimator: Optional TokenEstimator instance.
        """
        self._config = config
        self._parser = parser or ManifestParser()
        self._token_estimator = token_estimator or TokenEstimator()
        self._loader = SkillLoader(self._parser, self._token_estimator)
        self._skills_cache: dict[str, Skill] | None = None
        self._cache_lock = asyncio.Lock()
        self._cache_dir = config.cache_dir or GitRepositoryConfig.default_cache_dir()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def list_all(self) -> list[Skill]:
        """List all configured skills from Git repositories.

        Returns:
            List of all skills that were successfully fetched.
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

        try:
            res_type = ResourceType(resource_type)
        except ValueError as exc:
            raise ResourceNotFoundError(
                skill_name.value, resource_type, resource_name
            ) from exc

        resource = skill.get_resource(res_type, resource_name)
        if resource is None:
            raise ResourceNotFoundError(skill_name.value, resource_type, resource_name)

        # Validate path is within skill directory (path traversal protection).
        resolved_path = resource.path.resolve()
        if not is_path_safe(resolved_path, skill.path):
            raise ResourceNotFoundError(skill_name.value, resource_type, resource_name)

        try:
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
        """Refresh skills from repositories, invalidating the in-memory cache.

        This clears the internal cache and forces re-resolution on the next
        access. Pinned references hit their immutable snapshot with no network;
        branch references re-resolve and may produce a new snapshot directory.
        """
        async with self._cache_lock:
            self._skills_cache = None
            logger.info("Git skill cache cleared, will reload on next access")

    async def _load_skills(self) -> None:
        """Fetch and load all configured skills."""
        self._skills_cache = {}

        for skill_ref in self._config.skills:
            skills = await self._try_fetch_repo(skill_ref)
            for skill in skills:
                assert skill.skill_path is not None
                canonical_path = skill.skill_path.value
                if canonical_path in self._skills_cache:
                    logger.warning(
                        "Skill path %r from %s already provided by an earlier "
                        "reference; keeping the first",
                        canonical_path,
                        skill_ref.full_ref,
                    )
                    continue
                self._skills_cache[canonical_path] = skill

        logger.info("Loaded %d skills from Git repositories", len(self._skills_cache))

    async def _try_fetch_repo(self, ref: GitSkillReference) -> list[Skill]:
        """Fetch one repository, logging failures but never raising."""
        try:
            return await self._fetch_repo(ref)
        except (OSError, ValueError) as exc:
            logger.warning("Failed to fetch git repo %s: %s", ref.full_ref, exc)
            return []
        except Exception:  # catch-all for unexpected dulwich/network errors
            logger.exception("Unexpected error fetching git repo: %s", ref.full_ref)
            return []

    async def _fetch_repo(self, ref: GitSkillReference) -> list[Skill]:
        """Materialize a reference and discover its skills.

        Args:
            ref: The reference to fetch.

        Returns:
            The discovered skills, or an empty list if materialization failed.
        """
        materialized = await self._materialize(ref)
        if materialized is None:
            return []
        sha_dir, resolved_sha = materialized

        walk_root = sha_dir
        if ref.subdir is not None:
            candidate = (sha_dir / ref.subdir).resolve()
            if not is_path_safe(candidate, sha_dir):
                logger.warning(
                    "Subdir %r escapes repository root for %s; skipping",
                    ref.subdir,
                    ref.full_ref,
                )
                return []
            if not candidate.is_dir():
                logger.warning(
                    "Subdir %r not found for %s; skipping", ref.subdir, ref.full_ref
                )
                return []
            walk_root = candidate

        return await self._discover_skills(walk_root, sha_dir, ref, resolved_sha)

    async def _materialize(  # noqa: PLR0911 - distinct cache/offline exit paths
        self, ref: GitSkillReference
    ) -> tuple[Path, str] | None:
        """Resolve a reference to a cached snapshot directory.

        Args:
            ref: The reference to materialize.

        Returns:
            A ``(snapshot_dir, resolved_sha)`` tuple, or ``None`` if the
            reference could not be materialized.
        """
        loop = asyncio.get_event_loop()
        pinned = ref.pinned_sha

        # Pinned references are immutable: a complete snapshot needs no network.
        if pinned is not None:
            sha_dir = self._sha_dir(ref, pinned)
            if self._is_complete(sha_dir):
                logger.debug("Git cache hit (pinned): %s", ref.full_ref)
                return sha_dir, pinned

        url = ref.url_override or ref.https_url
        creds = resolve_git_credentials(ref.host, self._config.auth)

        # Pre-clone DNS/SSRF check (skipped for local url_override fixtures).
        if ref.url_override is None:
            try:
                await loop.run_in_executor(None, self._check_host_allowed, ref.host)
            except _PrivateHostError as exc:
                logger.warning("Refusing git host for %s: %s", ref.full_ref, exc)
                return None
            except OSError as exc:
                logger.warning(
                    "DNS resolution failed for %s: %s; trying cache",
                    ref.full_ref,
                    exc,
                )
                return self._offline(ref)

        # Resolve the reference to a commit SHA (network unless pinned).
        try:
            resolved = await asyncio.wait_for(
                loop.run_in_executor(None, self._resolve_sha, ref, url, creds, pinned),
                timeout=self._config.clone_timeout,
            )
        except TimeoutError:
            logger.warning("Timed out resolving %s; trying cache", ref.full_ref)
            return self._offline(ref)
        except Exception as exc:  # any failure falls back to the cache
            logger.warning("Failed to resolve %s: %s; trying cache", ref.full_ref, exc)
            return self._offline(ref)

        resolved_sha, resolved_ref = resolved
        sha_dir = self._sha_dir(ref, resolved_sha)
        if self._is_complete(sha_dir):
            logger.debug("Git cache hit: %s -> %s", ref.full_ref, resolved_sha[:12])
            self._write_pointer(ref, resolved_sha)
            return sha_dir, resolved_sha

        # Clone into the cache (atomic move on success only).
        try:
            ok = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    self._clone_to_cache,
                    ref,
                    url,
                    creds,
                    resolved_sha,
                    resolved_ref,
                    sha_dir,
                ),
                timeout=self._config.clone_timeout,
            )
        except TimeoutError:
            logger.warning("Timed out cloning %s", ref.full_ref)
            return None

        if not ok:
            return None
        self._write_pointer(ref, resolved_sha)
        return sha_dir, resolved_sha

    def _check_host_allowed(self, host: str) -> None:
        """Reject hosts resolving to non-public addresses (SSRF guard).

        Args:
            host: The Git host authority (may include a port).

        Raises:
            _PrivateHostError: If the host resolves to a disallowed address.
            OSError: If DNS resolution fails (treated as unreachable upstream).
        """
        if self._config.allow_private_hosts:
            return
        hostname, port = self._split_host_port(host)
        infos = socket.getaddrinfo(
            hostname, port or _DEFAULT_HTTPS_PORT, proto=socket.IPPROTO_TCP
        )
        addresses = [info[4][0] for info in infos]
        if not addresses:
            raise _PrivateHostError(f"no addresses resolved for {host!r}")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
                or ip.is_multicast
            ):
                raise _PrivateHostError(
                    f"{host!r} resolves to non-public address {address}"
                )

    @staticmethod
    def _split_host_port(host: str) -> tuple[str, int | None]:
        """Split a host authority into ``(hostname, port)``."""
        if host.startswith("["):
            end = host.find("]")
            name = host[1:end]
            rest = host[end + 1 :]
            port = int(rest[1:]) if rest.startswith(":") else None
            return name, port
        if host.count(":") == 1:
            name, raw_port = host.rsplit(":", 1)
            return name, int(raw_port)
        return host, None

    def _resolve_sha(
        self,
        ref: GitSkillReference,
        url: str,
        creds: tuple[str, str] | None,
        pinned: str | None,
    ) -> tuple[str, str]:
        """Resolve a reference to ``(commit_sha, resolved_ref_name)``.

        Runs in an executor thread. For pinned references the SHA is already
        known; otherwise ``ls_remote`` is queried (tags before heads).

        Args:
            ref: The reference being resolved.
            url: The HTTPS clone URL (or local override path).
            creds: Optional ``(username, password)`` credentials.
            pinned: A pre-resolved commit SHA, or ``None``.

        Returns:
            A ``(commit_sha, resolved_ref_name)`` tuple.

        Raises:
            ValueError: If the ref cannot be found on the remote.
        """
        if pinned is not None:
            return pinned, (ref.ref or "HEAD")

        username, password = creds if creds is not None else (None, None)
        result = porcelain.ls_remote(url, username=username, password=password)
        # Ref/ObjectID are NewType aliases of bytes; cast to the plain type.
        raw_refs = cast("dict[bytes, bytes | None]", result.refs)
        return self._select_sha(ref, raw_refs)

    def _select_sha(
        self,
        ref: GitSkillReference,
        raw_refs: dict[bytes, bytes | None],
    ) -> tuple[str, str]:
        """Select a commit SHA from an ls_remote result.

        Args:
            ref: The reference being resolved.
            raw_refs: The remote's advertised refs (values may be ``None``).

        Returns:
            A ``(commit_sha, resolved_ref_name)`` tuple.

        Raises:
            ValueError: If the ref cannot be found.
        """
        refs = {
            k.decode("utf-8", "replace"): v.decode("utf-8", "replace")
            for k, v in raw_refs.items()
            if v is not None
        }

        if ref.ref is None:
            head = refs.get("HEAD")
            if not head:
                raise ValueError(f"remote advertises no HEAD: {ref.full_ref}")
            return head, "HEAD"

        name = ref.ref
        # Prefer a peeled tag (dereferenced to its commit), then the tag itself,
        # then a branch head. Peeled refs are only advertised over HTTP smart
        # transport; local/other transports degrade to the plain tag ref.
        for key in (f"refs/tags/{name}^{{}}", f"refs/tags/{name}"):
            if key in refs:
                return refs[key], name
        head_key = f"refs/heads/{name}"
        if head_key in refs:
            return refs[head_key], name
        raise ValueError(f"ref {name!r} not found on remote: {ref.full_ref}")

    def _clone_to_cache(
        self,
        ref: GitSkillReference,
        url: str,
        creds: tuple[str, str] | None,
        resolved_sha: str,
        resolved_ref: str,
        sha_dir: Path,
    ) -> bool:
        """Clone a reference into the cache, atomically on success.

        Runs in an executor thread. Clones into a temporary directory under the
        repository's own cache subtree, strips ``.git``, writes the completion
        marker, then atomically renames into the SHA directory under a
        per-repository cross-process lock. Completion is idempotent: if the SHA
        directory is already complete (a concurrent process, or a late-arriving
        thread whose ``asyncio.wait_for`` already timed out), the temp dir is
        discarded — content is identical per SHA, so this is a safe no-op. This
        means a failed, timed-out, or racing clone never poisons the cache.

        Args:
            ref: The reference being cloned.
            url: The HTTPS clone URL (or local override path).
            creds: Optional ``(username, password)`` credentials.
            resolved_sha: The resolved commit SHA.
            resolved_ref: The resolved ref name (or ``"HEAD"``).
            sha_dir: The destination snapshot directory.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        repo_root = self._repo_cache_root(ref)
        repo_root.mkdir(parents=True, exist_ok=True)
        self._sweep_orphan_tempdirs(repo_root)
        tmp = Path(tempfile.mkdtemp(dir=repo_root, prefix=CLONE_TMP_PREFIX))
        pinned = ref.pinned_sha is not None
        # Pinned commits need a full clone (no want-by-SHA porcelain surface),
        # then an explicit checkout. Branches/tags use a shallow clone.
        depth = None if pinned else 1
        branch = None if (pinned or resolved_ref == "HEAD") else resolved_ref
        try:
            repo = self._run_clone(url, tmp, depth, branch, creds)
            try:
                if pinned:
                    porcelain.checkout(repo, target=resolved_sha)
            finally:
                repo.close()

            self._strip_git_dir(tmp)
            (tmp / CACHE_COMPLETE_MARKER).write_text(
                f"{resolved_sha}\n{resolved_ref}\n", encoding="utf-8"
            )
            with self._repo_lock(repo_root):
                if self._is_complete(sha_dir):
                    # Already materialized by a concurrent process/thread;
                    # the content is identical per SHA, so discard our copy.
                    shutil.rmtree(tmp, ignore_errors=True)
                    logger.debug(
                        "Snapshot already present for %s -> %s; discarding clone",
                        ref.full_ref,
                        resolved_sha[:12],
                    )
                    return True
                if sha_dir.exists():
                    shutil.rmtree(sha_dir, ignore_errors=True)
                tmp.replace(sha_dir)
        except Exception:  # failure is logged; the temp dir is cleaned up
            logger.exception("Git clone failed for %s", ref.full_ref)
            shutil.rmtree(tmp, ignore_errors=True)
            return False
        else:
            logger.info("Cloned %s -> %s", ref.full_ref, resolved_sha[:12])
            return True

    @contextlib.contextmanager
    def _repo_lock(self, repo_root: Path) -> Iterator[None]:
        """Hold a per-repository cross-process lock (bounded blocking wait).

        Serializes the rmtree/replace critical section across processes that
        share the same cache directory. Within a single process, separate
        file descriptors still conflict, so this also serializes executor
        threads racing on the same repository.

        Args:
            repo_root: The per-repository cache root.

        Yields:
            None, while the exclusive lock is held.

        Raises:
            TimeoutError: If the lock cannot be acquired within the bound.
        """
        lock_path = repo_root / REPO_LOCK_FILENAME
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            deadline = time.monotonic() + self._config.clone_timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"could not acquire cache lock for {repo_root}"
                        ) from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    @staticmethod
    def _sweep_orphan_tempdirs(repo_root: Path) -> None:
        """Remove leftover clone temp dirs older than the orphan threshold.

        A clone thread orphaned by an ``asyncio.wait_for`` timeout may leave a
        temp dir behind. These are swept opportunistically before each clone so
        they cannot accumulate unbounded.

        Args:
            repo_root: The per-repository cache root to sweep.
        """
        cutoff = time.time() - ORPHAN_TMP_MAX_AGE_S
        try:
            entries = list(repo_root.iterdir())
        except OSError:
            return
        for entry in entries:
            if not entry.name.startswith(CLONE_TMP_PREFIX):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    logger.debug("Swept orphaned clone temp dir: %s", entry)
            except OSError:
                continue

    @staticmethod
    def _run_clone(
        url: str,
        tmp: Path,
        depth: int | None,
        branch: str | None,
        creds: tuple[str, str] | None,
    ) -> Repo:
        """Clone into ``tmp``, passing credentials only as transport kwargs.

        Credentials are never embedded in the URL and are omitted entirely when
        anonymous.

        Args:
            url: The HTTPS clone URL (or local override path).
            tmp: The temporary clone destination.
            depth: Shallow clone depth (``None`` for a full clone).
            branch: The branch or tag to clone (``None`` for the default HEAD).
            creds: Optional ``(username, password)`` credentials.

        Returns:
            The cloned dulwich ``Repo`` (caller must close it).
        """
        if creds is not None:
            username, password = creds
            return porcelain.clone(
                url,
                target=str(tmp),
                depth=depth,
                branch=branch,
                checkout=True,
                username=username,
                password=password,
            )
        return porcelain.clone(
            url,
            target=str(tmp),
            depth=depth,
            branch=branch,
            checkout=True,
        )

    @staticmethod
    def _strip_git_dir(root: Path) -> None:
        """Delete the ``.git`` directory (or file) from a clone."""
        git_path = root / ".git"
        if git_path.is_dir():
            shutil.rmtree(git_path, ignore_errors=True)
        elif git_path.exists():
            git_path.unlink()

    def _offline(self, ref: GitSkillReference) -> tuple[Path, str] | None:
        """Serve a stale cached snapshot when the remote is unreachable.

        Args:
            ref: The reference being resolved.

        Returns:
            A ``(snapshot_dir, sha)`` tuple if a complete snapshot is cached,
            otherwise ``None``.
        """
        sha = self._read_pointer(ref)
        if sha is None:
            logger.warning(
                "Remote unreachable for %s and no cached snapshot; skipping",
                ref.full_ref,
            )
            return None
        sha_dir = self._sha_dir(ref, sha)
        if self._is_complete(sha_dir):
            logger.warning(
                "Serving stale %s@%s; remote unreachable", ref.full_ref, sha[:12]
            )
            return sha_dir, sha
        logger.warning(
            "Remote unreachable for %s and cached snapshot missing; skipping",
            ref.full_ref,
        )
        return None

    async def _discover_skills(
        self,
        walk_root: Path,
        sha_dir: Path,
        ref: GitSkillReference,
        resolved_sha: str,
    ) -> list[Skill]:
        """Walk a snapshot for skills (directories containing SKILL.md).

        Args:
            walk_root: The directory to walk (repo root or a scoped subdir).
            sha_dir: The snapshot root (for path-safety containment).
            ref: The reference being discovered (for diagnostics).
            resolved_sha: The resolved commit SHA (for diagnostics).

        Returns:
            The discovered skills, de-duplicated by name (first wins).
        """
        skills: dict[str, Skill] = {}

        # Synchronous local-filesystem walk by design; symlinks are not followed.
        for dirpath, dirnames, filenames in walk_root.walk(  # noqa: ASYNC240
            top_down=True, follow_symlinks=False
        ):
            dirnames[:] = sorted(
                name for name in dirnames if not self._should_prune_dir(name)
            )
            manifest_names = sorted(
                (name for name in filenames if name.casefold() == "skill.md"),
                key=lambda name: (name != "SKILL.md", name),
            )
            if not manifest_names:
                continue
            manifest_name = manifest_names[0]

            relative_path = dirpath.relative_to(walk_root).as_posix()
            root_directory_name = (
                ref.subdir.rstrip("/").rsplit("/", 1)[-1]
                if ref.subdir is not None
                else ref.repo
            )
            skill = self._loader.load_skill(
                dirpath,
                dirpath / manifest_name,
                self._read_manifest,
                relative_path,
                root_directory_name if relative_path == "." else dirpath.name,
            )
            if skill is None:
                continue
            assert skill.skill_path is not None
            canonical_path = skill.skill_path.value
            if canonical_path in skills:
                logger.warning(
                    "Duplicate skill path %r in %s; keeping first occurrence",
                    canonical_path,
                    ref.full_ref,
                )
                continue
            skills[canonical_path] = skill

        if (sha_dir / ".gitmodules").is_file():
            logger.warning(
                "Ignoring git submodules in %s (.gitmodules present, not recursed)",
                ref.full_ref,
            )

        logger.info(
            "Discovered %d skills in %s@%s",
            len(skills),
            ref.full_ref,
            resolved_sha[:12],
        )
        return list(skills.values())

    @staticmethod
    def _should_prune_dir(name: str) -> bool:
        """Return True for directory names excluded from discovery.

        Dot-prefixed directories and ``template``/``readme`` (matched
        case-insensitively) are pruned.
        """
        return name.startswith(".") or name.lower() in PRUNED_DIR_NAMES

    def _read_manifest(
        self, content: bytes, source: str, dir_name: str
    ) -> tuple[SkillManifest, str, bool] | None:
        """Parse a manifest, falling back to the directory name if unnamed.

        The frontmatter ``name`` is authoritative; when it differs from the
        directory name a warning is logged and frontmatter wins. When ``name``
        is missing and the directory name is a valid skill name, the directory
        name is used (with a warning); any other parse failure skips the skill.
        This is the Git-side manifest-reading strategy passed to the shared
        :class:`SkillLoader`.

        Args:
            content: Exact captured ``SKILL.md`` bytes.
            source: Source label for parse errors.
            dir_name: The containing directory name (fallback identity).

        Returns:
            A ``(manifest, body, SEP eligible)`` tuple, or None if skipped.
        """
        try:
            manifest, body = self._parser.parse_bytes(content, source)
        except MissingRequiredFieldError as exc:
            if exc.field != "name" or not SkillName.is_valid(dir_name):
                logger.warning("Skipping skill at %s: %s", source, exc)
                return None
            return self._parse_with_dir_name(content, source, dir_name)
        except ManifestParseError as exc:
            logger.warning("Skipping skill at %s: %s", source, exc)
            return None

        sep_eligible = manifest.name.value == dir_name
        if not sep_eligible:
            logger.warning(
                "Skill name %r differs from directory %r; frontmatter wins for "
                "legacy access and the skill is omitted from SEP",
                manifest.name.value,
                dir_name,
            )
        return manifest, body, sep_eligible

    def _parse_with_dir_name(
        self, content: bytes, source: str, dir_name: str
    ) -> tuple[SkillManifest, str, bool] | None:
        """Inject a legacy directory-name fallback into captured bytes."""
        try:
            text = content.decode("utf-8")
            post = frontmatter.loads(text)
            post["name"] = dir_name
            manifest, body = self._parser.parse_content(frontmatter.dumps(post), source)
        except (UnicodeDecodeError, ManifestParseError) as exc:
            logger.warning("Skipping skill at %s: %s", source, exc)
            return None
        logger.warning(
            "Skill at %s has no 'name'; using directory name %r for legacy access; "
            "the skill is omitted from SEP",
            source,
            dir_name,
        )
        return manifest, body, False

    def _repo_cache_root(self, ref: GitSkillReference) -> Path:
        """Return the per-repository cache root (host/owner/repo)."""
        return (
            self._cache_dir
            / self._sanitize(ref.host)
            / self._sanitize(ref.owner)
            / self._sanitize(ref.repo)
        )

    def _sha_dir(self, ref: GitSkillReference, sha: str) -> Path:
        """Return the snapshot directory for a resolved SHA."""
        return self._repo_cache_root(ref) / sha

    @staticmethod
    def _is_complete(sha_dir: Path) -> bool:
        """Return True if a snapshot directory carries the completion marker."""
        return (sha_dir / CACHE_COMPLETE_MARKER).is_file()

    def _pointer_path(self, ref: GitSkillReference) -> Path:
        """Return the per-ref pointer file path (last resolved SHA)."""
        safe_ref = self._sanitize(ref.ref) if ref.ref else "HEAD"
        return self._repo_cache_root(ref) / "refs" / safe_ref

    def _write_pointer(self, ref: GitSkillReference, sha: str) -> None:
        """Record the last resolved SHA for a ref (offline-stale + future GC)."""
        pointer = self._pointer_path(ref)
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(f"{sha}\n", encoding="utf-8")

    def _read_pointer(self, ref: GitSkillReference) -> str | None:
        """Read the last resolved SHA for a ref, or None if absent."""
        try:
            return self._pointer_path(ref).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    @staticmethod
    def _sanitize(part: str) -> str:
        """Sanitize a reference component for use as a cache path segment."""
        return part.replace("/", "_").replace(":", "_")
