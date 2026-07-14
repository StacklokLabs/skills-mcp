"""Configuration models for skills-mcp.

This module defines Pydantic models for configuration validation.
The configuration supports both local filesystem and OCI registry sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class LocalSourceConfig(BaseModel):
    """Configuration for local filesystem skill sources.

    Attributes:
        paths: List of directories to scan for skills.
    """

    paths: list[Path] = Field(default_factory=list)

    @field_validator("paths", mode="before")
    @classmethod
    def expand_paths(cls, v: list[str | Path]) -> list[Path]:
        """Expand ~ and resolve paths."""
        return [Path(p).expanduser() for p in v]


class _CredentialConfig(BaseModel):
    """Base authentication configuration for a remote source.

    Supports both direct values and file references (for the Docker secrets
    pattern). File references take precedence over direct values if both are
    specified. Shared by :class:`OCIAuthConfig` (OCI registries) and
    :class:`GitAuthConfig` (Git hosts).

    Attributes:
        username: Username for authentication (optional).
        password: Password or token for authentication (optional).
        username_file: Path to file containing username (optional).
        password_file: Path to file containing password (optional).
    """

    username: str | None = None
    password: str | None = None
    username_file: Path | None = None
    password_file: Path | None = None

    @field_validator("username_file", "password_file", mode="before")
    @classmethod
    def expand_file_paths(cls, v: str | Path | None) -> Path | None:
        """Expand ~ in file paths."""
        if v is None:
            return None
        return Path(v).expanduser()

    def get_username(self) -> str | None:
        """Get username, reading from file if username_file is set."""
        if self.username_file is not None:
            return self._read_credential_file(self.username_file, "username_file")
        return self.username

    def get_password(self) -> str | None:
        """Get password, reading from file if password_file is set."""
        if self.password_file is not None:
            return self._read_credential_file(self.password_file, "password_file")
        return self.password

    @staticmethod
    def _read_credential_file(path: Path, field_name: str) -> str:
        """Read credential from file, stripping whitespace."""
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            raise ValueError(f"{field_name}: file not found: {path}") from None
        except PermissionError:
            raise ValueError(f"{field_name}: permission denied: {path}") from None
        except OSError as e:
            raise ValueError(f"{field_name}: error reading {path}: {e}") from e


class OCIAuthConfig(_CredentialConfig):
    """Authentication configuration for an OCI registry.

    Direct values or file references (Docker secrets pattern); see
    :class:`_CredentialConfig`.
    """


class GitAuthConfig(_CredentialConfig):
    """Authentication configuration for a Git host.

    Direct values or file references (Docker secrets pattern); see
    :class:`_CredentialConfig`. Git access is HTTPS-with-token only: the
    password field carries the token (e.g. a PAT) and the username defaults to
    ``x-access-token`` when omitted.
    """


class OCISkillConfig(BaseModel):
    """Configuration for a single OCI skill reference.

    Attributes:
        image: Full OCI image reference (e.g., ghcr.io/org/skill:v1.0.0).
    """

    image: str


class OCISourceConfig(BaseModel):
    """Configuration for OCI registry skill sources.

    Attributes:
        cache_dir: Local cache directory for pulled artifacts.
        cache_ttl: Cache TTL in seconds (0 = never expire).
        verify_tls: Whether to verify TLS certificates.
        skills: List of OCI skill references to pull.
        auth: Per-registry authentication configuration.
    """

    cache_dir: Path | None = None
    cache_ttl: Annotated[int, Field(ge=0)] = 3600
    verify_tls: bool = True
    skills: list[OCISkillConfig] = Field(default_factory=list)
    auth: dict[str, OCIAuthConfig] = Field(default_factory=dict)

    @field_validator("cache_dir", mode="before")
    @classmethod
    def expand_cache_dir(cls, v: str | Path | None) -> Path | None:
        """Expand ~ in cache directory path."""
        if v is None:
            return None
        return Path(v).expanduser()


class GitSkillConfig(BaseModel):
    """Configuration for a single Git skill reference.

    Attributes:
        repo: Git reference string in ToolHive notation
            (``git://host/owner/repo[@ref][#subdir]``). Always fetched over
            HTTPS; ``git://`` is notation, not the git daemon protocol.
    """

    repo: str


class GitSourceConfig(BaseModel):
    """Configuration for Git repository skill sources.

    Attributes:
        cache_dir: Local cache directory for cloned snapshots.
        skills: List of Git skill references to fetch.
        auth: Per-host authentication configuration.
        allow_private_hosts: Bypass the pre-clone check that rejects hosts
            resolving only to private/loopback/link-local addresses. Off by
            default to guard against SSRF.
        clone_timeout: Per-repository clone/resolve timeout in seconds.
    """

    cache_dir: Path | None = None
    skills: list[GitSkillConfig] = Field(default_factory=list)
    auth: dict[str, GitAuthConfig] = Field(default_factory=dict)
    allow_private_hosts: bool = False
    clone_timeout: Annotated[int, Field(ge=1)] = 120

    @field_validator("cache_dir", mode="before")
    @classmethod
    def expand_cache_dir(cls, v: str | Path | None) -> Path | None:
        """Expand ~ in cache directory path."""
        if v is None:
            return None
        return Path(v).expanduser()


class ServerConfig(BaseModel):
    """Server configuration.

    Attributes:
        host: Host to bind to.
        port: Port to bind to.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        validation_paths: Directories under which the ``validate_skill`` tool
            is permitted to operate. Empty (the default) disables the tool.
    """

    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)] = 8080
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "WARNING"
    validation_paths: list[Path] = Field(default_factory=list)

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """Normalize log level to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator("validation_paths", mode="before")
    @classmethod
    def expand_validation_paths(cls, v: list[str | Path] | str | None) -> list[Path]:
        """Expand ~ in validation paths.

        Accepts a bare string as a single path (YAML ``validation_paths: ./x``)
        so it is not iterated character by character, and treats an explicit
        ``None`` as "no paths". Mirrors the defensive scalar handling in
        ``OCISourceConfig.expand_cache_dir``.
        """
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        return [Path(p).expanduser() for p in v]


class SkillsConfig(BaseModel):
    """Root configuration model for skills-mcp.

    This is the main configuration model that represents a skills.yaml file.

    Attributes:
        version: Configuration schema version.
        local: Configuration for local filesystem sources.
        oci: Configuration for OCI registry sources.
        git: Configuration for Git repository sources.
        server: Server configuration (host, port, log level).

    Example:
        ```yaml
        version: "1"

        local:
          paths:
            - ./skills
            - ~/.local/share/skills

        oci:
          cache_ttl: 3600
          skills:
            - image: ghcr.io/stacklok/skills/data-analysis:v1.0.0
            - image: ghcr.io/stacklok/skills/code-review:latest
          auth:
            ghcr.io:
              username: ${GITHUB_USER}
              password: ${GITHUB_TOKEN}

        git:
          cache_dir: ~/.cache/skills-mcp/git
          skills:
            - repo: git://github.com/stacklok/skills@v1.0.0
            - repo: git://github.com/stacklok/skills@main#analysis
          auth:
            github.com:
              password: ${GITHUB_TOKEN}

        server:
          host: 0.0.0.0
          port: 8080
          log_level: INFO
        ```
    """

    version: str = "1"
    local: LocalSourceConfig | None = None
    oci: OCISourceConfig | None = None
    git: GitSourceConfig | None = None
    server: ServerConfig = Field(default_factory=ServerConfig)

    def has_local_sources(self) -> bool:
        """Check if local sources are configured."""
        return self.local is not None and len(self.local.paths) > 0

    def has_oci_sources(self) -> bool:
        """Check if OCI sources are configured."""
        return self.oci is not None and len(self.oci.skills) > 0

    def has_git_sources(self) -> bool:
        """Check if Git sources are configured."""
        return self.git is not None and len(self.git.skills) > 0

    def is_empty(self) -> bool:
        """Check if no sources are configured."""
        return not (
            self.has_local_sources()
            or self.has_oci_sources()
            or self.has_git_sources()
        )
