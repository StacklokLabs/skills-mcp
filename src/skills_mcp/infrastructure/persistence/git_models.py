"""Git reference models for skill distribution.

This module defines data models for fetching skills from Git repositories,
using the ToolHive ``git://host/owner/repo[@ref][#subdir]`` reference notation.

Security note: ``git://`` here is *notation*, not the unauthenticated git
daemon protocol. Repositories are always fetched over HTTPS. Reference parsing
performs SSRF-hardening at construction time (rejecting userinfo, non-``git://``
schemes, and literal loopback/private/link-local/reserved IP hosts).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


logger = logging.getLogger(__name__)


# ToolHive reference scheme. Notation only; transport is always HTTPS.
_GIT_SCHEME = "git://"

# A 40-character lowercase hex string is treated as an already-resolved commit.
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")

# Advisory tag-shaped detection (e.g. "v1.2", "1.2.3"). Resolution order at
# fetch time is authoritative (tags before heads via ls_remote).
_TAG_SHAPED_RE = re.compile(r"^v?\d+\.\d+")

# Allowlisted characters for a git ref (branch or tag) name.
_REF_ALLOWED_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")
_MAX_REF_LENGTH = 255

# Default per-host credential username when only a token is configured.
DEFAULT_GIT_USERNAME = "x-access-token"

# Minimum path segments after the host: owner + repo.
_MIN_PATH_SEGMENTS = 2


def default_git_cache_dir() -> Path:
    """Return the default Git snapshot cache directory.

    Returns:
        Path to ``~/.cache/skills-mcp/git``.
    """
    return Path.home() / ".cache" / "skills-mcp" / "git"


def _validate_ref(ref: str) -> str:
    """Validate a git ref (branch or tag) name against an allowlist.

    Args:
        ref: The candidate ref name.

    Returns:
        The validated ref.

    Raises:
        ValueError: If the ref is empty or malformed.
    """
    if not ref:
        raise ValueError("git ref cannot be empty")
    if len(ref) > _MAX_REF_LENGTH:
        raise ValueError(f"git ref too long (>{_MAX_REF_LENGTH}): {ref!r}")
    if not _REF_ALLOWED_RE.match(ref):
        raise ValueError(f"git ref has disallowed characters: {ref!r}")
    if ".." in ref:
        raise ValueError(f"git ref cannot contain '..': {ref!r}")
    if ref.startswith("-"):
        raise ValueError(f"git ref cannot start with '-': {ref!r}")
    if ref.endswith(".lock"):
        raise ValueError(f"git ref cannot end with '.lock': {ref!r}")
    return ref


def _validate_subdir(subdir: str) -> str:
    """Validate a ``#subdir`` path fragment.

    Args:
        subdir: The candidate subdirectory (relative to the repo root).

    Returns:
        The normalized subdirectory (leading/trailing slashes stripped).

    Raises:
        ValueError: If the subdir is empty, absolute, or path-traversing.
    """
    if not subdir:
        raise ValueError("git subdir cannot be empty")
    if "\x00" in subdir:
        raise ValueError("git subdir cannot contain NUL")
    if "\\" in subdir:
        raise ValueError(f"git subdir cannot contain backslashes: {subdir!r}")
    if subdir.startswith("/"):
        raise ValueError(f"git subdir cannot be absolute: {subdir!r}")
    normalized = subdir.strip("/")
    if not normalized:
        raise ValueError("git subdir cannot be empty")
    if any(segment == ".." for segment in normalized.split("/")):
        raise ValueError(f"git subdir cannot traverse with '..': {subdir!r}")
    return normalized


def _ip_candidate(host: str) -> str:
    """Extract the IP-literal candidate from a host, stripping any port.

    Handles bracketed IPv6 (``[::1]`` / ``[::1]:443``), bare IP literals
    (``127.0.0.1`` / ``::1``), and ``host:port`` forms.

    Args:
        host: The authority host (may include a port).

    Returns:
        The candidate string to try as an IP address.

    Raises:
        ValueError: If a bracketed IPv6 literal is malformed.
    """
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            raise ValueError(f"malformed IPv6 host: {host!r}")
        return host[1:end]
    # Bare IP literal (covers IPv6 like ::1 with multiple colons).
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return host
    # host:port with a single colon -> strip the port.
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def _reject_private_ip_host(host: str) -> None:
    """Reject host authorities that are literal non-public IP addresses.

    Loopback, private, link-local, reserved, unspecified, and multicast IP
    literals are rejected at parse time (SSRF hardening). Hostnames are not
    resolved here; that DNS check happens once at fetch time in the repository.

    Args:
        host: The authority host (may include a port).

    Raises:
        ValueError: If the host is a disallowed IP literal.
    """
    candidate = _ip_candidate(host)
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return  # Not an IP literal; treat as a hostname (resolved later).
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        raise ValueError(f"git host resolves to a disallowed IP literal: {host!r}")


@dataclass(frozen=True, slots=True)
class GitSkillReference:
    """Parsed Git reference for a skill repository.

    Format: ``git://host/owner/repo[@ref][#subdir]`` (ToolHive notation).

    Examples:
        - ``git://github.com/stacklok/skills``
        - ``git://github.com/stacklok/skills@v1.0.0``
        - ``git://github.com/stacklok/skills@main#analysis``
        - ``git://gitlab.example.com:8443/team/group/repo@abc...``

    Attributes:
        host: The host authority (may include a port, e.g. ``host:8443``).
        owner: The owner/organization path (may be nested, e.g. ``team/group``).
        repo: The repository name (``.git`` suffix stripped).
        ref: An optional branch, tag, or 40-hex commit. ``None`` means the
            remote's default branch (``HEAD``).
        subdir: An optional repository-relative subdirectory to scope discovery.
        url_override: An internal/testing hook for cloning from a local path.
            Never set by :meth:`from_string`, so it cannot be reached from
            user configuration and introduces no SSRF surface.
    """

    host: str
    owner: str
    repo: str
    ref: str | None = None
    subdir: str | None = None
    url_override: str | None = None

    @property
    def https_url(self) -> str:
        """Return the HTTPS clone URL for this reference.

        Returns:
            URL like ``https://host/owner/repo.git``. Credentials are never
            embedded; they are passed as transport keyword arguments.
        """
        return f"https://{self.host}/{self.owner}/{self.repo}.git"

    @property
    def full_ref(self) -> str:
        """Return the canonical reference string (for logs and errors).

        Returns:
            A ``git://`` string reconstructed from the parsed components.
        """
        text = f"{_GIT_SCHEME}{self.host}/{self.owner}/{self.repo}"
        if self.ref is not None:
            text += f"@{self.ref}"
        if self.subdir is not None:
            text += f"#{self.subdir}"
        return text

    @property
    def ref_kind(self) -> str:
        """Classify the ref advisorily (actual resolution is via ls_remote).

        Returns:
            ``"commit"`` for a 40-hex SHA, ``"tag"`` for a version-shaped ref,
            ``"branch"`` otherwise, and ``"default"`` when no ref is given.
        """
        if self.ref is None:
            return "default"
        if _SHA_RE.match(self.ref):
            return "commit"
        if _TAG_SHAPED_RE.match(self.ref):
            return "tag"
        return "branch"

    @property
    def pinned_sha(self) -> str | None:
        """Return the lowercased commit SHA if this ref is a 40-hex pin.

        Returns:
            The lowercased SHA, or ``None`` if the ref is not a bare commit.
        """
        if self.ref is not None and _SHA_RE.match(self.ref):
            return self.ref.lower()
        return None

    @classmethod
    def from_string(cls, reference: str) -> GitSkillReference:
        """Parse a ``git://`` reference string with SSRF hardening.

        Args:
            reference: A ``git://host/owner/repo[@ref][#subdir]`` string.

        Returns:
            The parsed :class:`GitSkillReference`.

        Raises:
            ValueError: If the reference is empty, uses a non-``git://`` scheme,
                carries userinfo, targets a disallowed IP literal, or is
                otherwise malformed.
        """
        reference = reference.strip()
        if not reference:
            raise ValueError("git reference cannot be empty")
        if not reference.startswith(_GIT_SCHEME):
            raise ValueError(
                f"git reference must use the {_GIT_SCHEME} scheme: {reference!r}"
            )
        rest = reference[len(_GIT_SCHEME) :]
        if not rest:
            raise ValueError("git reference has no host or path")

        # Split off the optional #subdir first.
        subdir: str | None = None
        if "#" in rest:
            rest, raw_subdir = rest.split("#", 1)
            subdir = _validate_subdir(raw_subdir)

        # Reject userinfo (@ within the authority, before the first '/').
        first_slash = rest.find("/")
        authority = rest if first_slash < 0 else rest[:first_slash]
        if "@" in authority:
            raise ValueError(f"git reference cannot contain userinfo: {reference!r}")

        # Split off the optional @ref (the authority has no '@' at this point).
        ref: str | None = None
        if "@" in rest:
            rest, raw_ref = rest.rsplit("@", 1)
            ref = _validate_ref(raw_ref)

        segments = rest.split("/")
        host = segments[0]
        path_segments = segments[1:]
        if not host:
            raise ValueError(f"git reference has an empty host: {reference!r}")
        if len(path_segments) < _MIN_PATH_SEGMENTS:
            raise ValueError(
                f"git reference must include owner and repo: {reference!r}"
            )
        if any(not segment for segment in path_segments):
            raise ValueError(f"git reference has an empty path segment: {reference!r}")

        repo = path_segments[-1].removesuffix(".git")
        if not repo:
            raise ValueError(f"git reference has an empty repo: {reference!r}")
        owner = "/".join(path_segments[:-1])

        _reject_private_ip_host(host)

        return cls(host=host, owner=owner, repo=repo, ref=ref, subdir=subdir)

    def __str__(self) -> str:
        """Return the canonical reference string."""
        return self.full_ref


@dataclass
class GitAuthConfig:
    """Authentication configuration for a Git host.

    Access is HTTPS-with-token only: ``password`` carries the token and
    ``username`` defaults to ``x-access-token`` when omitted.

    Attributes:
        host: Host this auth applies to.
        username: Username for authentication (optional).
        password: Password or token for authentication (optional).
    """

    host: str
    username: str | None = None
    password: str | None = None

    @property
    def is_anonymous(self) -> bool:
        """Check if this is anonymous (no credentials)."""
        return self.username is None and self.password is None


@dataclass
class GitRepositoryConfig:
    """Configuration for a Git skill repository.

    Attributes:
        skills: References to fetch from Git hosts.
        auth: Per-host authentication configs.
        cache_dir: Local cache directory for cloned snapshots.
        allow_private_hosts: Bypass the pre-clone DNS check that rejects hosts
            resolving only to private/loopback/link-local addresses.
        clone_timeout: Per-repository clone/resolve timeout in seconds.
    """

    skills: list[GitSkillReference] = field(default_factory=list)
    auth: dict[str, GitAuthConfig] = field(default_factory=dict)
    cache_dir: Path | None = None
    allow_private_hosts: bool = False
    clone_timeout: int = 120

    @staticmethod
    def default_cache_dir() -> Path:
        """Return the default cache directory.

        Returns:
            Path to ``~/.cache/skills-mcp/git``.
        """
        return default_git_cache_dir()


def resolve_git_credentials(
    host: str, auth: dict[str, GitAuthConfig]
) -> tuple[str, str] | None:
    """Resolve ``(username, password)`` credentials for a host.

    Precedence: per-host config first, then environment-token fallback
    (``GITHUB_TOKEN`` for github.com, ``GITLAB_TOKEN`` for gitlab.com,
    ``GIT_TOKEN`` for any host). The username defaults to ``x-access-token``
    when only a token/password is available.

    Only the credential *source* is logged (at DEBUG); the secret itself is
    never logged.

    Args:
        host: The Git host authority.
        auth: Per-host authentication configs.

    Returns:
        A ``(username, password)`` tuple, or ``None`` when anonymous.
    """
    config = auth.get(host)
    if config is not None and not config.is_anonymous:
        logger.debug("git auth for %s: source=config", host)
        username = config.username or DEFAULT_GIT_USERNAME
        return username, config.password or ""

    token: str | None = None
    source: str | None = None
    github_token = os.environ.get("GITHUB_TOKEN")
    gitlab_token = os.environ.get("GITLAB_TOKEN")
    any_token = os.environ.get("GIT_TOKEN")
    if host == "github.com" and github_token:
        token, source = github_token, "GITHUB_TOKEN"
    elif host == "gitlab.com" and gitlab_token:
        token, source = gitlab_token, "GITLAB_TOKEN"
    elif any_token:
        token, source = any_token, "GIT_TOKEN"

    if token:
        logger.debug("git auth for %s: source=%s", host, source)
        return DEFAULT_GIT_USERNAME, token

    return None
